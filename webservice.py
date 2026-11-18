import datetime
import os
import subprocess
import tempfile
import time
import uuid

import pytz
import zeep

BASE_DIR = "/home/orangepi/Documents"
DEVICE_ID_PATH = os.path.join(BASE_DIR, "device_id.txt")
GPS_FILE = os.path.join(BASE_DIR, "gps.txt")
KM_FILE = os.path.join(BASE_DIR, "km.txt")
SERVER_STATUS = os.path.join(BASE_DIR, "serverstatus.txt")
FECHA_FILE = os.path.join(BASE_DIR, "fecha_srv.txt")
UNIDAD_FILE = os.path.join(BASE_DIR, "unidad_srv.txt")
ENTRADAS_PE = os.path.join(BASE_DIR, "data_barras_entradas_pe.txt")
ENTRADAS_PS = os.path.join(BASE_DIR, "data_barras_entradas_ps.txt")
PREDIO_FILE = os.path.join(BASE_DIR, "en_predio.txt")
DB_CONFIG_FILE = os.path.join(BASE_DIR, "sos_db.txt")
WSDL = "http://45.32.7.136:8080/WebServiceSOLV3-3/SolSrv?wsdl"
SOS_DB_HOST = "45.32.7.136"
SOS_DB_PORT = 3306
SOS_DB_NAME = "sos"
SQL_PREDIO = "SELECT esEnPredio(%s, %s)"
CALL_TRANSMISION = (
	"CALL insertarTranmision_v5(%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)"
)
timezone = pytz.timezone("America/Costa_Rica")

client = None


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


def get_client():
	global client
	if client is None:
		transport = zeep.Transport(timeout=5, operation_timeout=3)
		client = zeep.Client(wsdl=WSDL, transport=transport)
	return client


def reset_client():
	global client
	client = None


