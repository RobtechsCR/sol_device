import builtins
import importlib.util
import os
import subprocess
import sys
import time
import traceback

SCRIPT_NOMBRE = "webservice.py"
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


def config_chatbot():
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
