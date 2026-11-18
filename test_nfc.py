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
			"LOCAL_DB": nfc.LOCAL_DB,
			"call_registrar": nfc.call_registrar,
			"consultar_unidad": nfc.consultar_unidad,
			"iniciar_aviso": nfc.iniciar_aviso,
			"fetch_passenger_codes": nfc.fetch_passenger_codes,
			"aviso_generacion": nfc.aviso_generacion,
		}
		nfc.cerrar_local()
		nfc.QUEUE_FILE = os.path.join(self.directory, "cola.txt")
		nfc.RESULT_FILE = os.path.join(self.directory, "asistencia.txt")
		nfc.RESULT_LOG = os.path.join(self.directory, "asistencia_log.txt")
		nfc.BUS_FILE = os.path.join(self.directory, "bus_numero.txt")
		nfc.UNIDAD_FILE = os.path.join(self.directory, "unidad_srv.txt")
		nfc.GPS_FILE = os.path.join(self.directory, "gps.txt")
		nfc.DB_CONFIG_FILE = os.path.join(self.directory, "sos_db.txt")
		nfc.LOCAL_DB = os.path.join(self.directory, "nfc_local.db")
		nfc.aviso_generacion = 0
		self.avisos = []
		nfc.iniciar_aviso = self.avisos.append
		nfc.consultar_unidad = lambda: ""

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
		parsed = nfc.parse_db_config(
			"host=10.0.0.8\nport=3307\nuser=sol\npassword=a=b\n"
			"database=sos\npassenger_database=turintel_turismointel\npases_diarios=2\n"
		)
		self.assertEqual(parsed["host"], "10.0.0.8")
		self.assertEqual(parsed["port"], 3307)
		self.assertEqual(parsed["password"], "a=b")
		self.assertEqual(parsed["database"], "sos")
		self.assertEqual(parsed["passenger_database"], "turintel_turismointel")
		self.assertEqual(parsed["pases_diarios"], 2)
		self.assertEqual(nfc.pases_diarios(), 2)

	def test_el_limite_de_pases_sale_del_archivo(self):
		with open(nfc.DB_CONFIG_FILE, "w") as handle:
			handle.write("pases_diarios=1\n")
		nfc.reemplazar_pasajeros(["a36f48n9"])
		nfc.registrar_lectura_local("a36f48n9", "15", 1, 2, 10, "2026-09-28 08:00:00")
		segundo = nfc.registrar_lectura_local("a36f48n9", "15", 1, 2, 10, "2026-09-28 09:00:00")
		self.assertEqual(segundo["motivo"], "exceso_pases")
		self.assertEqual(len(nfc.listar_pendientes()), 2)

	def fila_registrada(self):
		return (
			"att_0fb53bd2bb8111f1",
			"hrs_ba6591673c93",
			"0",
			"Asistencia registrada: Esteban Robles",
			"cmp_3b827a32c35b",
			"2026-09-28",
		)

	def test_registra_y_saca_de_la_cola(self):
		nfc.call_registrar = lambda item: self.fila_registrada()
		nfc.reemplazar_pasajeros(["a36f48n9"])
		decision = nfc.registrar_lectura_local("a36f48n9", "15", 9.93, -84.08, 10, "2026-09-28 10:00:00")
		self.assertEqual(decision["feedback"], "aceptada")
		self.assertTrue(nfc.process_queue_once())
		self.assertEqual(nfc.listar_pendientes(), [])
		with open(nfc.RESULT_FILE, "r") as handle:
			saved = json.loads(handle.read())
		self.assertEqual(saved["estado"], "registrada")
		self.assertEqual(self.avisos, [])
		self.assertEqual(saved["attendance_id"], "att_0fb53bd2bb8111f1")
		self.assertEqual(saved["accuracy_meters"], 10)
		self.assertEqual(saved["lat"], 9.93)
		envios = nfc.listar_envios()
		self.assertEqual(envios[0]["estado"], "registrada")
		self.assertEqual(envios[0]["attendance_id"], "att_0fb53bd2bb8111f1")
		self.assertEqual(envios[0]["mensaje"], "Asistencia registrada: Esteban Robles")
		self.assertEqual(envios[0]["nfc_code"], "a36f48n9")

	def test_tarjeta_rechazada_no_se_reintenta(self):
		def rechazar(item):
			raise type("Rechazo", (Exception,), {})(1644, "Tarjeta no autorizada")

		nfc.call_registrar = rechazar
		nfc.registrar_lectura_local("a36f48n9", "15", 9.9, -84.0, 10, "2026-09-28 10:00:01")
		self.assertTrue(nfc.process_queue_once())
		self.assertEqual(nfc.listar_pendientes(), [])
		with open(nfc.RESULT_FILE, "r") as handle:
			saved = json.loads(handle.read())
		self.assertEqual(saved["estado"], "rechazada")
		self.assertEqual(self.avisos, [])
		self.assertEqual(saved["mensaje"], "Tarjeta no autorizada")
		self.assertEqual(nfc.listar_envios()[0]["estado"], "rechazada")

	def test_sin_conexion_conserva_la_cola(self):
		def sin_red(item):
			raise type("Conexion", (Exception,), {})(2003, "Can't connect to MySQL server")

		nfc.call_registrar = sin_red
		nfc.registrar_lectura_local("a36f48n9", "15", 9.9, -84.0, 10, "2026-09-28 10:00:02")
		self.assertFalse(nfc.process_queue_once())
		self.assertEqual(self.avisos, [])
		self.assertEqual(nfc.listar_pendientes()[0]["nfc_code"], "a36f48n9")
		self.assertEqual(nfc.listar_envios(), [])

	def test_ignora_unidad_vacia_y_consulta_el_servidor(self):
		with open(nfc.UNIDAD_FILE, "w") as handle:
			handle.write("None")
		self.assertEqual(nfc.read_bus_numero(), "")
		nfc.consultar_unidad = lambda: "15"
		nfc.call_registrar = lambda item: self.fila_registrada()
		nfc.save_queue([nfc.nueva_lectura("a36f48n9", "", 9.9, -84.0, "2026-09-28 10:00:05")])
		self.assertTrue(nfc.process_queue_once())
		self.assertEqual(nfc.load_queue(), [])
		with open(nfc.RESULT_FILE, "r") as handle:
			saved = json.loads(handle.read())
		self.assertEqual(saved["bus"], "15")
		self.assertEqual(nfc.listar_envios()[0]["motivo"], "pendiente_archivo")

	def test_espera_si_falta_el_numero_de_bus(self):
		nfc.save_queue([nfc.nueva_lectura("a36f48n9", "", 0, 0, "2026-09-28 10:00:03")])
		self.assertFalse(nfc.process_queue_once())
		self.assertEqual(nfc.load_queue(), [])
		self.assertEqual(len(nfc.listar_pendientes()), 1)

	def test_la_cola_sobrevive_al_reabrir_la_base(self):
		nfc.reemplazar_pasajeros(["a36f48n9"])
		nfc.registrar_lectura_local("a36f48n9", "15", 9.9, -84.0, 10, "2026-09-28 08:00:00")
		nfc.cerrar_local()
		self.assertEqual(len(nfc.listar_pendientes()), 1)
		self.assertEqual(nfc.pases_en("a36f48n9", "2026-09-28"), 1)

	def test_dos_pases_y_el_tercero_se_rechaza_pero_se_encola(self):
		nfc.reemplazar_pasajeros(["a36f48n9"])
		primero = nfc.registrar_lectura_local("a36f48n9", "15", 1, 2, 10, "2026-09-28 08:00:00")
		mismo = nfc.registrar_lectura_local("a36f48n9", "15", 1, 2, 10, "2026-09-28 08:19:00")
		segundo = nfc.registrar_lectura_local("a36f48n9", "15", 1, 2, 10, "2026-09-28 08:20:00")
		tercero = nfc.registrar_lectura_local("a36f48n9", "15", 1, 2, 10, "2026-09-28 10:00:00")
		self.assertEqual(primero["motivo"], "aceptada")
		self.assertEqual(mismo["motivo"], "mismo_viaje")
		self.assertEqual(mismo["feedback"], "aceptada")
		self.assertEqual(segundo["motivo"], "aceptada")
		self.assertEqual(tercero["motivo"], "exceso_pases")
		self.assertEqual(tercero["feedback"], "rechazada")
		self.assertEqual(nfc.pases_en("a36f48n9", "2026-09-28"), 2)
		self.assertEqual(len(nfc.listar_pendientes()), 4)

	def test_el_mismo_viaje_cruza_la_medianoche_sin_gastar_pase(self):
		nfc.reemplazar_pasajeros(["a36f48n9"])
		nfc.registrar_lectura_local("a36f48n9", "15", 1, 2, 10, "2026-09-28 23:50:00")
		siguiente = nfc.registrar_lectura_local("a36f48n9", "15", 1, 2, 10, "2026-09-29 00:05:00")
		self.assertEqual(siguiente["motivo"], "mismo_viaje")
		self.assertEqual(nfc.pases_en("a36f48n9", "2026-09-28"), 1)
		self.assertEqual(nfc.pases_en("a36f48n9", "2026-09-29"), 0)

	def test_tarjeta_desconocida_se_rechaza_y_se_encola(self):
		nfc.reemplazar_pasajeros(["otra123"])
		decision = nfc.registrar_lectura_local("a36f48n9", "15", 1, 2, 10, "2026-09-28 08:00:00")
		self.assertEqual(decision["motivo"], "no_autorizada")
		self.assertEqual(decision["feedback"], "rechazada")
		self.assertEqual(len(nfc.listar_pendientes()), 1)
		self.assertEqual(nfc.pases_en("a36f48n9", "2026-09-28"), 0)

	def test_la_autorizacion_no_distingue_mayusculas(self):
		nfc.reemplazar_pasajeros(["A36F48N9"])
		self.assertTrue(nfc.tarjeta_autorizada("a36f48n9"))
		decision = nfc.registrar_lectura_local("a36f48n9", "15", 1, 2, 10, "2026-09-28 08:00:00")
		self.assertEqual(decision["motivo"], "aceptada")

	def test_un_fallo_de_sincronizacion_conserva_la_lista(self):
		nfc.reemplazar_pasajeros(["a36f48n9"])

		def fallar():
			raise OSError("sin red")

		nfc.fetch_passenger_codes = fallar
		with self.assertRaises(OSError):
			nfc.sincronizar_pasajeros()
		self.assertTrue(nfc.tarjeta_autorizada("a36f48n9"))

	def test_la_sincronizacion_reemplaza_solo_si_la_consulta_responde(self):
		nfc.reemplazar_pasajeros(["a36f48n9"])
		nfc.fetch_passenger_codes = lambda: ["b36f48n9", "B36F48N9", "  "]
		self.assertEqual(nfc.sincronizar_pasajeros(), 1)
		self.assertFalse(nfc.tarjeta_autorizada("a36f48n9"))
		self.assertTrue(nfc.tarjeta_autorizada("b36f48n9"))


