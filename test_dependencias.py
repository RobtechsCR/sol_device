import os
import sys
import tempfile
import unittest

import data_device
import gpio
import gps
import nfc
import sql
import updater
import webservice


class DependenciasTest(unittest.TestCase):
	def setUp(self):
		self.modulos = (gps, gpio, sql, webservice, updater, nfc, data_device)
		for modulo in self.modulos:
			modulo._aviso_pendiente = None
			modulo._aviso_enviado = False
			modulo._importando = False

	def test_todos_los_scripts_omiten_wiring_y_evdev(self):
		for modulo in self.modulos:
			self.assertEqual(modulo.OMITIR_INSTALACION, {"wiringpi", "evdev"})
			self.assertEqual(modulo.ALIAS_PIP["serial"], "pyserial")
			self.assertEqual(modulo.CHATBOT_DB, "chatbot")
			self.assertEqual(modulo.DESTINO_AVISO, "50687465171")
			self.assertEqual(modulo.SISTEMA_AVISO, "SOL_DEVICE")
			self.assertTrue(modulo.SCRIPT_NOMBRE.endswith(".py"))

	def test_no_instala_si_el_modulo_ya_carga(self):
		def ejecutar(comando):
			raise AssertionError(comando)

		def original(nombre, globales, locales, fromlist, nivel):
			return "cargado"

		self.assertEqual(
			gps.importar_con_instalacion(original, "os", None, None, (), 0, ejecutar=ejecutar),
			"cargado",
		)

	def test_stdlib_y_omitidos_no_pasan_por_pip(self):
		self.assertFalse(gps.debe_instalar("os"))
		self.assertFalse(gps.debe_instalar("_wmi"))
		self.assertFalse(gps.debe_instalar("wiringpi"))
		self.assertFalse(gps.debe_instalar("evdev"))
		self.assertFalse(gps.debe_instalar("serial.tools", nivel=1))
		comandos = []

		def ejecutar(comando):
			comandos.append(comando)

		def original(nombre, globales, locales, fromlist, nivel):
			raise ImportError(nombre)

		for nombre in ("wiringpi", "evdev", "_wmi"):
			with self.assertRaises(ImportError):
				gps.importar_con_instalacion(
					original, nombre, None, None, (), 0, ejecutar=ejecutar
				)
		with self.assertRaises(ImportError):
			gps.importar_con_instalacion(
				original, "paquete.interno", None, None, (), 1, ejecutar=ejecutar
			)
		self.assertEqual(comandos, [])

	def test_serial_se_instala_como_pyserial(self):
		self.assertEqual(gps.paquete_pip("serial"), "pyserial")
		self.assertEqual(gps.paquete_pip("serial.tools.list_ports"), "pyserial")
		comandos = []

		def ejecutar(comando):
			comandos.append(list(comando))

		def original(nombre, globales, locales, fromlist, nivel):
			if not any(item[-1:] == ["pyserial"] for item in comandos):
				raise ImportError(nombre)
			return "ok"

		anterior = gps.debe_instalar
		gps.debe_instalar = lambda nombre, nivel=0: gps.modulo_raiz(nombre) == "serial"
		try:
			self.assertEqual(
				gps.importar_con_instalacion(
					original, "serial", None, None, (), 0, ejecutar=ejecutar, avisar=lambda mensaje: False
				),
				"ok",
			)
		finally:
			gps.debe_instalar = anterior
		self.assertIn([sys.executable, "-m", "pip", "install", "pyserial"], comandos)

	def test_un_modulo_nuevo_usa_su_propio_nombre(self):
		nombre = "sol_device_lib_zz"
		self.assertTrue(gps.debe_instalar(nombre))
		self.assertEqual(gps.paquete_pip(nombre), nombre)
		comandos = []

		def ejecutar(comando):
			comandos.append(list(comando))

		def original(n, globales, locales, fromlist, nivel):
			if not any(item[-1:] == [nombre] for item in comandos):
				raise ImportError(n)
			return "ok"

		self.assertEqual(
			gps.importar_con_instalacion(
				original, nombre, None, None, (), 0, ejecutar=ejecutar, avisar=lambda mensaje: False
			),
			"ok",
		)
		self.assertIn([sys.executable, "-m", "pip", "install", nombre], comandos)

	def test_sin_pip_instala_el_paquete_del_sistema(self):
		comandos = []

		def ejecutar(comando):
			comandos.append(list(comando))
			if "--version" in comando:
				raise OSError("no pip")

		gps.asegurar_pip(ejecutar)
		self.assertEqual(comandos[0][:4], [sys.executable, "-m", "pip", "--version"])
		self.assertEqual(comandos[1], ["apt-get", "install", "-y", "python3-pip"])

	def test_fallo_avisa_una_vez_y_reintenta_sin_cerrar(self):
		nombre = "sol_device_lib_zz"
		avisos = []
		esperas = []
		instalaciones = {"n": 0}

		def ejecutar(comando):
			if comando[-1] == "--version":
				return
			if comando[-1] == nombre:
				instalaciones["n"] += 1
				if instalaciones["n"] == 1:
					raise OSError("sin red")

		def original(n, globales, locales, fromlist, nivel):
			if instalaciones["n"] < 2:
				raise ImportError(n)
			return "ok"

		def avisar(mensaje):
			avisos.append(mensaje)
			return False

		resultado = gps.importar_con_instalacion(
			original,
			nombre,
			None,
			None,
			(),
			0,
			ejecutar=ejecutar,
			esperar=esperas.append,
			avisar=avisar,
		)
		self.assertEqual(resultado, "ok")
		self.assertEqual(esperas, [60])
		self.assertEqual(len(avisos), 1)
		self.assertIn("gps.py " + nombre, avisos[0])
		self.assertIn("sin red", avisos[0])

	def test_el_aviso_guarda_destino_estado_y_sistema(self):
		capturado = {}

		class Cursor(object):
			def execute(self, sql, params):
				capturado["sql"] = sql
				capturado["params"] = params

			def close(self):
				pass

		class Conexion(object):
			def cursor(self):
				return Cursor()

			def commit(self):
				capturado["commit"] = True

			def close(self):
				capturado["cerrada"] = True

		def conectar(config):
			capturado["config"] = config
			return Conexion()

		def importar(nombre, *args, **kwargs):
			return object()

		directorio = tempfile.mkdtemp()
		anterior = gps.SOS_DB_FILE
		gps.SOS_DB_FILE = os.path.join(directorio, "sos_db.txt")
		with open(gps.SOS_DB_FILE, "w") as handle:
			handle.write("host=10.0.0.8\nport=3307\nuser=sol\npassword=a=b\n")
		try:
			self.assertTrue(gps.enviar_aviso("gps.py lib: sin red", conectar=conectar, importar=importar))
		finally:
			gps.SOS_DB_FILE = anterior
		self.assertEqual(capturado["config"]["host"], "10.0.0.8")
		self.assertEqual(capturado["config"]["port"], 3307)
		self.assertEqual(capturado["config"]["password"], "a=b")
		self.assertEqual(capturado["config"]["database"], "chatbot")
		self.assertIn("mensajes_automaticos", capturado["sql"])
		self.assertEqual(
			capturado["params"],
			("50687465171", "gps.py lib: sin red", 0, "SOL_DEVICE"),
		)
		self.assertTrue(capturado["commit"])
		self.assertTrue(capturado["cerrada"])
		self.assertTrue(gps._aviso_enviado)
		self.assertIsNone(gps._aviso_pendiente)

	def test_un_import_ajeno_no_dispara_la_instalacion(self):
		self.assertFalse(gps.pedido_por_script())
		with self.assertRaises(ModuleNotFoundError):
			gps.gancho_import("sol_device_lib_zz")

	def test_crea_sos_db_con_las_credenciales_del_proyecto(self):
		directorio = tempfile.mkdtemp()
		anterior = gps.SOS_DB_FILE
		gps.SOS_DB_FILE = os.path.join(directorio, "sos_db.txt")
		try:
			config = gps.config_chatbot()
			with open(gps.SOS_DB_FILE, "r") as handle:
				texto = handle.read()
		finally:
			gps.SOS_DB_FILE = anterior
		self.assertEqual(config["user"], gps.SOS_DB_USER)
		self.assertEqual(config["password"], gps.SOS_DB_PASSWORD)
		self.assertEqual(config["host"], gps.SOS_DB_HOST)
		self.assertEqual(config["database"], "chatbot")
		self.assertIn("user=" + gps.SOS_DB_USER, texto)
		self.assertIn("database=sos", texto)
		anterior_ws = webservice.DB_CONFIG_FILE
		webservice.DB_CONFIG_FILE = os.path.join(directorio, "ws.txt")
		try:
			ws = webservice.db_config()
		finally:
			webservice.DB_CONFIG_FILE = anterior_ws
		self.assertEqual(ws["user"], webservice.SOS_DB_USER)
		self.assertEqual(ws["database"], "sos")

	def test_no_reemplaza_un_usuario_existente(self):
		directorio = tempfile.mkdtemp()
		ruta = os.path.join(directorio, "sos_db.txt")
		with open(ruta, "w") as handle:
			handle.write("host=10.0.0.8\nuser=sol\npassword=a=b\n")
		gps.asegurar_sos_db(ruta)
		with open(ruta, "r") as handle:
			texto = handle.read()
		self.assertIn("user=sol", texto)
		self.assertIn("password=a=b", texto)

	def test_sin_pymysql_el_aviso_queda_pendiente(self):
		def importar(nombre, *args, **kwargs):
			raise ImportError(nombre)

		self.assertFalse(gps.enviar_aviso("gps.py pymysql: sin red", importar=importar))
		self.assertEqual(gps._aviso_pendiente, "gps.py pymysql: sin red")
		self.assertFalse(gps._aviso_enviado)


if __name__ == "__main__":
	unittest.main()
