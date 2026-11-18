import os
import sqlite3
import tempfile
import unittest

import gpio
import sql
import webservice


class PredioTest(unittest.TestCase):
	def setUp(self):
		self.directory = tempfile.mkdtemp()
		self.original = {}
		for module, names in (
			(gpio, ("ENTRADAS_PE", "ENTRADAS_PS", "PREDIO_FILE")),
			(webservice, (
				"ENTRADAS_PE", "ENTRADAS_PS", "PREDIO_FILE", "GPS_FILE", "KM_FILE",
				"DEVICE_ID_PATH", "DB_CONFIG_FILE",
			)),
			(sql, (
				"BASE_DIR", "DB_PATH", "ENTRADAS_PE", "ENTRADAS_PS", "GPS_FILE",
				"SERVER_STATUS", "DEVICE_ID_PATH",
			)),
		):
			for name in names:
				self.original[(module, name)] = getattr(module, name)
		gpio.ENTRADAS_PE = os.path.join(self.directory, "pe.txt")
		gpio.ENTRADAS_PS = os.path.join(self.directory, "ps.txt")
		gpio.PREDIO_FILE = os.path.join(self.directory, "en_predio.txt")
		webservice.ENTRADAS_PE = gpio.ENTRADAS_PE
		webservice.ENTRADAS_PS = gpio.ENTRADAS_PS
		webservice.PREDIO_FILE = gpio.PREDIO_FILE
		webservice.GPS_FILE = os.path.join(self.directory, "gps.txt")
		webservice.KM_FILE = os.path.join(self.directory, "km.txt")
		webservice.DEVICE_ID_PATH = os.path.join(self.directory, "device_id.txt")
		webservice.DB_CONFIG_FILE = os.path.join(self.directory, "sos_db.txt")
		sql.BASE_DIR = self.directory
		sql.DB_PATH = os.path.join(self.directory, "backup.db")
		sql.ENTRADAS_PE = gpio.ENTRADAS_PE
		sql.ENTRADAS_PS = gpio.ENTRADAS_PS
		sql.GPS_FILE = webservice.GPS_FILE
		sql.SERVER_STATUS = os.path.join(self.directory, "serverstatus.txt")
		sql.DEVICE_ID_PATH = webservice.DEVICE_ID_PATH

	def tearDown(self):
		for (module, name), value in self.original.items():
			setattr(module, name, value)

	def escribir(self, path, data):
		with open(path, "w") as handle:
			handle.write(data)

	def test_la_transmision_sin_respuesta_se_confirma(self):
		params = (
			"2026-11-18 16:43:59", "9d623d49", "9.904499", "-84.127016", "0.071",
			"0", "0", "14", "85", 30092.5, "0", "0", "0", "0",
		)
		self.assertEqual(
			webservice.texto_transmision(params),
			"Transmision enviada 2026-11-18 16:43:59 9.904499,-84.127016 vel 0.071",
		)

	def test_cero_y_uno_del_servidor(self):
		self.assertFalse(webservice.interpretar_predio(0))
		self.assertTrue(webservice.interpretar_predio(1))
		self.assertTrue(webservice.interpretar_predio("1"))
		self.assertIsNone(webservice.interpretar_predio(None))
		self.assertIsNone(webservice.interpretar_predio("x"))

	def test_sin_coordenadas_no_cambia_el_estado(self):
		self.escribir(webservice.GPS_FILE, "Sin conexion con gps")
		self.escribir(webservice.PREDIO_FILE, "1\n")
		self.assertIsNone(webservice.coordenadas_actuales())
		webservice.actualizar_predio()
		with open(webservice.PREDIO_FILE, "r") as handle:
			self.assertEqual(handle.read().strip(), "1")

	def test_guarda_el_resultado_de_esEnPredio(self):
		self.escribir(webservice.GPS_FILE, "Latitud:9.93,Longitud: -84.08,Velocidad: 0")
		llamadas = []

		def consultar():
			llamadas.append(webservice.coordenadas_actuales())
			return True

		original = webservice.consultar_predio
		webservice.consultar_predio = consultar
		try:
			webservice.actualizar_predio()
		finally:
			webservice.consultar_predio = original
		self.assertEqual(llamadas, [("9.93", "-84.08")])
		with open(webservice.PREDIO_FILE, "r") as handle:
			self.assertEqual(handle.read().strip(), "1")

	def test_fuera_de_predio_sigue_el_contador_actual(self):
		self.escribir(gpio.ENTRADAS_PE, "GeneralEntradasPe: 4$$GeneralSalidasPe: 2$$")
		gpio.incremeta_entrada_pe()
		with open(gpio.ENTRADAS_PE, "r") as handle:
			texto = handle.read()
		self.assertEqual(webservice.get_entradas_pe(), 5)
		self.assertEqual(webservice.get_salidas_pe(), 2)
		self.assertEqual(webservice.get_entradas_pe_predio(), 0)
		self.assertEqual(webservice.get_salidas_pe_predio(), 0)
		self.assertIn("GeneralEntradasPe: 5$$", texto)

	def test_un_archivo_vacio_no_borra_la_copia(self):
		self.escribir(gpio.ENTRADAS_PE, "GeneralEntradasPe: 142$$GeneralSalidasPe: 116$$")
		gpio.proteger_contadores()
		self.escribir(gpio.ENTRADAS_PE, "")
		gpio.incremeta_entrada_pe()
		self.assertEqual(webservice.get_entradas_pe(), 143)
		self.assertEqual(webservice.get_salidas_pe(), 116)
		with open(gpio.ENTRADAS_PE, "r") as handle:
			self.assertIn("GeneralEntradasPe: 143$$", handle.read())

	def test_un_cero_no_reinicia_el_total(self):
		self.escribir(gpio.ENTRADAS_PE, "GeneralEntradasPe: 142$$GeneralSalidasPe: 116$$")
		gpio.proteger_contadores()
		self.escribir(gpio.ENTRADAS_PE, "GeneralEntradasPe: 0$$GeneralSalidasPe: 0$$")
		gpio.proteger_contadores()
		self.assertEqual(webservice.get_entradas_pe(), 142)
		self.assertEqual(webservice.get_salidas_pe(), 116)
		gpio.incremeta_entrada_pe()
		self.assertEqual(webservice.get_entradas_pe(), 143)
		with open(gpio.ruta_ultimo(gpio.ENTRADAS_PE), "r") as handle:
			copia = handle.read()
		self.assertIn("GeneralEntradasPe: 143$$", copia)
		self.assertIn("GeneralSalidasPe: 116$$", copia)

	def test_un_archivo_ilegible_no_se_reescribe(self):
		self.escribir(gpio.ENTRADAS_PE, "archivo danado")
		gpio.incremeta_entrada_pe()
		with open(gpio.ENTRADAS_PE, "r") as handle:
			self.assertEqual(handle.read(), "archivo danado")

	def test_en_predio_cuenta_aparte_y_conserva_el_anterior(self):
		self.escribir(gpio.PREDIO_FILE, "1\n")
		self.escribir(gpio.ENTRADAS_PE, "GeneralEntradasPe: 4$$GeneralSalidasPe: 2$$")
		gpio.incremeta_entrada_pe()
		gpio.incremeta_salidas_ps()
		self.assertEqual(webservice.get_entradas_pe(), 4)
		self.assertEqual(webservice.get_salidas_pe(), 2)
		self.assertEqual(webservice.get_entradas_pe_predio(), 1)
		self.assertEqual(webservice.get_salidas_ps(), 0)
		self.assertEqual(webservice.get_salidas_ps_predio(), 1)
		self.escribir(gpio.PREDIO_FILE, "0\n")
		gpio.incremeta_entrada_pe()
		self.assertEqual(webservice.get_entradas_pe(), 5)
		self.assertEqual(webservice.get_entradas_pe_predio(), 1)

	def test_la_transmision_v5_lleva_los_ocho_contadores(self):
		self.assertEqual(webservice.CALL_TRANSMISION.count("%s"), 14)
		self.assertIn("insertarTranmision_v5", webservice.CALL_TRANSMISION)
		self.assertEqual(webservice.SQL_PREDIO, "SELECT esEnPredio(%s, %s)")
		self.escribir(webservice.DEVICE_ID_PATH, "abc12345")
		self.escribir(webservice.GPS_FILE, "Latitud:9.93,Longitud: -84.08,Velocidad: 12.5")
		self.escribir(webservice.KM_FILE, "3.5")
		self.escribir(
			gpio.ENTRADAS_PE,
			"GeneralEntradasPe: 4$$GeneralSalidasPe: 2$$GeneralEntradasPe_Predio: 8$$GeneralSalidasPe_Predio: 7$$",
		)
		self.escribir(
			gpio.ENTRADAS_PS,
			"GeneralEntradasPs: 6$$GeneralSalidasPs: 1$$GeneralEntradasPs_Predio: 3$$GeneralSalidasPs_Predio: 9$$",
		)
		params = webservice.parametros_transmision()
		self.assertEqual(len(params), 14)
		self.assertEqual(params[1], "abc12345")
		self.assertEqual(params[2], "9.93")
		self.assertEqual(params[3], "-84.08")
		self.assertEqual(params[4], "12.5")
		self.assertEqual(params[5:9], ("4", "2", "6", "1"))
		self.assertEqual(params[9], 3.5)
		self.assertEqual(params[10:], ("8", "7", "3", "9"))

	def test_el_respaldo_local_agrega_los_contadores_de_predio(self):
		con = sqlite3.connect(sql.DB_PATH)
		con.execute(
			"""CREATE TABLE monitoreo(
				Fecha DATETIME not null,
				DeviceId VARCHAR(50) not null,
				latitud FLOAT not null,
				longitud FLOAT not null,
				Velocidad FLOAT not null,
				GeneralEntradasPe INTEGER not null,
				GeneralSalidasPe INTEGER not null,
				GeneralEntradasPs INTEGER not null,
				GeneralSalidasPs INTEGER not null,
				SrvOnline VARCHAR(50) not null
			)"""
		)
		con.commit()
		con.close()
		sql.init_db()
		con = sqlite3.connect(sql.DB_PATH)
		columnas = [row[1] for row in con.execute("PRAGMA table_info(monitoreo)")]
		con.close()
		for nombre in sql.PREDIO_COLUMNS:
			self.assertIn(nombre, columnas)
		self.escribir(sql.DEVICE_ID_PATH, "abc12345")
		self.escribir(sql.GPS_FILE, "Latitud:9.93,Longitud: -84.08,Velocidad: 0")
		self.escribir(sql.SERVER_STATUS, "estado True")
		self.escribir(
			sql.ENTRADAS_PE,
			"GeneralEntradasPe: 4$$GeneralSalidasPe: 2$$GeneralEntradasPe_Predio: 8$$GeneralSalidasPe_Predio: 7$$",
		)
		self.escribir(
			sql.ENTRADAS_PS,
			"GeneralEntradasPs: 6$$GeneralSalidasPs: 1$$GeneralEntradasPs_Predio: 3$$GeneralSalidasPs_Predio: 9$$",
		)
		sql.save_data_sql()
		con = sqlite3.connect(sql.DB_PATH)
		fila = con.execute(
			"SELECT GeneralEntradasPe, GeneralEntradasPe_Predio, GeneralSalidasPs_Predio FROM monitoreo"
		).fetchone()
		con.close()
		self.assertEqual(fila, (4, 8, 9))


if __name__ == "__main__":
	unittest.main()
