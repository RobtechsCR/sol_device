import builtins
import importlib.util
import os
import subprocess
import sys
import time
import traceback

SCRIPT_NOMBRE = "gps.py"
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

import os
import tempfile
import time

import pynmea2
import serial
import serial.tools.list_ports
from geopy.distance import geodesic
from serial.serialutil import SerialException

BASE_DIR = "/home/orangepi/Documents"
GPS_FILE = os.path.join(BASE_DIR, "gps.txt")
KM_FILE = os.path.join(BASE_DIR, "km.txt")
PREFERRED_PORT = "/dev/ttyACM0"

calidadgps = 0


def atomic_write(path, data):
	os.makedirs(os.path.dirname(path), exist_ok=True)
	fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path), suffix=".tmp")
	try:
		with os.fdopen(fd, "w") as handle:
			handle.write(data)
			handle.flush()
			os.fsync(handle.fileno())
		os.chmod(tmp, 0o666)
		os.replace(tmp, path)
	except Exception:
		try:
			os.unlink(tmp)
		except OSError:
			pass
		raise


def read_text(path):
	try:
		with open(path, "r") as handle:
			return handle.read()
	except OSError:
		return ""


def get_latitud():
	filedata = read_text(GPS_FILE)
	try:
		if "Latitud:" not in filedata:
			return 0.0
		start = filedata.index("Latitud:") + 8
		end = filedata.index(",", start)
		return float(filedata[start:end])
	except (ValueError, IndexError):
		return 0.0


def get_longitud():
	filedata = read_text(GPS_FILE)
	try:
		if "Longitud: " not in filedata:
			return 0.0
		start = filedata.index("Longitud: ") + 10
		end = filedata.index(",", start)
		return float(filedata[start:end])
	except (ValueError, IndexError):
		return 0.0


def get_km():
	filedata = read_text(KM_FILE).strip()
	if not filedata:
		return 0.0
	try:
		return float(filedata)
	except ValueError:
		return 0.0


def get_coordenadas_dms(coordenada, tipo):
	try:
		print(coordenada, tipo)
		if tipo == 1:
			grados = coordenada[0:2]
			minutos = coordenada[2:4]
			segundos = coordenada[5:len(coordenada) - 1]
		else:
			grados = coordenada[0:3]
			minutos = coordenada[3:5]
			segundos = coordenada[6:len(coordenada) - 1]
		segundos = "0." + str(segundos)
		sec = float(segundos) * 60
		direccion = coordenada[len(coordenada) - 1:]
		return [grados, minutos, str(sec), direccion]
	except Exception:
		print("Datos gps invalidos")
		return []


def dms_a_decimal(grados, minutos, segundos, direccion):
	try:
		dd = float(grados) + float(minutos) / 60 + float(segundos) / (60 * 60)
		if direccion in ("E", "S", "W"):
			dd *= -1
		return dd
	except Exception:
		return 0.0


def calcular_distancia(lat1, lon1, lat2, lon2):
	try:
		punto1 = (float(lat1), float(lon1))
		punto2 = (float(lat2), float(lon2))
		distancia = geodesic(punto1, punto2).meters
		print("Calcular Dist: ", distancia)
		return distancia
	except Exception:
		return 0.0


def find_gps_port():
	if os.path.exists(PREFERRED_PORT):
		return PREFERRED_PORT
	for port in serial.tools.list_ports.comports():
		device = port.device or ""
		if "ttyACM" in device or "ttyUSB" in device:
			return device
	return None


def format_gps(latitud, longitud, velocidad):
	return "Latitud:" + str(latitud) + ",Longitud: " + str(longitud) + ",Velocidad: " + str(velocidad)


def write_position(latitud, longitud, velocidad, km_acumulado, km_minimo):
	atomic_write(GPS_FILE, format_gps(latitud, longitud, velocidad))
	if float(km_acumulado) > km_minimo:
		print("Escribe en archivo ", str(km_acumulado))
		atomic_write(KM_FILE, str(km_acumulado))


def actualizar_km(latitud, longitud, velocidad):
	km_previo = get_km()
	km_recorrido = calcular_distancia(latitud, longitud, get_latitud(), get_longitud())
	print(km_recorrido)
	if km_recorrido >= 5 and km_recorrido < 70 and float(velocidad) > 2:
		return float(km_previo) + float(km_recorrido)
	return float(km_previo)


