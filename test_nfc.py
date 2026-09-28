import json
import os
import tempfile
import unittest

import nfc
from nfc import accept_code, begin_or_append, finish_burst, is_recent_duplicate


class AcceptCodeTest(unittest.TestCase):
	def test_ejemplo_de_tarjeta(self):
		self.assertEqual(accept_code("a36f48n9", 0.2, True), "a36f48n9")

	def test_mas_de_cinco_caracteres(self):
		self.assertEqual(accept_code("abc123", 0.1, True), "abc123")

	def test_cinco_caracteres_no_alcanzan(self):
		self.assertIsNone(accept_code("abc12", 0.1, True))

	def test_sin_enter(self):
		self.assertIsNone(accept_code("a36f48n9", 0.2, False))

	def test_llega_en_menos_de_un_segundo(self):
		self.assertEqual(accept_code("a36f48n9", 0.99, True), "a36f48n9")

	def test_tiempo_excedido(self):
		self.assertIsNone(accept_code("a36f48n9", 1.0, True))

	def test_pausa_dentro_del_bloque(self):
		self.assertIsNone(accept_code("a36f48n9", 0.2, True, True))

	def test_simbolos_no_son_tarjeta(self):
		self.assertIsNone(accept_code("a36f48-9", 0.2, True))


class BurstTest(unittest.TestCase):
	def test_lectura_rapida_con_enter(self):
		buffer = []
		first = None
		last = None
		start = 5.0
		for index, char in enumerate("a36f48n9"):
			buffer, first, last = begin_or_append(buffer, first, last, char, start + (index * 0.01))
		self.assertEqual(finish_burst(buffer, first, last, start + 0.2), "a36f48n9")

	def test_enter_tarda_un_segundo_o_mas(self):
		chars = list("a36f48n9")
		self.assertIsNone(finish_burst(chars, 0.0, 0.8, 1.0))

	def test_pausa_descarta_el_bloque_anterior(self):
		buffer, first, last = begin_or_append([], None, None, "a", 1.0)
		buffer, first, last = begin_or_append(buffer, first, last, "3", 1.05)
		buffer, first, last = begin_or_append(buffer, first, last, "6", 2.2)
		self.assertEqual(buffer, ["6"])
		self.assertIsNone(finish_burst(buffer, first, last, 2.25))


class DuplicateTest(unittest.TestCase):
	def test_repite_dentro_de_dos_segundos(self):
		self.assertTrue(is_recent_duplicate("a36f48n9", "a36f48n9", 10.0, 11.5))

	def test_la_misma_tarjeta_despues_de_la_ventana(self):
		self.assertFalse(is_recent_duplicate("a36f48n9", "a36f48n9", 10.0, 12.0))

	def test_otra_tarjeta(self):
		self.assertFalse(is_recent_duplicate("b36f48n9", "a36f48n9", 10.0, 10.2))


EJEMPLO = '"att_0fb53bd2bb8111f1","hrs_ba6591673c93","0","Asistencia registrada: Esteban Robles","cmp_3b827a32c35b","2026-09-28"'


