import builtins
import importlib.util
import os
import subprocess
import sys
import time
import traceback

SCRIPT_NOMBRE = "gpio.py"
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

import threading
from time import sleep

import os
import tempfile

global time_volumen_pe;
time_volumen_pe=80;
global time_volumen_ps;
time_volumen_ps=180;
global pe_validada
pe_validada=0
global pe_validada_ps
pe_validada_ps=0
BASE_DIR = "/home/orangepi/Documents"
ENTRADAS_PE = os.path.join(BASE_DIR, "data_barras_entradas_pe.txt")
ENTRADAS_PS = os.path.join(BASE_DIR, "data_barras_entradas_ps.txt")
PREDIO_FILE = os.path.join(BASE_DIR, "en_predio.txt")
CAMPOS_PE = (
	"GeneralEntradasPe",
	"GeneralSalidasPe",
	"GeneralEntradasPe_Predio",
	"GeneralSalidasPe_Predio",
)
CAMPOS_PS = (
	"GeneralEntradasPs",
	"GeneralSalidasPs",
	"GeneralEntradasPs_Predio",
	"GeneralSalidasPs_Predio",
)
contador_lock = threading.Lock()
wiringpi = None


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


def en_predio():
	try:
		with open(PREDIO_FILE, "r") as handle:
			return handle.read().strip() == "1"
	except OSError:
		return False


def leer_contadores(path, campos):
	try:
		with open(path, "r") as handle:
			filedata = handle.read()
	except OSError:
		filedata = ""
	valores = {}
	for campo in campos:
		label = campo + ": "
		try:
			start = filedata.index(label) + len(label)
			end = filedata.index("$$", start)
			valores[campo] = int(filedata[start:end].strip())
		except (ValueError, IndexError):
			valores[campo] = 0
	return valores


def escribir_contadores(path, campos, valores):
	body = "".join(campo + ": " + str(int(valores[campo])) + "$$" for campo in campos)
	atomic_write(path, body)


def incrementar_contador(path, campos, normal, predio):
	with contador_lock:
		valores = leer_contadores(path, campos)
		campo = predio if en_predio() else normal
		valores[campo] = int(valores.get(campo, 0)) + 1
		escribir_contadores(path, campos, valores)


def getval_se():
	
	global val_se
	global time_off_se
	global time_on_se
	global time_duracion_se
	global pe_validada
	global time_dif_val
	time_off_se=datetime.datetime.now()
	time_on_se=datetime.datetime.now()
	while wiringpi.digitalRead(11) == 0 :
		sleep(0.01)
		val_se=0
		
	time_off_se=datetime.datetime.now()
	while wiringpi.digitalRead(11) == 1 :
		sleep(0.01)		
		val_se=1
	val_se=1
	time_on_se=datetime.datetime.now()
	val_se=1;
	evt_entradaspe.set()
	time_duracion_se=(time_on_se-time_off_se).total_seconds() * 1000
	time_dif_val=(time_on_se-time_on_ss).total_seconds() * 1000
	if (time_duracion_se>time_volumen_pe and time_off_se<time_off_ss and (time_dif_val<2000 or time_dif_val>-2000)and pe_validada == 1):	
		pe_validada = 0
		incremeta_entrada_pe()	
		print("Pe Ent detectada duracion en ms: "+str(time_duracion_se))
	if ((time_dif_val>=2000 or time_dif_val<=-2000)and pe_validada == 1): 
		pe_validada = 0
		print("Signal Val tardia "+str(time_dif_val))
	threading.Timer(0.1,getval_se).start()

def getval_se_ps():
	
	global val_se_ps
	global time_off_se_ps
	global time_on_se_ps
	global time_duracion_se_ps
	global pe_validada_ps
	time_off_se_ps=datetime.datetime.now()
	time_on_se_ps=datetime.datetime.now()
	while wiringpi.digitalRead(17) == 0 :
		sleep(0.01)
		val_se_ps=0
		
	time_off_se_ps=datetime.datetime.now()
	while wiringpi.digitalRead(17) == 1 :
		sleep(0.01)		
		val_se_ps=1
	val_se_ps=1
	time_on_se_ps=datetime.datetime.now()
	val_se_ps=1;
	evt_entradasps.set()
	time_duracion_se_ps=(time_on_se_ps-time_off_se_ps).total_seconds() * 1000
	if (time_duracion_se_ps>time_volumen_ps and time_off_se_ps<time_off_ss_ps and time_on_se_ps>time_on_ss_ps and pe_validada_ps == 1):	
		pe_validada_ps = 0
		incremeta_entrada_ps()	
		print("Ps Ent detectada duracion en ms: "+str(time_duracion_se_ps))
	threading.Timer(0.1,getval_se_ps).start()


