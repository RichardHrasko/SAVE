from pathlib import Path

import numpy as np
import pandas as pd
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.collections import LineCollection
from matplotlib.colors import Normalize
from matplotlib.figure import Figure

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from data_loader import load_gps_track_profile, load_turn_radius_summary, normalize_stats_fields
from ui_theme import (
    ACCENT_WARM,
    APP_BG,
    BORDER,
    SURFACE_0,
    SURFACE_1,
    TEXT_MUTED,
    TEXT_PRIMARY,
    apply_dark_palette,
    inner_card_stylesheet,
    outer_card_stylesheet,
)


class GradientProfileCard(QFrame):
    def __init__(self, source_text: str):
        super().__init__()

        self.source_text = source_text
        self.profile = self._load_profile()
        self.max_profile_points = 2200
        self.ax = None
        self.default_xlim = None
        self.default_ylim = None
        self.pan_active = False
        self.pan_anchor = None
        self.pan_press_px = None
        self.pan_xlim = None
        self.pan_ylim = None

        self.setStyleSheet(inner_card_stylesheet())

        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 20, 22, 18)
        layout.setSpacing(8)

        eyebrow = QLabel("Terrain")
        eyebrow.setStyleSheet(
            """
            QLabel {
                color: """
            + ACCENT_WARM
            + """;
                font-size: 12px;
                font-weight: 700;
                letter-spacing: 0.08em;
                text-transform: uppercase;
                background: transparent;
                border: none;
            }
            """
        )
        layout.addWidget(eyebrow)

        title = QLabel("Gradient profile")
        title.setStyleSheet(
            """
            QLabel {
                color: """
            + TEXT_PRIMARY
            + """;
                font-size: 22px;
                font-weight: 700;
                background: transparent;
                border: none;
            }
            """
        )
        layout.addWidget(title)

        subtitle = QLabel("Distance vs elevation, colored by gradient")
        subtitle.setStyleSheet(
            """
            QLabel {
                color: """
            + TEXT_MUTED
            + """;
                font-size: 13px;
                background: transparent;
                border: none;
            }
            """
        )
        layout.addWidget(subtitle)

        self.figure = Figure(facecolor=SURFACE_1)
        self.canvas = FigureCanvas(self.figure)
        self.canvas.setMinimumHeight(250)
        self.canvas.setStyleSheet("background: transparent; border: none;")
        layout.addWidget(self.canvas)

        self.canvas.mpl_connect("scroll_event", self._on_scroll)
        self.canvas.mpl_connect("button_press_event", self._on_button_press)
        self.canvas.mpl_connect("motion_notify_event", self._on_mouse_move)
        self.canvas.mpl_connect("button_release_event", self._on_button_release)

        self._draw_profile()

    def _load_profile(self):
        if not self.source_text:
            return None
        try:
            return load_gps_track_profile(Path(self.source_text))
        except Exception:
            return None

    def _draw_profile(self):
        self.figure.clear()
        ax = self.figure.add_subplot(111)
        self.ax = ax
        ax.set_facecolor(SURFACE_0)
        ax.grid(True, color=BORDER, alpha=0.7, linewidth=0.8)
        ax.tick_params(colors=TEXT_PRIMARY, labelsize=10)

        for spine in ax.spines.values():
            spine.set_color(BORDER)

        ax.set_xlabel("distance [km]", color=TEXT_PRIMARY)
        ax.set_ylabel("elevation [m]", color=TEXT_PRIMARY)

        if self.profile is None or len(self.profile.distance_km) < 2:
            ax.text(
                0.5,
                0.5,
                "No GPS elevation profile available.",
                transform=ax.transAxes,
                ha="center",
                va="center",
                color=TEXT_PRIMARY,
                fontsize=12,
            )
            self.figure.subplots_adjust(left=0.08, right=0.98, top=0.93, bottom=0.20)
            self.default_xlim = tuple(ax.get_xlim())
            self.default_ylim = tuple(ax.get_ylim())
            self.canvas.draw_idle()
            return

        distance = np.asarray(self.profile.distance_km, dtype=float)
        altitude = np.asarray(self.profile.altitude_m, dtype=float)
        gradient = np.asarray(self.profile.gradient_pct, dtype=float)
        distance, altitude, gradient = self._decimate_profile(distance, altitude, gradient)

        points = np.column_stack((distance, altitude))
        segments = np.stack([points[:-1], points[1:]], axis=1)
        segment_gradient = 0.5 * (gradient[:-1] + gradient[1:])

        collection = LineCollection(
            segments,
            cmap="RdYlBu_r",
            norm=Normalize(vmin=-35.0, vmax=20.0),
            linewidths=4.8,
            capstyle="round",
        )
        collection.set_array(segment_gradient)
        ax.add_collection(collection)

        base_altitude = float(np.min(altitude)) - 4.0
        ax.fill_between(distance, altitude, base_altitude, color="#2a2d34", alpha=0.28)
        ax.plot(distance, altitude, color="#f5f9ff", linewidth=1.1, alpha=0.28)

        ax.set_xlim(float(distance[0]), float(distance[-1]))
        ax.set_ylim(base_altitude, float(np.max(altitude)) + 6.0)

        cbar = self.figure.colorbar(collection, ax=ax, pad=0.014, shrink=0.88)
        cbar.outline.set_edgecolor(BORDER)
        cbar.ax.tick_params(colors=TEXT_PRIMARY, labelsize=9)
        cbar.set_label("gradient [%]", color=TEXT_PRIMARY, fontsize=10)

        self.figure.subplots_adjust(left=0.075, right=0.94, top=0.94, bottom=0.20)
        self.default_xlim = tuple(ax.get_xlim())
        self.default_ylim = tuple(ax.get_ylim())
        self.canvas.draw_idle()

    def _zoom_limits(self, limits, center, scale):
        lower, upper = float(limits[0]), float(limits[1])
        center = float(center)
        new_lower = center - (center - lower) * scale
        new_upper = center + (upper - center) * scale
        if abs(new_upper - new_lower) < 1e-9:
            return limits
        return (new_lower, new_upper)

    def _on_scroll(self, event):
        if self.ax is None or event.inaxes is not self.ax or event.xdata is None or event.ydata is None:
            return
        scale = 0.85 if event.button == "up" else (1.0 / 0.85)
        self.ax.set_xlim(self._zoom_limits(self.ax.get_xlim(), event.xdata, scale))
        self.ax.set_ylim(self._zoom_limits(self.ax.get_ylim(), event.ydata, scale))
        self.canvas.draw_idle()

    def _on_button_press(self, event):
        if self.ax is None or event.inaxes is not self.ax:
            return
        if event.dblclick:
            if self.default_xlim is not None:
                self.ax.set_xlim(self.default_xlim)
            if self.default_ylim is not None:
                self.ax.set_ylim(self.default_ylim)
            self.canvas.draw_idle()
            return
        if event.button != 2:
            return
        if event.xdata is None or event.ydata is None:
            return

        self.pan_active = True
        self.pan_anchor = (float(event.xdata), float(event.ydata))
        self.pan_press_px = (event.x, event.y)
        self.pan_xlim = tuple(self.ax.get_xlim())
        self.pan_ylim = tuple(self.ax.get_ylim())

    def _on_mouse_move(self, event):
        if (
            not self.pan_active
            or self.ax is None
            or event.inaxes is not self.ax
            or event.xdata is None
            or event.ydata is None
            or self.pan_anchor is None
            or self.pan_press_px is None
            or self.pan_xlim is None
            or self.pan_ylim is None
        ):
            return

        dx_px = abs(float(event.x) - float(self.pan_press_px[0]))
        dy_px = abs(float(event.y) - float(self.pan_press_px[1]))
        if dx_px > 4 or dy_px > 4:
            self.canvas.setCursor(Qt.ClosedHandCursor)

        dx = float(event.xdata) - self.pan_anchor[0]
        dy = float(event.ydata) - self.pan_anchor[1]
        self.ax.set_xlim(self.pan_xlim[0] - dx, self.pan_xlim[1] - dx)
        self.ax.set_ylim(self.pan_ylim[0] - dy, self.pan_ylim[1] - dy)
        self.canvas.draw_idle()

    def _on_button_release(self, event):
        if event.button != 2:
            return
        self.pan_active = False
        self.pan_anchor = None
        self.pan_press_px = None
        self.pan_xlim = None
        self.pan_ylim = None
        self.canvas.unsetCursor()

    def _decimate_profile(self, distance, altitude, gradient):
        n = len(distance)
        if n <= self.max_profile_points:
            return distance, altitude, gradient

        idx = np.linspace(0, n - 1, self.max_profile_points).astype(int)
        idx = np.unique(idx)
        return distance[idx], altitude[idx], gradient[idx]