class AsistenciaTest(unittest.TestCase):
	def setUp(self):
		self.directory = tempfile.mkdtemp()
		self.original = {
			"QUEUE_FILE": nfc.QUEUE_FILE,
			"RESULT_FILE": nfc.RESULT_FILE,
			"RESULT_LOG": nfc.RESULT_LOG,
			"BUS_FILE": nfc.BUS_FILE,
			"UNIDAD_FILE": nfc.UNIDAD_FILE,
			"GPS_FILE": nfc.GPS_FILE,
			"DB_CONFIG_FILE": nfc.DB_CONFIG_FILE,
			"call_registrar": nfc.call_registrar,
		}
		nfc.QUEUE_FILE = os.path.join(self.directory, "cola.txt")
		nfc.RESULT_FILE = os.path.join(self.directory, "asistencia.txt")
		nfc.RESULT_LOG = os.path.join(self.directory, "asistencia_log.txt")
		nfc.BUS_FILE = os.path.join(self.directory, "bus_numero.txt")
		nfc.UNIDAD_FILE = os.path.join(self.directory, "unidad_srv.txt")
		nfc.GPS_FILE = os.path.join(self.directory, "gps.txt")
		nfc.DB_CONFIG_FILE = os.path.join(self.directory, "sos_db.txt")

	def tearDown(self):
		for key, value in self.original.items():
			setattr(nfc, key, value)

	def test_ejemplo_en_una_sola_cadena(self):
		parsed = nfc.parse_asistencia_row((EJEMPLO,))
		self.assertEqual(parsed["attendance_id"], "att_0fb53bd2bb8111f1")
		self.assertEqual(parsed["horario_id"], "hrs_ba6591673c93")
		self.assertEqual(parsed["duplicate"], "0")
		self.assertEqual(parsed["mensaje"], "Asistencia registrada: Esteban Robles")
		self.assertEqual(parsed["empresa_id"], "cmp_3b827a32c35b")
		self.assertEqual(parsed["fecha_servicio"], "2026-09-28")

	def test_ejemplo_en_columnas(self):
		parsed = nfc.parse_asistencia_row((
			"att_0fb53bd2bb8111f1",
			"hrs_ba6591673c93",
			"0",
			"Asistencia registrada: Esteban Robles",
			"cmp_3b827a32c35b",
			"2026-09-28",
		))
		self.assertEqual(parsed["mensaje"], "Asistencia registrada: Esteban Robles")

	def test_exactitud_por_defecto_es_10(self):
		item = nfc.nueva_lectura("a36f48n9", "15", 9.93, -84.08, "2026-09-28 10:00:00")
		self.assertEqual(item["accuracy"], 10)
		self.assertEqual(nfc.asistencia_params(item), ("15", "a36f48n9", 9.93, -84.08, 10))

	def test_sqlstate_45000_es_tarjeta_rechazada(self):
		rechazo = type("Rechazo", (Exception,), {})(1644, "Tarjeta no autorizada")
		self.assertTrue(nfc.is_tarjeta_rechazada(rechazo))
		con_estado = type("Estado", (Exception,), {"sqlstate": "45000"})("fallo")
		self.assertTrue(nfc.is_tarjeta_rechazada(con_estado))
		conexion = type("Conexion", (Exception,), {})(2003, "Can't connect to MySQL server")
		self.assertFalse(nfc.is_tarjeta_rechazada(conexion))

	def test_configuracion_de_la_base(self):
		parsed = nfc.parse_db_config("host=10.0.0.8\nport=3307\nuser=sol\npassword=a=b\ndatabase=sos\n")
		self.assertEqual(parsed["host"], "10.0.0.8")
		self.assertEqual(parsed["port"], 3307)
		self.assertEqual(parsed["password"], "a=b")
		self.assertEqual(parsed["database"], "sos")

	def test_registra_y_saca_de_la_cola(self):
		nfc.call_registrar = lambda item: (
			"att_0fb53bd2bb8111f1",
			"hrs_ba6591673c93",
			"0",
			"Asistencia registrada: Esteban Robles",
			"cmp_3b827a32c35b",
			"2026-09-28",
		)
		nfc.save_queue([nfc.nueva_lectura("a36f48n9", "15", 9.93, -84.08, "2026-09-28 10:00:00")])
		self.assertTrue(nfc.process_queue_once())
		self.assertEqual(nfc.load_queue(), [])
		with open(nfc.RESULT_FILE, "r") as handle:
			saved = json.loads(handle.read())
		self.assertEqual(saved["estado"], "registrada")
		self.assertEqual(saved["attendance_id"], "att_0fb53bd2bb8111f1")
		self.assertEqual(saved["accuracy_meters"], 10)
		self.assertEqual(saved["lat"], 9.93)

	def test_tarjeta_rechazada_no_se_reintenta(self):
		def rechazar(item):
			raise type("Rechazo", (Exception,), {})(1644, "Tarjeta no autorizada")

		nfc.call_registrar = rechazar
		nfc.save_queue([nfc.nueva_lectura("a36f48n9", "15", 9.9, -84.0, "2026-09-28 10:00:01")])
		self.assertTrue(nfc.process_queue_once())
		self.assertEqual(nfc.load_queue(), [])
		with open(nfc.RESULT_FILE, "r") as handle:
			saved = json.loads(handle.read())
		self.assertEqual(saved["estado"], "rechazada")
		self.assertEqual(saved["mensaje"], "Tarjeta no autorizada")

	def test_sin_conexion_conserva_la_cola(self):
		def sin_red(item):
			raise type("Conexion", (Exception,), {})(2003, "Can't connect to MySQL server")

		nfc.call_registrar = sin_red
		item = nfc.nueva_lectura("a36f48n9", "15", 9.9, -84.0, "2026-09-28 10:00:02")
		nfc.save_queue([item])
		self.assertFalse(nfc.process_queue_once())
		self.assertEqual(nfc.load_queue()[0]["codigo"], "a36f48n9")

	def test_espera_si_falta_el_numero_de_bus(self):
		nfc.save_queue([nfc.nueva_lectura("a36f48n9", "", 0, 0, "2026-09-28 10:00:03")])
		self.assertFalse(nfc.process_queue_once())
		self.assertEqual(len(nfc.load_queue()), 1)


if __name__ == "__main__":
	unittest.main()
