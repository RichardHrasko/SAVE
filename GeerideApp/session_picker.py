from pathlib import Path

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from data_loader import list_export_sessions
from ui_theme import (
    ACCENT_WARM,
    TEXT_MUTED,
    TEXT_PRIMARY,
    apply_dark_palette,
    inner_card_stylesheet,
    neutral_button_stylesheet,
    outer_card_stylesheet,
    status_chip_stylesheet,
)


class SessionPickerPage(QWidget):
    session_selected = Signal(str, bool)

    def __init__(self, export_root: str):
        super().__init__()

        self.export_root = Path(export_root)
        self.sessions: list[Path] = []
        self.refresh_frames = ["Refreshing", "Refreshing.", "Refreshing..", "Refreshing..."]
        self.refresh_frame_index = 0
        self.refresh_animation_active = False
        self.swap_sensors = False
        self.refresh_timer = QTimer(self)
        self.refresh_timer.setInterval(120)
        self.refresh_timer.timeout.connect(self._advance_refresh_animation)

        apply_dark_palette(self)
        self._build_ui()
        self._populate_sessions()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(22, 22, 22, 22)
        root.setSpacing(0)

        card = QFrame()
        card.setStyleSheet(outer_card_stylesheet())
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(30, 28, 30, 28)
        card_layout.setSpacing(18)

        eyebrow = QLabel("Session selector")
        eyebrow.setStyleSheet(
            f"""
            QLabel {{
                color: {ACCENT_WARM};
                font-size: 13px;
                font-weight: 700;
                letter-spacing: 0.08em;
                text-transform: uppercase;
                border: none;
            }}
            """
        )
        card_layout.addWidget(eyebrow)

        title = QLabel("Choose ride")
        title.setStyleSheet(
            f"""
            QLabel {{
                color: {TEXT_PRIMARY};
                font-size: 52px;
                font-weight: 700;
                border: none;
            }}
            """
        )
        card_layout.addWidget(title)

        subtitle = QLabel("Pick the exported session folder you want to analyze.")
        subtitle.setStyleSheet(
            f"""
            QLabel {{
                color: {TEXT_MUTED};
                font-size: 14px;
                border: none;
            }}
            """
        )
        card_layout.addWidget(subtitle)

        self.root_label = QLabel(str(self.export_root))
        self.root_label.setWordWrap(True)
        self.root_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.root_label.setStyleSheet(status_chip_stylesheet())
        card_layout.addWidget(self.root_label)

        controls = QHBoxLayout()
        controls.setSpacing(8)

        self.btn_select_folder = QPushButton("Select folder")
        self.btn_select_folder.setStyleSheet(neutral_button_stylesheet())
        self.btn_select_folder.clicked.connect(self._choose_export_root)

        self.btn_refresh = QPushButton("Refresh")
        self.btn_refresh.setStyleSheet(neutral_button_stylesheet())
        self.btn_refresh.clicked.connect(self._animate_refresh_sessions)

        self.btn_open = QPushButton("Open ride")
        self.btn_open.setStyleSheet(neutral_button_stylesheet())
        self.btn_open.clicked.connect(self._emit_selected)

        self.btn_sensor_mapping = QPushButton("")
        self.btn_sensor_mapping.setCheckable(True)
        self.btn_sensor_mapping.setChecked(False)
        self.btn_sensor_mapping.setStyleSheet(neutral_button_stylesheet())
        self.btn_sensor_mapping.clicked.connect(self._toggle_sensor_mapping)

        controls.addWidget(self.btn_select_folder)
        controls.addWidget(self.btn_refresh)
        controls.addWidget(self.btn_open)
        controls.addWidget(self.btn_sensor_mapping)
        controls.addStretch()
        card_layout.addLayout(controls)

        self.mapping_label = QLabel("")
        self.mapping_label.setStyleSheet(status_chip_stylesheet())
        card_layout.addWidget(self.mapping_label)
        self._sync_sensor_mapping_button()

        list_frame = QFrame()
        list_frame.setStyleSheet(inner_card_stylesheet())
        list_layout = QVBoxLayout(list_frame)
        list_layout.setContentsMargins(16, 16, 16, 16)
        list_layout.setSpacing(10)

        self.list_label = QLabel("Available rides")
        self.list_label.setStyleSheet(
            f"""
            QLabel {{
                color: {TEXT_PRIMARY};
                font-size: 18px;
                font-weight: 700;
                border: none;
            }}
            """
        )
        list_layout.addWidget(self.list_label)

        helper = QLabel("Double-click or press Enter to open the selected ride.")
        helper.setStyleSheet(
            f"""
            QLabel {{
                color: {TEXT_MUTED};
                font-size: 12px;
                border: none;
            }}
            """
        )
        list_layout.addWidget(helper)

        self.session_list = QListWidget()
        self.session_list.setStyleSheet(
            """
            QListWidget {
                background-color: #181a1f;
                color: #eef1f5;
                border: 1px solid #3a3d45;
                border-radius: 14px;
                padding: 8px;
                font-size: 15px;
                outline: none;
            }
            QListWidget::item {
                background-color: #24262d;
                border: 1px solid #3a3d45;
                border-radius: 10px;
                padding: 12px 14px;
                margin: 4px 0px;
            }
            QListWidget::item:selected {
                background-color: #30343d;
                border: 1px solid #505560;
                color: #ffffff;
            }
            QListWidget::item:hover {
                background-color: #2a2d35;
            }
            """
        )
        self.session_list.itemDoubleClicked.connect(self._emit_item_selected)
        self.session_list.itemActivated.connect(self._emit_item_selected)
        self.session_list.itemSelectionChanged.connect(self._update_selection_state)
        list_layout.addWidget(self.session_list, 1)

        self.status_label = QLabel("")
        self.status_label.setWordWrap(True)
        self.status_label.setStyleSheet(
            f"""
            QLabel {{
                color: {TEXT_MUTED};
                font-size: 13px;
                border: none;
                padding-top: 2px;
            }}
            """
        )
        list_layout.addWidget(self.status_label)

        card_layout.addWidget(list_frame, 1)
        root.addWidget(card)

        self._update_selection_state()

    def _populate_sessions(self):
        self.sessions = list_export_sessions(self.export_root)
        self.session_list.clear()

        for session in self.sessions:
            item = QListWidgetItem(session.name)
            item.setData(Qt.UserRole, str(session))
            self.session_list.addItem(item)

        if self.sessions:
            self.session_list.setCurrentRow(0)
            self.status_label.setText(
                f"Found {len(self.sessions)} ride folder(s) in {self.export_root.name}."
            )
        else:
            self.status_label.setText(
                "No ride folders found. Put exported sessions into subfolders under this root and press Refresh."
            )

        self._update_selection_state()

    def _advance_refresh_animation(self):
        self.refresh_frame_index = (self.refresh_frame_index + 1) % len(self.refresh_frames)
        self.btn_refresh.setText(self.refresh_frames[self.refresh_frame_index])

    def _finish_refresh_animation(self):
        self.refresh_timer.stop()
        self.refresh_animation_active = False
        self.btn_refresh.setEnabled(True)
        self.btn_refresh.setText("Refresh")

    def _run_refresh_sessions(self):
        self._populate_sessions()
        QTimer.singleShot(480, self._finish_refresh_animation)

    def _animate_refresh_sessions(self):
        if self.refresh_animation_active:
            return

        self.refresh_animation_active = True
        self.refresh_frame_index = 0
        self.btn_refresh.setEnabled(False)
        self.btn_refresh.setText(self.refresh_frames[self.refresh_frame_index])
        self.refresh_timer.start()
        QTimer.singleShot(0, self._run_refresh_sessions)

    def _choose_export_root(self):
        folder = QFileDialog.getExistingDirectory(
            self,
            "Select export root",
            str(self.export_root) if self.export_root else str(Path.cwd()),
        )
        if not folder:
            return

        self.export_root = Path(folder)
        self.root_label.setText(str(self.export_root))
        self._animate_refresh_sessions()

    def _update_selection_state(self):
        has_selection = self.session_list.currentItem() is not None
        self.btn_open.setEnabled(has_selection)

    def _sync_sensor_mapping_button(self):
        if self.swap_sensors:
            self.btn_sensor_mapping.setText("Sensor 1 = Left   Sensor 2 = Right")
            if hasattr(self, "mapping_label"):
                self.mapping_label.setText("Current mapping: Sensor 1 -> Left ski, Sensor 2 -> Right ski")
        else:
            self.btn_sensor_mapping.setText("Sensor 1 = Right   Sensor 2 = Left")
            if hasattr(self, "mapping_label"):
                self.mapping_label.setText("Current mapping: Sensor 1 -> Right ski, Sensor 2 -> Left ski")

    def _toggle_sensor_mapping(self):
        self.swap_sensors = self.btn_sensor_mapping.isChecked()
        self._sync_sensor_mapping_button()
        self.status_label.setText(
            "Sensor mapping changed. Open a ride to apply the new left/right assignment."
        )

    def _emit_selected(self):
        item = self.session_list.currentItem()
        if item is None:
            return
        self._emit_item_selected(item)

    def _emit_item_selected(self, item):
        if item is None:
            return
        session_path = item.data(Qt.UserRole)
        if session_path:
            self.session_selected.emit(str(session_path), self.swap_sensors)
