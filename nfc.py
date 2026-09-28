import csv
import datetime
import json
import os
import tempfile
import threading
import time

BASE_DIR = "/home/orangepi/Documents"
DEVICE_FILE = os.path.join(BASE_DIR, "nfc_device.txt")
LAST_FILE = os.path.join(BASE_DIR, "nfc.txt")
LOG_FILE = os.path.join(BASE_DIR, "nfc_lecturas.txt")
GPS_FILE = os.path.join(BASE_DIR, "gps.txt")
UNIDAD_FILE = os.path.join(BASE_DIR, "unidad_srv.txt")
BUS_FILE = os.path.join(BASE_DIR, "bus_numero.txt")
DB_CONFIG_FILE = os.path.join(BASE_DIR, "sos_db.txt")
QUEUE_FILE = os.path.join(BASE_DIR, "asistencia_pendiente.txt")
RESULT_FILE = os.path.join(BASE_DIR, "asistencia.txt")
RESULT_LOG = os.path.join(BASE_DIR, "asistencia_log.txt")
BURST_SECONDS = 1.0
DUPLICATE_SECONDS = 2.0
DEFAULT_ACCURACY_METERS = 10
# Pin fisico 7 del conector. wiringPiSetup(), igual que gpio.py, usa el numero wPi.
# En Orange Pi 5 ese pin es wPi 2 (GPIO 54, PWM15). En el conector H5 tambien es wPi 2 (PWM.1).
PIN_AVISO = 2
SECUENCIA_VALIDA = ((0.5, 1), (0.5, 0), (0.5, 1))
SECUENCIA_INVALIDA = (
	(0.2, 1), (0.5, 0),
	(0.2, 1), (0.5, 0),
	(0.2, 1), (0.5, 0),
	(0.2, 1), (0.5, 0),
	(0.2, 1),
)
gpio_listo = False
gpio_lock = threading.Lock()
SOS_DB_HOST = "45.32.7.136"
SOS_DB_PORT = 3306
SOS_DB_NAME = "sos"
ASISTENCIA_FIELDS = (
	"attendance_id",
	"horario_id",
	"duplicate",
	"mensaje",
	"empresa_id",
	"fecha_servicio",
)
CALL_SQL = "CALL proc_registrar_asistencia_entrada(%s, %s, %s, %s, %s)"
queue_lock = threading.Lock()
worker_started = False
SPECIFIC_HINTS = ("rfid", "nfc", "mifare", "barcode", "reader", "card", "sycreader", "proximity")
GENERIC_HINTS = ("hid",)


def accept_code(text, elapsed, ended_with_enter, gap_exceeded=False):
	if not ended_with_enter or gap_exceeded:
		return None
	try:
		elapsed = float(elapsed)
	except (TypeError, ValueError):
		return None
	if elapsed >= BURST_SECONDS:
		return None
	if text is None:
		return None
	code = str(text).strip()
	if len(code) <= 5 or not code.isalnum():
		return None
	return code


def is_recent_duplicate(code, previous_code, previous_ts, now, window=DUPLICATE_SECONDS):
	if not previous_code or previous_ts is None:
		return False
	return code == previous_code and (now - previous_ts) < window


def begin_or_append(buffer, first_ts, last_ts, char, now):
	if first_ts is None or last_ts is None or (now - last_ts) >= BURST_SECONDS or len(buffer) > 64:
		return [char], now, now
	return buffer + [char], first_ts, now


def finish_burst(buffer, first_ts, last_ts, now):
	if not buffer or first_ts is None:
		return None
	gap = last_ts is not None and (now - last_ts) >= BURST_SECONDS
	return accept_code("".join(buffer), now - first_ts, True, gap)


def atomic_write(path, data):
	os.makedirs(os.path.dirname(path), exist_ok=True)
	fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path), suffix=".tmp")
	try:
		with os.fdopen(fd, "w") as handle:
			handle.write(data)
			handle.flush()
			os.fsync(handle.fileno())
		os.replace(tmp, path)
	except Exception:
		try:
			os.unlink(tmp)
		except OSError:
			pass
		raise


