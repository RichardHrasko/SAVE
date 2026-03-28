import sys
from pathlib import Path

from PySide6.QtWidgets import QApplication

from app_window import AppWindow


def main():
    app = QApplication(sys.argv)

    export_root = Path(r"C:\Users\risko\Desktop\CSV_export")
    window = AppWindow(export_root=str(export_root))
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
