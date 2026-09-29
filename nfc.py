import csv
import datetime
import json
import os
import sqlite3
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
DEVICE_ID_PATH = os.path.join(BASE_DIR, "device_id.txt")
WSDL = "http://45.32.7.136:8080/WebServiceSOLV3-3/SolSrv?wsdl"
DB_CONFIG_FILE = os.path.join(BASE_DIR, "sos_db.txt")
QUEUE_FILE = os.path.join(BASE_DIR, "asistencia_pendiente.txt")
RESULT_FILE = os.path.join(BASE_DIR, "asistencia.txt")
RESULT_LOG = os.path.join(BASE_DIR, "asistencia_log.txt")
LOCAL_DB = os.path.join(BASE_DIR, "nfc_local.db")
BURST_SECONDS = 1.0
DUPLICATE_SECONDS = 2.0
DEFAULT_ACCURACY_METERS = 10
# wiringPiSetup(), igual que gpio.py, usa numeros wPi y no el numero fisico del conector.
# Pin fisico 7: wPi 2, buzzer. Pin fisico 11: wPi 5, LED verde. Pin fisico 13: wPi 7, LED rojo.
PIN_BUZZER = 2
PIN_LED_VERDE = 5
PIN_LED_ROJO = 7
PINES = {
	"buzzer": PIN_BUZZER,
	"verde": PIN_LED_VERDE,
	"rojo": PIN_LED_ROJO,
}
PITIDO_CORTO = 0.15
PAUSA_ENTRE_PITIDOS = 0.1
LED_VERDE_SEGUNDOS = 1.5
PITIDO_LARGO = 2.0
PASES_DIARIOS = 2
VENTANA_MISMO_VIAJE = 20 * 60
SYNC_SECONDS = 3600
PASSENGER_DB = "turintel_turismointel"
PASSENGER_SQL = (
	"SELECT nfc_code FROM passenger "
	"WHERE nfc_code IS NOT NULL AND TRIM(nfc_code) <> ''"
)
gpio_listo = False
aviso_generacion = 0
aviso_lock = threading.Lock()
soap_client = None
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
LOCAL_SCHEMA = """
CREATE TABLE IF NOT EXISTS pasajero_nfc (
	nfc_code TEXT PRIMARY KEY COLLATE NOCASE
);
CREATE TABLE IF NOT EXISTS pase_diario (
	nfc_code TEXT NOT NULL COLLATE NOCASE,
	fecha TEXT NOT NULL,
	pases INTEGER NOT NULL,
	ultimo_aceptado TEXT,
	PRIMARY KEY (nfc_code, fecha)
);
CREATE TABLE IF NOT EXISTS cola_envio (
	id INTEGER PRIMARY KEY AUTOINCREMENT,
	nfc_code TEXT NOT NULL,
	bus TEXT,
	lat REAL,
	lng REAL,
	accuracy INTEGER,
	fecha TEXT NOT NULL,
	motivo TEXT NOT NULL,
	estado TEXT NOT NULL DEFAULT 'pendiente'
);
CREATE INDEX IF NOT EXISTS idx_cola_estado ON cola_envio (estado, id);
CREATE TABLE IF NOT EXISTS envio_tarjeta (
	id INTEGER PRIMARY KEY AUTOINCREMENT,
	cola_id INTEGER,
	nfc_code TEXT NOT NULL,
	bus TEXT,
	lat REAL,
	lng REAL,
	accuracy INTEGER,
	fecha_lectura TEXT,
	fecha_envio TEXT,
	motivo TEXT,
	estado TEXT,
	attendance_id TEXT,
	horario_id TEXT,
	duplicate TEXT,
	mensaje TEXT,
	empresa_id TEXT,
	fecha_servicio TEXT
);
CREATE TABLE IF NOT EXISTS meta (
	clave TEXT PRIMARY KEY,
	valor TEXT
);
"""
queue_lock = threading.Lock()
db_lock = threading.Lock()
local_conn = None
local_path = None
worker_started = False
sync_started = False
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


def fecha_dia(stamp):
	text = "" if stamp is None else str(stamp)
	return text[:10]