def timestamp():
	try:
		import pytz
		zone = pytz.timezone("America/Costa_Rica")
		return datetime.datetime.now(zone).strftime("%Y-%m-%d %H:%M:%S")
	except Exception:
		return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def parse_db_config(text):
	found = {}
	for line in str(text).splitlines():
		line = line.strip()
		if not line or line.startswith("#") or "=" not in line:
			continue
		key, value = line.split("=", 1)
		key = key.strip().lower()
		if key in ("host", "port", "user", "password", "database"):
			found[key] = value.strip()
	if "port" in found and found["port"]:
		found["port"] = int(found["port"])
	return found


def db_config():
	config = {
		"host": SOS_DB_HOST,
		"port": SOS_DB_PORT,
		"user": "",
		"password": "",
		"database": SOS_DB_NAME,
	}
	try:
		with open(DB_CONFIG_FILE, "r") as handle:
			config.update(parse_db_config(handle.read()))
	except OSError:
		pass
	return config


def read_bus_numero():
	for path in (BUS_FILE, UNIDAD_FILE):
		try:
			with open(path, "r") as handle:
				value = handle.read().strip()
		except OSError:
			continue
		if value and value.lower() not in ("none", "null"):
			return value
	return ""


def read_position():
	try:
		with open(GPS_FILE, "r") as handle:
			data = handle.read()
		if "Latitud:" not in data or "Longitud: " not in data:
			return 0.0, 0.0
		lat_start = data.index("Latitud:") + 8
		lat_end = data.index(",", lat_start)
		lng_start = data.index("Longitud: ") + 10
		lng_end = data.index(",", lng_start)
		return float(data[lat_start:lat_end].strip()), float(data[lng_start:lng_end].strip())
	except (OSError, ValueError):
		return 0.0, 0.0


def nueva_lectura(codigo, bus, lat, lng, fecha, accuracy=DEFAULT_ACCURACY_METERS):
	return {
		"codigo": "" if codigo is None else str(codigo).strip(),
		"bus": "" if bus is None else str(bus).strip(),
		"lat": float(lat or 0),
		"lng": float(lng or 0),
		"accuracy": int(accuracy),
		"fecha": fecha,
	}


def asistencia_params(item):
	return (
		item["bus"],
		item["codigo"],
		float(item["lat"]),
		float(item["lng"]),
		int(item.get("accuracy", DEFAULT_ACCURACY_METERS)),
	)


def split_csv_row(text):
	return next(csv.reader([str(text)]))


def parse_asistencia_row(row):
	if row is None:
		return None
	if isinstance(row, dict):
		if all(key in row for key in ASISTENCIA_FIELDS):
			return {key: "" if row[key] is None else str(row[key]) for key in ASISTENCIA_FIELDS}
		row = tuple(row.values())
	if isinstance(row, (list, tuple)) and len(row) == 1 and isinstance(row[0], str) and "," in row[0]:
		row = split_csv_row(row[0])
	if not isinstance(row, (list, tuple)) or len(row) < len(ASISTENCIA_FIELDS):
		return None
	return {
		key: "" if value is None else str(value)
		for key, value in zip(ASISTENCIA_FIELDS, row)
	}


def is_tarjeta_rechazada(error):
	if getattr(error, "sqlstate", None) == "45000":
		return True
	args = getattr(error, "args", ())
	if args and args[0] == 1644:
		return True
	return "45000" in str(error)


def error_mensaje(error):
	args = getattr(error, "args", ())
	if len(args) > 1 and args[1]:
		return str(args[1])
	return str(error)


def load_queue():
	try:
		with open(QUEUE_FILE, "r") as handle:
			lines = handle.read().splitlines()
	except OSError:
		return []
	items = []
	for line in lines:
		line = line.strip()
		if not line:
			continue
		try:
			item = json.loads(line)
		except ValueError:
			print("Lectura pendiente ilegible")
			continue
		if isinstance(item, dict) and item.get("codigo"):
			items.append(item)
	return items


def save_queue(items):
	body = "".join(json.dumps(item, ensure_ascii=False) + "\n" for item in items)
	atomic_write(QUEUE_FILE, body)


def enqueue_asistencia(codigo):
	lat, lng = read_position()
	item = nueva_lectura(codigo, read_bus_numero(), lat, lng, timestamp())
	with queue_lock:
		items = load_queue()
		items.append(item)
		save_queue(items)
	print("Asistencia en cola " + item["codigo"])
	return item