def device_id():
	try:
		if os.path.isfile(DEVICE_ID_PATH):
			with open(DEVICE_ID_PATH, "r") as handle:
				existing = handle.read().strip()
			if existing:
				return existing
		os.makedirs(BASE_DIR, exist_ok=True)
		new_id = str(uuid.uuid4())[-8:]
		try:
			fd = os.open(DEVICE_ID_PATH, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
		except FileExistsError:
			with open(DEVICE_ID_PATH, "r") as handle:
				existing = handle.read().strip()
			if existing:
				return existing
			raise
		with os.fdopen(fd, "w") as handle:
			handle.write(new_id)
		return new_id
	except OSError as error:
		print("No se pudo leer el id del dispositivo", error)
		return "unknown"


def getFecha():
	result = get_client().service.getFechaSrv()
	atomic_write(FECHA_FILE, str(result))
	try:
		subprocess.run(["timedatectl", "set-timezone", "America/Costa_Rica"], check=True)
		subprocess.run(["date", "-s", str(result)], check=True)
		print("Fecha Actualizada Exitosamente")
		print(result)
	except (subprocess.CalledProcessError, OSError) as error:
		print(error)
	return str(result)


def server_alive():
	now = datetime.datetime.now(timezone)
	try:
		result = get_client().service.checkConnection()
		print(result)
		atomic_write(SERVER_STATUS, str(now) + " estado " + str(result) + "\n")
	except Exception:
		print("SIN CONEXION")
		reset_client()
		try:
			atomic_write(SERVER_STATUS, str(now) + " estado SIN CONEXION")
		except OSError as error:
			print(error)


def getKM():
	try:
		with open(KM_FILE, "r") as handle:
			filedata = handle.read().strip()
		if filedata:
			return filedata
	except OSError:
		pass
	return "0"


def getUnidad():
	filedata = device_id()
	result = get_client().service.getUnidad(str(filedata))
	atomic_write(UNIDAD_FILE, str(result))
	return str(result)


def read_marked(path, label):
	try:
		with open(path, "r") as handle:
			filedata = handle.read()
		start = filedata.index(label) + len(label)
		end = filedata.index("$$", start)
		return int(filedata[start:end].strip())
	except (OSError, ValueError):
		return 0


def get_salidas_pe():
	return read_marked(ENTRADAS_PE, "GeneralSalidasPe: ")


def get_salidas_ps():
	return read_marked(ENTRADAS_PS, "GeneralSalidasPs: ")


def get_entradas_pe():
	return read_marked(ENTRADAS_PE, "GeneralEntradasPe: ")


def get_entradas_ps():
	return read_marked(ENTRADAS_PS, "GeneralEntradasPs: ")


def get_entradas_pe_predio():
	return read_marked(ENTRADAS_PE, "GeneralEntradasPe_Predio: ")


def get_salidas_pe_predio():
	return read_marked(ENTRADAS_PE, "GeneralSalidasPe_Predio: ")


def get_entradas_ps_predio():
	return read_marked(ENTRADAS_PS, "GeneralEntradasPs_Predio: ")


def get_salidas_ps_predio():
	return read_marked(ENTRADAS_PS, "GeneralSalidasPs_Predio: ")


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


def connect_mysql():
	import pymysql
	config = db_config()
	if not config.get("user"):
		raise RuntimeError("Falta el usuario de MySQL en " + DB_CONFIG_FILE)
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


def interpretar_predio(value):
	if value is None:
		return None
	if isinstance(value, bool):
		return value
	if isinstance(value, (int, float)):
		return int(value) == 1
	text = str(value).strip()
	if text in ("1", "True", "true"):
		return True
	if text in ("0", "False", "false"):
		return False
	return None


def coordenadas_actuales():
	lat = get_latitud()
	lng = get_longitud()
	try:
		lat_n = float(lat)
		lng_n = float(lng)
	except (TypeError, ValueError):
		return None
	if lat_n == 0.0 and lng_n == 0.0:
		return None
	return str(lat), str(lng)


def consultar_predio():
	coords = coordenadas_actuales()
	if coords is None:
		return None
	connection = connect_mysql()
	try:
		with connection.cursor() as cursor:
			cursor.execute(SQL_PREDIO, coords)
			row = cursor.fetchone()
	finally:
		connection.close()
	if not row:
		return None
	value = row[0] if not isinstance(row, dict) else next(iter(row.values()))
	return interpretar_predio(value)


def leer_predio():
	try:
		with open(PREDIO_FILE, "r") as handle:
			return handle.read().strip()
	except OSError:
		return ""


def actualizar_predio():
	estado = consultar_predio()
	if estado is None:
		return
	nuevo = "1" if estado else "0"
	if leer_predio() == nuevo:
		return
	atomic_write(PREDIO_FILE, nuevo + "\n")
	print("En predio " + nuevo)


def parametros_transmision():
	now = datetime.datetime.now(timezone).strftime("%Y-%m-%d %H:%M:%S")
	try:
		km = float(getKM())
	except (TypeError, ValueError):
		km = 0.0
	return (
		now,
		str(device_id()),
		str(get_latitud()),
		str(get_longitud()),
		str(get_velocidad()),
		str(get_entradas_pe()),
		str(get_salidas_pe()),
		str(get_entradas_ps()),
		str(get_salidas_ps()),
		km,
		str(get_entradas_pe_predio()),
		str(get_salidas_pe_predio()),
		str(get_entradas_ps_predio()),
		str(get_salidas_ps_predio()),
	)


def enviar_transmision(params):
	connection = connect_mysql()
	try:
		with connection.cursor() as cursor:
			cursor.execute(CALL_TRANSMISION, params)
			try:
				return cursor.fetchone()
			except Exception:
				return None
	finally:
		connection.close()


def get_latitud():
	try:
		with open(GPS_FILE, "r") as handle:
			filedata = handle.read()
		if "Latitud:" not in filedata:
			return "0"
		start = filedata.index("Latitud:") + 8
		end = filedata.index(",", start)
		return filedata[start:end].strip() or "0"
	except (OSError, ValueError):
		return "0"


def get_longitud():
	try:
		with open(GPS_FILE, "r") as handle:
			filedata = handle.read()
		if "Longitud: " not in filedata:
			return "0"
		start = filedata.index("Longitud: ") + 10
		end = filedata.index(",", start)
		return filedata[start:end].strip() or "0"
	except (OSError, ValueError):
		return "0"


def get_velocidad():
	try:
		with open(GPS_FILE, "r") as handle:
			filedata = handle.read()
		if "Velocidad: " not in filedata:
			return 0.0
		start = filedata.index("Velocidad: ") + 11
		velocidad = float(filedata[start:].strip())
		print(velocidad)
		return velocidad
	except (OSError, ValueError):
		return 0.0


def send_data_srv():
	try:
		print("Unidad Sol:" + getUnidad())
	except Exception as error:
		print(error)
		reset_client()
	try:
		result = enviar_transmision(parametros_transmision())
		print(result)
	except Exception as error:
		print(error)


def main():
	print("Device Id:" + device_id())
	last_check = None
	last_send = None
	last_predio = None
	last_fecha_ok = None
	last_fecha_try = None
	while True:
		now = time.monotonic()
		fecha_pendiente = last_fecha_ok is None or now - last_fecha_ok >= 3600
		fecha_puede_reintentar = last_fecha_try is None or now - last_fecha_try >= 60
		if fecha_pendiente and fecha_puede_reintentar:
			last_fecha_try = now
			try:
				print("Fecha srv:" + getFecha())
				last_fecha_ok = time.monotonic()
			except Exception as error:
				print(error)
				reset_client()
		now = time.monotonic()
		if last_check is None or now - last_check >= 10:
			try:
				server_alive()
			except Exception as error:
				print(error)
				reset_client()
			last_check = time.monotonic()
		now = time.monotonic()
		if last_predio is None or now - last_predio >= 10:
			try:
				actualizar_predio()
			except Exception as error:
				print("No se pudo consultar el predio", error)
			last_predio = time.monotonic()
		now = time.monotonic()
		if last_send is None or now - last_send >= 15:
			send_data_srv()
			last_send = time.monotonic()
		time.sleep(1)


if __name__ == "__main__":
	main()
