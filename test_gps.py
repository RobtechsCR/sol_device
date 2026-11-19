import os
import tempfile
import time
import unittest

import pynmea2

import gps


def sentencia(cuerpo):
	checksum = 0
	for caracter in cuerpo:
		checksum ^= ord(caracter)
	return "$" + cuerpo + "*%02X" % checksum


class PosicionGpsTest(unittest.TestCase):
	def setUp(self):
		self.directorio = tempfile.TemporaryDirectory()
		self.gps_file = os.path.join(self.directorio.name, "gps.txt")
		self.km_file = os.path.join(self.directorio.name, "km.txt")
		gps.GPS_FILE = self.gps_file
		gps.KM_FILE = self.km_file
		gps.ultima_velocidad = 0.0
		gps.calidadgps = 0
		gps._temporales_limpiados = False
		gps.atomic_write(self.gps_file, "Latitud:9.9044991667,Longitud: -84.1270158333,Velocidad: 0.071")
		gps.atomic_write(self.km_file, "10")

	def tearDown(self):
		self.directorio.cleanup()

	def texto(self):
		with open(self.gps_file, "r") as handle:
			return handle.read()

	def test_gnrmc_actualiza_aunque_no_sea_gprmc(self):
		linea = sentencia("GNRMC,123519.00,A,0955.0000,N,08410.0000,W,20.0,90.0,191126,,,A")
		gps.handle_line(None, linea)
		texto = self.texto()
		self.assertIn("Latitud:9.916666666666666", texto)
		self.assertNotIn("9.9044991667", texto)
		self.assertIn("Velocidad: 37.04", texto)

	def test_gga_con_poca_precision_tambien_se_guarda(self):
		linea = sentencia("GPGGA,123519,1000.0000,N,08400.0000,W,1,08,5.5,545.4,M,46.9,M,,")
		gps.handle_line(None, linea)
		self.assertIn("Latitud:10.0", self.texto())
		self.assertGreater(gps.calidadgps, 2)

	def test_sin_cobertura_no_borra_la_ultima_posicion(self):
		linea = sentencia("GPGGA,123519,,,,,0,00,99.9,,,,,,")
		gps.handle_line(None, linea)
		self.assertIn("9.9044991667", self.texto())

	def test_no_deja_archivos_temporales(self):
		viejo = os.path.join(self.directorio.name, "tmpabcd1234.tmp")
		with open(viejo, "w") as handle:
			handle.write("viejo")
		antiguo = time.time() - 120
		os.utime(viejo, (antiguo, antiguo))
		gps._temporales_limpiados = False
		gps.atomic_write(self.gps_file, "Latitud:10,Longitud: -84,Velocidad: 1")
		gps.atomic_write(self.gps_file, "Latitud:10,Longitud: -84,Velocidad: 1")
		nombres = os.listdir(self.directorio.name)
		self.assertFalse(any(nombre.endswith(".tmp") for nombre in nombres))
		self.assertFalse(os.path.exists(viejo))
		with open(self.gps_file, "r") as handle:
			self.assertEqual(handle.read(), "Latitud:10,Longitud: -84,Velocidad: 1")

	def test_un_error_de_kilometraje_no_impide_guardar(self):
		def falla(*args):
			raise ValueError("km")

		original = gps.actualizar_km
		gps.actualizar_km = falla
		try:
			linea = sentencia("GPRMC,123519.00,A,1001.0000,N,08401.0000,W,1.0,90.0,191126,,,A")
			gps.handle_line(None, linea)
		finally:
			gps.actualizar_km = original
		self.assertIn("Latitud:10.016666666666667", self.texto())


if __name__ == "__main__":
	unittest.main()
