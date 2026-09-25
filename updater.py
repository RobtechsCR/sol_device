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