def secuencia_para_estado(estado):
	if estado == "registrada":
		return SECUENCIA_VALIDA
	if estado == "rechazada":
		return SECUENCIA_INVALIDA
	return ()


def reproducir_secuencia(secuencia, escribir, esperar):
	for duracion, nivel in secuencia:
		escribir(nivel)
		esperar(duracion)
	escribir(0)


def preparar_gpio():
	global gpio_listo
	if gpio_listo:
		return
	import wiringpi
	from wiringpi import GPIO
	if wiringpi.wiringPiSetup() == -1:
		raise RuntimeError("wiringPiSetup no pudo iniciar")
	wiringpi.pinMode(PIN_AVISO, GPIO.OUTPUT)
	wiringpi.digitalWrite(PIN_AVISO, GPIO.LOW)
	gpio_listo = True


def escribir_gpio(nivel):
	import wiringpi
	from wiringpi import GPIO
	wiringpi.digitalWrite(PIN_AVISO, GPIO.HIGH if nivel else GPIO.LOW)


def avisar_gpio(estado):
	secuencia = secuencia_para_estado(estado)
	if not secuencia:
		return
	with gpio_lock:
		try:
			preparar_gpio()
			reproducir_secuencia(secuencia, escribir_gpio, time.sleep)
			print("Aviso GPIO", estado)
		except Exception as error:
			global gpio_listo
			gpio_listo = False
			print("No se pudo mover el pin de aviso", error)


def record_result(result):
	body = json.dumps(result, ensure_ascii=False)
	atomic_write(RESULT_FILE, body + "\n")
	with open(RESULT_LOG, "a") as handle:
		handle.write(body + "\n")
		handle.flush()
	print(result.get("estado", ""), result.get("mensaje", ""), result.get("tarjeta", ""))


def connect_sos():
	import pymysql
	config = db_config()
	if not config.get("user"):
		raise RuntimeError("Falta el usuario de la base sos en " + DB_CONFIG_FILE)
	return pymysql.connect(
		host=config["host"],
		port=int(config["port"]),
		user=config["user"],
		password=config["password"],
		database=config["database"],
		connect_timeout=5,
		read_timeout=8,
		write_timeout=8,
		autocommit=True,
		charset="utf8mb4",
	)


def fetch_asistencia(cursor, item):
	cursor.execute(CALL_SQL, asistencia_params(item))
	row = cursor.fetchone()
	while row is None and cursor.nextset():
		row = cursor.fetchone()
	return row


def call_registrar(item):
	connection = connect_sos()
	try:
		with connection.cursor() as cursor:
			return fetch_asistencia(cursor, item)
	finally:
		connection.close()


def drop_item(item):
	with queue_lock:
		items = load_queue()
		remaining = []
		removed = False
		for current in items:
			if not removed and current.get("codigo") == item.get("codigo") and current.get("fecha") == item.get("fecha"):
				removed = True
				continue
			remaining.append(current)
		save_queue(remaining)


def resultado_base(item):
	return {
		"tarjeta": item.get("codigo", ""),
		"bus": item.get("bus", ""),
		"lat": item.get("lat", 0),
		"lng": item.get("lng", 0),
		"accuracy_meters": int(item.get("accuracy", DEFAULT_ACCURACY_METERS)),
		"fecha": item.get("fecha", ""),
	}


def process_queue_once():
	with queue_lock:
		items = load_queue()
	if not items:
		return False
	item = dict(items[0])
	if not item.get("bus"):
		item["bus"] = read_bus_numero()
	if not item.get("bus"):
		print("Asistencia en espera, falta el numero de bus")
		return False
	try:
		row = call_registrar(item)
	except Exception as error:
		if not is_tarjeta_rechazada(error):
			print("No se pudo registrar asistencia", error)
			return False
		result = resultado_base(item)
		result.update({
			"estado": "rechazada",
			"mensaje": error_mensaje(error),
			"attendance_id": "",
			"horario_id": "",
			"duplicate": "",
			"empresa_id": "",
			"fecha_servicio": "",
		})
		record_result(result)
		drop_item(item)
		avisar_gpio(result["estado"])
		return True
	parsed = parse_asistencia_row(row)
	if not parsed:
		result = resultado_base(item)
		result.update({
			"estado": "sin_datos",
			"mensaje": "La base sos no devolvio la asistencia",
			"attendance_id": "",
			"horario_id": "",
			"duplicate": "",
			"empresa_id": "",
			"fecha_servicio": "",
		})
		record_result(result)
		drop_item(item)
		avisar_gpio(result["estado"])
		return True
	result = resultado_base(item)
	result.update(parsed)
	result["estado"] = "registrada"
	record_result(result)
	drop_item(item)
	avisar_gpio(result["estado"])
	return True


