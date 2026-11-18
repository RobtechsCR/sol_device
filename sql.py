import builtins
import importlib.util
import os
import subprocess
import sys
import time
import traceback

SCRIPT_NOMBRE = "sql.py"
OMITIR_INSTALACION = {"wiringpi", "evdev"}
SCRIPTS_SERVICIO = {
	"gps.py", "gpio.py", "sql.py", "webservice.py",
	"updater.py", "nfc.py", "data_device.py",
}
ALIAS_PIP = {"serial": "pyserial"}
DESTINO_AVISO = "50687465171"
SISTEMA_AVISO = "SOL_DEVICE"
CHATBOT_DB = "chatbot"
SOS_DB_FILE = "/home/orangepi/Documents/sos_db.txt"
SOS_DB_HOST = "45.32.7.136"
SOS_DB_PORT = 3306
SOS_DB_USER = "EROBLES"
SOS_DB_PASSWORD = "LopezM5825"
SOS_DB_NAME = "sos"
_aviso_pendiente = None
_aviso_enviado = False
_importando = False
_import_original = getattr(builtins, "_sol_device_import_original", builtins.__import__)


def modulo_raiz(nombre):
	if not nombre:
		return ""
	return str(nombre).split(".", 1)[0]


def paquete_pip(nombre):
	raiz = modulo_raiz(nombre)
	return ALIAS_PIP.get(raiz, raiz)


def es_biblioteca_estandar(nombre):
	raiz = modulo_raiz(nombre)
	if not raiz or raiz.startswith("_"):
		return True
	if raiz in sys.builtin_module_names:
		return True
	return raiz in getattr(sys, "stdlib_module_names", ())


def debe_instalar(nombre, nivel=0):
	if nivel:
		return False
	raiz = modulo_raiz(nombre)
	if not raiz or raiz in OMITIR_INSTALACION or es_biblioteca_estandar(raiz):
		return False
	try:
		encontrado = importlib.util.find_spec(raiz) is not None
	except (ImportError, ValueError, ModuleNotFoundError):
		encontrado = False
	return not encontrado


def ejecutar_comando(comando):
	entorno = os.environ.copy()
	entorno["DEBIAN_FRONTEND"] = "noninteractive"
	opciones = {"env": entorno}
	if "--version" in comando:
		opciones["stdout"] = subprocess.DEVNULL
		opciones["stderr"] = subprocess.DEVNULL
	subprocess.check_call(comando, **opciones)


def asegurar_pip(ejecutar=None):
	ejecutar = ejecutar or ejecutar_comando
	try:
		ejecutar([sys.executable, "-m", "pip", "--version"])
	except Exception:
		ejecutar(["apt-get", "install", "-y", "python3-pip"])


def instalar_modulo(nombre, ejecutar=None):
	ejecutar = ejecutar or ejecutar_comando
	asegurar_pip(ejecutar)
	ejecutar([sys.executable, "-m", "pip", "install", paquete_pip(nombre)])


def asegurar_sos_db(path=None):
	path = path or SOS_DB_FILE
	texto = ""
	try:
		with open(path, "r") as handle:
			texto = handle.read()
	except OSError:
		texto = ""
	datos = {}
	for line in texto.splitlines():
		line = line.strip()
		if not line or line.startswith("#") or "=" not in line:
			continue
		key, value = line.split("=", 1)
		datos[key.strip().lower()] = value.strip()
	if datos.get("user"):
		return
	datos["host"] = datos.get("host") or SOS_DB_HOST
	datos["port"] = datos.get("port") or str(SOS_DB_PORT)
	datos["user"] = SOS_DB_USER
	datos["password"] = datos.get("password") or SOS_DB_PASSWORD
	datos["database"] = datos.get("database") or SOS_DB_NAME
	directorio = os.path.dirname(path)
	try:
		if directorio:
			os.makedirs(directorio, exist_ok=True)
		contenido = "".join("%s=%s\n" % (key, datos[key]) for key in ("host", "port", "user", "password", "database"))
		fd = os.open(path, os.O_CREAT | os.O_WRONLY | os.O_TRUNC, 0o600)
		with os.fdopen(fd, "w") as handle:
			handle.write(contenido)
	except OSError:
		return


def config_chatbot():
	asegurar_sos_db(SOS_DB_FILE)
	config = {
		"host": SOS_DB_HOST,
		"port": SOS_DB_PORT,
		"user": "",
		"password": "",
		"database": CHATBOT_DB,
	}
	try:
		with open(SOS_DB_FILE, "r") as handle:
			texto = handle.read()
	except OSError:
		return config
	for line in texto.splitlines():
		line = line.strip()
		if not line or line.startswith("#") or "=" not in line:
			continue
		key, value = line.split("=", 1)
		key = key.strip().lower()
		value = value.strip()
		if key == "port" and value:
			try:
				config["port"] = int(value)
			except ValueError:
				pass
		elif key in ("host", "user", "password"):
			config[key] = value
	return config