def segundos_entre(inicio, fin):
	try:
		fmt = "%Y-%m-%d %H:%M:%S"
		a = datetime.datetime.strptime(str(inicio), fmt)
		b = datetime.datetime.strptime(str(fin), fmt)
	except (TypeError, ValueError):
		return None
	return (b - a).total_seconds()


def parse_db_config(text):
	found = {}
	for line in str(text).splitlines():
		line = line.strip()
		if not line or line.startswith("#") or "=" not in line:
			continue
		key, value = line.split("=", 1)
		key = key.strip().lower()
		value = value.strip()
		if key == "pases_diarios":
			if value:
				found[key] = int(value)
		elif key == "passenger_database":
			if value:
				found[key] = value
		elif key in ("host", "port", "user", "password", "database"):
			found[key] = value
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
		"passenger_database": PASSENGER_DB,
		"pases_diarios": PASES_DIARIOS,
	}
	try:
		with open(DB_CONFIG_FILE, "r") as handle:
			config.update(parse_db_config(handle.read()))
	except OSError:
		pass
	return config


def pases_diarios():
	try:
		limite = int(db_config().get("pases_diarios", PASES_DIARIOS))
	except (TypeError, ValueError):
		return PASES_DIARIOS
	if limite < 1:
		return PASES_DIARIOS
	return limite


def normalizar_bus(value):
	if value is None:
		return ""
	text = str(value).strip()
	if text.lower() in ("", "none", "null", "unknown"):
		return ""
	return text


def read_bus_numero():
	for path in (BUS_FILE, UNIDAD_FILE):
		try:
			with open(path, "r") as handle:
				value = normalizar_bus(handle.read())
		except OSError:
			continue
		if value:
			return value
	return ""


def read_device_id():
	try:
		with open(DEVICE_ID_PATH, "r") as handle:
			return normalizar_bus(handle.read())
	except OSError:
		return ""


def get_soap_client():
	global soap_client
	if soap_client is None:
		import zeep
		transport = zeep.Transport(timeout=5, operation_timeout=5)
		soap_client = zeep.Client(wsdl=WSDL, transport=transport)
	return soap_client


def reset_soap_client():
	global soap_client
	soap_client = None


def consultar_unidad():
	serial = read_device_id()
	if not serial:
		print("No hay device_id.txt para consultar el numero de bus")
		return ""
	try:
		result = get_soap_client().service.getUnidad(serial)
	except Exception as error:
		reset_soap_client()
		print("No se pudo consultar la unidad", error)
		return ""
	bus = normalizar_bus(result)
	if not bus:
		print("El servidor no tiene numero de bus para " + serial)
		return ""
	try:
		atomic_write(UNIDAD_FILE, bus)
	except OSError as error:
		print(error)
	print("Numero de bus " + bus)
	return bus


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


def decidir_tarjeta(autorizada, pases_hoy, segundos_desde_ultimo, limite=PASES_DIARIOS, ventana_seg=VENTANA_MISMO_VIAJE):
	if not autorizada:
		return {"feedback": "rechazada", "motivo": "no_autorizada", "incrementar": False}
	if segundos_desde_ultimo is not None and 0 <= segundos_desde_ultimo < ventana_seg:
		return {"feedback": "aceptada", "motivo": "mismo_viaje", "incrementar": False}
	if pases_hoy >= limite:
		return {"feedback": "rechazada", "motivo": "exceso_pases", "incrementar": False}
	return {"feedback": "aceptada", "motivo": "aceptada", "incrementar": True}


def cerrar_local():
	global local_conn, local_path
	with db_lock:
		if local_conn is not None:
			try:
				local_conn.close()
			except sqlite3.Error:
				pass
		local_conn = None
		local_path = None


def local_db():
	global local_conn, local_path
	if local_conn is not None and local_path == LOCAL_DB:
		return local_conn
	if local_conn is not None:
		try:
			local_conn.close()
		except sqlite3.Error:
			pass
		local_conn = None
	os.makedirs(os.path.dirname(LOCAL_DB), exist_ok=True)
	local_conn = sqlite3.connect(LOCAL_DB, timeout=30, check_same_thread=False, isolation_level=None)
	local_conn.row_factory = sqlite3.Row
	local_conn.execute("PRAGMA journal_mode=WAL")
	local_conn.execute("PRAGMA synchronous=FULL")
	local_conn.executescript(LOCAL_SCHEMA)
	local_path = LOCAL_DB
	return local_conn


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
	print("Asistencia en archivo " + item["codigo"])
	return item