def process_pending():
	while process_queue_once():
		pass


def worker():
	while True:
		try:
			process_pending()
		except Exception as error:
			print("Error asistencia", error)
		time.sleep(2)


def start_worker():
	global worker_started
	if worker_started:
		return
	thread = threading.Thread(target=worker, name="asistencia-sos", daemon=True)
	thread.start()
	worker_started = True


def save_read(code):
	stamp = timestamp()
	atomic_write(LAST_FILE, "Tarjeta:" + code + ",Fecha: " + stamp + "\n")
	with open(LOG_FILE, "a") as handle:
		handle.write(stamp + " " + code + "\n")
		handle.flush()
	print("Tarjeta leida " + code)
	try:
		enqueue_asistencia(code)
	except Exception as error:
		print("No se pudo encolar la asistencia", error)


def configured_device():
	try:
		with open(DEVICE_FILE, "r") as handle:
			hint = handle.read().strip()
	except OSError:
		return None
	return hint or None


def usb_keyboard_paths():
	base = "/dev/input/by-id"
	found = []
	if not os.path.isdir(base):
		return found
	for name in os.listdir(base):
		lower = name.lower()
		if "usb" in lower and ("kbd" in lower or "keyboard" in lower):
			found.append(os.path.realpath(os.path.join(base, name)))
	return found


def is_keyboard(device, ecodes):
	keys = device.capabilities().get(ecodes.EV_KEY, [])
	has_enter = ecodes.KEY_ENTER in keys or ecodes.KEY_KPENTER in keys
	has_chars = ecodes.KEY_A in keys or ecodes.KEY_1 in keys
	return has_enter and has_chars


def match_hint(hint, devices, evdev_module):
	path = hint
	if hint.startswith("event"):
		path = os.path.join("/dev/input", hint)
	if path.startswith("/dev/") and os.path.exists(path):
		for device in devices:
			if device.path == path:
				return device
		return evdev_module.InputDevice(path)
	lowered = hint.lower()
	for device in devices:
		name = (device.name or "").lower()
		if lowered == name or lowered in name or lowered in device.path.lower():
			return device
	return None


def match_reader(devices, ecodes):
	keyboards = [device for device in devices if is_keyboard(device, ecodes)]
	specific = []
	generic = []
	for device in keyboards:
		name = (device.name or "").lower()
		if any(hint in name for hint in SPECIFIC_HINTS):
			specific.append(device)
		elif any(hint in name for hint in GENERIC_HINTS):
			generic.append(device)
	if specific:
		if len(specific) > 1:
			print("Varios lectores, se usa " + specific[0].path + " " + specific[0].name)
		return specific[0]
	if len(generic) == 1:
		return generic[0]
	usb_paths = set(usb_keyboard_paths())
	usb = [device for device in keyboards if os.path.realpath(device.path) in usb_paths]
	if len(usb) == 1:
		return usb[0]
	return None


def close_unused(devices, selected):
	selected_path = None if selected is None else selected.path
	for device in devices:
		if device.path == selected_path:
			continue
		try:
			device.close()
		except Exception:
			pass


def find_device(evdev_module):
	devices = []
	for path in evdev_module.list_devices():
		try:
			devices.append(evdev_module.InputDevice(path))
		except (OSError, PermissionError) as error:
			print(error)
	selected = None
	try:
		hint = configured_device()
		if hint:
			try:
				selected = match_hint(hint, devices, evdev_module)
			except (OSError, PermissionError) as error:
				print(error)
		if selected is None:
			selected = match_reader(devices, evdev_module.ecodes)
		return selected
	except Exception:
		if selected is not None:
			try:
				selected.close()
			except Exception:
				pass
		raise
	finally:
		close_unused(devices, None if selected is None else selected)