class StatItem(QFrame):
    def __init__(self, label_text: str, value_text: str = "-"):
        super().__init__()

        self.setMinimumHeight(112)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self.setStyleSheet(inner_card_stylesheet(16))

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(8)

        self.label = QLabel(label_text)
        self.label.setAlignment(Qt.AlignLeft | Qt.AlignTop)
        self.label.setStyleSheet(
            """
            QLabel {
                color: """
            + TEXT_MUTED
            + """;
                font-size: 13px;
                font-weight: 600;
                background: transparent;
                border: none;
            }
            """
        )

        self.value = QLabel(value_text)
        self.value.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self.value.setWordWrap(True)
        self.value.setStyleSheet(
            """
            QLabel {
                color: """
            + TEXT_PRIMARY
            + """;
                font-size: 30px;
                font-weight: 700;
                background: transparent;
                border: none;
            }
            """
        )

        layout.addWidget(self.label)
        layout.addWidget(self.value)
        layout.addStretch()

    def set_value(self, text: str):
        self.value.setText(text)


class GeneralOverviewPage(QWidget):
    def __init__(self, right=None, left=None, source_text=""):
        super().__init__()

        self.right = right
        self.left = left
        self.source_text = source_text
        self.session_name = Path(source_text).name if source_text else "Ride overview"
        self.stats_data = self._load_stats_from_csv()

        apply_dark_palette(self)

        root = QVBoxLayout(self)
        root.setContentsMargins(20, 20, 20, 20)
        root.setSpacing(0)

        card = QFrame()
        card.setStyleSheet(outer_card_stylesheet())
        card.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(30, 28, 30, 28)
        card_layout.setSpacing(22)

        header = QVBoxLayout()
        header.setSpacing(6)

        eyebrow = QLabel("Selected ride")
        eyebrow.setStyleSheet(
            """
            QLabel {
                color: """
            + ACCENT_WARM
            + """;
                font-size: 13px;
                font-weight: 700;
                letter-spacing: 0.08em;
                text-transform: uppercase;
                background: transparent;
                border: none;
            }
            """
        )
        header.addWidget(eyebrow)

        title = QLabel(self.session_name)
        title.setAlignment(Qt.AlignLeft | Qt.AlignTop)
        title.setStyleSheet(
            """
            QLabel {
                color: """
            + TEXT_PRIMARY
            + """;
                font-size: 56px;
                font-weight: 700;
                background: transparent;
                border: none;
            }
            """
        )
        header.addWidget(title)

        subtitle = QLabel("Core ride metrics and terrain profile from the selected exported ski session.")
        subtitle.setStyleSheet(
            """
            QLabel {
                color: """
            + TEXT_MUTED
            + """;
                font-size: 14px;
                background: transparent;
                border: none;
            }
            """
        )
        header.addWidget(subtitle)

        card_layout.addLayout(header)

        grid = QGridLayout()
        grid.setHorizontalSpacing(16)
        grid.setVerticalSpacing(16)

        stat_items = [
            "Max speed:",
            "Average speed:",
            "Max G:",
            "Average G:",
            "Distance:",
            "Elevation loss:",
            "Run count:",
            "Turn count:",
        ]

        self.stats = {}

        for index, text in enumerate(stat_items):
            item = StatItem(text, "-")
            self.stats[text] = item
            row = index // 4
            col = index % 4
            grid.addWidget(item, row, col)

        card_layout.addLayout(grid)

        self.gradient_profile = GradientProfileCard(self.source_text)
        card_layout.addWidget(self.gradient_profile)

        root.addWidget(card)

        self._fill_stats()

    def _load_stats_from_csv(self) -> dict:
        if not self.source_text:
            return {}

        file = Path(self.source_text) / "overall_stats.csv"
        if not file.exists():
            return {}

        try:
            df = pd.read_csv(file)
            if df.empty:
                return {}
            stats = normalize_stats_fields(df.iloc[0].to_dict())
            stats.update(load_turn_radius_summary(Path(self.source_text)))
            return normalize_stats_fields(stats)
        except Exception:
            return {}
    def set_stat(self, name: str, value: str):
        if name in self.stats:
            self.stats[name].set_value(value)

    def _fill_stats(self):
        s = self.stats_data

        self.set_stat("Max speed:", f"{s.get('maxspeed', 0):.2f} km/h")
        self.set_stat("Average speed:", f"{s.get('avrgspeed', 0):.2f} km/h")
        self.set_stat("Max G:", f"{s.get('maxG', 0):.2f}")
        self.set_stat("Average G:", f"{s.get('averageG', 0):.2f}")
        self.set_stat("Distance:", f"{s.get('distance', 0):.2f} km")
        self.set_stat("Elevation loss:", f"{s.get('elevationloss', 0):.0f} m")
        self.set_stat("Run count:", f"{int(s.get('runCount', 0))}")
        self.set_stat("Turn count:", f"{int(s.get('turnCount', 0))}")