def absorber_respaldo():
	items = load_queue()
	if not items:
		return 0
	with db_lock:
		conn = local_db()
		conn.execute("BEGIN IMMEDIATE")
		try:
			for item in items:
				codigo = "" if item.get("codigo") is None else str(item.get("codigo")).strip()
				if not codigo:
					continue
				conn.execute(
					"""INSERT INTO cola_envio
					(nfc_code, bus, lat, lng, accuracy, fecha, motivo, estado)
					VALUES (?, ?, ?, ?, ?, ?, 'pendiente_archivo', 'pendiente')""",
					(
						codigo,
						str(item.get("bus") or ""),
						float(item.get("lat") or 0),
						float(item.get("lng") or 0),
						int(item.get("accuracy") or DEFAULT_ACCURACY_METERS),
						item.get("fecha") or timestamp(),
					),
				)
			conn.commit()
		except Exception:
			conn.rollback()
			raise
	save_queue([])
	print("Cola recuperada " + str(len(items)))
	return len(items)


def reemplazar_pasajeros(codes):
	limpios = []
	vistos = set()
	for code in codes:
		text = "" if code is None else str(code).strip()
		if not text:
			continue
		clave = text.casefold()
		if clave in vistos:
			continue
		vistos.add(clave)
		limpios.append(text)
	with db_lock:
		conn = local_db()
		conn.execute("BEGIN IMMEDIATE")
		try:
			conn.execute("DELETE FROM pasajero_nfc")
			if limpios:
				conn.executemany(
					"INSERT INTO pasajero_nfc (nfc_code) VALUES (?)",
					[(code,) for code in limpios],
				)
			conn.execute(
				"INSERT OR REPLACE INTO meta (clave, valor) VALUES ('ultima_sync', ?)",
				(timestamp(),),
			)
			conn.commit()
		except Exception:
			conn.rollback()
			raise
	print("Tarjetas autorizadas " + str(len(limpios)))
	return len(limpios)


def tarjeta_autorizada(codigo):
	with db_lock:
		row = local_db().execute(
			"SELECT 1 FROM pasajero_nfc WHERE nfc_code = ?",
			(codigo,),
		).fetchone()
		return row is not None


def pases_en(codigo, fecha):
	with db_lock:
		row = local_db().execute(
			"SELECT pases FROM pase_diario WHERE nfc_code = ? AND fecha = ?",
			(codigo, fecha),
		).fetchone()
		return 0 if row is None else int(row["pases"])


def listar_pendientes():
	with db_lock:
		rows = local_db().execute(
			"SELECT id, nfc_code, bus, motivo, estado FROM cola_envio WHERE estado = 'pendiente' ORDER BY id"
		).fetchall()
		return [dict(row) for row in rows]


def listar_envios():
	with db_lock:
		rows = local_db().execute(
			"SELECT * FROM envio_tarjeta ORDER BY id"
		).fetchall()
		return [dict(row) for row in rows]


def estado_pase(conn, codigo, dia):
	row = conn.execute(
		"SELECT pases, ultimo_aceptado FROM pase_diario WHERE nfc_code = ? AND fecha = ?",
		(codigo, dia),
	).fetchone()
	pases = 0 if row is None else int(row["pases"])
	ultimo = None if row is None else row["ultimo_aceptado"]
	if not ultimo:
		previo = conn.execute(
			"""SELECT ultimo_aceptado FROM pase_diario
			WHERE nfc_code = ? AND ultimo_aceptado IS NOT NULL AND ultimo_aceptado <> ''
			ORDER BY ultimo_aceptado DESC LIMIT 1""",
			(codigo,),
		).fetchone()
		if previo is not None:
			ultimo = previo["ultimo_aceptado"]
	return pases, ultimo, row is not None