def getval_ss():
	global val_ss
	global time_off_ss
	global time_on_ss
	global time_duracion_ss
	global pe_validada
	global time_dif_val
	time_off_ss=datetime.datetime.now()
	time_on_ss=datetime.datetime.now()
	while wiringpi.digitalRead(12) == 0 :
		sleep(0.01)
		val_ss=0	
	time_off_ss=datetime.datetime.now()
	while wiringpi.digitalRead(12) == 1 :
		sleep(0.01)		
		val_ss=1
	time_on_ss=datetime.datetime.now()
	val_ss=1;
	evt_salidaspe.set()
	time_duracion_ss=(time_on_ss-time_off_ss).total_seconds() * 1000
	time_dif_val=(time_on_se-time_on_ss).total_seconds() * 1000
	if (time_duracion_ss>time_volumen_pe and time_off_ss<time_off_se and time_on_se<time_on_ss and (time_dif_val<2000 or time_dif_val>-2000) and pe_validada == 1):
		pe_validada = 0	
		incremeta_salidas_pe()
		print("Pe Sal detectada duracion en ms: "+str(time_duracion_ss))
	if ((time_dif_val>=2000 or time_dif_val<=-2000)and pe_validada == 1): 
		pe_validada = 0
		print("Signal Val tardia "+str(time_dif_val))
	threading.Timer(0.1,getval_ss).start()

def getval_ss_ps():
	global val_ss_ps
	global time_off_ss_ps
	global time_on_ss_ps
	global time_duracion_ss_ps
	global pe_validada_ps
	time_off_ss_ps=datetime.datetime.now()
	time_on_ss_ps=datetime.datetime.now()
	while wiringpi.digitalRead(19) == 0 :
		sleep(0.01)
		val_ss_ps=0	
	time_off_ss_ps=datetime.datetime.now()
	while wiringpi.digitalRead(19) == 1 :
		sleep(0.01)		
		val_ss_ps=1
	time_on_ss_ps=datetime.datetime.now()
	val_ss_ps=1;
	evt_salidasps.set()
	time_duracion_ss_ps=(time_on_ss_ps-time_off_ss_ps).total_seconds() * 1000
	if (time_duracion_ss_ps>time_volumen_ps and time_off_ss_ps<time_off_se_ps and time_on_se_ps<time_on_ss_ps and pe_validada_ps == 1):
		pe_validada_ps = 0	
		incremeta_salidas_ps()
		print("Ps Sal detectada duracion en ms: "+str(time_duracion_ss_ps))
	threading.Timer(0.1,getval_ss_ps).start()


def getval_sv():
	global pe_validada
	global val_sv
	global time_off_sv
	global time_on_sv
	global time_duracion_sv
	time_off_sv=datetime.datetime.now()
	
	while wiringpi.digitalRead(14) == 0 :
		sleep(0.01)		
		val_sv=1
		
	time_off_sv=datetime.datetime.now()
	pe_validada=1
	while wiringpi.digitalRead(14) == 1 :
		sleep(0.01)
		time_on_sv=datetime.datetime.now()
		time_duracion_sv=(time_on_sv-time_off_sv).total_seconds() * 1000
		if (time_duracion_sv>10000):
			
			pe_validada=1		
		val_sv=1
	time_on_sv=datetime.datetime.now()
	val_sv=1;
	evt_validadorpe.set()
	time_duracion_sv=(time_on_sv-time_off_sv).total_seconds() * 1000
	threading.Timer(0.1,getval_sv).start()

def getval_sv_ps():
	global pe_validada_ps
	global val_sv_ps
	global time_off_sv_ps
	global time_on_sv_ps
	global time_duracion_sv_ps
	time_off_sv_ps=datetime.datetime.now()
	pe_validada_ps=0
	while wiringpi.digitalRead(20) == 0 :
		sleep(0.01)		
		val_sv_ps=1	
	time_off_sv_ps=datetime.datetime.now()
	pe_validada_ps=1
	while wiringpi.digitalRead(20) == 1 :
		sleep(0.01)
		time_on_sv_ps=datetime.datetime.now()
		time_duracion_sv_ps=(time_on_sv_ps-time_off_sv_ps).total_seconds() * 1000
		if (time_duracion_sv_ps>30000):
			
			pe_validada_ps=1		
		val_sv_ps=1
	time_on_sv_ps=datetime.datetime.now()
	pe_validada_ps=0
	val_sv_ps=1;
	evt_validadorps.set()
	time_duracion_sv_ps=(time_on_sv_ps-time_off_sv_ps).total_seconds() * 1000
	threading.Timer(0.1,getval_sv_ps).start()


