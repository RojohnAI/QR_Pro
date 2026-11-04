"""Проверки изолированы во временной папке и не меняют результаты пользователя."""
import tempfile
import unittest
from unittest.mock import patch

from pathlib import Path
import run  # Подключает локальные зависимости.
import main as app
from main import Settings, batch, create_image, filename, save

class Tests(unittest.TestCase):
    def test_validation(self):
        for data in ("", "   "):
            with self.assertRaises(ValueError):
                create_image(data, Settings())
        for name in ("CON", "a/b", "bad?"):
            with self.assertRaises(ValueError):
                filename(name)
        with self.assertRaises(ValueError):
            Settings(foreground="#ffffff").validate()
        with self.assertRaises(ValueError):
            create_image("я" * 1000, Settings(version=1))

    def test_save_and_batch(self):
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp)
            first = save("Привет", Settings(), folder, "example")
            second = save("Привет", Settings(), folder, "example")
            self.assertNotEqual(first, second)
            self.assertEqual(first.read_bytes()[:8], b"\x89PNG\r\n\x1a\n")
            source = folder / "input.txt"
            source.write_text("Привет\n\n  текст  \n" + "я" * 1000,
                              encoding="utf-8-sig")
            result = batch(source, folder, Settings(version=2))
            self.assertEqual(result, dict(processed=4, saved=2, skipped=1, errors=1))

    def test_menu_batch_default_after_text(self):
        """Enter выбирает TXT даже после ввода одиночного текста и смены cwd."""
        import os
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            (base / "examples").mkdir()
            (base / "examples" / "batch.txt").write_text(
                "Первая строка\nВторая строка\n", encoding="utf-8"
            )
            previous = Path.cwd()
            try:
                os.chdir(base.parent)
                with patch.object(app, "BASE", base), \
                     patch.object(app, "configure_logging"), \
                     patch("builtins.input", side_effect=[
                         "1", "Одиночный текст", "4", "", "", "0"
                     ]), patch("builtins.print"):
                    app.main()
            finally:
                os.chdir(previous)
            self.assertEqual(len(list((base / "output").glob("*.png"))), 2)

    def test_levels(self):
        for level in "LMQH":
            image = create_image("https://example.org", Settings(correction=level))
            self.assertGreater(image.size[0], 0)

if __name__ == "__main__":
    unittest.main()