def registrar_lectura_local(codigo, bus, lat, lng, accuracy, ahora):
	dia = fecha_dia(ahora)
	limite = pases_diarios()
	with db_lock:
		conn = local_db()
		conn.execute("BEGIN IMMEDIATE")
		try:
			autorizada = conn.execute(
				"SELECT 1 FROM pasajero_nfc WHERE nfc_code = ?",
				(codigo,),
			).fetchone() is not None
			pases, ultimo, existe = estado_pase(conn, codigo, dia)
			segundos = segundos_entre(ultimo, ahora) if ultimo else None
			if segundos is not None and segundos < 0:
				segundos = None
			decision = decidir_tarjeta(autorizada, pases, segundos, limite, VENTANA_MISMO_VIAJE)
			if decision["incrementar"]:
				if existe:
					conn.execute(
						"""UPDATE pase_diario
						SET pases = pases + 1, ultimo_aceptado = ?
						WHERE nfc_code = ? AND fecha = ?""",
						(ahora, codigo, dia),
					)
				else:
					conn.execute(
						"""INSERT INTO pase_diario (nfc_code, fecha, pases, ultimo_aceptado)
						VALUES (?, ?, 1, ?)""",
						(codigo, dia, ahora),
					)
			cur = conn.execute(
				"""INSERT INTO cola_envio
				(nfc_code, bus, lat, lng, accuracy, fecha, motivo, estado)
				VALUES (?, ?, ?, ?, ?, ?, ?, 'pendiente')""",
				(
					codigo,
					"" if bus is None else str(bus),
					float(lat or 0),
					float(lng or 0),
					int(accuracy),
					ahora,
					decision["motivo"],
				),
			)
			decision["cola_id"] = cur.lastrowid
			conn.commit()
		except Exception:
			conn.rollback()
			raise
		return decision


def construir_patron(estado):
	if estado == "aceptada":
		pitidos = PITIDO_CORTO + PAUSA_ENTRE_PITIDOS + PITIDO_CORTO
		resto_verde = LED_VERDE_SEGUNDOS - pitidos
		if resto_verde < 0:
			resto_verde = 0
		return [
			(0, "buzzer", 1),
			(PITIDO_CORTO, "buzzer", 0),
			(PAUSA_ENTRE_PITIDOS, "verde", 1),
			(0, "buzzer", 1),
			(PITIDO_CORTO, "buzzer", 0),
			(PAUSA_ENTRE_PITIDOS, "buzzer", 1),
			(PITIDO_CORTO, "buzzer", 0),
			(resto_verde, "verde", 0),
		]
	if estado == "rechazada":
		return [
			(0, "buzzer", 1),
			(PITIDO_CORTO, "buzzer", 0),
			(PAUSA_ENTRE_PITIDOS, "rojo", 1),
			(0, "buzzer", 1),
			(PITIDO_LARGO, "buzzer", 0),
			(0, "rojo", 0),
		]
	return []


def aviso_vigente(generacion):
	return generacion == aviso_generacion


def esperar_cancelable(segundos, generacion, esperar):
	restante = float(segundos)
	while restante > 0:
		if not aviso_vigente(generacion):
			return False
		paso = min(0.05, restante)
		esperar(paso)
		restante -= paso
	return aviso_vigente(generacion)


def aplicar_nivel(pin, nivel, generacion, escribir):
	with aviso_lock:
		if generacion != aviso_generacion:
			return False
		escribir(pin, nivel)
		return True


def reproducir_patron(acciones, generacion, escribir, esperar, preparar):
	global gpio_listo
	try:
		preparar()
	except Exception as error:
		gpio_listo = False
		print("No se pudo preparar el aviso", error)
		return
	for pin in (PIN_BUZZER, PIN_LED_VERDE, PIN_LED_ROJO):
		if not aplicar_nivel(pin, 0, generacion, escribir):
			return
	for espera, nombre, nivel in acciones:
		if espera and not esperar_cancelable(espera, generacion, esperar):
			return
		if not aplicar_nivel(PINES[nombre], nivel, generacion, escribir):
			return


