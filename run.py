"""Запуск с локальными зависимостями, установленными в .deps."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent / ".deps"))
from main import main
if __name__ == "__main__":
    main()
