from pathlib import Path

import numpy as np

from matplotlib import colormaps
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.collections import LineCollection
from matplotlib.figure import Figure

from PySide6.QtCore import QElapsedTimer, QTimer, QRectF, Qt, QUrl
from PySide6.QtGui import (
    QBrush,
    QColor,
    QFont,
    QKeySequence,
    QLinearGradient,
    QPainter,
    QPen,
    QShortcut,
)
from PySide6.QtWidgets import (
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSizePolicy,
    QSlider,
    QStackedLayout,
    QVBoxLayout,
    QWidget,
)

from data_loader import (
    DataLoadError,
    load_gps_path,
    load_turn_radius_segments,
    load_turn_radius_timeseries,
    load_turn_intervals,
    slice_gps_path_to_interval,
    slice_ski_data_to_interval,
)
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
    top_bar_frame_stylesheet,
)

try:
    from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
    from PySide6.QtMultimediaWidgets import QVideoWidget

    QT_VIDEO_AVAILABLE = True
except Exception:
    QAudioOutput = None
    QMediaPlayer = None
    QVideoWidget = None
    QT_VIDEO_AVAILABLE = False


class SkiAnimationScene(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(390)

        self.left_roll = None
        self.right_roll = None
        self.left_color = QColor("#ff9a3d")
        self.right_color = QColor("#5aa9ff")
        self.mirror_view = False
        self.show_turn_separation = False
        self.active_turn_start = None
        self.active_turn_stop = None
        self.current_time = None

    def set_state(
        self,
        *,
        left_roll,
        right_roll,
        left_color,
        right_color,
        mirror_view=False,
        show_turn_separation=False,
        active_turn_start=None,
        active_turn_stop=None,
        current_time=None,
    ):
        self.left_roll = left_roll
        self.right_roll = right_roll
        self.left_color = left_color
        self.right_color = right_color
        self.mirror_view = bool(mirror_view)
        self.show_turn_separation = bool(show_turn_separation)
        self.active_turn_start = active_turn_start
        self.active_turn_stop = active_turn_stop
        self.current_time = current_time
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)

        card = self.rect().adjusted(8, 8, -8, -8)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor("#2b2b2b"))
        painter.drawRoundedRect(card, 22, 22)

        self._draw_scene(painter, card)

    def _draw_scene(self, painter: QPainter, card):
        scene = QRectF(card.left() + 10, card.top() + 12, card.width() - 20, card.height() - 24)
        ground_y = scene.bottom() - 64

        painter.setPen(QPen(QColor("#ff2b2b"), 4))
        painter.drawLine(scene.left() + 10, ground_y, scene.right() - 10, ground_y)

        slot_width = scene.width() * 0.23
        left_slot_left = scene.left() + scene.width() * 0.18
        left_slot_right = left_slot_left + slot_width
        right_slot_left = scene.right() - scene.width() * 0.18 - slot_width
        right_slot_right = right_slot_left + slot_width

        left_target_left = right_slot_left if self.mirror_view else left_slot_left
        left_target_right = right_slot_right if self.mirror_view else left_slot_right
        right_target_left = left_slot_left if self.mirror_view else right_slot_left
        right_target_right = left_slot_right if self.mirror_view else right_slot_right

        painter.setPen(QColor("#f2f2f2"))
        painter.setFont(QFont("Segoe UI", 14, QFont.Weight.Bold))
        painter.drawText(
            QRectF(left_target_left, ground_y + 24, slot_width, 30),
            Qt.AlignHCenter,
            "L",
        )
        painter.drawText(
            QRectF(right_target_left, ground_y + 24, slot_width, 30),
            Qt.AlignHCenter,
            "R",
        )

        self._draw_ski(
            painter,
            slot_left=left_target_left,
            slot_right=left_target_right,
            scene_top=scene.top(),
            ground_y=ground_y,
            angle_deg=(
                None if self.left_roll is None else (-float(self.left_roll) if self.mirror_view else self.left_roll)
            ),
            fill_color=self.left_color,
        )
        self._draw_ski(
            painter,
            slot_left=right_target_left,
            slot_right=right_target_right,
            scene_top=scene.top(),
            ground_y=ground_y,
            angle_deg=(
                None
                if self.right_roll is None
                else (-float(self.right_roll) if self.mirror_view else self.right_roll)
            ),
            fill_color=self.right_color,
        )

        if self.show_turn_separation and self.active_turn_start is not None and self.active_turn_stop is not None:
            self._draw_turn_overlay(painter, scene)

    def _draw_turn_overlay(self, painter: QPainter, scene: QRectF):
        start_t = float(self.active_turn_start)
        stop_t = float(self.active_turn_stop)
        duration_t = max(0.0, stop_t - start_t)
        current_t = None if self.current_time is None else float(self.current_time)
        progress = 0.0
        if current_t is not None and stop_t > start_t:
            progress = float(np.clip((current_t - start_t) / (stop_t - start_t), 0.0, 1.0))

        pill_height = 28.0
        pill_y = scene.top() + 6.0
        left_pill = QRectF(scene.left() + 12.0, pill_y, 122.0, pill_height)
        right_pill = QRectF(scene.right() - 134.0, pill_y, 122.0, pill_height)
        bar_rect = QRectF(left_pill.right() + 14.0, pill_y + 7.0, max(40.0, right_pill.left() - left_pill.right() - 28.0), 14.0)

        painter.save()
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(28, 36, 43, 220))
        painter.drawRoundedRect(left_pill, 10, 10)
        painter.drawRoundedRect(right_pill, 10, 10)

        painter.setBrush(QColor("#20252b"))
        painter.drawRoundedRect(bar_rect, 7, 7)

        fill_rect = QRectF(bar_rect.left(), bar_rect.top(), bar_rect.width() * progress, bar_rect.height())
        painter.setBrush(QColor("#6cbf7c"))
        painter.drawRoundedRect(fill_rect, 7, 7)

        painter.setPen(QColor("#e8eef5"))
        painter.setFont(QFont("Segoe UI", 9, QFont.Weight.DemiBold))
        painter.drawText(left_pill, Qt.AlignCenter, "0.00s")
        painter.drawText(right_pill, Qt.AlignCenter, f"{duration_t:.2f}s")
        painter.restore()

    def _draw_ski(
        self,
        painter: QPainter,
        *,
        slot_left,
        slot_right,
        scene_top,
        ground_y,
        angle_deg,
        fill_color,
    ):
        ski_length = max(88.0, float(slot_right - slot_left))
        ski_height = 28.0
        angle = 0.0 if angle_deg is None else float(np.clip(angle_deg, -55.0, 55.0))
        angle_abs_rad = np.radians(abs(angle))
        vertical_clearance = max(40.0, float(ground_y - scene_top - 12.0))

        if angle_abs_rad > 1e-3:
            max_length_from_height = (
                vertical_clearance - ski_height * np.cos(angle_abs_rad)
            ) / np.sin(angle_abs_rad)
            ski_length = min(ski_length, max(60.0, float(max_length_from_height)))

        pivot_on_left = angle >= 0.0
        pivot_x = slot_left if pivot_on_left else slot_right

        if pivot_on_left:
            ski_rect = QRectF(0, -ski_height, ski_length, ski_height)
        else:
            ski_rect = QRectF(-ski_length, -ski_height, ski_length, ski_height)

        painter.save()
        painter.translate(pivot_x, ground_y)
        painter.rotate(-angle)

        ski_gradient = QLinearGradient(ski_rect.topLeft(), ski_rect.bottomLeft())
        base = QColor(fill_color)
        ski_gradient.setColorAt(0.0, base.lighter(125))
        ski_gradient.setColorAt(1.0, base.darker(122))

        painter.setPen(QPen(QColor("#f4f8fb"), 2.6))
        painter.setBrush(QBrush(ski_gradient))
        painter.drawRect(ski_rect)
        painter.restore()