def keymap(ecodes):
	keys = {}
	digits = (
		(ecodes.KEY_1, "1"),
		(ecodes.KEY_2, "2"),
		(ecodes.KEY_3, "3"),
		(ecodes.KEY_4, "4"),
		(ecodes.KEY_5, "5"),
		(ecodes.KEY_6, "6"),
		(ecodes.KEY_7, "7"),
		(ecodes.KEY_8, "8"),
		(ecodes.KEY_9, "9"),
		(ecodes.KEY_0, "0"),
	)
	letters = "abcdefghijklmnopqrstuvwxyz"
	letter_codes = (
		ecodes.KEY_A, ecodes.KEY_B, ecodes.KEY_C, ecodes.KEY_D, ecodes.KEY_E,
		ecodes.KEY_F, ecodes.KEY_G, ecodes.KEY_H, ecodes.KEY_I, ecodes.KEY_J,
		ecodes.KEY_K, ecodes.KEY_L, ecodes.KEY_M, ecodes.KEY_N, ecodes.KEY_O,
		ecodes.KEY_P, ecodes.KEY_Q, ecodes.KEY_R, ecodes.KEY_S, ecodes.KEY_T,
		ecodes.KEY_U, ecodes.KEY_V, ecodes.KEY_W, ecodes.KEY_X, ecodes.KEY_Y,
		ecodes.KEY_Z,
	)
	keypad = (
		(ecodes.KEY_KP0, "0"),
		(ecodes.KEY_KP1, "1"),
		(ecodes.KEY_KP2, "2"),
		(ecodes.KEY_KP3, "3"),
		(ecodes.KEY_KP4, "4"),
		(ecodes.KEY_KP5, "5"),
		(ecodes.KEY_KP6, "6"),
		(ecodes.KEY_KP7, "7"),
		(ecodes.KEY_KP8, "8"),
		(ecodes.KEY_KP9, "9"),
	)
	for code, char in digits:
		keys[code] = char
	for code, char in zip(letter_codes, letters):
		keys[code] = char
	for code, char in keypad:
		keys[code] = char
	return keys


def read_loop(device, evdev_module):
	ecodes = evdev_module.ecodes
	keys = keymap(ecodes)
	buffer = []
	first_ts = None
	last_ts = None
	shifted = False
	previous_code = None
	previous_ts = None
	shift_codes = {ecodes.KEY_LEFTSHIFT, ecodes.KEY_RIGHTSHIFT}
	enter_codes = {ecodes.KEY_ENTER, ecodes.KEY_KPENTER}
	for event in device.read_loop():
		if event.type != ecodes.EV_KEY:
			continue
		now = time.monotonic()
		if event.code in shift_codes:
			shifted = event.value != 0
			continue
		if event.value != 1:
			continue
		if event.code in enter_codes:
			code = finish_burst(buffer, first_ts, last_ts, now)
			buffer = []
			first_ts = None
			last_ts = None
			if code and not is_recent_duplicate(code, previous_code, previous_ts, now):
				try:
					save_read(code)
					previous_code = code
					previous_ts = now
				except OSError as error:
					print(error)
			continue
		char = keys.get(event.code)
		if char is None:
			continue
		if shifted and char.isalpha():
			char = char.upper()
		buffer, first_ts, last_ts = begin_or_append(buffer, first_ts, last_ts, char, now)


def main():
	start_worker()
	while True:
		device = None
		try:
			import evdev
		except ImportError:
			print("Falta el modulo evdev")
			time.sleep(10)
			continue
		try:
			device = find_device(evdev)
			if device is None:
				print("Lector NFC no encontrado")
				time.sleep(2)
				continue
			print("Lector NFC " + device.path + " " + device.name)
			read_loop(device, evdev)
		except Exception as error:
			print("Error NFC", error)
			time.sleep(2)
		finally:
			if device is not None:
				try:
					device.close()
				except Exception:
					pass


if __name__ == "__main__":
	main()
