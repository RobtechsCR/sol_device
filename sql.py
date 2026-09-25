import datetime
import os
import sqlite3
import time
import uuid

import pytz

BASE_DIR = "/home/orangepi/Documents"
DB_PATH = os.path.join(BASE_DIR, "backup.db")
DEVICE_ID_PATH = os.path.join(BASE_DIR, "device_id.txt")
GPS_FILE = os.path.join(BASE_DIR, "gps.txt")
SERVER_STATUS = os.path.join(BASE_DIR, "serverstatus.txt")
ENTRADAS_PE = os.path.join(BASE_DIR, "data_barras_entradas_pe.txt")
ENTRADAS_PS = os.path.join(BASE_DIR, "data_barras_entradas_ps.txt")
timezone = pytz.timezone("America/Costa_Rica")
PURGE_SECONDS = 24 * 60 * 60

CREATE_TABLE = """
CREATE TABLE if not exists monitoreo(
	Fecha DATETIME not null,
	DeviceId VARCHAR(50) not null,
	latitud FLOAT not null,
	longitud FLOAT not null,
	Velocidad FLOAT not null,
	GeneralEntradasPe INTEGER not null,
	GeneralSalidasPe INTEGER not null,
	GeneralEntradasPs INTEGER not null,
	GeneralSalidasPs INTEGER not null,
	SrvOnline VARCHAR(50) not null
)
"""


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


def connect():
	os.makedirs(BASE_DIR, exist_ok=True)
	con = sqlite3.connect(DB_PATH, timeout=10)
	con.execute("PRAGMA journal_mode=WAL")
	return con


def init_db():
	con = connect()
	try:
		con.execute(CREATE_TABLE)
		con.commit()
	finally:
		con.close()


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


def read_gps_field(prefix, end_at_comma):
	try:
		with open(GPS_FILE, "r") as handle:
			filedata = handle.read()
		if prefix not in filedata:
			return 0.0
		start = filedata.index(prefix) + len(prefix)
		if end_at_comma:
			end = filedata.index(",", start)
			return float(filedata[start:end].strip())
		return float(filedata[start:].strip())
	except (OSError, ValueError):
		return 0.0


def get_latitud():
	return read_gps_field("Latitud:", True)


def get_longitud():
	return read_gps_field("Longitud: ", True)


def get_velocidad():
	velocidad = read_gps_field("Velocidad: ", False)
	print(velocidad)
	return velocidad


def server_alive():
	try:
		with open(SERVER_STATUS, "r") as handle:
			filedata = handle.read()
		if "True" in filedata:
			return "True"
	except OSError:
		pass
	return "False"


def save_data_sql():
	deviceid = device_id()
	entradas = get_entradas_pe()
	salidas = get_salidas_pe()
	entradas_ps = get_entradas_ps()
	salidas_ps = get_salidas_ps()
	latitud = get_latitud()
	longitud = get_longitud()
	velocidad = get_velocidad()
	is_online = server_alive()
	now = datetime.datetime.now(timezone)
	fecha = now.strftime("%Y-%m-%d %H:%M:%S")
	con = connect()
	try:
		cur = con.cursor()
		cur.execute(
			"insert into monitoreo (Fecha, DeviceId, latitud, longitud, Velocidad, GeneralEntradasPe, GeneralSalidasPe, GeneralEntradasPs, GeneralSalidasPs, SrvOnline) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
			(fecha, str(deviceid), latitud, longitud, velocidad, entradas, salidas, entradas_ps, salidas_ps, is_online),
		)
		con.commit()
		print("Respaldo guardado", fecha, deviceid, latitud, longitud, velocidad, is_online)
	finally:
		con.close()


def delete_data_sql():
	con = connect()
	try:
		cur = con.cursor()
		cur.execute("delete from monitoreo where Fecha < DATETIME('now','-180 day')")
		con.commit()
		print("Limpieza de respaldos mayores a 180 dias")
	finally:
		con.close()


def main():
	print("Device Id:" + device_id())
	last_purge = 0
	while True:
		try:
			init_db()
			now = time.monotonic()
			if last_purge == 0 or now - last_purge >= PURGE_SECONDS:
				delete_data_sql()
				last_purge = now
			save_data_sql()
		except Exception as error:
			print("Error al insertar dato ")
			print(error)
		time.sleep(30)


if __name__ == "__main__":
	main()