class PlaybackTrajectoryScene(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(280)
        self.track_view_mode = "3d"
        self.track_x = None
        self.track_y = None
        self.track_altitude = None
        self.segment_colors = None
        self.current_point = None
        self.turn_start_points = []
        self.turn_end_points = []
        self.view_bounds = None
        self.default_bounds = None
        self.drag_active = False
        self.drag_start_pos = None
        self.drag_start_bounds = None

    def set_track(self, x_values, y_values, altitude_values=None, segment_colors=None):
        self.track_x = None if x_values is None else np.asarray(x_values, dtype=float)
        self.track_y = None if y_values is None else np.asarray(y_values, dtype=float)
        self.track_altitude = None if altitude_values is None else np.asarray(altitude_values, dtype=float)
        self.segment_colors = segment_colors
        self._reset_view()
        self.update()

    def set_track_view_mode(self, mode: str):
        mode = "2d" if str(mode).lower() == "2d" else "3d"
        if self.track_view_mode == mode:
            return
        self.track_view_mode = mode
        self._reset_view()
        self.update()

    def set_current_point(self, point):
        self.current_point = point
        self.update()

    def set_turn_markers(self, start_points, end_points):
        self.turn_start_points = [] if start_points is None else [tuple(point) for point in start_points]
        self.turn_end_points = [] if end_points is None else [tuple(point) for point in end_points]
        self.update()

    def clear(self):
        self.track_x = None
        self.track_y = None
        self.track_altitude = None
        self.segment_colors = None
        self.current_point = None
        self.turn_start_points = []
        self.turn_end_points = []
        self.view_bounds = None
        self.default_bounds = None
        self.drag_active = False
        self.drag_start_pos = None
        self.drag_start_bounds = None
        self.update()

    def _card_rect(self):
        return self.rect().adjusted(8, 8, -8, -8)

    def _content_rect(self):
        card = self._card_rect()
        return QRectF(card.left() + 18, card.top() + 18, card.width() - 36, card.height() - 36)

    def _compute_bounds(self):
        projected = self._projected_track()
        if projected is None:
            return None

        proj_x, proj_y, floor_x, floor_y = projected
        min_x = float(min(np.min(proj_x), np.min(floor_x)))
        max_x = float(max(np.max(proj_x), np.max(floor_x)))
        min_y = float(min(np.min(proj_y), np.min(floor_y)))
        max_y = float(max(np.max(proj_y), np.max(floor_y)))

        x_span = max(max_x - min_x, 1e-9)
        y_span = max(max_y - min_y, 1e-9)
        pad_x = max(x_span * 0.08, 1e-9)
        pad_y = max(y_span * 0.08, 1e-9)
        return (
            min_x - pad_x,
            max_x + pad_x,
            min_y - pad_y,
            max_y + pad_y,
        )

    def _reset_view(self):
        bounds = self._compute_bounds()
        self.default_bounds = bounds
        self.view_bounds = None if bounds is None else tuple(bounds)

    def _projection_context(self):
        if self.track_x is None or self.track_y is None:
            return None

        x_values = np.asarray(self.track_x, dtype=float).reshape(-1)
        y_values = np.asarray(self.track_y, dtype=float).reshape(-1)
        n = min(len(x_values), len(y_values))
        if n < 2:
            return None

        x_values = x_values[:n]
        y_values = y_values[:n]
        lon0 = float(np.mean(x_values))
        lat0 = float(np.mean(y_values))
        cos_lat = max(np.cos(np.radians(lat0)), 1e-6)

        altitude_values = self.track_altitude
        if altitude_values is None:
            altitude_values = np.zeros(n, dtype=float)
        else:
            altitude_values = np.asarray(altitude_values, dtype=float).reshape(-1)[:n]
            if len(altitude_values) != n:
                altitude_values = np.zeros(n, dtype=float)
            else:
                finite_alt = np.isfinite(altitude_values)
                if not np.any(finite_alt):
                    altitude_values = np.zeros(n, dtype=float)
                elif not np.all(finite_alt):
                    idx = np.arange(n, dtype=float)
                    altitude_values = np.interp(idx, idx[finite_alt], altitude_values[finite_alt])

        x_m = (x_values - lon0) * 111320.0 * cos_lat
        y_m = (y_values - lat0) * 111320.0
        z_m = altitude_values - float(np.min(altitude_values))
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
                "alt0": float(np.min(altitude_values)),
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
            "alt0": float(np.min(altitude_values)),
            "z_scale": z_scale,
            "mean_x_m": float(np.mean(x_m)),
            "mean_y_m": float(np.mean(y_m)),
            "tilt_x": 0.74,
            "tilt_y": -0.42,
            "rot_cos": 1.0,
            "rot_sin": 0.0,
        }

    def _project_points(self, x_values, y_values, altitude_values=None, *, context=None):
        if x_values is None or y_values is None:
            return None

        x_values = np.asarray(x_values, dtype=float).reshape(-1)
        y_values = np.asarray(y_values, dtype=float).reshape(-1)
        n = min(len(x_values), len(y_values))
        if n < 1:
            return None

        x_values = x_values[:n]
        y_values = y_values[:n]

        if context is None:
            context = self._projection_context()
        if context is None:
            return None

        if altitude_values is not None:
            altitude_values = np.asarray(altitude_values, dtype=float).reshape(-1)[:n]
            if len(altitude_values) != n:
                altitude_values = None
        if altitude_values is None or len(altitude_values) != n:
            altitude_values = np.zeros(n, dtype=float)
        else:
            finite_alt = np.isfinite(altitude_values)
            if not np.any(finite_alt):
                altitude_values = np.zeros(n, dtype=float)
            elif not np.all(finite_alt):
                idx = np.arange(n, dtype=float)
                altitude_values = np.interp(idx, idx[finite_alt], altitude_values[finite_alt])

        x_m = (x_values - context["lon0"]) * 111320.0 * context["cos_lat"]
        y_m = (y_values - context["lat0"]) * 111320.0
        z_m = altitude_values - context["alt0"]

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

    def _projected_track(self):
        return self._project_points(self.track_x, self.track_y, self.track_altitude)

    def _map_to_screen(self, x_values, y_values, content, bounds):
        min_x, max_x, min_y, max_y = bounds
        x_span = max(max_x - min_x, 1e-9)
        y_span = max(max_y - min_y, 1e-9)

        pts = []
        for xv, yv in zip(x_values, y_values):
            px = content.left() + ((float(xv) - min_x) / x_span) * content.width()
            py = content.bottom() - ((float(yv) - min_y) / y_span) * content.height()
            pts.append((px, py))
        return pts

    def _render_bounds(self, content=None):
        bounds = self.view_bounds
        if bounds is None:
            return None
        if self.track_view_mode != "2d":
            return bounds

        if content is None:
            content = self._content_rect()
        width = max(float(content.width()), 1e-9)
        height = max(float(content.height()), 1e-9)

        min_x, max_x, min_y, max_y = bounds
        x_span = max(max_x - min_x, 1e-9)
        y_span = max(max_y - min_y, 1e-9)
        center_x = 0.5 * (min_x + max_x)
        center_y = 0.5 * (min_y + max_y)

        screen_aspect = width / height
        data_aspect = x_span / y_span

        if data_aspect < screen_aspect:
            x_span = y_span * screen_aspect
        else:
            y_span = x_span / screen_aspect

        return (
            center_x - 0.5 * x_span,
            center_x + 0.5 * x_span,
            center_y - 0.5 * y_span,
            center_y + 0.5 * y_span,
        )

    def _screen_to_data(self, px: float, py: float):
        content = self._content_rect()
        if not content.contains(px, py):
            return None

        bounds = self._render_bounds(content)
        if bounds is None:
            return None

        min_x, max_x, min_y, max_y = bounds
        x_span = max(max_x - min_x, 1e-9)
        y_span = max(max_y - min_y, 1e-9)
        xv = min_x + ((px - content.left()) / max(content.width(), 1e-9)) * x_span
        yv = min_y + ((content.bottom() - py) / max(content.height(), 1e-9)) * y_span
        return float(xv), float(yv)

    def wheelEvent(self, event):
        if self.track_x is None or self.track_y is None or len(self.track_x) < 2 or self.view_bounds is None:
            event.ignore()
            return

        pos = event.position()
        anchor = self._screen_to_data(pos.x(), pos.y())
        if anchor is None:
            event.ignore()
            return

        zoom_in = event.angleDelta().y() > 0
        scale = 0.85 if zoom_in else (1.0 / 0.85)
        min_x, max_x, min_y, max_y = self.view_bounds
        anchor_x, anchor_y = anchor

        new_min_x = anchor_x - (anchor_x - min_x) * scale
        new_max_x = anchor_x + (max_x - anchor_x) * scale
        new_min_y = anchor_y - (anchor_y - min_y) * scale
        new_max_y = anchor_y + (max_y - anchor_y) * scale

        if self.default_bounds is not None:
            default_min_x, default_max_x, default_min_y, default_max_y = self.default_bounds
            min_span_x = max((default_max_x - default_min_x) * 0.02, 1e-9)
            min_span_y = max((default_max_y - default_min_y) * 0.02, 1e-9)
            if (new_max_x - new_min_x) < min_span_x or (new_max_y - new_min_y) < min_span_y:
                event.accept()
                return

        self.view_bounds = (new_min_x, new_max_x, new_min_y, new_max_y)
        self.update()
        event.accept()

    def mousePressEvent(self, event):
        if event.button() != Qt.MiddleButton or self.view_bounds is None:
            super().mousePressEvent(event)
            return

        pos = event.position()
        if self._screen_to_data(pos.x(), pos.y()) is None:
            super().mousePressEvent(event)
            return

        self.drag_active = True
        self.drag_start_pos = (float(pos.x()), float(pos.y()))
        self.drag_start_bounds = tuple(self.view_bounds)
        self.setCursor(Qt.ClosedHandCursor)
        event.accept()

    def mouseMoveEvent(self, event):
        if not self.drag_active or self.drag_start_pos is None or self.drag_start_bounds is None:
            super().mouseMoveEvent(event)
            return

        content = self._content_rect()
        width = max(content.width(), 1e-9)
        height = max(content.height(), 1e-9)
        min_x, max_x, min_y, max_y = self.drag_start_bounds
        x_span = max(max_x - min_x, 1e-9)
        y_span = max(max_y - min_y, 1e-9)

        pos = event.position()
        dx_px = float(pos.x()) - self.drag_start_pos[0]
        dy_px = float(pos.y()) - self.drag_start_pos[1]
        dx_data = (dx_px / width) * x_span
        dy_data = (dy_px / height) * y_span

        self.view_bounds = (
            min_x - dx_data,
            max_x - dx_data,
            min_y + dy_data,
            max_y + dy_data,
        )
        self.update()
        event.accept()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MiddleButton and self.drag_active:
            self.drag_active = False
            self.drag_start_pos = None
            self.drag_start_bounds = None
            self.unsetCursor()
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.LeftButton and self.default_bounds is not None:
            self.view_bounds = tuple(self.default_bounds)
            self.drag_active = False
            self.drag_start_pos = None
            self.drag_start_bounds = None
            self.unsetCursor()
            self.update()
            event.accept()
            return
        super().mouseDoubleClickEvent(event)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)

        card = self._card_rect()
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor("#20252b"))
        painter.drawRoundedRect(card, 18, 18)

        projected = self._projected_track()
        if projected is None:
            return

        content = self._content_rect()
        if self.view_bounds is None:
            self._reset_view()
        if self.view_bounds is None:
            return
        render_bounds = self._render_bounds(content)
        if render_bounds is None:
            return
        projection_context = self._projection_context()
        if projection_context is None:
            return

        proj_x, proj_y, floor_x, floor_y = projected
        pts = self._map_to_screen(proj_x, proj_y, content, render_bounds)
        floor_pts = self._map_to_screen(floor_x, floor_y, content, render_bounds)

        if self.track_view_mode == "3d":
            connector_pen = QPen(QColor(104, 114, 124, 95), 1.4)
            connector_pen.setCapStyle(Qt.RoundCap)
            painter.setPen(connector_pen)
            connector_step = max(6, len(pts) // 22)
            for idx in range(0, len(pts), connector_step):
                painter.drawLine(
                    floor_pts[idx][0],
                    floor_pts[idx][1],
                    pts[idx][0],
                    pts[idx][1],
                )

        for idx in range(len(pts) - 1):
            color = QColor("#eef3f7")
            if self.segment_colors is not None and idx < len(self.segment_colors):
                color = self.segment_colors[idx]
            pen = QPen(color, 2.6)
            pen.setCapStyle(Qt.RoundCap)
            pen.setJoinStyle(Qt.RoundJoin)
            painter.setPen(pen)
            painter.drawLine(pts[idx][0], pts[idx][1], pts[idx + 1][0], pts[idx + 1][1])

        start_px, start_py = pts[0]
        end_px, end_py = pts[-1]
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor("#67d08c"))
        painter.drawEllipse(QRectF(end_px - 5, end_py - 5, 10, 10))
        painter.setBrush(QColor("#ff7272"))
        painter.drawEllipse(QRectF(start_px - 5, start_py - 5, 10, 10))

        painter.setPen(Qt.NoPen)
        for marker in self.turn_start_points:
            projected_marker = self._project_points(
                [marker[0]],
                [marker[1]],
                [marker[2]] if len(marker) >= 3 else None,
                context=projection_context,
            )
            if projected_marker is None:
                continue
            marker_pts = self._map_to_screen(projected_marker[0], projected_marker[1], content, render_bounds)
            px, py = marker_pts[0]
            painter.setBrush(QColor("#52d273"))
            painter.drawEllipse(QRectF(px - 4.5, py - 4.5, 9, 9))

        for marker in self.turn_end_points:
            projected_marker = self._project_points(
                [marker[0]],
                [marker[1]],
                [marker[2]] if len(marker) >= 3 else None,
                context=projection_context,
            )
            if projected_marker is None:
                continue
            marker_pts = self._map_to_screen(projected_marker[0], projected_marker[1], content, render_bounds)
            px, py = marker_pts[0]
            painter.setBrush(QColor("#ff6b6b"))
            painter.drawEllipse(QRectF(px - 4.5, py - 4.5, 9, 9))

        if self.current_point is not None:
            projected_current = self._project_points(
                [self.current_point[0]],
                [self.current_point[1]],
                [self.current_point[2]] if len(self.current_point) >= 3 else None,
                context=projection_context,
            )
            if projected_current is not None:
                marker_pts = self._map_to_screen(projected_current[0], projected_current[1], content, render_bounds)
                px, py = marker_pts[0]
                painter.setBrush(QColor("#f5f7fa"))
                painter.drawEllipse(QRectF(px - 4.5, py - 4.5, 9, 9))

