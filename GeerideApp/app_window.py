from pathlib import Path

from PySide6.QtCore import QObject, Qt, QThread, QTimer, Signal, Slot
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from data_loader import load_exported_ski_folder
from general_overview import GeneralOverviewPage
from interval_viewer import IntervalViewerPage
from playback_3d_viewer import Playback3DViewerPage
from playback_viewer import PlaybackViewerPage
from rpy_viewer import RPYViewerPage
from session_picker import SessionPickerPage
from ui_theme import (
    apply_dark_palette,
    nav_button_stylesheet,
    outer_card_stylesheet,
    status_chip_stylesheet,
    top_bar_frame_stylesheet,
)


class SessionLoadWorker(QObject):
    finished = Signal(object, object, str)
    failed = Signal(str)

    def __init__(self, session_path: str, swap_sensors: bool = False):
        super().__init__()
        self.session_path = session_path
        self.swap_sensors = bool(swap_sensors)

    @Slot()
    def run(self):
        try:
            right, left = load_exported_ski_folder(Path(self.session_path))
        except Exception as exc:
            self.failed.emit(str(exc))
            return

        if self.swap_sensors:
            right, left = left, right

        self.finished.emit(right, left, self.session_path)


class AppWindow(QMainWindow):
    HOME_INDEX = 0
    LOADING_INDEX = 1
    OVERVIEW_INDEX = 2
    RPY_INDEX = 3
    INTERVALS_INDEX = 4
    PLAYBACK_INDEX = 5
    MAP3D_INDEX = 6

    def __init__(self, export_root="", right=None, left=None, source_text=""):
        super().__init__()

        self.export_root = Path(export_root) if export_root else Path(source_text) if source_text else Path()
        self.right = right
        self.left = left
        self.source_text = source_text

        self.page_overview = None
        self.page_rpy = None
        self.page_intervals = None
        self.page_playback = None
        self.page_playback_3d = None
        self.loading_dots_frames = ["", ".", "..", "..."]
        self.loading_dots_index = 0
        self.loading_timer = QTimer(self)
        self.loading_timer.setInterval(260)
        self.loading_timer.timeout.connect(self._advance_loading_dots)
        self.load_thread = None
        self.load_worker = None
        self.swap_sensors = False

        self.assets_dir = Path(__file__).resolve().parent / "assets"
        self.logo_path = self._resolve_logo_path()
        self.icon_path = self._resolve_icon_path()
        self.brand_path = self._resolve_brand_path()

        self.setWindowTitle("SkiSense")
        if self.icon_path is not None:
            self.setWindowIcon(QIcon(str(self.icon_path)))
        elif self.logo_path is not None:
            self.setWindowIcon(QIcon(str(self.logo_path)))
        self.resize(1400, 900)

        apply_dark_palette(self)

        central = QWidget()
        self.setCentralWidget(central)

        root = QVBoxLayout(central)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(12)

        top_frame = QFrame()
        top_frame.setStyleSheet(top_bar_frame_stylesheet())
        top_layout = QHBoxLayout(top_frame)
        top_layout.setContentsMargins(12, 10, 12, 10)
        top_layout.setSpacing(10)

        brand_wrap = QFrame()
        brand_wrap.setStyleSheet(
            """
            QFrame {
                background: transparent;
                border: none;
            }
            """
        )
        brand_layout = QHBoxLayout(brand_wrap)
        brand_layout.setContentsMargins(0, 0, 8, 0)
        brand_layout.setSpacing(10)

        brand_icon = QLabel()
        brand_icon.setFixedSize(52, 52)
        brand_icon.setAlignment(Qt.AlignCenter)
        brand_icon.setStyleSheet(
            """
            QLabel {
                background: transparent;
                border: none;
                padding: 0px;
            }
            """
        )
        brand_source = self.brand_path or self.icon_path or self.logo_path
        if brand_source is not None:
            brand_pixmap = QPixmap(str(brand_source)).scaled(
                46,
                46,
                Qt.KeepAspectRatio,
                Qt.SmoothTransformation,
            )
            brand_icon.setPixmap(brand_pixmap)

        brand_text = QLabel("SkiSense")
        brand_text.setStyleSheet(
            """
            QLabel {
                color: #f2f3f5;
                font-size: 18px;
                font-weight: 800;
                letter-spacing: 1.4px;
                border: none;
            }
            """
        )

        brand_layout.addWidget(brand_icon)
        brand_layout.addWidget(brand_text)

        top_bar = QHBoxLayout()
        top_bar.setSpacing(10)

        self.btn_home = QPushButton("Home")
        self.btn_overview = QPushButton("Overview")
        self.btn_rpy = QPushButton("RPY Viewer")
        self.btn_intervals = QPushButton("Intervals")
        self.btn_playback = QPushButton("Playback")
        self.btn_playback_3d = QPushButton("Map")

        self.nav_buttons = [
            self.btn_home,
            self.btn_overview,
            self.btn_rpy,
            self.btn_intervals,
            self.btn_playback,
            self.btn_playback_3d,
        ]

        for btn in self.nav_buttons:
            btn.setFixedHeight(40)
            btn.setCheckable(True)
            btn.setStyleSheet(nav_button_stylesheet())

        top_bar.addWidget(self.btn_home)
        top_bar.addWidget(self.btn_overview)
        top_bar.addWidget(self.btn_rpy)
        top_bar.addWidget(self.btn_intervals)
        top_bar.addWidget(self.btn_playback)
        top_bar.addWidget(self.btn_playback_3d)
        top_bar.addStretch()

        self.session_chip = QLabel("No ride selected")
        self.session_chip.setStyleSheet(status_chip_stylesheet())
        self.session_chip.setMinimumWidth(170)
        self.session_chip.setAlignment(Qt.AlignCenter)

        top_layout.addWidget(brand_wrap, 0, Qt.AlignVCenter)
        top_layout.addLayout(top_bar, 1)
        top_layout.addWidget(self.session_chip)
        root.addWidget(top_frame)

        self.stack = QStackedWidget()
        root.addWidget(self.stack)

        self.page_home = SessionPickerPage(str(self.export_root))
        self.page_home.session_selected.connect(self._load_session)
        self.stack.addWidget(self.page_home)

        self.page_loading = self._build_loading_page()
        self.stack.addWidget(self.page_loading)

        self.btn_home.clicked.connect(lambda: self.switch_page(self.HOME_INDEX))
        self.btn_overview.clicked.connect(lambda: self.switch_page(self.OVERVIEW_INDEX))
        self.btn_rpy.clicked.connect(lambda: self.switch_page(self.RPY_INDEX))
        self.btn_intervals.clicked.connect(lambda: self.switch_page(self.INTERVALS_INDEX))
        self.btn_playback.clicked.connect(lambda: self.switch_page(self.PLAYBACK_INDEX))
        self.btn_playback_3d.clicked.connect(lambda: self.switch_page(self.MAP3D_INDEX))

        self._set_analysis_buttons_enabled(False)

        if self.right is not None or self.left is not None:
            self._build_analysis_pages()
            self._set_analysis_buttons_enabled(True)
            if self.source_text:
                self.session_chip.setText(Path(self.source_text).name)
            self.switch_page(self.OVERVIEW_INDEX)
        else:
            self.switch_page(self.HOME_INDEX)

    def _mapping_chip_text(self) -> str:
        return "S1->L  S2->R" if self.swap_sensors else "S1->R  S2->L"

    def _resolve_logo_path(self) -> Path | None:
        for name in ("geeride_logo.png", "geeride_logo.jpg", "geeride_logo.jpeg", "geeride_logo.svg"):
            candidate = self.assets_dir / name
            if candidate.exists():
                return candidate
        return None

    def _resolve_icon_path(self) -> Path | None:
        for name in ("geeride_icon.png", "geeride_icon.jpg", "geeride_icon.jpeg", "geeride_icon.svg"):
            candidate = self.assets_dir / name
            if candidate.exists():
                return candidate
        return None

    def _resolve_brand_path(self) -> Path | None:
        for name in ("geeride_brand.png", "geeride_brand.jpg", "geeride_brand.jpeg", "geeride_brand.svg"):
            candidate = self.assets_dir / name
            if candidate.exists():
                return candidate
        return None

    def _build_loading_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(40, 40, 40, 40)
        layout.setSpacing(12)

        layout.addStretch()

        card = QFrame()
        card.setMaximumWidth(560)
        card.setStyleSheet(outer_card_stylesheet(24))
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(28, 26, 28, 26)
        card_layout.setSpacing(8)

        eyebrow = QLabel("Preparing session")
        eyebrow.setAlignment(Qt.AlignCenter)
        eyebrow.setStyleSheet(
            """
            QLabel {
                color: #c8ad84;
                font-size: 13px;
                font-weight: 700;
                border: none;
            }
            """
        )
        card_layout.addWidget(eyebrow)

        title = QLabel("Loading ride")
        title.setStyleSheet(
            """
            QLabel {
                color: #eef3f7;
                font-size: 34px;
                font-weight: 700;
                border: none;
            }
            """
        )
        title.setAlignment(Qt.AlignCenter)
        card_layout.addWidget(title)

        self.loading_label = QLabel("Preparing session...")
        self.loading_label.setStyleSheet(
            """
            QLabel {
                color: #b8c5d1;
                font-size: 15px;
                border: none;
            }
            """
        )
        self.loading_label.setAlignment(Qt.AlignCenter)
        card_layout.addWidget(self.loading_label)

        self.loading_dots_label = QLabel("...")
        self.loading_dots_label.setAlignment(Qt.AlignCenter)
        self.loading_dots_label.setStyleSheet(
            """
            QLabel {
                color: #f2f3f5;
                font-size: 28px;
                font-weight: 700;
                letter-spacing: 4px;
                border: none;
            }
            """
        )
        card_layout.addWidget(self.loading_dots_label)

        layout.addWidget(card, 0, Qt.AlignHCenter)

        layout.addStretch()
        return page

    def _advance_loading_dots(self):
        self.loading_dots_index = (self.loading_dots_index + 1) % len(self.loading_dots_frames)
        if hasattr(self, "loading_dots_label"):
            self.loading_dots_label.setText(self.loading_dots_frames[self.loading_dots_index])

    def _start_loading_dots(self):
        self.loading_dots_index = 0
        if hasattr(self, "loading_dots_label"):
            self.loading_dots_label.setText(self.loading_dots_frames[self.loading_dots_index])
        self.loading_timer.start()

    def _stop_loading_dots(self):
        self.loading_timer.stop()
        if hasattr(self, "loading_dots_label"):
            self.loading_dots_label.setText("...")

    def _cleanup_loader(self):
        if self.load_thread is not None:
            self.load_thread.quit()
            self.load_thread.wait()
            self.load_thread.deleteLater()
            self.load_thread = None
        if self.load_worker is not None:
            self.load_worker.deleteLater()
            self.load_worker = None

    def _set_analysis_buttons_enabled(self, enabled: bool):
        for btn in [
            self.btn_overview,
            self.btn_rpy,
            self.btn_intervals,
            self.btn_playback,
            self.btn_playback_3d,
        ]:
            btn.setEnabled(enabled)

    def _clear_analysis_pages(self):
        while self.stack.count() > 2:
            widget = self.stack.widget(2)
            self.stack.removeWidget(widget)
            widget.deleteLater()

        self.page_overview = None
        self.page_rpy = None
        self.page_intervals = None
        self.page_playback = None
        self.page_playback_3d = None

    def _build_analysis_pages(self):
        self._clear_analysis_pages()

        self.page_overview = GeneralOverviewPage(
            right=self.right,
            left=self.left,
            source_text=self.source_text,
        )
        self.page_rpy = RPYViewerPage(
            right=self.right,
            left=self.left,
            source_text=self.source_text,
        )
        self.page_intervals = IntervalViewerPage(
            right=self.right,
            left=self.left,
            source_text=self.source_text,
        )
        self.page_playback = PlaybackViewerPage(
            right=self.right,
            left=self.left,
            source_text=self.source_text,
        )
        self.page_playback_3d = Playback3DViewerPage(
            right=self.right,
            left=self.left,
            source_text=self.source_text,
        )

        self.stack.addWidget(self.page_overview)
        self.stack.addWidget(self.page_rpy)
        self.stack.addWidget(self.page_intervals)
        self.stack.addWidget(self.page_playback)
        self.stack.addWidget(self.page_playback_3d)

    def _load_session(self, session_path: str, swap_sensors: bool = False):
        if self.load_thread is not None and self.load_thread.isRunning():
            return

        folder = Path(session_path)
        self.swap_sensors = bool(swap_sensors)

        self.loading_label.setText(f"Opening {folder.name}   |   {self._mapping_chip_text()}")
        self._set_analysis_buttons_enabled(False)
        self.switch_page(self.LOADING_INDEX)
        self.loading_dots_label.setText("")

        self.load_thread = QThread(self)
        self.load_worker = SessionLoadWorker(str(folder), swap_sensors=self.swap_sensors)
        self.load_worker.moveToThread(self.load_thread)

        self.load_thread.started.connect(self.load_worker.run)
        self.load_worker.finished.connect(self._finish_session_load)
        self.load_worker.failed.connect(self._fail_session_load)
        self.load_worker.finished.connect(self._cleanup_loader)
        self.load_worker.failed.connect(self._cleanup_loader)
        self.load_thread.start()

    @Slot(object, object, str)
    def _finish_session_load(self, right, left, session_path: str):
        folder = Path(session_path)

        self.loading_label.setText(f"Opening {folder.name}   |   {self._mapping_chip_text()}")
        self.right = right
        self.left = left
        self.source_text = str(folder)

        self._build_analysis_pages()
        self._set_analysis_buttons_enabled(True)
        self.setWindowTitle(f"SkiSense - {folder.name}")
        self.session_chip.setText(f"{folder.name}   |   {self._mapping_chip_text()}")
        self.switch_page(self.OVERVIEW_INDEX)

    @Slot(str)
    def _fail_session_load(self, error_text: str):
        self.switch_page(self.HOME_INDEX)
        QMessageBox.critical(self, "Session load error", error_text)

    def switch_page(self, index: int):
        if index >= self.stack.count():
            return

        if index not in (self.HOME_INDEX, self.LOADING_INDEX) and self.stack.count() <= 2:
            return

        self.stack.setCurrentIndex(index)

        if index == self.LOADING_INDEX:
            self._start_loading_dots()
        else:
            self._stop_loading_dots()

        self.btn_home.setChecked(index == self.HOME_INDEX)
        self.btn_overview.setChecked(index == self.OVERVIEW_INDEX)
        self.btn_rpy.setChecked(index == self.RPY_INDEX)
        self.btn_intervals.setChecked(index == self.INTERVALS_INDEX)
        self.btn_playback.setChecked(index == self.PLAYBACK_INDEX)
        self.btn_playback_3d.setChecked(index == self.MAP3D_INDEX)
        if index == self.HOME_INDEX:
            self.session_chip.setText("Choose ride")
        elif self.source_text:
            self.session_chip.setText(f"{Path(self.source_text).name}   |   {self._mapping_chip_text()}")
