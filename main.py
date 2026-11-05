"""QR_Pro: генерация QR-кодов. Запуск: python main.py."""
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
import logging
import re

import qrcode
from qrcode.exceptions import DataOverflowError

BASE = Path(__file__).resolve().parent
LOGGER = logging.getLogger("qr_pro")


@dataclass
class Settings:
    """Параметры, общие для одиночной и пакетной обработки."""
    version: int | None = None
    size: int = 10
    correction: str = "M"
    foreground: str = "#000000"
    background: str = "#FFFFFF"

    def validate(self):
        """Проверяем настройки также при вызове из тестов или другого кода."""
        if self.version is not None and not 1 <= self.version <= 40:
            raise ValueError("Версия должна быть от 1 до 40.")
        if not 1 <= self.size <= 50:
            raise ValueError("Размер модуля должен быть от 1 до 50 пикселей.")
        if self.correction not in "LMQH" or len(self.correction) != 1:
            raise ValueError("Уровень коррекции: L, M, Q или H.")
        for color in (self.foreground, self.background):
            if not re.fullmatch(r"#[0-9a-fA-F]{6}", color):
                raise ValueError("Цвет задаётся в формате #RRGGBB.")
        if self.foreground.lower() == self.background.lower():
            raise ValueError("Цвета кода и фона должны различаться.")


def luminance(color):
    """Относительная яркость sRGB для предупреждения о контрасте."""
    channels = [int(color[i:i + 2], 16) / 255 for i in (1, 3, 5)]
    linear = [v / 12.92 if v <= .04045 else ((v + .055) / 1.055) ** 2.4
              for v in channels]
    return sum(v * w for v, w in zip(linear, (.2126, .7152, .0722)))


def create_image(text, settings):
    """Не обрезаем пробелы: содержимое QR должно точно совпадать с вводом."""
    if not text.strip():
        raise ValueError("Введите непустой текст.")
    settings.validate()
    levels = dict(zip("LMQH", (qrcode.constants.ERROR_CORRECT_L,
                              qrcode.constants.ERROR_CORRECT_M,
                              qrcode.constants.ERROR_CORRECT_Q,
                              qrcode.constants.ERROR_CORRECT_H)))
    qr = qrcode.QRCode(version=settings.version, box_size=settings.size,
                       error_correction=levels[settings.correction], border=4)
    qr.add_data(text.encode("utf-8"))
    try:
        # fit=False гарантирует, что фиксированная версия не изменится скрытно.
        qr.make(fit=settings.version is None)
    except DataOverflowError as exc:
        raise ValueError("Данные не помещаются: сократите текст или измените "
                         "версию/коррекцию.") from exc
    return qr.make_image(fill_color=settings.foreground,
                         back_color=settings.background)


def filename(value):
    """Исключаем пути, запрещённые символы и зарезервированные имена Windows."""
    value = value or datetime.now().strftime("qr_%Y%m%d_%H%M%S.png")
    if not value.lower().endswith(".png"):
        value += ".png"
    stem = value[:-4]
    if (not stem or stem.endswith((" ", "."))
            or re.search(r'[<>:"/\\|?*\x00-\x1f]', value)
            or re.fullmatch(r"CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9]",
                            stem.split(".")[0], re.I)):
        raise ValueError("Недопустимое имя файла Windows.")
    return value


def save(text, settings, folder, name=""):
    """Эксклюзивное открытие защищает существующие файлы от перезаписи."""
    image = create_image(text, settings)
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    original = Path(filename(name))
    index = 0
    while True:
        target = folder / (original.name if index == 0 else
                           f"{original.stem}_{index}.png")
        try:
            stream = target.open("xb")
            break
        except FileExistsError:
            index += 1
    try:
        with stream:
            image.save(stream, format="PNG")
    except Exception:
        # Удаляем только собственный незавершённый файл, не чужие результаты.
        target.unlink(missing_ok=True)
        raise
    LOGGER.info("Сохранено: %s", target.resolve())
    return target.resolve()


