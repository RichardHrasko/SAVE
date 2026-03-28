from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QVBoxLayout,
    QWidget,
)
import sys


class AnalysisTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 18)

        card = QFrame()
        card.setObjectName("analysisCard")
        card.setStyleSheet(
            """
            QFrame#analysisCard {
                background-color: #232323;
                border: 2px solid #505050;
                border-radius: 18px;
            }
            """
        )

        card_layout = QHBoxLayout(card)
        card_layout.setContentsMargins(28, 26, 28, 26)
        card_layout.setSpacing(36)

        left_col = QWidget()
        left_grid = QGridLayout(left_col)
        left_grid.setContentsMargins(0, 0, 0, 0)
        left_grid.setHorizontalSpacing(18)
        left_grid.setVerticalSpacing(18)

        left_title = QLabel("Analysis")
        left_title.setStyleSheet("color: #ffffff; font-size: 30px; font-weight: 700;")
        left_grid.addWidget(left_title, 0, 0, 1, 2)

        self.lbl_max_speed = self._metric_pair("Max speed")
        self.lbl_avg_speed = self._metric_pair("Average speed")
        self.lbl_max_g = self._metric_pair("Max G")
        self.lbl_avg_g = self._metric_pair("Average G")

        left_grid.addWidget(self.lbl_max_speed[0], 1, 0)
        left_grid.addWidget(self.lbl_max_speed[1], 1, 1)
        left_grid.addWidget(self.lbl_avg_speed[0], 2, 0)
        left_grid.addWidget(self.lbl_avg_speed[1], 2, 1)
        left_grid.addWidget(self.lbl_max_g[0], 3, 0)
        left_grid.addWidget(self.lbl_max_g[1], 3, 1)
        left_grid.addWidget(self.lbl_avg_g[0], 4, 0)
        left_grid.addWidget(self.lbl_avg_g[1], 4, 1)

        right_col = QWidget()
        right_grid = QGridLayout(right_col)
        right_grid.setContentsMargins(0, 58, 0, 0)
        right_grid.setHorizontalSpacing(18)
        right_grid.setVerticalSpacing(18)

        self.lbl_run_count = self._metric_pair("Run count")
        self.lbl_turn_count = self._metric_pair("Turn count")
        self.lbl_avg_turn_length = self._metric_pair("Average turn length")
        self.lbl_max_edge_angle = self._metric_pair("Max edge angle")
        self.lbl_avg_edge_angle = self._metric_pair("Average edge angle")
        self.lbl_time_in_lod = self._metric_pair("Time in LOD")

        right_grid.addWidget(self.lbl_run_count[0], 0, 0)
        right_grid.addWidget(self.lbl_run_count[1], 0, 1)
        right_grid.addWidget(self.lbl_turn_count[0], 1, 0)
        right_grid.addWidget(self.lbl_turn_count[1], 1, 1)
        right_grid.addWidget(self.lbl_avg_turn_length[0], 2, 0)
        right_grid.addWidget(self.lbl_avg_turn_length[1], 2, 1)
        right_grid.addWidget(self.lbl_max_edge_angle[0], 3, 0)
        right_grid.addWidget(self.lbl_max_edge_angle[1], 3, 1)
        right_grid.addWidget(self.lbl_avg_edge_angle[0], 4, 0)
        right_grid.addWidget(self.lbl_avg_edge_angle[1], 4, 1)
        right_grid.addWidget(self.lbl_time_in_lod[0], 5, 0)
        right_grid.addWidget(self.lbl_time_in_lod[1], 5, 1)

        card_layout.addWidget(left_col, 1)
        card_layout.addWidget(right_col, 1)

        layout.addWidget(card)
        layout.addStretch()

    def _metric_pair(self, name):
        label = QLabel(f"{name}:")
        label.setStyleSheet("color: #d7d7d7; font-size: 16px; font-weight: 600;")
        value = QLabel("—")
        value.setStyleSheet("color: #8f8f8f; font-size: 16px; font-weight: 500;")
        value.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        return label, value


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Analysis")
        self.resize(1100, 500)
        self._apply_dark_palette()
        self.setCentralWidget(AnalysisTab())

    def _apply_dark_palette(self):
        self.setStyleSheet(
            """
            QMainWindow, QWidget {
                background-color: #1e1e1e;
                color: #eaeaea;
            }
            """
        )

        pal = self.palette()
        pal.setColor(QPalette.Window, QColor("#1e1e1e"))
        pal.setColor(QPalette.WindowText, QColor("#eaeaea"))
        pal.setColor(QPalette.Base, QColor("#1e1e1e"))
        pal.setColor(QPalette.AlternateBase, QColor("#2b2b2b"))
        pal.setColor(QPalette.Text, QColor("#eaeaea"))
        pal.setColor(QPalette.Button, QColor("#2b2b2b"))
        pal.setColor(QPalette.ButtonText, QColor("#eaeaea"))
        self.setPalette(pal)


def main():
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
