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
WSDL = "http://45.32.7.136:8080/WebServiceSOLV3-3/SolSrv?wsdl"
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
		deviceid = device_id()
		entradas = get_entradas_pe()
		salidas = get_salidas_pe()
		entradas_ps = get_entradas_ps()
		salidas_ps = get_salidas_ps()
		latitud = get_latitud()
		longitud = get_longitud()
		velocidad = get_velocidad()
		km = getKM()
		now = datetime.datetime.now(timezone)
		result = get_client().service.insertarTransmisionConKM(
			now, deviceid, latitud, longitud, velocidad, entradas, salidas, entradas_ps, salidas_ps, km
		)
		print(result)
	except Exception as error:
		print(error)
		reset_client()


def main():
	print("Device Id:" + device_id())
	last_check = None
	last_send = None
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
		if last_send is None or now - last_send >= 15:
			send_data_srv()
			last_send = time.monotonic()
		time.sleep(1)


if __name__ == "__main__":
	main()