def batch(source, folder, settings):
    """Читаем построчно, ошибки данных не останавливают остальные строки."""
    counts = dict(processed=0, saved=0, skipped=0, errors=0)
    with Path(source).open(encoding="utf-8-sig") as stream:
        for number, line in enumerate(stream, 1):
            counts["processed"] += 1
            text = line.rstrip("\r\n")
            if not text.strip():
                counts["skipped"] += 1
                continue
            try:
                save(text, settings, folder, f"qr_line_{number}.png")
                counts["saved"] += 1
                LOGGER.info("Пакет: строка %s сохранена", number)
            except ValueError:
                counts["errors"] += 1
                LOGGER.warning("Пакет: ошибка данных в строке %s", number)
            except OSError:
                LOGGER.error("Пакет: ошибка записи в строке %s", number)
                raise
    return counts


class SafeFileHandler(logging.FileHandler):
    """При недоступности лога сообщаем пользователю без падения приложения."""
    def handleError(self, record):
        print("Не удалось записать сообщение в лог.")


def configure_logging():
    LOGGER.setLevel(logging.INFO)
    try:
        handler = SafeFileHandler(BASE / "qr_pro.log", encoding="utf-8")
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
        LOGGER.addHandler(handler)
    except OSError:
        print("Лог недоступен. Работа продолжится без файлового журнала.")
        LOGGER.addHandler(logging.NullHandler())


def main():
    """Цикл меню хранит введённые данные и настройки между операциями."""
    configure_logging()
    settings = Settings()
    text = ""
    while True:
        print(f"\nQR_Pro | {settings}")
        print("1 — Ввести текст/URL\n2 — Параметры\n3 — Создать и сохранить"
              "\n4 — Пакет из TXT\n0 — Выход")
        try:
            choice = input("Выбор: ").strip()
            if choice == "0":
                break
            if choice == "1":
                text = input("Текст или URL: ")
            elif choice == "2":
                version = input("Версия 1–40 (Enter — автоматически): ").strip()
                candidate = Settings(
                    int(version) if version else None,
                    int(input("Размер модуля 1–50: ")),
                    input("Коррекция L/M/Q/H: ").strip().upper(),
                    input("Цвет кода #RRGGBB: ").strip(),
                    input("Цвет фона #RRGGBB: ").strip())
                candidate.validate()
                a, b = sorted((luminance(candidate.foreground),
                               luminance(candidate.background)))
                if (b + .05) / (a + .05) < 4.5:
                    print("Предупреждение: низкий контраст, считывание затруднено.")
                settings = candidate
            elif choice in ("3", "4"):
                # Пустой ответ выбирает пример относительно папки программы,
                # независимо от текста пункта 1 и текущей папки терминала.
                source = None
                if choice == "4":
                    entered = input(
                        "Путь к TXT (Enter — examples/batch.txt): "
                    ).strip()
                    source = Path(entered) if entered else BASE / "examples" / "batch.txt"
                folder = input("Папка (Enter — output): ").strip() or BASE / "output"
                if choice == "3":
                    name = input("Имя PNG (Enter — автоматически): ").strip()
                    print("Сохранено:", save(text, settings, folder, name))
                else:
                    print("Исходный файл:", source.resolve())
                    print("Папка результатов:", Path(folder).resolve())
                    print("Итог пакета:", batch(source, folder, settings))
            else:
                print("Выберите существующий пункт меню.")
        except (ValueError, OSError, UnicodeError) as exc:
            # Лог не содержит введённый текст или содержимое ошибочной строки.
            LOGGER.error("Операция не выполнена: %s", type(exc).__name__)
            print("Ошибка:", exc)
        except (KeyboardInterrupt, EOFError):
            print("\nРабота завершена.")
            break


if __name__ == "__main__":
    main()
