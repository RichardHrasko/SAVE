from pathlib import Path

import numpy as np

from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.backends.backend_qtagg import NavigationToolbar2QT as NavigationToolbar
from matplotlib.collections import LineCollection
from matplotlib.figure import Figure

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from data_loader import DataLoadError, load_gps_path, load_turn_radius_segments, load_turn_radius_timeseries
from scalar_color import (
    GPS_ACCURACY_CMAP,
    SCALAR_CMAP,
    build_gps_accuracy_norm,
    build_shared_scalar_norm,
    build_turn_radius_norm,
    build_turn_radius_series_norm,
    combine_scalar_series,
    get_scalar_data,
    get_gps_accuracy_data,
    interpolate_scalar_to_time,
    lookup_turn_radius_at_time,
    lookup_turn_radius_series_at_time,
    sample_turn_radius_segments,
    sample_turn_radius_series,
)
from ui_theme import (
    cursor_button_stylesheet,
    info_label_stylesheet,
    neutral_button_stylesheet,
    ski_toggle_stylesheet,
    toolbar_stylesheet,
    top_bar_frame_stylesheet,
)


class RPYViewerPage(QWidget):
    LEFT_COLOR = "#ff9a3d"
    RIGHT_COLOR = "#5aa9ff"

    def __init__(self, right=None, left=None, source_text=""):
        super().__init__()

        self.right = right
        self.left = left
        self.source_text = source_text

        self.show_right = right is not None
        self.show_left = left is not None

        self.max_points = 4000
        self.max_track_points = 1800
        self.use_full_resolution = False
        self.track_view_mode = "2d"

        self.color_modes = ["fixed", "speed", "acc", "gyro", "radius"]
        self.color_mode_index = 0
        self.color_mode = self.color_modes[self.color_mode_index]
        self.hover_cursor_enabled = False

        self.cbar = None
        self.cbar_ax = None
        self.locked_hover_info = None
        self.locked_value_annotation = None
        self.locked_point_markers = []
        self.locked_track_marker = None
        self.axes_default_limits = {}
        self.plot_pan_active = False
        self.plot_pan_axis = None
        self.plot_pan_press = None
        self.plot_pan_press_px = None
        self.plot_pan_xlim = None
        self.plot_pan_ylim = None
        self.plot_moved = False
        self.skip_left_release = False
        self.gps_path = None
        self.turn_radius_segments = []
        self.turn_radius_series = None
        self.gps_load_error = ""
        self._load_gps_path()

        self.setWindowTitle("RPY Viewer")
        self.resize(1400, 900)

        self._apply_dark_palette()

        root = QVBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(8)

        controls_frame = QFrame()
        controls_frame.setStyleSheet(top_bar_frame_stylesheet(14))
        controls_layout = QHBoxLayout(controls_frame)
        controls_layout.setContentsMargins(12, 10, 12, 10)
        controls_layout.setSpacing(8)

        self.btn_left = QPushButton("L")
        self.btn_left.setCheckable(True)
        self.btn_left.setChecked(self.show_left)
        self.btn_left.setFixedHeight(34)
        self.btn_left.setFixedWidth(52)
        self.btn_left.clicked.connect(self._toggle_left)
        self.btn_left.setStyleSheet(ski_toggle_stylesheet(self.LEFT_COLOR))

        self.btn_right = QPushButton("R")
        self.btn_right.setCheckable(True)
        self.btn_right.setChecked(self.show_right)
        self.btn_right.setFixedHeight(34)
        self.btn_right.setFixedWidth(52)
        self.btn_right.clicked.connect(self._toggle_right)
        self.btn_right.setStyleSheet(ski_toggle_stylesheet(self.RIGHT_COLOR, "#ffffff"))

        self.btn_color_mode = QPushButton("Fixed")
        self.btn_color_mode.setFixedHeight(34)
        self.btn_color_mode.setMinimumWidth(84)
        self.btn_color_mode.clicked.connect(self._cycle_color_mode)
        self.btn_color_mode.setStyleSheet(neutral_button_stylesheet())

        self.btn_hover_cursor = QPushButton("Cursor")
        self.btn_hover_cursor.setCheckable(True)
        self.btn_hover_cursor.setChecked(False)
        self.btn_hover_cursor.setFixedHeight(34)
        self.btn_hover_cursor.setMinimumWidth(76)
        self.btn_hover_cursor.clicked.connect(self._toggle_hover_cursor)
        self.btn_hover_cursor.setStyleSheet(cursor_button_stylesheet())

        self.btn_resolution = QPushButton("Low res")
        self.btn_resolution.setFixedHeight(34)
        self.btn_resolution.setMinimumWidth(96)
        self.btn_resolution.clicked.connect(self._toggle_resolution)
        self.btn_resolution.setStyleSheet(neutral_button_stylesheet())

        self.coord_label = QLabel("fixed   t: -   deg: -")
        self.coord_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.coord_label.setMinimumWidth(390)
        self.coord_label.setStyleSheet(info_label_stylesheet())

        controls_layout.addWidget(self.btn_left)
        controls_layout.addWidget(self.btn_right)
        controls_layout.addSpacing(4)
        controls_layout.addWidget(self.btn_color_mode)
        controls_layout.addWidget(self.btn_hover_cursor)
        controls_layout.addWidget(self.btn_resolution)
        controls_layout.addStretch()
        controls_layout.addWidget(self.coord_label)

        root.addWidget(controls_frame)

        self.figure = Figure(facecolor="#1e1e1e")
        self.canvas = FigureCanvas(self.figure)
        self.canvas.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        self.toolbar = NavigationToolbar(self.canvas, self)

        for action in list(self.toolbar.actions()):
            text = action.text().strip().lower()
            if text in {"subplots", "customize", "configure subplots"}:
                self.toolbar.removeAction(action)

        self.toolbar.set_message = lambda s: None
        self.toolbar.setStyleSheet(toolbar_stylesheet())

        root.addWidget(self.toolbar)
        root.addWidget(self.canvas)

        grid = self.figure.add_gridspec(
            3,
            2,
            width_ratios=[4.8, 1.35],
            wspace=0.12,
            hspace=0.18,
        )
        self.ax_roll = self.figure.add_subplot(grid[0, 0])
        self.ax_pitch = self.figure.add_subplot(grid[1, 0], sharex=self.ax_roll)
        self.ax_yaw = self.figure.add_subplot(grid[2, 0], sharex=self.ax_roll)
        self.ax_track = self.figure.add_subplot(grid[:, 1])
        self.rpy_axes = [self.ax_roll, self.ax_pitch, self.ax_yaw]
        self.axes = [self.ax_roll, self.ax_pitch, self.ax_yaw]
        self.hover_lines = []

        self._style_axes()
        self._plot_all()

        self.canvas.mpl_connect("scroll_event", self._on_plot_scroll)
        self.canvas.mpl_connect("button_press_event", self._on_plot_button_press)
        self.canvas.mpl_connect("motion_notify_event", self._on_mouse_move)
        self.canvas.mpl_connect("button_release_event", self._on_plot_button_release)

    def _load_gps_path(self):
        if not self.source_text:
            return

        try:
            self.gps_path = load_gps_path(Path(self.source_text))
            self.turn_radius_segments = load_turn_radius_segments(Path(self.source_text))
            self.turn_radius_series = load_turn_radius_timeseries(Path(self.source_text))
        except DataLoadError as exc:
            self.gps_load_error = str(exc)
        except Exception as exc:
            self.gps_load_error = f"Failed to load GPS trajectory: {exc}"

    def _apply_dark_palette(self):
        self.setStyleSheet(
            """
            QMainWindow, QWidget {
                background-color: #1e1e1e;
                color: #eaeaea;
            }
            QPushButton {
                background-color: #2b2b2b;
                color: #eaeaea;
                border: 1px solid #4a4a4a;
                border-radius: 6px;
                padding: 6px 14px;
                font-size: 13px;
                font-weight: 600;
            }
            QPushButton:hover {
                background-color: #3a3a3a;
            }
            QPushButton:checked {
                background-color: #4f8cff;
                border: 1px solid #4f8cff;
                color: white;
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

    def _style_axes(self):
        for ax in self.rpy_axes + [self.ax_track]:
            ax.set_facecolor("#1e1e1e")
            ax.grid(True, color="#3a3a3a", alpha=0.9, linewidth=0.8)
            ax.tick_params(colors="#d8d8d8", labelsize=10)
            for spine in ax.spines.values():
                spine.set_color("#555555")

        self.ax_roll.set_ylabel("roll [deg]", color="#eaeaea")
        self.ax_pitch.set_ylabel("pitch [deg]", color="#eaeaea")
        self.ax_yaw.set_ylabel("yaw [deg]", color="#eaeaea")
        self.ax_yaw.set_xlabel("time [s]", color="#eaeaea")
        self.ax_track.set_ylabel("")
        self.ax_track.set_xlabel("")
        self.ax_track.set_title("")
        self.ax_track.ticklabel_format(style="plain", useOffset=False, axis="both")
        self.ax_track.grid(False)
        self.ax_track.set_xticks([])
        self.ax_track.set_yticks([])

    def _store_default_limits(self):
        self.axes_default_limits = {
            ax: (tuple(ax.get_xlim()), tuple(ax.get_ylim()))
            for ax in self.rpy_axes + [self.ax_track]
        }

    def _zoom_limits(self, limits, center, scale):
        lower, upper = float(limits[0]), float(limits[1])
        center = float(center)
        new_lower = center - (center - lower) * scale
        new_upper = center + (upper - center) * scale
        if abs(new_upper - new_lower) < 1e-9:
            return limits
        return (new_lower, new_upper)

    def _reset_axis_view(self, axis):
        if axis in self.rpy_axes:
            for ax in self.rpy_axes:
                limits = self.axes_default_limits.get(ax)
                if limits is None:
                    continue
                ax.set_xlim(limits[0])
                ax.set_ylim(limits[1])
        else:
            limits = self.axes_default_limits.get(axis)
            if limits is not None:
                axis.set_xlim(limits[0])
                axis.set_ylim(limits[1])

    def _on_plot_scroll(self, event):
        if event.inaxes not in (self.rpy_axes + [self.ax_track]):
            return
        if event.xdata is None or event.ydata is None:
            return

        scale = 0.85 if event.button == "up" else (1.0 / 0.85)
        if event.inaxes in self.rpy_axes:
            new_xlim = self._zoom_limits(self.ax_roll.get_xlim(), event.xdata, scale)
            for ax in self.rpy_axes:
                ax.set_xlim(new_xlim)
            event.inaxes.set_ylim(self._zoom_limits(event.inaxes.get_ylim(), event.ydata, scale))
        else:
            event.inaxes.set_xlim(self._zoom_limits(event.inaxes.get_xlim(), event.xdata, scale))
            event.inaxes.set_ylim(self._zoom_limits(event.inaxes.get_ylim(), event.ydata, scale))
        self.canvas.draw_idle()

    def _on_plot_button_press(self, event):
        if event.button == 3:
            self.locked_hover_info = None
            self._hide_locked_marker()
            self._hide_locked_annotation()
            if not self.hover_cursor_enabled:
                self._hide_hover_lines()
            self.coord_label.setText(f"{self._display_color_mode().lower()}   t: -   deg: -")
            self.canvas.draw_idle()
            return

        if event.button == 1:
            if event.inaxes in (self.rpy_axes + [self.ax_track]) and event.dblclick:
                self._reset_axis_view(event.inaxes)
                self.skip_left_release = True
                self.canvas.draw_idle()
            return

        if event.button != 2:
            return
        if event.inaxes not in (self.rpy_axes + [self.ax_track]):
            return
        if event.xdata is None or event.ydata is None:
            return

        self.plot_pan_active = True
        self.plot_pan_axis = event.inaxes
        self.plot_pan_press = (float(event.xdata), float(event.ydata))
        self.plot_pan_press_px = (event.x, event.y)
        self.plot_pan_xlim = tuple(event.inaxes.get_xlim())
        self.plot_pan_ylim = tuple(event.inaxes.get_ylim())
        self.plot_moved = False

    def _pan_axis(self, axis, x0, y0, x1, y1):
        dx = float(x1) - float(x0)
        dy = float(y1) - float(y0)
        if axis in self.rpy_axes:
            for ax in self.rpy_axes:
                ax.set_xlim(self.plot_pan_xlim[0] - dx, self.plot_pan_xlim[1] - dx)
            axis.set_ylim(self.plot_pan_ylim[0] - dy, self.plot_pan_ylim[1] - dy)
        else:
            axis.set_xlim(self.plot_pan_xlim[0] - dx, self.plot_pan_xlim[1] - dx)
            axis.set_ylim(self.plot_pan_ylim[0] - dy, self.plot_pan_ylim[1] - dy)

    def _on_plot_button_release(self, event):
        if event.button == 1:
            if self.skip_left_release:
                self.skip_left_release = False
                return
            if event.inaxes not in (self.axes + [self.ax_track]) or event.xdata is None or event.ydata is None:
                return

            info = self._get_hover_info(event)
            if info is None:
                return

            self.locked_hover_info = info
            if self.hover_cursor_enabled:
                self._set_hover_x(info["t"])
            self._show_locked_marker(info)
            self._show_locked_annotation(info)
            self.coord_label.setText(self._format_hover_label_text(info))
            self.canvas.draw_idle()
            return

        if event.button != 2 or not self.plot_pan_active:
            return

        moved = self.plot_moved
        self.plot_pan_active = False
        self.plot_pan_axis = None
        self.plot_pan_press = None
        self.plot_pan_press_px = None
        self.plot_pan_xlim = None
        self.plot_pan_ylim = None

        if moved:
            self.canvas.unsetCursor()
            self.canvas.draw_idle()
            return

    def _init_hover_lines(self):
        self.hover_lines = [
            ax.axvline(
                0,
                color="#ffd166",
                linewidth=0.9,
                linestyle="--",
                alpha=0.85,
                visible=False,
                zorder=10,
            )
            for ax in self.axes
        ]
        self.locked_point_markers = []
        for ax in self.axes:
            marker_line = ax.plot(
                [],
                [],
                linestyle="None",
                marker="o",
                markersize=7,
                markerfacecolor="#ffffff",
                markeredgecolor="#101010",
                markeredgewidth=0.8,
                visible=False,
                zorder=11,
            )[0]
            self.locked_point_markers.append(marker_line)
        self.locked_track_marker = self.ax_track.plot(
            [],
            [],
            linestyle="None",
            marker="o",
            markersize=8,
            markerfacecolor="#ffffff",
            markeredgecolor="#101010",
            markeredgewidth=0.9,
            visible=False,
            zorder=11,
        )[0]

    def _set_hover_x(self, x_value):
        if not self.hover_cursor_enabled:
            self._hide_hover_lines()
            return
        for line in self.hover_lines:
            line.set_xdata([x_value, x_value])
            line.set_visible(True)

    def _hide_hover_lines(self):
        for line in self.hover_lines:
            line.set_visible(False)

    def _hide_locked_marker(self):
        for marker in self.locked_point_markers:
            marker.set_visible(False)
        if self.locked_track_marker is not None:
            self.locked_track_marker.set_visible(False)

    def _hide_locked_annotation(self):
        if self.locked_value_annotation is not None:
            try:
                self.locked_value_annotation.remove()
            except Exception:
                pass
            self.locked_value_annotation = None

    def _axis_name(self, axis):
        if axis is self.ax_roll:
            return "roll"
        if axis is self.ax_pitch:
            return "pitch"
        if axis is self.ax_yaw:
            return "yaw"
        return "value"

    def _format_locked_annotation_text(self, info):
        if info["axis"] is self.ax_track:
            lines = [
                "GPS track",
                f"t: {info['t']:.3f} s",
            ]
        else:
            lines = [
                f"{info['side']}  {self._axis_name(info['axis'])}",
                f"t: {info['t']:.3f} s",
                f"{info['deg']:.3f} deg",
            ]
        if info["scalar_text"] is not None:
            lines.append(info["scalar_text"])
        if info.get("radius_text") is not None:
            lines.append(info["radius_text"])
        return "\n".join(lines)

    def _show_locked_annotation(self, info):
        axis = info.get("axis")
        if axis not in (self.axes + [self.ax_track]):
            return

        self._hide_locked_annotation()

        x_mid = 0.5 * sum(axis.get_xlim())
        y_mid = 0.5 * sum(axis.get_ylim())
        x_offset = -22 if info["t"] >= x_mid else 22
        anchor_y = info["deg"] if axis is not self.ax_track else info["track_y"]
        y_offset = -18 if anchor_y >= y_mid else 18
        ha = "right" if x_offset < 0 else "left"
        va = "top" if y_offset < 0 else "bottom"

        self.locked_value_annotation = axis.annotate(
            self._format_locked_annotation_text(info),
            xy=((info["t"], anchor_y) if axis is not self.ax_track else (info["track_x"], info["track_y"])),
            xytext=(x_offset, y_offset),
            textcoords="offset points",
            ha=ha,
            va=va,
            fontsize=9.5,
            color="#11161b",
            bbox={
                "boxstyle": "round,pad=0.42,rounding_size=0.9",
                "fc": "#ffffff",
                "ec": "#d9dde3",
                "lw": 1.0,
                "alpha": 0.98,
            },
            arrowprops={
                "arrowstyle": "->",
                "color": "#ffffff",
                "lw": 1.4,
                "shrinkA": 6,
                "shrinkB": 6,
                "connectionstyle": "arc3,rad=0.08",
            },
            zorder=20,
        )

    def _show_locked_marker(self, info):
        self._hide_locked_marker()

        axis = info.get("axis")
        if axis in self.axes:
            marker = self.locked_point_markers[self.axes.index(axis)]
            marker.set_xdata([info["t"]])
            marker.set_ydata([info["deg"]])
            marker.set_markerfacecolor(
                self.LEFT_COLOR if info.get("side") == "L" else self.RIGHT_COLOR
            )
            marker.set_visible(True)

        if self.gps_path is None or self.locked_track_marker is None:
            return

        if axis is self.ax_track:
            marker_x = float(info["track_x"])
            marker_y = float(info["track_y"])
            marker_color = "#f5f7fa"
        else:
            gps_time = np.asarray(self.gps_path.time, dtype=float)
            longitude = np.asarray(self.gps_path.longitude, dtype=float)
            latitude = np.asarray(self.gps_path.latitude, dtype=float)
            if len(gps_time) == 0 or len(longitude) != len(gps_time) or len(latitude) != len(gps_time):
                return

            gps_idx = self._nearest_index(gps_time, info["t"])
            if gps_idx is None:
                return

            altitude = (
                None
                if self.gps_path.altitude_m is None
                else np.asarray(self.gps_path.altitude_m, dtype=float)
            )
            projection_context = self._track_projection_context(longitude, latitude, altitude)
            if projection_context is None:
                return
            point_alt = None if altitude is None or gps_idx >= len(altitude) else [float(altitude[gps_idx])]
            projected = self._project_track_points(
                [float(longitude[gps_idx])],
                [float(latitude[gps_idx])],
                point_alt,
                context=projection_context,
            )
            if projected is None:
                return
            marker_x = float(projected[0][0])
            marker_y = float(projected[1][0])
            marker_color = self.LEFT_COLOR if info.get("side") == "L" else self.RIGHT_COLOR

        self.locked_track_marker.set_xdata([marker_x])
        self.locked_track_marker.set_ydata([marker_y])
        self.locked_track_marker.set_markerfacecolor(marker_color)
        self.locked_track_marker.set_visible(True)

    def _radius_text_at_time(self, time_value):
        if time_value is None:
            return None
        radius_value = lookup_turn_radius_series_at_time(self.turn_radius_series, time_value)
        if radius_value is None:
            radius_value = lookup_turn_radius_at_time(self.turn_radius_segments, time_value)
        if radius_value is None or not np.isfinite(radius_value):
            return None
        return f"radius: {float(radius_value):.3f} m"

    def _decimate_xy(self, x, y, c=None):
        if self.use_full_resolution:
            return x, y, c
        n = len(x)
        if n <= self.max_points:
            return x, y, c

        idx = np.linspace(0, n - 1, self.max_points).astype(int)
        idx = np.unique(idx)

        if c is None:
            return x[idx], y[idx], None

        return x[idx], y[idx], c[idx]

    def _decimate_track_xy(self, x, y, z=None, c=None):
        if self.use_full_resolution:
            return x, y, z, c
        n = len(x)
        if n <= self.max_track_points:
            return x, y, z, c

        idx = np.linspace(0, n - 1, self.max_track_points).astype(int)
        idx = np.unique(idx)
        z_out = None if z is None else z[idx]
        c_out = None if c is None else c[idx]
        return x[idx], y[idx], z_out, c_out

    def _track_projection_context(self, longitude, latitude, altitude=None):
        longitude = np.asarray(longitude, dtype=float).reshape(-1)
        latitude = np.asarray(latitude, dtype=float).reshape(-1)
        n = min(len(longitude), len(latitude))
        if n < 2:
            return None

        longitude = longitude[:n]
        latitude = latitude[:n]

        if altitude is None:
            altitude = np.zeros(n, dtype=float)
        else:
            altitude = np.asarray(altitude, dtype=float).reshape(-1)[:n]
            if len(altitude) != n:
                altitude = np.zeros(n, dtype=float)
            else:
                finite_alt = np.isfinite(altitude)
                if not np.any(finite_alt):
                    altitude = np.zeros(n, dtype=float)
                elif not np.all(finite_alt):
                    idx = np.arange(n, dtype=float)
                    altitude = np.interp(idx, idx[finite_alt], altitude[finite_alt])

        lon0 = float(np.mean(longitude))
        lat0 = float(np.mean(latitude))
        cos_lat = max(np.cos(np.radians(lat0)), 1e-6)
        x_m = (longitude - lon0) * 111320.0 * cos_lat
        y_m = (latitude - lat0) * 111320.0
        z_m = altitude - float(np.min(altitude))
        x_centered = x_m - float(np.mean(x_m))
        y_centered = y_m - float(np.mean(y_m))

        rot_cos = 1.0
        rot_sin = 0.0
        dx = float(x_centered[-1] - x_centered[0])
        dy = float(y_centered[-1] - y_centered[0])
        if abs(dx) > 1e-9 or abs(dy) > 1e-9:
            theta = (-0.5 * np.pi) - float(np.arctan2(dy, dx))
            rot_cos = float(np.cos(theta))
            rot_sin = float(np.sin(theta))

        if self.track_view_mode == "2d":
            return {
                "lon0": lon0,
                "lat0": lat0,
                "cos_lat": cos_lat,
                "alt0": float(np.min(altitude)),
                "z_scale": 0.0,
                "mean_x_m": float(np.mean(x_m)),
                "mean_y_m": float(np.mean(y_m)),
                "tilt_x": 0.0,
                "tilt_y": 1.0,
                "rot_cos": rot_cos,
                "rot_sin": rot_sin,
            }

        horizontal_span = max(float(np.ptp(x_m)), float(np.ptp(y_m)), 1.0)
        altitude_span = max(float(np.ptp(z_m)), 1.0)
        z_scale = max(1.8, 0.52 * horizontal_span / altitude_span)

        return {
            "lon0": lon0,
            "lat0": lat0,
            "cos_lat": cos_lat,
            "alt0": float(np.min(altitude)),
            "z_scale": z_scale,
            "mean_x_m": float(np.mean(x_m)),
            "mean_y_m": float(np.mean(y_m)),
            "tilt_x": 0.74,
            "tilt_y": -0.42,
            "rot_cos": 1.0,
            "rot_sin": 0.0,
        }

    def _project_track_points(self, longitude, latitude, altitude=None, *, context=None):
        longitude = np.asarray(longitude, dtype=float).reshape(-1)
        latitude = np.asarray(latitude, dtype=float).reshape(-1)
        n = min(len(longitude), len(latitude))
        if n < 1:
            return None

        longitude = longitude[:n]
        latitude = latitude[:n]

        if context is None:
            context = self._track_projection_context(longitude, latitude, altitude)
        if context is None:
            return None

        if altitude is None:
            altitude = np.zeros(n, dtype=float)
        else:
            altitude = np.asarray(altitude, dtype=float).reshape(-1)[:n]
            if len(altitude) != n:
                altitude = np.zeros(n, dtype=float)
            else:
                finite_alt = np.isfinite(altitude)
                if not np.any(finite_alt):
                    altitude = np.zeros(n, dtype=float)
                elif not np.all(finite_alt):
                    idx = np.arange(n, dtype=float)
                    altitude = np.interp(idx, idx[finite_alt], altitude[finite_alt])

        x_m = (longitude - context["lon0"]) * 111320.0 * context["cos_lat"]
        y_m = (latitude - context["lat0"]) * 111320.0
        z_m = altitude - context["alt0"]

        x_m = x_m - context["mean_x_m"]
        y_m = y_m - context["mean_y_m"]
        rot_cos = context.get("rot_cos", 1.0)
        rot_sin = context.get("rot_sin", 0.0)
        x_rot = rot_cos * x_m - rot_sin * y_m
        y_rot = rot_sin * x_m + rot_cos * y_m

        floor_x = x_rot + context["tilt_x"] * y_rot
        floor_y = context["tilt_y"] * y_rot
        proj_x = floor_x
        proj_y = floor_y + z_m * context["z_scale"]
        return proj_x, proj_y, floor_x, floor_y

    def _set_projected_track_limits(self, proj_x, proj_y, floor_x, floor_y):
        min_x = float(min(np.min(proj_x), np.min(floor_x)))
        max_x = float(max(np.max(proj_x), np.max(floor_x)))
        min_y = float(min(np.min(proj_y), np.min(floor_y)))
        max_y = float(max(np.max(proj_y), np.max(floor_y)))
        x_pad = max((max_x - min_x) * 0.08, 1e-5)
        y_pad = max((max_y - min_y) * 0.08, 1e-5)
        self.ax_track.set_xlim(min_x - x_pad, max_x + x_pad)
        self.ax_track.set_ylim(min_y - y_pad, max_y + y_pad)

    def _get_scalar_data(self, ski, mode):
        if mode == "radius":
            if ski is None:
                return None
            target_time = np.asarray(getattr(ski, "time", []), dtype=float)
            scalar = sample_turn_radius_series(self.turn_radius_series, target_time)
            if scalar is not None:
                return scalar
            return sample_turn_radius_segments(self.turn_radius_segments, target_time)
        return get_scalar_data(ski, mode)

    def _get_track_speed_norm(self):
        skis = []
        if self.right is not None:
            skis.append(self.right)
        if self.left is not None:
            skis.append(self.left)

        norm = build_shared_scalar_norm(skis, "speed")
        if norm is not None:
            return norm

        if self.gps_path is None or self.gps_path.speed_kmh is None:
            return None

        speed = np.asarray(self.gps_path.speed_kmh, dtype=float)
        finite = speed[np.isfinite(speed)]
        if finite.size < 2:
            return None

        from matplotlib import colors

        vmin = float(np.nanpercentile(finite, 5))
        vmax = float(np.nanpercentile(finite, 95))
        if vmax <= vmin:
            vmax = vmin + 1.0
        return colors.Normalize(vmin=vmin, vmax=vmax)

    def _get_track_scalar_data(self, target_time: np.ndarray):
        if self.color_mode == "fixed":
            return get_gps_accuracy_data(self.gps_path), build_gps_accuracy_norm(self.gps_path)

        if self.color_mode == "speed":
            if self.gps_path is None or self.gps_path.speed_kmh is None:
                return None, None
            return (
                np.asarray(self.gps_path.speed_kmh, dtype=float).reshape(-1),
                self._get_track_speed_norm(),
            )

        if self.color_mode == "acc":
            series_list = []

            for ski, visible in ((self.left, self.show_left), (self.right, self.show_right)):
                if ski is None or not visible:
                    continue
                series_list.append(interpolate_scalar_to_time(ski, "acc", target_time))

            if not series_list:
                for ski in (self.left, self.right):
                    if ski is not None:
                        series_list.append(interpolate_scalar_to_time(ski, "acc", target_time))

            scalar = combine_scalar_series(series_list)
            norm = build_shared_scalar_norm(
                [ski for ski in (self.left, self.right) if ski is not None],
                "acc",
            )
            return scalar, norm

        if self.color_mode == "gyro":
            series_list = []

            for ski, visible in ((self.left, self.show_left), (self.right, self.show_right)):
                if ski is None or not visible:
                    continue
                series_list.append(interpolate_scalar_to_time(ski, "gyro", target_time))

            if not series_list:
                for ski in (self.left, self.right):
                    if ski is not None:
                        series_list.append(interpolate_scalar_to_time(ski, "gyro", target_time))

            scalar = combine_scalar_series(series_list)
            norm = build_shared_scalar_norm(
                [ski for ski in (self.left, self.right) if ski is not None],
                "gyro",
            )
            return scalar, norm

        if self.color_mode == "radius":
            scalar = sample_turn_radius_series(self.turn_radius_series, target_time)
            norm = build_turn_radius_series_norm(self.turn_radius_series)
            if scalar is not None and norm is not None:
                return scalar, norm
            return (
                sample_turn_radius_segments(self.turn_radius_segments, target_time),
                build_turn_radius_norm(self.turn_radius_segments),
            )

        return None, None

    def _make_segments(self, x, y):
        points = np.array([x, y]).T.reshape(-1, 1, 2)
        return np.concatenate([points[:-1], points[1:]], axis=1)

    def _plot_colored_line(self, ax, x, y, c, norm, cmap="viridis", lw=1.5):
        if len(x) < 2:
            return None

        if np.isnan(c).any():
            ax.plot(x, y, color="#cfd4da", linewidth=max(0.9, lw * 0.45), alpha=0.55)

        segments = self._make_segments(x, y)
        cseg = 0.5 * (c[:-1] + c[1:])
        cseg = np.ma.masked_invalid(cseg)

        lc = LineCollection(
            segments,
            cmap=cmap,
            norm=norm,
            linewidth=lw,
        )
        lc.set_array(cseg)
        ax.add_collection(lc)
        ax.autoscale_view()
        return lc

    def _plot_one(self, ax, ski, attr, color, label, norm=None):
        x = np.asarray(ski.time, dtype=float)
        values = getattr(ski, attr)
        if values is None:
            return None
        y = np.asarray(values, dtype=float)

        scalar = None
        if self.color_mode in ("speed", "acc", "gyro", "radius"):
            scalar = self._get_scalar_data(ski, self.color_mode)

        x2, y2, c2 = self._decimate_xy(x, y, scalar)

        if self.color_mode == "fixed" or c2 is None or norm is None:
            ax.plot(x2, y2, color=color, linewidth=1.0, label=label)
            return None

        return self._plot_colored_line(ax, x2, y2, c2, norm=norm, cmap=SCALAR_CMAP, lw=1.5)

    def _get_shared_norm(self):
        if self.color_mode == "radius":
            norm = build_turn_radius_series_norm(self.turn_radius_series)
            if norm is not None:
                return norm
            return build_turn_radius_norm(self.turn_radius_segments)
        skis = []
        if self.right is not None:
            skis.append(self.right)
        if self.left is not None:
            skis.append(self.left)
        return build_shared_scalar_norm(skis, self.color_mode)

    def _remove_colorbar(self):
        if self.cbar is not None:
            try:
                self.cbar.remove()
            except Exception:
                pass
            self.cbar = None

        if self.cbar_ax is not None:
            try:
                self.cbar_ax.remove()
            except Exception:
                pass
            self.cbar_ax = None

    def _add_colorbar_if_needed(self, mappable):
        self._remove_colorbar()

        if self.color_mode == "fixed" or mappable is None:
            return

        self.cbar_ax = self.figure.add_axes([0.925, 0.10, 0.016, 0.80])
        self.cbar = self.figure.colorbar(mappable, cax=self.cbar_ax)

        self.cbar.ax.set_facecolor("#1e1e1e")
        self.cbar.ax.yaxis.set_tick_params(color="#d8d8d8")

        for tick in self.cbar.ax.get_yticklabels():
            tick.set_color("#d8d8d8")

        self.cbar.outline.set_edgecolor("#555555")

        if self.color_mode == "speed":
            self.cbar.set_label("speed [km/h]", color="#eaeaea")
        elif self.color_mode == "acc":
            self.cbar.set_label("|acc| [G]", color="#eaeaea")
        elif self.color_mode == "gyro":
            self.cbar.set_label("ang vel [deg/s]", color="#eaeaea")
        elif self.color_mode == "radius":
            self.cbar.set_label("turn radius [m]", color="#eaeaea")
    def _plot_all(self):
        self._remove_colorbar()
        self.locked_hover_info = None
        self._hide_locked_annotation()

        for ax in self.rpy_axes + [self.ax_track]:
            ax.clear()

        for ax in self.rpy_axes:
            ax.axhline(0, color="#7a7a7a", linewidth=1.0, linestyle="-", label="_nolegend_")

        self._style_axes()
        self._init_hover_lines()

        norm = self._get_shared_norm()
        first_mappable = None

        if self.show_right and self.right is not None:
            for ax, attr in zip(self.axes, ["roll", "pitch", "yaw"]):
                m = self._plot_one(ax, self.right, attr, self.RIGHT_COLOR, "Right", norm)
                if first_mappable is None and m is not None:
                    first_mappable = m

        if self.show_left and self.left is not None:
            for ax, attr in zip(self.axes, ["roll", "pitch", "yaw"]):
                m = self._plot_one(ax, self.left, attr, self.LEFT_COLOR, "Left", norm)
                if first_mappable is None and m is not None:
                    first_mappable = m

        self._plot_gps_track()
        self._store_default_limits()

        self.figure.subplots_adjust(
            left=0.07,
            right=0.91 if self.color_mode != "fixed" else 0.98,
            top=0.97,
            bottom=0.08,
        )

        self._add_colorbar_if_needed(first_mappable)
        self.canvas.draw_idle()

    def _plot_gps_track(self):
        if self.gps_path is None:
            message = self.gps_load_error or "No GPS trajectory available."
            self.ax_track.text(
                0.5,
                0.5,
                message,
                transform=self.ax_track.transAxes,
                ha="center",
                va="center",
                color="#d0d0d0",
                fontsize=10,
            )
            return

        longitude = np.asarray(self.gps_path.longitude, dtype=float)
        latitude = np.asarray(self.gps_path.latitude, dtype=float)
        altitude = (
            None
            if self.gps_path.altitude_m is None
            else np.asarray(self.gps_path.altitude_m, dtype=float)
        )
        scalar, scalar_norm = self._get_track_scalar_data(
            np.asarray(self.gps_path.time, dtype=float)
        )

        if len(longitude) < 2 or len(latitude) < 2:
            self.ax_track.text(
                0.5,
                0.5,
                "No GPS trajectory available.",
                transform=self.ax_track.transAxes,
                ha="center",
                va="center",
                color="#d0d0d0",
                fontsize=10,
            )
            return

        longitude, latitude, altitude, scalar = self._decimate_track_xy(longitude, latitude, altitude, scalar)
        track_cmap = GPS_ACCURACY_CMAP if self.color_mode == "fixed" else SCALAR_CMAP

        if self.track_view_mode == "3d" and altitude is not None:
            projection_context = self._track_projection_context(longitude, latitude, altitude)
            projected = self._project_track_points(
                longitude,
                latitude,
                altitude,
                context=projection_context,
            )
            if projected is None:
                return

            proj_x, proj_y, floor_x, floor_y = projected
            connector_step = max(6, len(proj_x) // 22)
            for idx in range(0, len(proj_x), connector_step):
                self.ax_track.plot(
                    [floor_x[idx], proj_x[idx]],
                    [floor_y[idx], proj_y[idx]],
                    color="#68727c",
                    linewidth=1.0,
                    alpha=0.45,
                    zorder=2,
                )

            if scalar is None or scalar_norm is None:
                self.ax_track.plot(
                    proj_x,
                    proj_y,
                    color="#d8d8d8",
                    linewidth=1.4,
                    alpha=0.95,
                )
            else:
                self._plot_colored_line(
                    self.ax_track,
                    proj_x,
                    proj_y,
                    scalar,
                    norm=scalar_norm,
                    cmap=track_cmap,
                    lw=2.0,
                )

            start_x, start_y = proj_x[0], proj_y[0]
            end_x, end_y = proj_x[-1], proj_y[-1]
            self._set_projected_track_limits(proj_x, proj_y, floor_x, floor_y)
        else:
            projection_context = self._track_projection_context(longitude, latitude, altitude)
            projected = self._project_track_points(
                longitude,
                latitude,
                altitude,
                context=projection_context,
            )
            if projected is None:
                return
            proj_x, proj_y, floor_x, floor_y = projected

            if scalar is None or scalar_norm is None:
                self.ax_track.plot(
                    proj_x,
                    proj_y,
                    color="#d8d8d8",
                    linewidth=1.4,
                    alpha=0.95,
                )
            else:
                self._plot_colored_line(
                    self.ax_track,
                    proj_x,
                    proj_y,
                    scalar,
                    norm=scalar_norm,
                    cmap=track_cmap,
                    lw=2.0,
                )

            start_x, start_y = proj_x[0], proj_y[0]
            end_x, end_y = proj_x[-1], proj_y[-1]
            self._set_projected_track_limits(proj_x, proj_y, floor_x, floor_y)

        self.ax_track.scatter(
            start_x,
            start_y,
            color="#ff6b6b",
            s=30,
            edgecolors="#1e1e1e",
            linewidths=0.6,
            zorder=5,
        )
        self.ax_track.scatter(
            end_x,
            end_y,
            color="#7bd88f",
            s=30,
            edgecolors="#1e1e1e",
            linewidths=0.6,
            zorder=5,
        )
        if self.track_view_mode == "2d":
            self.ax_track.set_aspect("equal", adjustable="box")
        else:
            self.ax_track.set_aspect("auto")

    def _toggle_left(self):
        self.show_left = self.btn_left.isChecked()
        self._plot_all()

    def _toggle_right(self):
        self.show_right = self.btn_right.isChecked()
        self._plot_all()

    def _cycle_color_mode(self):
        self.color_mode_index = (self.color_mode_index + 1) % len(self.color_modes)
        self.color_mode = self.color_modes[self.color_mode_index]
        self.btn_color_mode.setText(self._display_color_mode())
        self._plot_all()

    def _toggle_resolution(self):
        self.use_full_resolution = not self.use_full_resolution
        self.btn_resolution.setText("High res" if self.use_full_resolution else "Low res")
        self._plot_all()

    def _toggle_track_view(self):
        self.track_view_mode = "2d" if self.track_view_mode == "3d" else "3d"
        self.btn_track_view.setText(self.track_view_mode.upper())
        self._plot_all()

    def _toggle_hover_cursor(self):
        self.hover_cursor_enabled = self.btn_hover_cursor.isChecked()
        if not self.hover_cursor_enabled:
            self._hide_hover_lines()
            self.canvas.draw_idle()

    def _nearest_index(self, x, x0):
        x = np.asarray(x, dtype=float)
        if x.size == 0:
            return None
        return int(np.argmin(np.abs(x - x0)))

    def _format_scalar_value(self, ski, idx):
        if ski is None or idx is None:
            return None

        scalar = self._get_scalar_data(ski, self.color_mode)
        if scalar is None:
            return None

        if idx < 0 or idx >= len(scalar):
            return None

        value = float(scalar[idx])

        if self.color_mode == "speed":
            return f"speed: {value:.3f} km/h"
        if self.color_mode == "acc":
            return f"acc: {value:.3f} G"
        if self.color_mode == "gyro":
            return f"ang vel: {value:.3f} deg/s"
        if self.color_mode == "radius":
            return f"radius: {value:.3f} m"
        return None

    def _format_hover_label_text(self, info):
        text = (
            f"{self._display_color_mode().lower()}   ski: {info['side']}   "
            f"t: {info['t']:.3f}   deg: {info['deg']:.3f}"
        )

        if info["scalar_text"] is not None:
            text += f"   {info['scalar_text']}"
        if info.get("radius_text") is not None:
            text += f"   {info['radius_text']}"
        return text

    def _display_color_mode(self) -> str:
        return {"fixed": "Fixed", "speed": "Speed", "acc": "G", "gyro": "Gyro", "radius": "Radius"}.get(
            self.color_mode, self.color_mode.title()
        )

    def _get_hover_info(self, event):
        if event.inaxes is self.ax_track:
            if self.gps_path is None:
                return None

            gps_time = np.asarray(self.gps_path.time, dtype=float)
            longitude = np.asarray(self.gps_path.longitude, dtype=float)
            latitude = np.asarray(self.gps_path.latitude, dtype=float)
            altitude = (
                None
                if self.gps_path.altitude_m is None
                else np.asarray(self.gps_path.altitude_m, dtype=float)
            )
            projected = self._project_track_points(longitude, latitude, altitude)
            if projected is None:
                return None

            proj_x = np.asarray(projected[0], dtype=float)
            proj_y = np.asarray(projected[1], dtype=float)
            if len(proj_x) == 0 or len(gps_time) != len(proj_x):
                return None

            dist = (proj_x - float(event.xdata)) ** 2 + (proj_y - float(event.ydata)) ** 2
            idx = int(np.argmin(dist))
            time_value = float(gps_time[idx])
            return {
                "side": "GPS",
                "idx": idx,
                "t": time_value,
                "deg": 0.0,
                "axis": self.ax_track,
                "scalar_text": None,
                "radius_text": self._radius_text_at_time(time_value),
                "track_x": float(proj_x[idx]),
                "track_y": float(proj_y[idx]),
            }

        if event.inaxes not in self.axes:
            return None

        candidates = []

        if self.show_right and self.right is not None:
            idx = self._nearest_index(self.right.time, event.xdata)
            if idx is not None:
                y_map = {
                    self.ax_roll: self.right.roll,
                    self.ax_pitch: self.right.pitch,
                    self.ax_yaw: self.right.yaw,
                }
                axis_values = y_map.get(event.inaxes)
                if axis_values is not None:
                    y = float(np.asarray(axis_values, dtype=float)[idx])
                    dist = abs(y - float(event.ydata))
                    candidates.append(("R", self.right, idx, dist, y))

        if self.show_left and self.left is not None:
            idx = self._nearest_index(self.left.time, event.xdata)
            if idx is not None:
                y_map = {
                    self.ax_roll: self.left.roll,
                    self.ax_pitch: self.left.pitch,
                    self.ax_yaw: self.left.yaw,
                }
                axis_values = y_map.get(event.inaxes)
                if axis_values is not None:
                    y = float(np.asarray(axis_values, dtype=float)[idx])
                    dist = abs(y - float(event.ydata))
                    candidates.append(("L", self.left, idx, dist, y))

        if not candidates:
            return None

        side, ski, idx, _, y = min(candidates, key=lambda item: item[3])
        scalar_text = self._format_scalar_value(ski, idx)
        return {
            "side": side,
            "idx": idx,
            "t": float(np.asarray(ski.time, dtype=float)[idx]),
            "deg": y,
            "axis": event.inaxes,
            "scalar_text": scalar_text,
            "radius_text": self._radius_text_at_time(float(np.asarray(ski.time, dtype=float)[idx])),
        }

    def _on_mouse_move(self, event):
        if self.plot_pan_active:
            if (
                event.inaxes is self.plot_pan_axis
                and event.xdata is not None
                and event.ydata is not None
                and self.plot_pan_press is not None
                and self.plot_pan_press_px is not None
            ):
                if not self.plot_moved:
                    dx_px = abs(float(event.x) - float(self.plot_pan_press_px[0]))
                    dy_px = abs(float(event.y) - float(self.plot_pan_press_px[1]))
                    self.plot_moved = dx_px > 4 or dy_px > 4
                    if self.plot_moved:
                        self.canvas.setCursor(Qt.ClosedHandCursor)
                if self.plot_moved:
                    self._pan_axis(
                        self.plot_pan_axis,
                        self.plot_pan_press[0],
                        self.plot_pan_press[1],
                        event.xdata,
                        event.ydata,
                    )
                    self.canvas.draw_idle()
            return

        if self.locked_hover_info is not None:
            return

        if event.inaxes is None or event.xdata is None or event.ydata is None:
            self._hide_hover_lines()
            self.coord_label.setText(f"{self._display_color_mode().lower()}   t: -   deg: -")
            self.canvas.draw_idle()
            return

        if self.hover_cursor_enabled:
            self._set_hover_x(float(event.xdata))
        else:
            self._hide_hover_lines()

        info = self._get_hover_info(event)
        if info is None:
            self.coord_label.setText(
                f"{self._display_color_mode().lower()}   t: {event.xdata:.3f}   deg: {event.ydata:.3f}"
            )
            self.canvas.draw_idle()
            return

        self.coord_label.setText(self._format_hover_label_text(info))
        self.canvas.draw_idle()
