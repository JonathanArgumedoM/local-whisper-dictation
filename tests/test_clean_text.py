import json
import unittest
from pathlib import Path

from src.dictation_app import clean_text


class CleanTextTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        config_path = Path(__file__).resolve().parents[1] / "config.json"
        cls.config = json.loads(config_path.read_text(encoding="utf-8"))

    def clean(self, text: str) -> str:
        config = {**self.config, "append_space": False, "prepend_space": False}
        return clean_text(text, config)

    def test_preserves_punto_de_venta(self) -> None:
        self.assertEqual(
            self.clean("Necesito revisar el punto de venta"),
            "Necesito revisar el punto de venta",
        )

    def test_preserves_phrase_case_and_plural(self) -> None:
        self.assertEqual(
            self.clean("Punto de venta y puntos de venta"),
            "Punto de venta y puntos de venta",
        )

    def test_standalone_punto_remains_a_punctuation_command(self) -> None:
        self.assertEqual(
            self.clean("Terminamos punto siguiente tema"),
            "Terminamos. siguiente tema",
        )

    def test_accented_and_capitalized_newline(self) -> None:
        for command in ("nueva línea", "nueva linea", "Nueva Línea", "NEW LINE"):
            with self.subTest(command=command):
                self.assertEqual(self.clean(f"Primera {command} segunda"), "Primera\nsegunda")

    def test_standalone_newline_preserves_formatting(self) -> None:
        for text in ("nueva línea", "Nueva línea.", "New line."):
            with self.subTest(text=text):
                self.assertEqual(self.clean(text), "\n")

    def test_newline_at_end_and_repeated_newlines(self) -> None:
        self.assertEqual(self.clean("Hola nueva línea"), "Hola\n")
        self.assertEqual(self.clean("nueva línea nueva línea"), "\n\n")

    def test_longer_commands_and_accents(self) -> None:
        self.assertEqual(self.clean("Lista dos puntos uno coma dos"), "Lista: uno, dos")
        self.assertEqual(self.clean("abrir paréntesis ejemplo cerrar paréntesis"), "(ejemplo)")

    def test_commands_do_not_replace_word_fragments(self) -> None:
        self.assertEqual(self.clean("La plataforma acompunto registra comas"), "La plataforma acompunto registra comas")

    def test_custom_terms_and_protected_phrase_work_with_newline(self) -> None:
        self.assertEqual(self.clean("travel desk nueva línea Punto de venta"), "TravelDesk\nPunto de venta")

    def test_empty_text_does_not_become_a_space(self) -> None:
        self.assertEqual(clean_text("  ", {**self.config, "prepend_space": True}), "")

    def test_default_spacing_does_not_change_newline(self) -> None:
        self.assertEqual(clean_text("Nueva línea.", self.config), "\n")


if __name__ == "__main__":
    unittest.main()