def preparar_gpio():
	global gpio_listo
	if gpio_listo:
		return
	import wiringpi
	from wiringpi import GPIO
	if wiringpi.wiringPiSetup() == -1:
		raise RuntimeError("wiringPiSetup no pudo iniciar")
	for pin in (PIN_BUZZER, PIN_LED_VERDE, PIN_LED_ROJO):
		wiringpi.pinMode(pin, GPIO.OUTPUT)
		wiringpi.digitalWrite(pin, GPIO.LOW)
	gpio_listo = True


def escribir_pin(pin, nivel):
	import wiringpi
	from wiringpi import GPIO
	wiringpi.digitalWrite(pin, GPIO.HIGH if nivel else GPIO.LOW)


def iniciar_aviso(estado):
	global aviso_generacion
	acciones = construir_patron(estado)
	if not acciones:
		return
	with aviso_lock:
		aviso_generacion += 1
		generacion = aviso_generacion
	threading.Thread(
		target=reproducir_patron,
		args=(acciones, generacion, escribir_pin, time.sleep, preparar_gpio),
		name="aviso-nfc",
		daemon=True,
	).start()


def simular_patron(estado):
	reloj = {"ms": 0}
	eventos = []

	def escribir(pin, nivel):
		eventos.append((reloj["ms"] / 1000.0, pin, nivel))

	def esperar(segundos):
		reloj["ms"] += int(round(float(segundos) * 1000))

	reproducir_patron(construir_patron(estado), aviso_generacion, escribir, esperar, lambda: None)
	return eventos


def record_result(result):
	body = json.dumps(result, ensure_ascii=False)
	atomic_write(RESULT_FILE, body + "\n")
	with open(RESULT_LOG, "a") as handle:
		handle.write(body + "\n")
		handle.flush()
	print(result.get("estado", ""), result.get("mensaje", ""), result.get("tarjeta", ""))


def connect_mysql(database):
	import pymysql
	config = db_config()
	if not config.get("user"):
		raise RuntimeError("Falta el usuario de MySQL en " + DB_CONFIG_FILE)
	return pymysql.connect(
		host=config["host"],
		port=int(config["port"]),
		user=config["user"],
		password=config["password"],
		database=database,
		connect_timeout=5,
		read_timeout=8,
		write_timeout=8,
		autocommit=True,
		charset="utf8mb4",
	)


def connect_sos():
	return connect_mysql(db_config()["database"])


def connect_passenger():
	return connect_mysql(db_config()["passenger_database"])


def fetch_passenger_codes():
	connection = connect_passenger()
	try:
		with connection.cursor() as cursor:
			cursor.execute(PASSENGER_SQL)
			rows = cursor.fetchall()
	finally:
		connection.close()
	codes = []
	for row in rows:
		value = row.get("nfc_code") if isinstance(row, dict) else row[0]
		if value is not None and str(value).strip():
			codes.append(str(value).strip())
	return codes


def sincronizar_pasajeros():
	codes = fetch_passenger_codes()
	return reemplazar_pasajeros(codes)


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


def resultado_base(item):
	return {
		"tarjeta": item.get("codigo", ""),
		"bus": item.get("bus", ""),
		"lat": item.get("lat", 0),
		"lng": item.get("lng", 0),
		"accuracy_meters": int(item.get("accuracy", DEFAULT_ACCURACY_METERS)),
		"fecha": item.get("fecha", ""),
		"motivo": item.get("motivo", ""),
	}


def tomar_pendiente():
	with db_lock:
		row = local_db().execute(
			"""SELECT id, nfc_code, bus, lat, lng, accuracy, fecha, motivo
			FROM cola_envio WHERE estado = 'pendiente' ORDER BY id LIMIT 1"""
		).fetchone()
		if row is None:
			return None
		return {
			"id": row["id"],
			"codigo": row["nfc_code"],
			"bus": row["bus"] or "",
			"lat": row["lat"] or 0,
			"lng": row["lng"] or 0,
			"accuracy": DEFAULT_ACCURACY_METERS if row["accuracy"] is None else int(row["accuracy"]),
			"fecha": row["fecha"],
			"motivo": row["motivo"] or "",
		}


def fijar_bus(cola_id, bus):
	with db_lock:
		local_db().execute("UPDATE cola_envio SET bus = ? WHERE id = ?", (bus, cola_id))