class PlaybackViewerPage(QWidget):
    DISPLAY_COLOR_MODE = {
        "fixed": "Fixed",
        "speed": "Speed",
        "acc": "G",
        "gyro": "Gyro",
        "radius": "Radius",
    }
    PLAYBACK_TIMESTEP_S = 1.0 / 60.0

    def __init__(self, right=None, left=None, source_text=""):
        super().__init__()

        self.right_source = right
        self.left_source = left
        self.source_text = source_text

        self.intervals = []
        self.load_error = ""
        self.current_interval_index = 0
        self.max_points = 2200
        self.max_track_points = 1000
        self.use_full_resolution = False
        self.track_view_mode = "3d"

        self.current_right = None
        self.current_left = None
        self.gps_path = None
        self.current_gps_path = None
        self.turn_radius_segments = []
        self.turn_radius_series = None
        self.playback_times = np.array([], dtype=float)
        self.current_time = None
        self.interval_time_offset = 0.0

        self.color_modes = ["fixed", "speed", "acc", "gyro", "radius"]
        self.color_mode_index = 0
        self.color_mode = self.color_modes[self.color_mode_index]
        self.playback_rates = [1.0, 2.0, 0.5]
        self.playback_rate_index = 0
        self.scalar_norm = None

        self.timer = QTimer(self)
        self.timer.setInterval(16)
        self.timer.timeout.connect(self._advance_playback)
        self.elapsed_timer = QElapsedTimer()
        self.playback_start_time = None

        self.plot_cursor = None
        self.left_marker = None
        self.right_marker = None
        self.ax = None
        self.plot_pan_active = False
        self.plot_pan_anchor = None
        self.plot_pan_xlim = None
        self.plot_pan_ylim = None
        self.plot_default_xlim = None
        self.plot_default_ylim = None

        self.left_time_values = None
        self.right_time_values = None
        self.left_roll_values = None
        self.right_roll_values = None
        self.left_pitch_values = None
        self.right_pitch_values = None
        self.left_yaw_values = None
        self.right_yaw_values = None
        self.left_speed_values = None
        self.right_speed_values = None
        self.left_acc_values = None
        self.right_acc_values = None
        self.current_gps_time_values = None
        self.current_gps_longitude = None
        self.current_gps_latitude = None
        self.current_gps_altitude = None
        self.video_offset_s = 0.0
        self.video_path = None
        self.video_player = None
        self.audio_output = None
        self.video_widget = None
        self.video_placeholder = None
        self.front_view_enabled = False
        self.show_turn_separation = False

        self._load_intervals()
        self._build_ui()
        self._init_video_player()
        self.space_shortcut = QShortcut(QKeySequence(Qt.Key_Space), self)
        self.space_shortcut.setContext(Qt.WidgetWithChildrenShortcut)
        self.space_shortcut.activated.connect(self._toggle_playback)
        self._auto_load_video()
        self._load_current_interval()

    def _load_intervals(self):
        if not self.source_text:
            return

        try:
            self.intervals = load_turn_intervals(Path(self.source_text))
            self.gps_path = load_gps_path(Path(self.source_text))
            self.turn_radius_segments = load_turn_radius_segments(Path(self.source_text))
            self.turn_radius_series = load_turn_radius_timeseries(Path(self.source_text))
        except DataLoadError as exc:
            self.load_error = str(exc)
        except Exception as exc:
            self.load_error = f"Failed to load playback intervals: {exc}"

    def _build_ui(self):
        self.setStyleSheet(
            """
            QWidget {
                background-color: #1b1f24;
                color: #ecf1f6;
            }
            QPushButton {
                background-color: #27313c;
                color: #eef3f7;
                border: 1px solid #3d4a57;
                border-radius: 8px;
                outline: none;
                padding: 7px 14px;
                font-size: 13px;
                font-weight: 600;
            }
            QPushButton:hover {
                background-color: #33414e;
            }
            QPushButton:focus {
                outline: none;
                border: 1px solid #3d4a57;
            }
            QPushButton:disabled {
                color: #6f7a85;
                border-color: #313941;
            }
            QLabel {
                outline: none;
            }
            QSlider {
                outline: none;
            }
            QSlider:focus {
                outline: none;
            }
            QSlider::groove:horizontal {
                border: 1px solid #364553;
                height: 8px;
                background: #10171d;
                border-radius: 4px;
            }
            QSlider::sub-page:horizontal {
                background: #4f8cff;
                border-radius: 4px;
            }
            QSlider::handle:horizontal {
                background: #f0f6ff;
                border: 2px solid #4f8cff;
                width: 16px;
                margin: -6px 0;
                border-radius: 8px;
            }
            """
        )

        root = QVBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(8)

        top_controls_frame = QFrame()
        top_controls_frame.setStyleSheet(top_bar_frame_stylesheet(14))
        top_bar = QHBoxLayout(top_controls_frame)
        top_bar.setContentsMargins(12, 10, 12, 10)
        top_bar.setSpacing(8)

        self.btn_prev_interval = QPushButton("←")
        self.btn_prev_interval.setMinimumWidth(46)
        self.btn_prev_interval.clicked.connect(self._show_prev_interval)
        self.btn_prev_interval.setStyleSheet(neutral_button_stylesheet())

        self.btn_next_interval = QPushButton("→")
        self.btn_next_interval.setMinimumWidth(46)
        self.btn_next_interval.clicked.connect(self._show_next_interval)
        self.btn_next_interval.setStyleSheet(neutral_button_stylesheet())

        self.interval_label = QLabel("No intervals")
        self.interval_label.setMinimumWidth(110)
        self.interval_label.setAlignment(Qt.AlignCenter)
        self.interval_label.setStyleSheet(info_label_stylesheet())

        self.btn_play = QPushButton("▶")
        self.btn_play.clicked.connect(self._toggle_playback)
        self.btn_play.setMinimumWidth(46)
        self.btn_play.setStyleSheet(cursor_button_stylesheet())

        self.btn_rate = QPushButton("1x")
        self.btn_rate.clicked.connect(self._cycle_playback_rate)
        self.btn_rate.setMinimumWidth(64)
        self.btn_rate.setStyleSheet(neutral_button_stylesheet())

        self.btn_color_mode = QPushButton("Fixed")
        self.btn_color_mode.clicked.connect(self._cycle_color_mode)
        self.btn_color_mode.setMinimumWidth(86)
        self.btn_color_mode.setStyleSheet(neutral_button_stylesheet())

        self.btn_resolution = QPushButton("Low res")
        self.btn_resolution.clicked.connect(self._toggle_resolution)
        self.btn_resolution.setMinimumWidth(92)
        self.btn_resolution.setStyleSheet(neutral_button_stylesheet())

        self.btn_track_view = QPushButton("3D")
        self.btn_track_view.clicked.connect(self._toggle_track_view)
        self.btn_track_view.setMinimumWidth(72)
        self.btn_track_view.setStyleSheet(neutral_button_stylesheet())

        self.btn_view_mode = QPushButton("Rear")
        self.btn_view_mode.setCheckable(True)
        self.btn_view_mode.setChecked(False)
        self.btn_view_mode.clicked.connect(self._toggle_view_mode)
        self.btn_view_mode.setMinimumWidth(72)
        self.btn_view_mode.setStyleSheet(cursor_button_stylesheet())

        self.btn_turn_separation = QPushButton("Turn separation")
        self.btn_turn_separation.setCheckable(True)
        self.btn_turn_separation.setChecked(False)
        self.btn_turn_separation.clicked.connect(self._toggle_turn_separation)
        self.btn_turn_separation.setMinimumWidth(148)
        self.btn_turn_separation.setStyleSheet(cursor_button_stylesheet())

        self.btn_load_video = QPushButton("Load")
        self.btn_load_video.clicked.connect(self._load_video_dialog)
        self.btn_load_video.setMinimumWidth(74)
        self.btn_load_video.setStyleSheet(neutral_button_stylesheet())

        self.btn_clear_video = QPushButton("Remove")
        self.btn_clear_video.clicked.connect(self._clear_video)
        self.btn_clear_video.setMinimumWidth(84)
        self.btn_clear_video.setStyleSheet(neutral_button_stylesheet())

        self.btn_video_offset_minus = QPushButton("-")
        self.btn_video_offset_minus.clicked.connect(lambda: self._adjust_video_offset(-0.001))
        self.btn_video_offset_minus.setMinimumWidth(40)
        self.btn_video_offset_minus.setStyleSheet(neutral_button_stylesheet())

        self.video_offset_input = QLineEdit("+0.000")
        self.video_offset_input.setMinimumWidth(92)
        self.video_offset_input.setMaximumWidth(92)
        self.video_offset_input.setAlignment(Qt.AlignCenter)
        self.video_offset_input.setPlaceholderText("offset")
        self.video_offset_input.editingFinished.connect(self._commit_video_offset_input)
        self.video_offset_input.setStyleSheet(
            """
            QLineEdit {
                color: #d8dce3;
                background-color: #202228;
                border: 1px solid #3a3d45;
                border-radius: 10px;
                padding: 7px 10px;
                font-size: 13px;
                font-weight: 600;
            }
            QLineEdit:focus {
                border: 1px solid #505560;
                background-color: #24262d;
            }
            """
        )

        self.btn_video_offset_plus = QPushButton("+")
        self.btn_video_offset_plus.clicked.connect(lambda: self._adjust_video_offset(0.001))
        self.btn_video_offset_plus.setMinimumWidth(40)
        self.btn_video_offset_plus.setStyleSheet(neutral_button_stylesheet())

        self.video_status_label = QLabel("No video")
        self.video_status_label.setWordWrap(False)
        self.video_status_label.setMinimumWidth(120)
        self.video_status_label.setMaximumWidth(220)
        self.video_status_label.setStyleSheet(info_label_stylesheet())

        top_bar.addWidget(self.btn_prev_interval)
        top_bar.addWidget(self.btn_next_interval)
        top_bar.addWidget(self.interval_label)
        top_bar.addWidget(self.btn_rate)
        top_bar.addWidget(self.btn_color_mode)
        top_bar.addWidget(self.btn_resolution)
        top_bar.addWidget(self.btn_track_view)
        top_bar.addWidget(self.btn_view_mode)
        top_bar.addWidget(self.btn_turn_separation)
        top_bar.addStretch()
        top_bar.addWidget(self.btn_load_video)
        top_bar.addWidget(self.btn_clear_video)
        top_bar.addWidget(self.btn_video_offset_minus)
        top_bar.addWidget(self.video_offset_input)
        top_bar.addWidget(self.btn_video_offset_plus)
        top_bar.addWidget(self.video_status_label)

        root.addWidget(top_controls_frame)

        self.video_frame = QFrame()
        self.video_frame.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.video_frame.setMinimumHeight(300)
        self.video_frame.setStyleSheet(
            """
            QFrame {
                background-color: #20252b;
                border: 1px solid #353f49;
                border-radius: 14px;
            }
            """
        )

        video_layout = QVBoxLayout(self.video_frame)
        video_layout.setContentsMargins(10, 10, 10, 10)
        video_layout.setSpacing(0)

        video_surface = QWidget()
        video_surface.setMinimumHeight(244)
        video_surface.setStyleSheet("background: transparent; border: none;")
        surface_stack = QStackedLayout(video_surface)
        surface_stack.setContentsMargins(0, 0, 0, 0)
        surface_stack.setStackingMode(QStackedLayout.StackAll)

        if QT_VIDEO_AVAILABLE:
            self.video_widget = QVideoWidget()
            self.video_widget.setMinimumHeight(244)
            self.video_widget.setStyleSheet("background-color: #11161b; border-radius: 10px;")
            surface_stack.addWidget(self.video_widget)
        else:
            self.video_placeholder = QLabel("Qt video backend is not available in this build.")
            self.video_placeholder.setAlignment(Qt.AlignCenter)
            self.video_placeholder.setStyleSheet(
                """
                QLabel {
                    background-color: #11161b;
                    color: #94a0ad;
                    border: 1px solid #2d3640;
                    border-radius: 10px;
                    padding: 20px;
                    font-size: 13px;
                }
                """
            )
            surface_stack.addWidget(self.video_placeholder)

        video_layout.addWidget(video_surface, 1)

        self.animation_scene = SkiAnimationScene()
        self.animation_scene.setMinimumHeight(300)
        self.animation_scene.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        self.trajectory_scene = PlaybackTrajectoryScene()
        self.trajectory_scene.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        rpy_card = QWidget()
        rpy_card.setStyleSheet(
            """
            QWidget {
                background-color: #20252b;
                border: 1px solid #353f49;
                border-radius: 14px;
            }
            """
        )
        rpy_layout = QVBoxLayout(rpy_card)
        rpy_layout.setContentsMargins(10, 10, 10, 10)
        rpy_layout.setSpacing(0)

        self.figure = Figure(facecolor="#20252b")
        self.canvas = FigureCanvas(self.figure)
        self.canvas.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.canvas.setStyleSheet("background: transparent; border: none;")
        self.canvas.setMinimumHeight(280)
        self.canvas.mpl_connect("scroll_event", self._on_plot_scroll)
        self.canvas.mpl_connect("button_press_event", self._on_plot_button_press)
        self.canvas.mpl_connect("motion_notify_event", self._on_plot_mouse_move)
        self.canvas.mpl_connect("button_release_event", self._on_plot_button_release)
        rpy_layout.addWidget(self.canvas)

        content_grid = QGridLayout()
        content_grid.setContentsMargins(0, 0, 0, 0)
        content_grid.setHorizontalSpacing(14)
        content_grid.setVerticalSpacing(14)
        content_grid.addWidget(self.video_frame, 0, 0)
        content_grid.addWidget(self.animation_scene, 0, 1)
        content_grid.addWidget(self.trajectory_scene, 1, 0)
        content_grid.addWidget(rpy_card, 1, 1)
        content_grid.setColumnStretch(0, 1)
        content_grid.setColumnStretch(1, 1)
        content_grid.setRowStretch(0, 1)
        content_grid.setRowStretch(1, 1)
        root.addLayout(content_grid, 1)

        self.scene_info_label = QLabel("")
        self.scene_info_label.setStyleSheet(info_label_stylesheet())
        self.scene_info_label.setWordWrap(True)
        root.addWidget(self.scene_info_label)

        slider_frame = QFrame()
        slider_frame.setStyleSheet(top_bar_frame_stylesheet(14))
        slider_row = QHBoxLayout(slider_frame)
        slider_row.setSpacing(10)
        slider_row.setContentsMargins(12, 8, 12, 8)

        self.time_label = QLabel("t = -")
        self.time_label.setMinimumWidth(92)
        self.time_label.setStyleSheet("color: #dce7f2; font-size: 13px; font-weight: 600; background: transparent; border: none;")

        self.slider = QSlider(Qt.Horizontal)
        self.slider.setEnabled(False)
        self.slider.valueChanged.connect(self._on_slider_changed)

        self.end_time_label = QLabel("-")
        self.end_time_label.setMinimumWidth(70)
        self.end_time_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.end_time_label.setStyleSheet(
            "color: #8ea0b0; font-size: 12px; background: transparent; border: none;"
        )

        slider_row.addWidget(self.btn_play)
        slider_row.addWidget(self.time_label)
        slider_row.addWidget(self.slider, 1)
        slider_row.addWidget(self.end_time_label)

        root.addWidget(slider_frame)

    def _init_video_player(self):
        if not QT_VIDEO_AVAILABLE or self.video_widget is None:
            self.btn_load_video.setEnabled(False)
            self.btn_clear_video.setEnabled(False)
            self.btn_video_offset_minus.setEnabled(False)
            self.btn_video_offset_plus.setEnabled(False)
            self.video_offset_input.setEnabled(False)
            self.video_status_label.setText("Video: Qt multimedia backend unavailable")
            return

        self.audio_output = QAudioOutput(self)
        self.audio_output.setVolume(0.0)
        self.video_player = QMediaPlayer(self)
        self.video_player.setAudioOutput(self.audio_output)
        self.video_player.setVideoOutput(self.video_widget)
        self.video_player.setPlaybackRate(self.playback_rates[self.playback_rate_index])

    def _auto_load_video(self):
        if not QT_VIDEO_AVAILABLE or not self.source_text:
            self._refresh_video_status()
            return

        folder = Path(self.source_text)
        if not folder.exists():
            self._refresh_video_status()
            return

        candidates = []
        for pattern in ("*.mp4", "*.mov", "*.avi", "*.mkv", "*.m4v"):
            candidates.extend(sorted(folder.glob(pattern)))

        if len(candidates) == 1:
            self._set_video_source(candidates[0])
        else:
            self._refresh_video_status()

    def _load_video_dialog(self):
        start_dir = self.source_text if self.source_text else str(Path.cwd())
        file_name, _ = QFileDialog.getOpenFileName(
            self,
            "Select session video",
            start_dir,
            "Video files (*.mp4 *.mov *.avi *.mkv *.m4v);;All files (*.*)",
        )
        if file_name:
            self._set_video_source(Path(file_name))

    def _set_video_source(self, path: Path):
        if not QT_VIDEO_AVAILABLE or self.video_player is None:
            return

        self.video_path = str(path)
        self.video_player.stop()
        self.video_player.setSource(QUrl.fromLocalFile(self.video_path))
        self.video_player.setPlaybackRate(self.playback_rates[self.playback_rate_index])
        self._sync_video_to_current_time(force=True)
        self._refresh_video_status()

    def _clear_video(self):
        if self.video_player is not None:
            self.video_player.stop()
            self.video_player.setSource(QUrl())
        self.video_path = None
        self.video_offset_s = 0.0
        self._refresh_video_status()

    def _adjust_video_offset(self, delta_s: float):
        self.video_offset_s = float(np.clip(self.video_offset_s + delta_s, -30.0, 30.0))
        self._sync_video_to_current_time(force=True)
        self._refresh_video_status()

    def _commit_video_offset_input(self):
        raw = self.video_offset_input.text().strip().replace(",", ".")
        if not raw:
            self._refresh_video_status()
            return
        try:
            value = float(raw)
        except ValueError:
            self._refresh_video_status()
            return

        self.video_offset_s = float(np.clip(value, -30.0, 30.0))
        self._sync_video_to_current_time(force=True)
        self._refresh_video_status()

    def _target_video_position_ms(self):
        interval = self._current_interval()
        if interval is None or self.current_time is None:
            return None

        rel_s = float(self.current_time - interval.time_start + self.video_offset_s)
        return max(0, int(round(rel_s * 1000.0)))

    def _sync_video_to_current_time(self, *, force: bool = False):
        if not QT_VIDEO_AVAILABLE or self.video_player is None or not self.video_path:
            return

        target_ms = self._target_video_position_ms()
        if target_ms is None:
            return

        current_ms = int(self.video_player.position())
        drift_ms = abs(current_ms - target_ms)

        if force or not self.timer.isActive():
            if drift_ms > 25:
                self.video_player.setPosition(target_ms)
            return

        if drift_ms > 160:
            self.video_player.setPosition(target_ms)

    def _refresh_video_status(self):
        self.video_offset_input.setText(f"{self.video_offset_s:+.3f}")

        if not QT_VIDEO_AVAILABLE:
            self.video_status_label.setText("Video unavailable")
            return

        if self.video_path:
            self.video_status_label.setText(Path(self.video_path).name)
        else:
            self.video_status_label.setText("No video")

    def _current_interval(self):
        if not self.intervals:
            return None
        self.current_interval_index = max(0, min(self.current_interval_index, len(self.intervals) - 1))
        return self.intervals[self.current_interval_index]

    def _show_prev_interval(self):
        if self.current_interval_index <= 0:
            return
        self.current_interval_index -= 1
        self._load_current_interval()

    def _show_next_interval(self):
        if self.current_interval_index >= len(self.intervals) - 1:
            return
        self.current_interval_index += 1
        self._load_current_interval()

    def _toggle_playback(self):
        if self.playback_times.size == 0:
            return

        if self.timer.isActive():
            self.timer.stop()
            if self.video_player is not None and self.video_path:
                self.video_player.pause()
            self.btn_play.setText("▶")
            return

        if self.slider.value() >= self.slider.maximum():
            self.slider.setValue(0)

        self.playback_start_time = (
            float(self.current_time)
            if self.current_time is not None
            else float(self.playback_times[0])
        )
        self.elapsed_timer.restart()
        if self.video_player is not None and self.video_path:
            self.video_player.setPlaybackRate(self.playback_rates[self.playback_rate_index])
            self._sync_video_to_current_time(force=True)
            self.video_player.play()
        self.timer.start()
        self.btn_play.setText("⏸")

    def _cycle_playback_rate(self):
        self.playback_rate_index = (self.playback_rate_index + 1) % len(self.playback_rates)
        self.btn_rate.setText(f"{self.playback_rates[self.playback_rate_index]:g}x")
        if self.video_player is not None:
            self.video_player.setPlaybackRate(self.playback_rates[self.playback_rate_index])

    def _cycle_color_mode(self):
        self.color_mode_index = (self.color_mode_index + 1) % len(self.color_modes)
        self.color_mode = self.color_modes[self.color_mode_index]
        self.btn_color_mode.setText(self.DISPLAY_COLOR_MODE[self.color_mode])
        self.scalar_norm = self._build_scalar_norm()
        self._refresh_trajectory_scene()
        self._rebuild_plot()
        self._update_frame()

    def _toggle_view_mode(self):
        self.front_view_enabled = self.btn_view_mode.isChecked()
        self.btn_view_mode.setText("Front" if self.front_view_enabled else "Rear")
        self._update_frame(update_plot=False)

    def _toggle_turn_separation(self):
        self.show_turn_separation = self.btn_turn_separation.isChecked()
        self._refresh_trajectory_scene()
        self._rebuild_plot()
        self._update_frame(update_plot=False)

    def _toggle_resolution(self):
        self.use_full_resolution = not self.use_full_resolution
        self.btn_resolution.setText("High res" if self.use_full_resolution else "Low res")
        self._refresh_trajectory_scene()
        self._rebuild_plot()
        self._update_frame(update_plot=False)

    def _toggle_track_view(self):
        self.track_view_mode = "2d" if self.track_view_mode == "3d" else "3d"
        self.btn_track_view.setText(self.track_view_mode.upper())
        self._refresh_trajectory_scene()
        self._update_frame(update_plot=False)

    def _load_current_interval(self):
        self.timer.stop()
        if self.video_player is not None:
            self.video_player.pause()
        self.btn_play.setText("▶")
        self.playback_start_time = None

        interval = self._current_interval()
        has_intervals = interval is not None
        self.btn_prev_interval.setEnabled(has_intervals and self.current_interval_index > 0)
        self.btn_next_interval.setEnabled(has_intervals and self.current_interval_index < len(self.intervals) - 1)

        if interval is None:
            self.interval_label.setText("No intervals")
            self.current_right = None
            self.current_left = None
            self.current_gps_path = None
            self._refresh_cached_series()
            self.playback_times = np.array([], dtype=float)
            self.current_time = None
            self.interval_time_offset = 0.0
            self.slider.setEnabled(False)
            self.slider.setRange(0, 0)
            self.trajectory_scene.clear()
            self._rebuild_plot()
            self._update_frame()
            self._sync_video_to_current_time(force=True)
            return

        self.interval_label.setText(f"{interval.interval_index}/{len(self.intervals)}")
        self.interval_time_offset = float(interval.time_start)

        self.current_right = slice_ski_data_to_interval(
            self.right_source, interval.time_start, interval.time_stop
        )
        self.current_left = slice_ski_data_to_interval(
            self.left_source, interval.time_start, interval.time_stop
        )
        self.current_gps_path = slice_gps_path_to_interval(
            self.gps_path, interval.time_start, interval.time_stop
        )

        self._refresh_cached_series()
        self.playback_times = self._build_playback_timebase(interval)
        self.scalar_norm = self._build_scalar_norm()

        if self.playback_times.size:
            self.slider.setEnabled(True)
            self.slider.setRange(0, len(self.playback_times) - 1)
            self.slider.setValue(0)
        else:
            self.slider.setEnabled(False)
            self.slider.setRange(0, 0)
            self.current_time = None

        self.end_time_label.setText(
            "-" if not self.playback_times.size else f"{self._display_time(self.playback_times[-1]):.2f}s"
        )
        self._refresh_trajectory_scene()
        self._rebuild_plot()
        self._update_frame()
        self._sync_video_to_current_time(force=True)

    def _on_slider_changed(self, value: int):
        if self.playback_times.size == 0:
            self.current_time = None
        else:
            value = max(0, min(value, len(self.playback_times) - 1))
            self.current_time = float(self.playback_times[value])
            if self.timer.isActive():
                self.playback_start_time = self.current_time
                self.elapsed_timer.restart()
                self._sync_video_to_current_time(force=True)
        self._update_frame()

    def _advance_playback(self):
        if self.playback_times.size == 0:
            self.timer.stop()
            if self.video_player is not None and self.video_path:
                self.video_player.pause()
            self.btn_play.setText("▶")
            return

        if self.playback_start_time is None:
            self.playback_start_time = (
                float(self.current_time)
                if self.current_time is not None
                else float(self.playback_times[0])
            )
            self.elapsed_timer.restart()

        elapsed_s = self.elapsed_timer.elapsed() / 1000.0
        target_time = self.playback_start_time + elapsed_s * self.playback_rates[self.playback_rate_index]
        next_idx = int(np.searchsorted(self.playback_times, target_time, side="left"))

        if next_idx >= len(self.playback_times):
            next_idx = len(self.playback_times) - 1
            self.timer.stop()
            if self.video_player is not None and self.video_path:
                self.video_player.pause()
            self.btn_play.setText("▶")
            self.playback_start_time = None
        self.current_time = float(self.playback_times[next_idx])
        self.slider.blockSignals(True)
        self.slider.setValue(next_idx)
        self.slider.blockSignals(False)
        self._update_frame(update_plot=True)

    def _rebuild_plot(self):
        self.figure.clear()
        self.ax = self.figure.add_subplot(111)
        self.plot_pan_active = False
        self.plot_pan_anchor = None
        self.plot_pan_xlim = None
        self.plot_pan_ylim = None

        self.ax.set_facecolor("#20252b")
        self.ax.grid(True, color="#3a3a3a", alpha=0.85, linewidth=0.8)
        self.ax.tick_params(colors="#d8d8d8", labelsize=8)
        for spine in self.ax.spines.values():
            spine.set_color("#555555")
        self.ax.axhline(0, color="#7a7a7a", linewidth=1.0)
        self.ax.set_ylabel("roll [deg]", color="#eaeaea")
        self.ax.set_xlabel("relative time [s]", color="#eaeaea")

        interval = self._current_interval()
        if self.current_left is not None and self.left_roll_values is not None:
            left_t = self._display_array(self.current_left.time)
            self._plot_series(
                self.current_left,
                self.ax,
                left_t,
                self.left_roll_values,
                "#ff9a3d",
            )
            self.left_marker, = self.ax.plot([], [], "o", color="#ff9a3d", markersize=6.0)
        else:
            self.left_marker = None

        if self.current_right is not None and self.right_roll_values is not None:
            right_t = self._display_array(self.current_right.time)
            self._plot_series(
                self.current_right,
                self.ax,
                right_t,
                self.right_roll_values,
                "#5aa9ff",
            )
            self.right_marker, = self.ax.plot([], [], "o", color="#5aa9ff", markersize=6.0)
        else:
            self.right_marker = None

        if self.current_left is None and self.current_right is None:
            self.ax.text(
                0.5,
                0.5,
                self.load_error or "No interval data available for playback.",
                transform=self.ax.transAxes,
                ha="center",
                va="center",
                color="#d0d7df",
                fontsize=12,
            )

        if interval is not None:
            self.ax.set_xlim(0.0, float(interval.time_stop - interval.time_start))

        if self.show_turn_separation and interval is not None:
            for bound_index, (start_t, stop_t) in enumerate(getattr(interval, "turn_bounds", [])):
                start_label = "Turn start" if bound_index == 0 else "_nolegend_"
                stop_label = "Turn end" if bound_index == 0 else "_nolegend_"
                self.ax.axvline(
                    self._display_time(start_t),
                    color="#52d273",
                    linestyle="--",
                    linewidth=1.0,
                    alpha=0.85,
                    label=start_label,
                )
                self.ax.axvline(
                    self._display_time(stop_t),
                    color="#ff6b6b",
                    linestyle="--",
                    linewidth=1.0,
                    alpha=0.85,
                    label=stop_label,
                )

        self.plot_cursor = self.ax.axvline(0, color="#9dd8ff", linewidth=1.8, alpha=0.95)
        self.plot_default_xlim = tuple(self.ax.get_xlim())
        self.plot_default_ylim = tuple(self.ax.get_ylim())
        self.figure.subplots_adjust(left=0.10, right=0.985, top=0.95, bottom=0.16)
        self.canvas.draw_idle()

    def _zoom_limits(self, limits, center, scale):
        lower, upper = float(limits[0]), float(limits[1])
        center = float(center)
        new_lower = center - (center - lower) * scale
        new_upper = center + (upper - center) * scale
        if abs(new_upper - new_lower) < 1e-9:
            return limits
        return (new_lower, new_upper)

    def _on_plot_scroll(self, event):
        if self.ax is None or event.inaxes is not self.ax or event.xdata is None or event.ydata is None:
            return

        scale = 0.85 if event.button == "up" else (1.0 / 0.85)
        self.ax.set_xlim(self._zoom_limits(self.ax.get_xlim(), event.xdata, scale))
        self.ax.set_ylim(self._zoom_limits(self.ax.get_ylim(), event.ydata, scale))
        self.canvas.draw_idle()

    def _on_plot_button_press(self, event):
        if self.ax is None or event.inaxes is not self.ax:
            return
        if event.dblclick:
            if self.plot_default_xlim is not None:
                self.ax.set_xlim(self.plot_default_xlim)
            if self.plot_default_ylim is not None:
                self.ax.set_ylim(self.plot_default_ylim)
            self.canvas.draw_idle()
            return
        if event.button != 2:
            return
        if event.xdata is None or event.ydata is None:
            return

        self.plot_pan_active = True
        self.plot_pan_anchor = (float(event.xdata), float(event.ydata))
        self.plot_pan_xlim = tuple(self.ax.get_xlim())
        self.plot_pan_ylim = tuple(self.ax.get_ylim())
        self.canvas.setCursor(Qt.ClosedHandCursor)

    def _on_plot_mouse_move(self, event):
        if (
            not self.plot_pan_active
            or self.ax is None
            or event.inaxes is not self.ax
            or event.xdata is None
            or event.ydata is None
            or self.plot_pan_anchor is None
            or self.plot_pan_xlim is None
            or self.plot_pan_ylim is None
        ):
            return

        dx = float(event.xdata) - self.plot_pan_anchor[0]
        dy = float(event.ydata) - self.plot_pan_anchor[1]
        self.ax.set_xlim(self.plot_pan_xlim[0] - dx, self.plot_pan_xlim[1] - dx)
        self.ax.set_ylim(self.plot_pan_ylim[0] - dy, self.plot_pan_ylim[1] - dy)
        self.canvas.draw_idle()

    def _on_plot_button_release(self, event):
        if event.button != 2:
            return
        self.plot_pan_active = False
        self.plot_pan_anchor = None
        self.plot_pan_xlim = None
        self.plot_pan_ylim = None
        self.canvas.unsetCursor()

    def _update_frame(self, update_plot: bool = True):
        interval = self._current_interval()
        interval_name = "No interval" if interval is None else f"Interval {interval.interval_index}"

        left_roll = self._value_at_time(self.current_left, "roll", self.current_time)
        right_roll = self._value_at_time(self.current_right, "roll", self.current_time)

        left_scalar = self._scalar_at_time(self.current_left, self.current_time)
        right_scalar = self._scalar_at_time(self.current_right, self.current_time)

        left_color = self._ski_color(left_scalar, side="left")
        right_color = self._ski_color(right_scalar, side="right")
        active_turn_bounds = self._active_turn_bounds()

        self.animation_scene.set_state(
            left_roll=left_roll,
            right_roll=right_roll,
            left_color=left_color,
            right_color=right_color,
            mirror_view=self.front_view_enabled,
            show_turn_separation=self.show_turn_separation,
            active_turn_start=None if active_turn_bounds is None else self._display_time(active_turn_bounds[0]),
            active_turn_stop=None if active_turn_bounds is None else self._display_time(active_turn_bounds[1]),
            current_time=self._display_time(self.current_time),
        )

        display_time = self._display_time(self.current_time)
        self.time_label.setText("t = -" if display_time is None else f"t = {display_time:.2f}s")
        left_roll_text = "-" if left_roll is None else f"{left_roll:.1f} deg"
        right_roll_text = "-" if right_roll is None else f"{right_roll:.1f} deg"
        color_mode_text = self.DISPLAY_COLOR_MODE[self.color_mode]
        gradient_parts = [
            part
            for part in (
                self._scalar_text(left_scalar, side="L"),
                self._scalar_text(right_scalar, side="R"),
            )
            if part
        ]
        gradient_text = ""
        if gradient_parts:
            gradient_text = "   |   " + "Gradient: " + "   ".join(gradient_parts)
        turn_text = ""
        if self.show_turn_separation:
            if active_turn_bounds is None:
                turn_text = "   |   Turn separation: off-turn"
            else:
                turn_text = (
                    f"   |   Turn separation: {self._display_time(active_turn_bounds[0]):.2f}s"
                    f" -> {self._display_time(active_turn_bounds[1]):.2f}s"
                )
        self.scene_info_label.setText(
            f"{interval_name}   |   t = {'-' if display_time is None else f'{display_time:.2f} s'}   |   "
            f"Left roll: {left_roll_text}   |   Right roll: {right_roll_text}   |   "
            f"Color mode: {color_mode_text}   |   View: {'front' if self.front_view_enabled else 'rear'}   |   "
            f"Video offset: {self.video_offset_s:+.2f}s"
            f"{turn_text}"
            f"{gradient_text}"
        )
        self._update_trajectory_marker()
        self._sync_video_to_current_time(force=not self.timer.isActive())
        if update_plot:
            self._update_plot_cursor()

    def _update_plot_cursor(self):
        if self.ax is None or self.plot_cursor is None:
            return

        x_value = 0.0 if self.current_time is None else self._display_time(self.current_time)
        self.plot_cursor.set_xdata([x_value, x_value])

        left_scalar = self._scalar_at_time(self.current_left, self.current_time)
        right_scalar = self._scalar_at_time(self.current_right, self.current_time)

        value = self._value_at_time(self.current_left, "roll", self.current_time)
        if self.left_marker is not None:
            if value is None:
                self.left_marker.set_data([], [])
            else:
                self.left_marker.set_data([x_value], [value])
                self.left_marker.set_color(self._marker_color("left", left_scalar))

        value = self._value_at_time(self.current_right, "roll", self.current_time)
        if self.right_marker is not None:
            if value is None:
                self.right_marker.set_data([], [])
            else:
                self.right_marker.set_data([x_value], [value])
                self.right_marker.set_color(self._marker_color("right", right_scalar))

        self.canvas.draw_idle()

    def _display_time(self, time_value):
        if time_value is None:
            return None
        return float(time_value - self.interval_time_offset)

    def _display_array(self, values):
        array = np.asarray(values, dtype=float)
        return array - self.interval_time_offset

    def _build_playback_timebase(self, interval) -> np.ndarray:
        if interval is None:
            return np.array([], dtype=float)

        start = float(interval.time_start)
        stop = float(interval.time_stop)
        if stop <= start:
            return np.array([start], dtype=float)

        step = self.PLAYBACK_TIMESTEP_S
        playback_times = np.arange(start, stop + step * 0.5, step, dtype=float)
        if playback_times.size == 0 or playback_times[-1] < stop:
            playback_times = np.append(playback_times, stop)
        else:
            playback_times[-1] = stop
        return playback_times

    def _value_at_time(self, ski, attr: str, time_value):
        if ski is None or time_value is None:
            return None

        if ski is self.current_left:
            x = self.left_time_values
            value_map = {
                "roll": self.left_roll_values,
                "pitch": self.left_pitch_values,
                "yaw": self.left_yaw_values,
            }
            values = value_map.get(attr)
        elif ski is self.current_right:
            x = self.right_time_values
            value_map = {
                "roll": self.right_roll_values,
                "pitch": self.right_pitch_values,
                "yaw": self.right_yaw_values,
            }
            values = value_map.get(attr)
        else:
            x = np.asarray(ski.time, dtype=float)
            values = np.asarray(getattr(ski, attr), dtype=float)

        if x is None or values is None or len(x) == 0:
            return None

        if len(x) == 1:
            return float(values[0])
        return float(np.interp(time_value, x, values))

    def _scalar_series(self, ski):
        if ski is None:
            return None

        if self.color_mode == "speed":
            if ski is self.current_left:
                return self.left_speed_values
            if ski is self.current_right:
                return self.right_speed_values
            if ski.speed is None:
                return None
            values = np.asarray(ski.speed, dtype=float).reshape(-1)
            return values if len(values) == len(ski.time) else None

        if self.color_mode == "acc":
            if ski is self.current_left:
                return self.left_acc_values
            if ski is self.current_right:
                return self.right_acc_values
            if ski.acc is None:
                return None
            acc = np.asarray(ski.acc, dtype=float)
            if acc.ndim == 2 and acc.shape[1] >= 3:
                values = np.linalg.norm(acc[:, :3], axis=1) / 9.80665
            else:
                values = np.abs(acc).reshape(-1) / 9.80665
            return values if len(values) == len(ski.time) else None

        if self.color_mode == "gyro":
            return get_scalar_data(ski, "gyro")

        if self.color_mode == "radius":
            scalar = sample_turn_radius_series(
                self.turn_radius_series,
                np.asarray(getattr(ski, "time", []), dtype=float),
            )
            if scalar is not None:
                return scalar
            return sample_turn_radius_segments(
                self.turn_radius_segments,
                np.asarray(getattr(ski, "time", []), dtype=float),
            )

        return None

    def _make_segments(self, x, y):
        points = np.array([x, y]).T.reshape(-1, 1, 2)
        return np.concatenate([points[:-1], points[1:]], axis=1)

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

    def _plot_series(self, ski, ax, x_values, y_values, fixed_color):
        scalar = self._scalar_series(ski)
        x_values, y_values, scalar = self._decimate_xy(x_values, y_values, scalar)
        if self.color_mode == "fixed" or scalar is None or self.scalar_norm is None or len(x_values) < 2:
            ax.plot(x_values, y_values, color=fixed_color, linewidth=1.9)
            return

        scalar = np.asarray(scalar, dtype=float)
        if np.isnan(scalar).any():
            ax.plot(x_values, y_values, color="#cfd4da", linewidth=1.15, alpha=0.55)
        segments = self._make_segments(x_values, y_values)
        cseg = 0.5 * (scalar[:-1] + scalar[1:])
        cseg = np.ma.masked_invalid(cseg)

        line = LineCollection(
            segments,
            cmap=SCALAR_CMAP,
            norm=self.scalar_norm,
            linewidth=2.2,
        )
        line.set_array(cseg)
        ax.add_collection(line)
        ax.autoscale_view()

    def _scalar_at_time(self, ski, time_value):
        values = self._scalar_series(ski)
        if values is None or time_value is None:
            return None

        if ski is self.current_left:
            x = self.left_time_values
        elif ski is self.current_right:
            x = self.right_time_values
        else:
            x = np.asarray(ski.time, dtype=float)
        if x is None or x.size == 0:
            return None
        if len(x) == 1:
            return float(values[0])
        if self.color_mode == "radius":
            radius_value = lookup_turn_radius_series_at_time(self.turn_radius_series, time_value)
            if radius_value is not None:
                return radius_value
            return lookup_turn_radius_at_time(self.turn_radius_segments, time_value)
        return float(np.interp(time_value, x, values))

    def _refresh_cached_series(self):
        self.left_time_values = self._time_values(self.current_left)
        self.right_time_values = self._time_values(self.current_right)
        self.left_roll_values = self._attr_values(self.current_left, "roll")
        self.right_roll_values = self._attr_values(self.current_right, "roll")
        self.left_pitch_values = self._attr_values(self.current_left, "pitch")
        self.right_pitch_values = self._attr_values(self.current_right, "pitch")
        self.left_yaw_values = self._attr_values(self.current_left, "yaw")
        self.right_yaw_values = self._attr_values(self.current_right, "yaw")
        self.left_speed_values = self._speed_values(self.current_left)
        self.right_speed_values = self._speed_values(self.current_right)
        self.left_acc_values = self._acc_values(self.current_left)
        self.right_acc_values = self._acc_values(self.current_right)
        self.current_gps_time_values = self._gps_values(self.current_gps_path, "time")
        self.current_gps_longitude = self._gps_values(self.current_gps_path, "longitude")
        self.current_gps_latitude = self._gps_values(self.current_gps_path, "latitude")
        self.current_gps_altitude = self._gps_values(self.current_gps_path, "altitude_m")

    def _time_values(self, ski):
        if ski is None:
            return None
        values = np.asarray(ski.time, dtype=float).reshape(-1)
        return values if len(values) else None

    def _attr_values(self, ski, attr: str):
        if ski is None:
            return None
        values = np.asarray(getattr(ski, attr), dtype=float).reshape(-1)
        return values if len(values) else None

    def _speed_values(self, ski):
        if ski is None or ski.speed is None:
            return None
        values = np.asarray(ski.speed, dtype=float).reshape(-1)
        return values if len(values) == len(ski.time) else None

    def _acc_values(self, ski):
        return get_scalar_data(ski, "acc")

    def _gps_values(self, gps_path, attr: str):
        if gps_path is None:
            return None
        values = getattr(gps_path, attr, None)
        if values is None:
            return None
        values = np.asarray(values, dtype=float).reshape(-1)
        return values if len(values) else None

    def _nearest_index(self, x: np.ndarray, time_value: float) -> int:
        idx = int(np.searchsorted(x, time_value, side="left"))
        if idx <= 0:
            return 0
        if idx >= len(x):
            return len(x) - 1
        prev_idx = idx - 1
        if abs(x[idx] - time_value) < abs(time_value - x[prev_idx]):
            return idx
        return prev_idx

    def _build_scalar_norm(self):
        if self.color_mode == "radius":
            norm = build_turn_radius_series_norm(self.turn_radius_series)
            if norm is not None:
                return norm
            return build_turn_radius_norm(self.turn_radius_segments)
        skis = []
        if self.left_source is not None:
            skis.append(self.left_source)
        if self.right_source is not None:
            skis.append(self.right_source)

        return build_shared_scalar_norm(skis, self.color_mode)

    def _get_track_speed_norm(self):
        skis = []
        if self.left_source is not None:
            skis.append(self.left_source)
        if self.right_source is not None:
            skis.append(self.right_source)

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
            return (
                get_gps_accuracy_data(self.current_gps_path),
                build_gps_accuracy_norm(self.current_gps_path),
            )

        if self.color_mode == "speed":
            if self.current_gps_path is None or self.current_gps_path.speed_kmh is None:
                return None, None
            return (
                np.asarray(self.current_gps_path.speed_kmh, dtype=float).reshape(-1),
                self._get_track_speed_norm(),
            )

        if self.color_mode == "acc":
            series_list = []
            for ski in (self.current_left, self.current_right):
                if ski is not None:
                    series_list.append(interpolate_scalar_to_time(ski, "acc", target_time))

            scalar = combine_scalar_series(series_list)
            norm = build_shared_scalar_norm(
                [ski for ski in (self.left_source, self.right_source) if ski is not None],
                "acc",
            )
            return scalar, norm

        if self.color_mode == "gyro":
            series_list = []
            for ski in (self.current_left, self.current_right):
                if ski is not None:
                    series_list.append(interpolate_scalar_to_time(ski, "gyro", target_time))

            scalar = combine_scalar_series(series_list)
            norm = build_shared_scalar_norm(
                [ski for ski in (self.left_source, self.right_source) if ski is not None],
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

    def _refresh_trajectory_scene(self):
        if (
            self.current_gps_longitude is None
            or self.current_gps_latitude is None
            or len(self.current_gps_longitude) < 2
        ):
            self.trajectory_scene.clear()
            return

        segment_colors = None
        scalar, norm = self._get_track_scalar_data(self.current_gps_time_values)
        track_cmap = GPS_ACCURACY_CMAP if self.color_mode == "fixed" else SCALAR_CMAP
        longitude = np.asarray(self.current_gps_longitude, dtype=float)
        latitude = np.asarray(self.current_gps_latitude, dtype=float)
        altitude = (
            None
            if self.current_gps_altitude is None
            else np.asarray(self.current_gps_altitude, dtype=float)
        )
        longitude, latitude, altitude, scalar = self._decimate_track_xy(longitude, latitude, altitude, scalar)
        if scalar is not None and norm is not None and len(scalar) >= 2:
            scalar = np.asarray(scalar, dtype=float)
            cseg = np.ma.masked_invalid(0.5 * (scalar[:-1] + scalar[1:]))
            segment_colors = []
            for value in cseg:
                if np.ma.is_masked(value) or not np.isfinite(float(np.ma.filled(value, np.nan))):
                    segment_colors.append(QColor("#cfd4da"))
                    continue
                rgba = colormaps[track_cmap](float(norm(value)))
                segment_colors.append(QColor.fromRgbF(rgba[0], rgba[1], rgba[2], 1.0))

        self.trajectory_scene.set_track(
            longitude,
            latitude,
            altitude_values=altitude,
            segment_colors=segment_colors,
        )
        self.trajectory_scene.set_track_view_mode(self.track_view_mode)
        if self.show_turn_separation:
            self.trajectory_scene.set_turn_markers(
                self._track_turn_markers(marker_kind="start"),
                self._track_turn_markers(marker_kind="end"),
            )
        else:
            self.trajectory_scene.set_turn_markers([], [])
        self._update_trajectory_marker()

    def _active_turn_bounds(self):
        interval = self._current_interval()
        if interval is None or self.current_time is None:
            return None

        for start_t, stop_t in getattr(interval, "turn_bounds", []):
            if float(start_t) <= float(self.current_time) <= float(stop_t):
                return float(start_t), float(stop_t)
        return None

    def _track_turn_markers(self, *, marker_kind: str):
        interval = self._current_interval()
        if (
            interval is None
            or self.current_gps_time_values is None
            or self.current_gps_longitude is None
            or self.current_gps_latitude is None
            or self.current_gps_altitude is None
            or len(self.current_gps_time_values) < 2
        ):
            return []

        gps_time = np.asarray(self.current_gps_time_values, dtype=float)
        longitude = np.asarray(self.current_gps_longitude, dtype=float)
        latitude = np.asarray(self.current_gps_latitude, dtype=float)
        altitude = np.asarray(self.current_gps_altitude, dtype=float)
        bounds = getattr(interval, "turn_bounds", [])

        points = []
        for start_t, stop_t in bounds:
            time_value = float(start_t if marker_kind == "start" else stop_t)
            if not (gps_time[0] <= time_value <= gps_time[-1]):
                continue
            xv = float(np.interp(time_value, gps_time, longitude))
            yv = float(np.interp(time_value, gps_time, latitude))
            zv = float(np.interp(time_value, gps_time, altitude))
            points.append((xv, yv, zv))
        return points

    def _track_point_at_time(self, time_value):
        if (
            time_value is None
            or self.current_gps_time_values is None
            or self.current_gps_longitude is None
            or self.current_gps_latitude is None
            or self.current_gps_altitude is None
            or len(self.current_gps_time_values) == 0
        ):
            return None

        if len(self.current_gps_time_values) == 1:
            return (
                float(self.current_gps_longitude[0]),
                float(self.current_gps_latitude[0]),
                float(self.current_gps_altitude[0]),
            )

        return (
            float(np.interp(time_value, self.current_gps_time_values, self.current_gps_longitude)),
            float(np.interp(time_value, self.current_gps_time_values, self.current_gps_latitude)),
            float(np.interp(time_value, self.current_gps_time_values, self.current_gps_altitude)),
        )

    def _update_trajectory_marker(self):
        self.trajectory_scene.set_current_point(self._track_point_at_time(self.current_time))

    def _ski_color(self, scalar_value, *, side: str) -> QColor:
        if self.color_mode == "fixed" or scalar_value is None or self.scalar_norm is None:
            return QColor("#ff9a3d") if side == "left" else QColor("#5aa9ff")

        rgba = colormaps[SCALAR_CMAP](float(self.scalar_norm(scalar_value)))
        return QColor.fromRgbF(rgba[0], rgba[1], rgba[2], 1.0)

    def _mpl_color(self, color: QColor):
        return (
            color.redF(),
            color.greenF(),
            color.blueF(),
            color.alphaF(),
        )

    def _marker_color(self, side: str, scalar_value):
        if self.color_mode == "fixed":
            return "#ff9a3d" if side == "left" else "#5aa9ff"
        return self._mpl_color(self._ski_color(scalar_value, side=side))

    def _scalar_text(self, scalar_value, *, side: str) -> str:
        if scalar_value is None or self.color_mode == "fixed":
            return ""

        if self.color_mode == "speed":
            return f"{side}: {scalar_value:.1f} km/h"
        if self.color_mode == "acc":
            return f"{side}: {scalar_value:.2f} G"
        if self.color_mode == "gyro":
            return f"{side}: {scalar_value:.1f} deg/s"
        if self.color_mode == "radius":
            return f"{side}: {scalar_value:.1f} m"
        return ""