def getval_bloqueo_pe():
	global pe_bloqueada
	global val_pe_bloqueo
	global time_off_pe_bloqueo
	global time_on_pe_bloqueo
	global time_duracion_pe_bloqueo
	time_off_pe_bloqueo=datetime.datetime.now()
	while wiringpi.digitalRead(11) == 0 and wiringpi.digitalRead(12)  and wiringpi.digitalRead(14) == 0 :
		sleep(0.05)		
		pe_bloqueada=0
	time_off_pe_bloqueo=datetime.datetime.now()
	
	pe_bloqueada=1
	while wiringpi.digitalRead(11) == 1 or wiringpi.digitalRead(12) == 1 or wiringpi.digitalRead(14) == 1 :
		sleep(0.05)
		val_sv=1
		time_on_pe_bloqueo=datetime.datetime.now()
		time_duracion_bloqueo=(time_on_pe_bloqueo-time_off_pe_bloqueo).total_seconds() * 1000
		if (time_duracion_bloqueo>3000):
			print("Barra bloqueada")
			sleep(1)
	pe_bloqueada=0
	val_pe_bloqueo=1;
	evt_bloqueope.set()
	threading.Timer(0.1,getval_bloqueo_pe).start()

def getval_bloqueo_ps():
	global ps_bloqueada
	global val_ps_bloqueo
	global time_off_ps_bloqueo
	global time_on_ps_bloqueo
	global time_duracion_ps_bloqueo
	time_off_ps_bloqueo=datetime.datetime.now()
	while wiringpi.digitalRead(17) == 0 and wiringpi.digitalRead(19)  and wiringpi.digitalRead(20) == 0 :
		sleep(0.05)		
		ps_bloqueada=0
	time_off_ps_bloqueo=datetime.datetime.now()
	
	ps_bloqueada=1
	while wiringpi.digitalRead(17) == 1 or wiringpi.digitalRead(19) == 1 or wiringpi.digitalRead(20) == 1 :
		sleep(0.05)
		val_sv_ps=1
		time_on_ps_bloqueo=datetime.datetime.now()
		time_duracion_bloqueo_ps=(time_on_ps_bloqueo-time_off_ps_bloqueo).total_seconds() * 1000
		if (time_duracion_bloqueo_ps>8000):
			print("Barra Salida bloqueada")
			sleep(1)
	ps_bloqueada=0
	val_ps_bloqueo=1;
	evt_bloqueops.set()
	threading.Timer(0.1,getval_bloqueo_ps).start()


def incremeta_entrada_pe():
	incrementar_contador(ENTRADAS_PE, CAMPOS_PE, "GeneralEntradasPe", "GeneralEntradasPe_Predio")

def incremeta_entrada_ps():
	incrementar_contador(ENTRADAS_PS, CAMPOS_PS, "GeneralEntradasPs", "GeneralEntradasPs_Predio")


def incremeta_salidas_pe():
	incrementar_contador(ENTRADAS_PE, CAMPOS_PE, "GeneralSalidasPe", "GeneralSalidasPe_Predio")

def incremeta_salidas_ps():
	incrementar_contador(ENTRADAS_PS, CAMPOS_PS, "GeneralSalidasPs", "GeneralSalidasPs_Predio")


def iniciar():
	global wiringpi
	import wiringpi as modulo
	from wiringpi import GPIO
	wiringpi = modulo
	wiringpi.wiringPiSetup()
	wiringpi.pinMode(17, GPIO.INPUT)
	wiringpi.pinMode(19, GPIO.INPUT)
	wiringpi.pinMode(20, GPIO.INPUT)
	wiringpi.pinMode(11, GPIO.INPUT)
	wiringpi.pinMode(12, GPIO.INPUT)
	wiringpi.pinMode(14, GPIO.INPUT)
	global evt_entradaspe, evt_salidaspe, evt_validadorpe, evt_bloqueope
	global evt_entradasps, evt_salidasps, evt_validadorps, evt_bloqueops
	global val_se, val_ss, val_sv, val_pe_bloqueo
	global val_se_ps, val_ss_ps, val_sv_ps, val_ps_bloqueo
	evt_entradaspe=threading.Event()
	val_se=""
	threading.Thread(target=getval_se).start()
	evt_salidaspe=threading.Event()
	val_ss=""
	threading.Thread(target=getval_ss).start()
	evt_validadorpe=threading.Event()
	val_sv=""
	threading.Thread(target=getval_sv).start()
	evt_bloqueope=threading.Event()
	val_pe_bloqueo=""
	threading.Thread(target=getval_bloqueo_pe).start()

	evt_entradasps=threading.Event()
	val_se_ps=""
	threading.Thread(target=getval_se_ps).start()
	evt_salidasps=threading.Event()
	val_ss_ps=""
	threading.Thread(target=getval_ss_ps).start()
	evt_validadorps=threading.Event()
	val_sv_ps=""
	threading.Thread(target=getval_sv_ps).start()
	evt_bloqueops=threading.Event()
	val_ps_bloqueo=""
	threading.Thread(target=getval_bloqueo_ps).start()


if __name__ == "__main__":
	iniciar()