class DecisionTest(unittest.TestCase):
	def test_reglas_de_pase(self):
		self.assertEqual(nfc.decidir_tarjeta(False, 0, None)["motivo"], "no_autorizada")
		self.assertEqual(nfc.decidir_tarjeta(False, 1, 10)["feedback"], "rechazada")
		primera = nfc.decidir_tarjeta(True, 0, None)
		self.assertEqual(primera["motivo"], "aceptada")
		self.assertTrue(primera["incrementar"])
		mismo = nfc.decidir_tarjeta(True, 1, (20 * 60) - 1)
		self.assertEqual(mismo["motivo"], "mismo_viaje")
		self.assertEqual(mismo["feedback"], "aceptada")
		self.assertFalse(mismo["incrementar"])
		self.assertEqual(nfc.decidir_tarjeta(True, 1, 20 * 60)["motivo"], "aceptada")
		exceso = nfc.decidir_tarjeta(True, 2, 20 * 60)
		self.assertEqual(exceso["motivo"], "exceso_pases")
		self.assertEqual(exceso["feedback"], "rechazada")
		self.assertFalse(exceso["incrementar"])
		self.assertEqual(nfc.decidir_tarjeta(True, 1, None, limite=1)["motivo"], "exceso_pases")


class AvisoTest(unittest.TestCase):
	def setUp(self):
		self.generacion = nfc.aviso_generacion
		nfc.aviso_generacion = 0

	def tearDown(self):
		nfc.aviso_generacion = self.generacion

	def test_pines_fisicos_en_numeros_wpi(self):
		self.assertEqual(nfc.PIN_BUZZER, 2)
		self.assertEqual(nfc.PIN_LED_VERDE, 5)
		self.assertEqual(nfc.PIN_LED_ROJO, 7)

	def test_aceptada_pita_y_enciende_el_verde(self):
		buzzer = nfc.PIN_BUZZER
		verde = nfc.PIN_LED_VERDE
		rojo = nfc.PIN_LED_ROJO
		self.assertEqual(nfc.simular_patron("aceptada"), [
			(0.0, buzzer, 0),
			(0.0, verde, 0),
			(0.0, rojo, 0),
			(0.0, buzzer, 1),
			(0.15, buzzer, 0),
			(0.25, verde, 1),
			(0.25, buzzer, 1),
			(0.4, buzzer, 0),
			(0.5, buzzer, 1),
			(0.65, buzzer, 0),
			(1.75, verde, 0),
		])

	def test_rechazada_pita_largo_y_enciende_el_rojo(self):
		buzzer = nfc.PIN_BUZZER
		verde = nfc.PIN_LED_VERDE
		rojo = nfc.PIN_LED_ROJO
		self.assertEqual(nfc.simular_patron("rechazada"), [
			(0.0, buzzer, 0),
			(0.0, verde, 0),
			(0.0, rojo, 0),
			(0.0, buzzer, 1),
			(0.15, buzzer, 0),
			(0.25, rojo, 1),
			(0.25, buzzer, 1),
			(2.25, buzzer, 0),
			(2.25, rojo, 0),
		])

	def test_una_lectura_nueva_corta_el_aviso_anterior(self):
		nfc.aviso_generacion = 1
		escritos = []

		def esperar(segundos):
			nfc.aviso_generacion = 2

		nfc.reproducir_patron(
			nfc.construir_patron("rechazada"),
			1,
			lambda pin, nivel: escritos.append((pin, nivel)),
			esperar,
			lambda: None,
		)
		self.assertEqual(escritos, [
			(nfc.PIN_BUZZER, 0),
			(nfc.PIN_LED_VERDE, 0),
			(nfc.PIN_LED_ROJO, 0),
			(nfc.PIN_BUZZER, 1),
		])


if __name__ == "__main__":
	unittest.main()