def guardar_respuesta(item, estado, mensaje, parsed=None):
	campos = {key: "" for key in ASISTENCIA_FIELDS}
	if parsed:
		campos.update(parsed)
	if mensaje is None:
		mensaje = campos.get("mensaje", "")
	else:
		campos["mensaje"] = mensaje
	with db_lock:
		conn = local_db()
		conn.execute("BEGIN IMMEDIATE")
		try:
			conn.execute(
				"""INSERT INTO envio_tarjeta (
					cola_id, nfc_code, bus, lat, lng, accuracy,
					fecha_lectura, fecha_envio, motivo, estado,
					attendance_id, horario_id, duplicate, mensaje, empresa_id, fecha_servicio
				) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
				(
					item.get("id"),
					item.get("codigo", ""),
					item.get("bus", ""),
					item.get("lat", 0),
					item.get("lng", 0),
					int(item.get("accuracy", DEFAULT_ACCURACY_METERS)),
					item.get("fecha", ""),
					timestamp(),
					item.get("motivo", ""),
					estado,
					campos.get("attendance_id", ""),
					campos.get("horario_id", ""),
					campos.get("duplicate", ""),
					mensaje,
					campos.get("empresa_id", ""),
					campos.get("fecha_servicio", ""),
				),
			)
			if item.get("id") is not None:
				conn.execute("UPDATE cola_envio SET estado = 'enviado' WHERE id = ?", (item["id"],))
			conn.commit()
		except Exception:
			conn.rollback()
			raise
	result = resultado_base(item)
	result.update(campos)
	result["estado"] = estado
	result["mensaje"] = mensaje
	try:
		record_result(result)
	except OSError as error:
		print(error)


def process_queue_once():
	try:
		absorber_respaldo()
	except Exception as error:
		print("No se pudo recuperar la cola", error)
	item = tomar_pendiente()
	if not item:
		return False
	if not item.get("bus"):
		item["bus"] = read_bus_numero() or consultar_unidad()
	if not item.get("bus"):
		print("Asistencia en espera, falta el numero de bus")
		return False
	try:
		fijar_bus(item["id"], item["bus"])
	except Exception as error:
		print(error)
	try:
		row = call_registrar(item)
	except Exception as error:
		if not is_tarjeta_rechazada(error):
			print("No se pudo registrar asistencia", error)
			return False
		guardar_respuesta(item, "rechazada", error_mensaje(error), None)
		return True
	parsed = parse_asistencia_row(row)
	if not parsed:
		guardar_respuesta(item, "sin_datos", "La base sos no devolvio la asistencia", None)
		return True
	guardar_respuesta(item, "registrada", None, parsed)
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


def sync_worker():
	while True:
		try:
			sincronizar_pasajeros()
		except Exception as error:
			print("No se pudo actualizar las tarjetas autorizadas", error)
		time.sleep(SYNC_SECONDS)


def start_worker():
	global worker_started
	if worker_started:
		return
	thread = threading.Thread(target=worker, name="asistencia-sos", daemon=True)
	thread.start()
	worker_started = True


def start_sync_worker():
	global sync_started
	if sync_started:
		return
	thread = threading.Thread(target=sync_worker, name="sync-nfc", daemon=True)
	thread.start()
	sync_started = True


def save_read(code):
	stamp = timestamp()
	atomic_write(LAST_FILE, "Tarjeta:" + code + ",Fecha: " + stamp + "\n")
	with open(LOG_FILE, "a") as handle:
		handle.write(stamp + " " + code + "\n")
		handle.flush()
	print("Tarjeta leida " + code)
	lat, lng = read_position()
	bus = read_bus_numero()
	try:
		decision = registrar_lectura_local(code, bus, lat, lng, DEFAULT_ACCURACY_METERS, stamp)
	except Exception as error:
		print("No se pudo encolar la asistencia", error)
		try:
			enqueue_asistencia(code)
		except Exception as segundo:
			print(segundo)
		iniciar_aviso("rechazada")
		return
	print(decision["motivo"] + " " + code)
	iniciar_aviso(decision["feedback"])


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
	try:
		local_db()
	except Exception as error:
		print("No se pudo abrir la base local", error)
	start_worker()
	start_sync_worker()
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
