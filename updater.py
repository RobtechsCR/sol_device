import builtins
import importlib.util
import os
import subprocess
import sys
import time
import traceback

SCRIPT_NOMBRE = "updater.py"
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

import os
import subprocess
import tempfile
import time

import zeep

BASE_DIR = "/home/orangepi/Documents"
WSDL = "http://45.32.7.136:8080/WebServiceSOLV3-3/SolSrv?wsdl"

COMPONENTS = [
	{
		"nombre": "gps",
		"version": "getGpsV",
		"script": "getGpsScript",
		"path": os.path.join(BASE_DIR, "gps.py"),
		"version_path": os.path.join(BASE_DIR, "version_gps.txt"),
		"service": "gps.service",
		"ok": "GPS actualizado",
		"nueva": "Nueva version de gps encontrada",
	},
	{
		"nombre": "gpio",
		"version": "getGpioV",
		"script": "getGpioScript",
		"path": os.path.join(BASE_DIR, "gpio.py"),
		"version_path": os.path.join(BASE_DIR, "version_gpio.txt"),
		"service": "gpio.service",
		"ok": "GPIO actualizado",
		"nueva": "Nueva version de gpio encontrada",
	},
	{
		"nombre": "webservice",
		"version": "getWbV",
		"script": "getWbScript",
		"path": os.path.join(BASE_DIR, "webservice.py"),
		"version_path": os.path.join(BASE_DIR, "version_wb.txt"),
		"service": "webservice.service",
		"ok": "Webservice actualizado",
		"nueva": "Nueva version de webservice encontrada",
	},
	{
		"nombre": "sql",
		"version": "getSqlV",
		"script": "getSqlScript",
		"path": os.path.join(BASE_DIR, "sql.py"),
		"version_path": os.path.join(BASE_DIR, "version_sql.txt"),
		"service": "sql.service",
		"ok": "SQL actualizado",
		"nueva": "Nueva version de sql encontrada",
	},
	{
		"nombre": "aux1",
		"version": "getAux1V",
		"script": "getAux1Script",
		"path": os.path.join(BASE_DIR, "aux1.py"),
		"version_path": os.path.join(BASE_DIR, "version_aux1.txt"),
		"service": "aux1.service",
		"ok": "Auxiliar 1 actualizado",
		"nueva": "Nueva version de Auxiliar 1 encontrada",
	},
	{
		"nombre": "aux2",
		"version": "getAux2V",
		"script": "getAux2Script",
		"path": os.path.join(BASE_DIR, "aux2.py"),
		"version_path": os.path.join(BASE_DIR, "version_aux2.txt"),
		"service": "aux2.service",
		"ok": "Auxiliar 2 actualizado",
		"nueva": "Nueva version de Auxiliar 2 encontrada",
	},
	{
		"nombre": "aux3",
		"version": "getAux3V",
		"script": "getAux3Script",
		"path": os.path.join(BASE_DIR, "aux3.py"),
		"version_path": os.path.join(BASE_DIR, "version_aux3.txt"),
		"service": "aux3.service",
		"ok": "Auxiliar 3 actualizado",
		"nueva": "Nueva version de Auxiliar 3 encontrada",
	},
	{
		"nombre": "aux4",
		"version": "getAux4V",
		"script": "getAux4Script",
		"path": os.path.join(BASE_DIR, "aux4.py"),
		"version_path": os.path.join(BASE_DIR, "version_aux4.txt"),
		"service": "aux4.service",
		"ok": "Auxiliar 4 actualizado",
		"nueva": "Nueva version de Auxiliar 4 encontrada",
	},
	{
		"nombre": "aux5",
		"version": "getAux5V",
		"script": "getAux5Script",
		"path": os.path.join(BASE_DIR, "aux5.py"),
		"version_path": os.path.join(BASE_DIR, "version_aux5.txt"),
		"service": "aux5.service",
		"ok": "Auxiliar 5 actualizado",
		"nueva": "Nueva version de Auxiliar 5 encontrada",
	},
]

client = None


def get_client():
	global client
	if client is None:
		transport = zeep.Transport(timeout=15, operation_timeout=15)
		client = zeep.Client(wsdl=WSDL, transport=transport)
	return client


def reset_client():
	global client
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


def read_version(path):
	if not os.path.isfile(path):
		return None
	with open(path, "r") as handle:
		filedata = handle.read().strip()
	if not filedata:
		return None
	return float(filedata)


def store_script(text, script_path):
	if text is None:
		return False
	text = str(text)
	if not text.strip():
		return False
	compile(text, script_path, "exec")
	directory = os.path.dirname(script_path)
	os.makedirs(directory, exist_ok=True)
	fd, tmp = tempfile.mkstemp(dir=directory, suffix=".py.tmp")
	try:
		with os.fdopen(fd, "w") as handle:
			handle.write(text)
			handle.flush()
			os.fsync(handle.fileno())
		os.replace(tmp, script_path)
		return True
	except Exception:
		try:
			os.unlink(tmp)
		except OSError:
			pass
		raise


def install_script(script_method, script_path):
	result = getattr(get_client().service, script_method)()
	return store_script(result, script_path)


def restart_service(service):
	completed = subprocess.run(["systemctl", "restart", service], check=False)
	if completed.returncode != 0:
		print("No se pudo reiniciar " + service)
		return False
	return True


def update_component(component):
	print("Check Version " + component["nombre"])
	result = getattr(get_client().service, component["version"])()
	version_srv = float(result)
	version_device = read_version(component["version_path"])
	if version_device is None:
		atomic_write(component["version_path"], str(version_srv))
		return
	if version_srv > version_device:
		print(component["nueva"])
		print("Aplicando actualizacion " + component["nombre"])
		if not install_script(component["script"], component["path"]):
			print("Actualizacion vacia, se reintentara")
			return
		atomic_write(component["version_path"], str(version_srv))
		restart_service(component["service"])
	else:
		print(component["ok"])


def run_cycle():
	get_client()
	for index, component in enumerate(COMPONENTS):
		if index:
			time.sleep(10)
		try:
			update_component(component)
		except Exception as error:
			print(error)
			reset_client()


def main():
	print("Inicio updater")
	print("Updater online:")
	time.sleep(10)
	while True:
		try:
			run_cycle()
		except Exception as error:
			print(error)
			reset_client()
		time.sleep(180)


if __name__ == "__main__":
	main()
