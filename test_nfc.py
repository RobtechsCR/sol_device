import unittest

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


if __name__ == "__main__":
	unittest.main()
