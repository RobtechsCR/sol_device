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