def enviar_aviso(mensaje, conectar=None, importar=None):
	global _aviso_pendiente, _aviso_enviado
	_aviso_pendiente = mensaje
	if _aviso_enviado:
		return True
	importar = importar or _import_original
	try:
		pymysql = importar("pymysql")
	except ImportError:
		print(mensaje)
		return False
	try:
		config = config_chatbot()
		if not config.get("user"):
			raise RuntimeError("Falta el usuario de MySQL en " + SOS_DB_FILE)
		if conectar is None:
			conexion = pymysql.connect(
				host=config["host"],
				port=int(config["port"]),
				user=config["user"],
				password=config["password"],
				database=config["database"],
				connect_timeout=5,
				autocommit=True,
				charset="utf8mb4",
			)
		else:
			conexion = conectar(config)
		try:
			cursor = conexion.cursor()
			cursor.execute(
				"INSERT INTO mensajes_automaticos (Destino, Mensaje, Estado, Sistema) VALUES (%s, %s, %s, %s)",
				(DESTINO_AVISO, mensaje, 0, SISTEMA_AVISO),
			)
			confirmar = getattr(conexion, "commit", None)
			if confirmar:
				confirmar()
			cerrar = getattr(cursor, "close", None)
			if cerrar:
				cerrar()
		finally:
			conexion.close()
		_aviso_enviado = True
		_aviso_pendiente = None
		return True
	except Exception as error:
		print(mensaje)
		print(error)
		return False


def texto_fallo(nombre, error):
	return SCRIPT_NOMBRE + " " + modulo_raiz(nombre) + ": " + str(error)


def importar_con_instalacion(original, nombre, globales, locales, fromlist, nivel, ejecutar=None, esperar=None, avisar=None, intentos=None):
	global _importando
	try:
		return original(nombre, globales, locales, fromlist, nivel)
	except ImportError:
		if _importando or not debe_instalar(nombre, nivel):
			raise
		avisar = avisar or enviar_aviso
		esperar = esperar or time.sleep
		notificado = False
		_importando = True
		try:
			while True:
				try:
					instalar_modulo(nombre, ejecutar)
					resultado = original(nombre, globales, locales, fromlist, nivel)
					if _aviso_pendiente and not _aviso_enviado:
						avisar(_aviso_pendiente)
					return resultado
				except Exception as error:
					texto = texto_fallo(nombre, error)
					print(texto)
					if not notificado:
						avisar(texto)
						notificado = True
					elif _aviso_pendiente and not _aviso_enviado:
						avisar(_aviso_pendiente)
					if intentos is not None:
						intentos -= 1
						if intentos <= 0:
							raise
					esperar(60)
		finally:
			_importando = False


def pedido_por_script():
	propios = {
		"gancho_import", "importar_con_instalacion", "enviar_aviso",
		"debe_instalar", "instalar_modulo", "asegurar_pip", "pedido_por_script",
	}
	for frame in reversed(traceback.extract_stack()[:-1]):
		if frame.name in propios:
			continue
		archivo = frame.filename.replace("\\", "/").rsplit("/", 1)[-1]
		return archivo in SCRIPTS_SERVICIO
	return False


def gancho_import(name, globals=None, locals=None, fromlist=(), level=0):
	if not pedido_por_script():
		return _import_original(name, globals, locals, fromlist, level)
	return importar_con_instalacion(
		_import_original, name, globals, locals, fromlist, level
	)


def activar_gancho():
	if getattr(builtins, "_sol_device_gancho", False):
		return
	builtins._sol_device_import_original = builtins.__import__
	builtins._sol_device_gancho = True
	builtins.__import__ = gancho_import


activar_gancho()

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
	SrvOnline VARCHAR(50) not null,
	GeneralEntradasPe_Predio INTEGER not null DEFAULT 0,
	GeneralSalidasPe_Predio INTEGER not null DEFAULT 0,
	GeneralEntradasPs_Predio INTEGER not null DEFAULT 0,
	GeneralSalidasPs_Predio INTEGER not null DEFAULT 0
)
"""

PREDIO_COLUMNS = (
	"GeneralEntradasPe_Predio",
	"GeneralSalidasPe_Predio",
	"GeneralEntradasPs_Predio",
	"GeneralSalidasPs_Predio",
)


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


def ensure_predio_columns(con):
	existing = {row[1] for row in con.execute("PRAGMA table_info(monitoreo)")}
	for name in PREDIO_COLUMNS:
		if name not in existing:
			con.execute(
				"ALTER TABLE monitoreo ADD COLUMN " + name + " INTEGER not null DEFAULT 0"
			)


def init_db():
	con = connect()
	try:
		con.execute(CREATE_TABLE)
		ensure_predio_columns(con)
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


def get_entradas_pe_predio():
	return read_marked(ENTRADAS_PE, "GeneralEntradasPe_Predio: ")


def get_salidas_pe_predio():
	return read_marked(ENTRADAS_PE, "GeneralSalidasPe_Predio: ")


def get_entradas_ps_predio():
	return read_marked(ENTRADAS_PS, "GeneralEntradasPs_Predio: ")


def get_salidas_ps_predio():
	return read_marked(ENTRADAS_PS, "GeneralSalidasPs_Predio: ")


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
	entradas_pe_predio = get_entradas_pe_predio()
	salidas_pe_predio = get_salidas_pe_predio()
	entradas_ps_predio = get_entradas_ps_predio()
	salidas_ps_predio = get_salidas_ps_predio()
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
			"""insert into monitoreo (
				Fecha, DeviceId, latitud, longitud, Velocidad,
				GeneralEntradasPe, GeneralSalidasPe, GeneralEntradasPs, GeneralSalidasPs, SrvOnline,
				GeneralEntradasPe_Predio, GeneralSalidasPe_Predio, GeneralEntradasPs_Predio, GeneralSalidasPs_Predio
			) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
			(
				fecha, str(deviceid), latitud, longitud, velocidad,
				entradas, salidas, entradas_ps, salidas_ps, is_online,
				entradas_pe_predio, salidas_pe_predio, entradas_ps_predio, salidas_ps_predio,
			),
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