def update_quality(line):
	global calidadgps
	if "GGA" not in line:
		return
	try:
		msg = pynmea2.parse(line)
		hdop = msg.horizontal_dil
		calidad = msg.gps_qual
		print("Calidad gps ", hdop, calidad)
		if float(calidad) > 0 and float(hdop) < 2:
			calidadgps = float(hdop)
		else:
			calidadgps = 1000
		print("Exactitud gps: ", calidadgps)
	except (pynmea2.ParseError, ValueError, TypeError) as error:
		print(error)


def handle_rmc(line):
	resp = pynmea2.parse(line)
	latitud = resp.latitude
	longitud = resp.longitude
	velocidad_n = resp.spd_over_grnd
	velocidad = float(velocidad_n) * 1.852 if velocidad_n else 0.0
	print(str(latitud) + ", " + str(longitud))
	print(velocidad)
	km_acumulado = actualizar_km(latitud, longitud, velocidad)
	print(km_acumulado)
	write_position(latitud, longitud, velocidad, km_acumulado, 0)


def collect_gngll(gps, first_line):
	line = first_line
	previous_timeout = gps.timeout
	gps.timeout = 0.2
	started = time.monotonic()
	try:
		while "$GNVTG" not in line:
			if time.monotonic() - started > 2.0:
				print("GNGLL sin VTG, se re-sincroniza")
				return None
			raw = gps.readline()
			if not raw:
				continue
			line = line + raw.decode("ascii", errors="replace").strip()
		return line
	finally:
		gps.timeout = previous_timeout


def handle_gngll(gps, line):
	line = collect_gngll(gps, line)
	if not line:
		return
	print("Getting coordinates")
	print(line)
	index1 = line.index("$GNGLL") + 7
	index2 = line.index(",", index1)
	index3 = line.index(",", index2 + 1)
	index4 = line.index(",", index3 + 1)
	index5 = line.index(",", index4 + 1)
	latitud = line[index1:index2]
	latitud_t = line[index2 + 1:index3]
	longitud = line[index3 + 1:index4]
	longitud_t = line[index4 + 1:index5]
	latitud_dms = get_coordenadas_dms(latitud + latitud_t, 1)
	longitud_dms = get_coordenadas_dms(longitud + longitud_t, 2)
	if not latitud_dms or not longitud_dms:
		print("Datos gps invalidos")
		return
	latitud_decimal = dms_a_decimal(latitud_dms[0], latitud_dms[1], latitud_dms[2], latitud_dms[3])
	longitud_decimal = dms_a_decimal(longitud_dms[0], longitud_dms[1], longitud_dms[2], longitud_dms[3])
	index_vtg = line.index("$GNVTG")
	index_n = line.index("N", index_vtg + 6)
	index_end = line.index(",", index_n + 2)
	velocidad = line[index_n + 2:index_end]
	km_acumulado = actualizar_km(latitud_decimal, longitud_decimal, velocidad)
	print("KM ACUMU", km_acumulado)
	write_position(latitud_decimal, longitud_decimal, velocidad, km_acumulado, 4)


def handle_line(gps, line):
	global calidadgps
	print(line)
	update_quality(line)
	if calidadgps > 2:
		print("GPS Poco Preciso")
	if calidadgps > 2:
		return
	if line.startswith("$GPRMC"):
		print("Getting coordinates")
		handle_rmc(line)
	elif line.startswith("$GNGLL"):
		handle_gngll(gps, line)


def run_session():
	global calidadgps
	port = find_gps_port()
	if not port:
		print("Sin conexion con gps")
		try:
			atomic_write(GPS_FILE, "Sin conexion con gps")
		except OSError as error:
			print(error)
		return
	print("Open serial port gps", port)
	try:
		gps = serial.Serial(port, baudrate=19200, timeout=1)
	except (SerialException, OSError) as error:
		print("Sin conexion con gps", error)
		try:
			atomic_write(GPS_FILE, "Sin conexion con gps")
		except OSError:
			pass
		return
	calidadgps = 0
	print("Serial Port abierto", port)
	try:
		while True:
			try:
				raw = gps.readline()
				if not raw:
					continue
				line = raw.decode("ascii", errors="replace").strip()
				if not line:
					continue
				handle_line(gps, line)
			except pynmea2.ParseError:
				print("Pynmea2 error")
				continue
			except ValueError as error:
				print("Caught an error: " + str(error))
				continue
			except (SerialException, OSError) as error:
				print("Conexion Serial con error, puerto cerrado o sin comunicacion con dispositivo")
				print(error)
				return
			except Exception as error:
				print(error)
				continue
	finally:
		try:
			if gps.isOpen():
				gps.close()
		except Exception:
			pass


def main():
	while True:
		try:
			run_session()
		except Exception as error:
			print("Error en sesion GPS", error)
		time.sleep(2)


if __name__ == "__main__":
	main()
