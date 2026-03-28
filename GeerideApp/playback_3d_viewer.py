import json
from pathlib import Path

import numpy as np
from matplotlib import colormaps
from matplotlib.colors import Normalize

from PySide6.QtCore import QUrl, Qt
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)
from ui_theme import info_label_stylesheet, neutral_button_stylesheet, top_bar_frame_stylesheet

from data_loader import (
    DataLoadError,
    GpsPath,
    detect_gps_runs,
    load_gps_path,
    load_turn_intervals,
    slice_gps_path_to_interval,
)
from scalar_color import GPS_ACCURACY_CMAP, build_gps_accuracy_norm

SPEED_COLOR_VMIN_KMH = 0.0
SPEED_COLOR_VMAX_KMH = 100.0

try:
    from PySide6.QtWebEngineWidgets import QWebEngineView

    QT_WEBENGINE_AVAILABLE = True
except Exception:
    QWebEngineView = None
    QT_WEBENGINE_AVAILABLE = False


def _downsample_path(gps_path: GpsPath | None, max_points: int) -> list[list[float]]:
    if gps_path is None:
        return []

    latitude = np.asarray(gps_path.latitude, dtype=float)
    longitude = np.asarray(gps_path.longitude, dtype=float)
    if latitude.size == 0 or longitude.size == 0:
        return []

    n = min(len(latitude), len(longitude))
    if n <= 0:
        return []

    if n <= max_points:
        idx = np.arange(n, dtype=int)
    else:
        idx = np.linspace(0, n - 1, num=max_points, dtype=int)
        idx = np.unique(idx)

    return [[float(latitude[i]), float(longitude[i])] for i in idx]


def _speed_norm(gps_path: GpsPath | None) -> Normalize | None:
    if gps_path is None or gps_path.speed_kmh is None:
        return None

    speed = np.asarray(gps_path.speed_kmh, dtype=float).reshape(-1)
    speed = speed[np.isfinite(speed)]
    if speed.size < 2:
        return None

    return Normalize(vmin=SPEED_COLOR_VMIN_KMH, vmax=SPEED_COLOR_VMAX_KMH)


def _accuracy_norm(gps_path: GpsPath | None) -> Normalize | None:
    return build_gps_accuracy_norm(gps_path)


def _downsample_indices(length: int, max_points: int) -> np.ndarray:
    if length <= 0:
        return np.array([], dtype=int)
    if length <= max_points:
        return np.arange(length, dtype=int)
    idx = np.linspace(0, length - 1, num=max_points, dtype=int)
    return np.unique(idx)


def _route_payload(
    gps_path: GpsPath | None,
    max_points: int,
    *,
    norm: Normalize | None = None,
    metric: str | None = None,
):
    if gps_path is None:
        return {"coords": [], "segmentColors": [], "speed": [], "altitude": [], "accuracy": []}

    latitude = np.asarray(gps_path.latitude, dtype=float)
    longitude = np.asarray(gps_path.longitude, dtype=float)
    if latitude.size == 0 or longitude.size == 0:
        return {"coords": [], "segmentColors": [], "speed": [], "altitude": [], "accuracy": []}

    n = min(len(latitude), len(longitude))
    latitude = latitude[:n]
    longitude = longitude[:n]

    valid = (
        np.isfinite(latitude)
        & np.isfinite(longitude)
        & (np.abs(latitude) <= 90.0)
        & (np.abs(longitude) <= 180.0)
    )
    if not np.any(valid):
        return {"coords": [], "segmentColors": [], "speed": [], "altitude": [], "accuracy": []}

    latitude = latitude[valid]
    longitude = longitude[valid]
    n = len(latitude)
    if n < 2:
        return {"coords": [], "segmentColors": [], "speed": [], "altitude": [], "accuracy": []}

    idx = _downsample_indices(n, max_points)
    coords = [[float(latitude[i]), float(longitude[i])] for i in idx]
    speed_values: list[float | None] = []
    altitude_values: list[float | None] = []
    accuracy_values: list[float | None] = []

    if gps_path.speed_kmh is not None:
        speed = np.asarray(gps_path.speed_kmh, dtype=float).reshape(-1)[: len(valid)][valid]
        speed_values = [None if not np.isfinite(speed[i]) else float(speed[i]) for i in idx]
    else:
        speed_values = [None for _ in idx]

    if gps_path.altitude_m is not None:
        altitude = np.asarray(gps_path.altitude_m, dtype=float).reshape(-1)[: len(valid)][valid]
        altitude_values = [None if not np.isfinite(altitude[i]) else float(altitude[i]) for i in idx]
    else:
        altitude_values = [None for _ in idx]

    if gps_path.accuracy_m is not None:
        accuracy = np.asarray(gps_path.accuracy_m, dtype=float).reshape(-1)[: len(valid)][valid]
        accuracy_values = [None if not np.isfinite(accuracy[i]) else float(accuracy[i]) for i in idx]
    else:
        accuracy_values = [None for _ in idx]

    segment_colors: list[str] = []
    if norm is not None and len(idx) >= 2:
        series = None
        cmap_name = "turbo"
        if metric == "accuracy" and gps_path.accuracy_m is not None:
            series = np.asarray(gps_path.accuracy_m, dtype=float).reshape(-1)[: len(valid)][valid]
            cmap_name = GPS_ACCURACY_CMAP
        elif metric == "speed" and gps_path.speed_kmh is not None:
            series = np.asarray(gps_path.speed_kmh, dtype=float).reshape(-1)[: len(valid)][valid]

        if series is not None:
            for start, stop in zip(idx[:-1], idx[1:]):
                value = float(np.nanmean(series[start : stop + 1]))
                rgba = colormaps[cmap_name](float(norm(value)))
                segment_colors.append(
                    "#{:02x}{:02x}{:02x}".format(
                        int(round(rgba[0] * 255)),
                        int(round(rgba[1] * 255)),
                        int(round(rgba[2] * 255)),
                    )
                )

    return {
        "coords": coords,
        "segmentColors": segment_colors,
        "speed": speed_values,
        "altitude": altitude_values,
        "accuracy": accuracy_values,
    }


def _gps_distance_km(gps_path: GpsPath | None) -> float:
    if gps_path is None:
        return 0.0

    latitude = np.asarray(gps_path.latitude, dtype=float)
    longitude = np.asarray(gps_path.longitude, dtype=float)
    n = min(len(latitude), len(longitude))
    if n < 2:
        return 0.0

    earth_radius_m = 6371000.0
    lat_rad = np.deg2rad(latitude[:n])
    lon_rad = np.deg2rad(longitude[:n])
    dlat = np.diff(lat_rad)
    dlon = np.diff(lon_rad)
    a = np.sin(dlat / 2.0) ** 2 + np.cos(lat_rad[:-1]) * np.cos(lat_rad[1:]) * np.sin(dlon / 2.0) ** 2
    c = 2.0 * np.arctan2(np.sqrt(a), np.sqrt(1.0 - a))
    return float(np.sum(earth_radius_m * c) / 1000.0)


def _gps_drop_m(gps_path: GpsPath | None) -> float:
    if gps_path is None or gps_path.altitude_m is None:
        return 0.0

    altitude = np.asarray(gps_path.altitude_m, dtype=float)
    altitude = altitude[np.isfinite(altitude)]
    if altitude.size < 2:
        return 0.0

    return float(altitude[0] - altitude[-1])


def _optional_float(value) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None

    if not np.isfinite(number):
        return None
    return number


class TrackMapScene(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)

        self.full_route: dict = {"coords": [], "segmentColors": []}
        self.run_route: dict = {"coords": [], "segmentColors": []}
        self.show_full_route = False
        self.color_mode = "fixed"

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        if QT_WEBENGINE_AVAILABLE:
            self.web_view = QWebEngineView()
            self.web_view.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
            layout.addWidget(self.web_view)
            self.placeholder = None
        else:
            self.web_view = None
            self.placeholder = QLabel("Qt WebEngine is not available, so the map cannot be shown.")
            self.placeholder.setAlignment(Qt.AlignCenter)
            self.placeholder.setWordWrap(True)
            self.placeholder.setStyleSheet(
                """
                QLabel {
                    background-color: #20252b;
                    color: #cfd8e1;
                    border: 1px solid #353f49;
                    border-radius: 10px;
                    padding: 20px;
                    font-size: 13px;
                }
                """
            )
            layout.addWidget(self.placeholder)

    def reset_view(self):
        self._render()

    def set_view_options(self, *, show_full_route: bool, color_mode: str):
        self.show_full_route = bool(show_full_route)
        self.color_mode = color_mode
        self._render()

    def set_tracks(self, gps_path: GpsPath | None, run_path: GpsPath | None = None):
        metric = "speed" if self.color_mode == "speed" else "accuracy"
        norm = _speed_norm(gps_path) if metric == "speed" else _accuracy_norm(gps_path)
        self.full_route = _route_payload(
            gps_path,
            5000,
            norm=norm,
            metric=metric,
        )
        self.run_route = _route_payload(
            run_path,
            1800,
            norm=norm,
            metric=metric,
        )
        self._render()

    def update_map(
        self,
        *,
        gps_path: GpsPath | None,
        run_path: GpsPath | None,
        show_full_route: bool,
        color_mode: str,
    ):
        self.show_full_route = bool(show_full_route)
        self.color_mode = color_mode

        metric = "speed" if self.color_mode == "speed" else "accuracy"
        norm = _speed_norm(gps_path) if metric == "speed" else _accuracy_norm(gps_path)
        self.full_route = _route_payload(
            gps_path,
            5000,
            norm=norm,
            metric=metric,
        )
        self.run_route = _route_payload(
            run_path,
            1800,
            norm=norm,
            metric=metric,
        )
        self._render()

    def _render(self):
        if self.web_view is None:
            return
        self.web_view.setHtml(self._build_html(), QUrl("https://leafletjs.com/"))

    def _build_html(self) -> str:
        full_route_json = json.dumps(self.full_route)
        run_route_json = json.dumps(self.run_route)
        active_route = self.full_route if self.show_full_route else self.run_route
        active_coords = active_route["coords"]
        marker_coords = active_coords
        if self.show_full_route and self.run_route["coords"]:
            marker_coords = self.run_route["coords"]
        start_json = json.dumps(marker_coords[0] if marker_coords else None)
        end_json = json.dumps(marker_coords[-1] if marker_coords else None)
        show_full_json = json.dumps(self.show_full_route)
        color_mode_json = json.dumps(self.color_mode)

        return f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <link
    rel="stylesheet"
    href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"
    integrity="sha256-p4NxAoJBhIIN+hmNHrzRCf9tD/miZyoHS5obTRR9BMY="
    crossorigin=""
  />
  <style>
    html, body, #map {{
      width: 100%;
      height: 100%;
      margin: 0;
      background: #1b1f24;
    }}
    .leaflet-control-attribution {{
      background: rgba(27, 31, 36, 0.85);
      color: #d0d7df;
      font-size: 10px;
    }}
    .leaflet-control-zoom a {{
      background: #20252b;
      color: #eef3f7;
      border-bottom: 1px solid #353f49;
    }}
  </style>
</head>
<body>
  <div id="map"></div>
  <script
    src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"
    integrity="sha256-20nQCchB9co0qIjJZRGuk2/Z9VM+kNiyxNV1lvTlZBo="
    crossorigin=""
  ></script>
  <script>
    const fullRoute = {full_route_json};
    const runRoute = {run_route_json};
    const runStart = {start_json};
    const runEnd = {end_json};
    const showFullRoute = {show_full_json};
    const colorMode = {color_mode_json};

    const map = L.map('map', {{
      zoomControl: true,
      attributionControl: true
    }});

    const imagery = L.tileLayer(
      'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{{z}}/{{y}}/{{x}}',
      {{
        maxZoom: 19,
        attribution: 'Tiles &copy; Esri'
      }}
    ).addTo(map);

    function addMarker(latlng, fillColor) {{
      if (!latlng) return;
      L.circleMarker(latlng, {{
        radius: 6,
        color: '#11161b',
        weight: 1,
        fillColor: fillColor,
        fillOpacity: 1.0
      }}).addTo(map);
    }}

    function drawRoute(route, options = {{}}) {{
      const coords = route.coords || [];
      const segmentColors = route.segmentColors || [];
      if (coords.length < 2) return null;

      const layerGroup = L.featureGroup();
      if ((colorMode === 'speed' || colorMode === 'accuracy') && segmentColors.length === coords.length - 1) {{
        for (let i = 0; i < coords.length - 1; i++) {{
          L.polyline([coords[i], coords[i + 1]], {{
            color: segmentColors[i],
            weight: options.weight || 5,
            opacity: options.opacity ?? 0.98,
            lineCap: 'round',
            lineJoin: 'round'
          }}).addTo(layerGroup);
        }}
      }} else {{
        L.polyline(coords, {{
          color: options.color || '#f3f5f7',
          weight: options.weight || 5,
          opacity: options.opacity ?? 0.98,
          lineCap: 'round',
          lineJoin: 'round'
        }}).addTo(layerGroup);
      }}
      return layerGroup;
    }}

    function nearestPointInfo(route, latlng) {{
      const coords = route.coords || [];
      const speed = route.speed || [];
      const altitude = route.altitude || [];
      const accuracy = route.accuracy || [];
      if (!coords.length) return null;

      let bestIdx = 0;
      let bestDistance = Infinity;
      for (let i = 0; i < coords.length; i++) {{
        const candidate = L.latLng(coords[i][0], coords[i][1]);
        const distance = candidate.distanceTo(latlng);
        if (distance < bestDistance) {{
          bestDistance = distance;
          bestIdx = i;
        }}
      }}

      return {{
        latlng: coords[bestIdx],
        speed: bestIdx < speed.length ? speed[bestIdx] : null,
        altitude: bestIdx < altitude.length ? altitude[bestIdx] : null,
        accuracy: bestIdx < accuracy.length ? accuracy[bestIdx] : null
      }};
    }}

    let selectedMarker = null;
    let selectedPopup = null;

    function showPointInfo(route, latlng) {{
      const info = nearestPointInfo(route, latlng);
      if (!info || !info.latlng) return;

      if (selectedMarker) {{
        map.removeLayer(selectedMarker);
        selectedMarker = null;
      }}
      if (selectedPopup) {{
        map.closePopup(selectedPopup);
        selectedPopup = null;
      }}

      selectedMarker = L.circleMarker(info.latlng, {{
        radius: 5,
        color: '#11161b',
        weight: 1,
        fillColor: '#f3f5f7',
        fillOpacity: 1.0
      }}).addTo(map);

      let text = '';
      if (colorMode === 'speed') {{
        text = info.speed == null ? 'Speed: -' : `Speed: ${{info.speed.toFixed(1)}} km/h`;
      }} else if (colorMode === 'accuracy') {{
        text = info.accuracy == null ? 'Accuracy: -' : `Accuracy: ${{info.accuracy.toFixed(1)}} m`;
      }} else {{
        text = info.altitude == null ? 'Altitude: -' : `Altitude: ${{info.altitude.toFixed(1)}} m`;
      }}

      selectedPopup = L.popup({{ closeButton: false, offset: [0, -8] }})
        .setLatLng(info.latlng)
        .setContent(text)
        .openOn(map);
    }}

    let boundsLayer = null;
    const activeRoute = showFullRoute ? fullRoute : runRoute;

    if (showFullRoute) {{
      const fullLayer = drawRoute(fullRoute, {{
        color: '#f3f5f7',
        weight: 5,
        opacity: 0.98
      }});
      if (fullLayer) {{
        fullLayer.addTo(map);
        boundsLayer = fullLayer;
      }}

      if (runRoute.coords.length > 1) {{
        const selectionLayer = drawRoute(runRoute, {{
          color: '#ffb14a',
          weight: 6,
          opacity: 0.96
        }});
        if (selectionLayer) {{
          selectionLayer.addTo(map);
        }}
      }}
    }} else {{
      if (fullRoute.coords.length > 1) {{
        boundsLayer = L.polyline(fullRoute.coords, {{
          color: '#9ca3ad',
          weight: 4,
          opacity: 0.38,
          lineCap: 'round',
          lineJoin: 'round'
        }}).addTo(map);
      }}

      const activeLayer = drawRoute(runRoute, {{
        color: '#f3f5f7',
        weight: 5,
        opacity: 0.98
      }});
      if (activeLayer) {{
        activeLayer.addTo(map);
        boundsLayer = activeLayer;
      }}
    }}

    if (activeRoute.coords.length > 1) {{
      addMarker(runStart, '#7bd88f');
      addMarker(runEnd, '#ff6b6b');
    }}

    if (boundsLayer) {{
      map.fitBounds(boundsLayer.getBounds(), {{ padding: [28, 28] }});
    }} else {{
      map.setView([49.2265, 19.0380], 14);
    }}

    map.on('click', function(e) {{
      showPointInfo(activeRoute, e.latlng);
    }});
  </script>
</body>
</html>"""


class Playback3DViewerPage(QWidget):
    def __init__(self, right=None, left=None, source_text=""):
        super().__init__()

        self.right_source = right
        self.left_source = left
        self.source_text = source_text

        self.runs = []
        self.turn_intervals = []
        self.gps_path = None
        self.load_error = ""
        self.current_run_index = 0
        self.current_turn_interval_index = 0
        self.segment_mode = "runs"
        self.show_full_map = False
        self.map_color_mode = "accuracy"

        self._load_data()
        self._build_ui()
        self._refresh_view()

    def _load_data(self):
        if not self.source_text:
            return

        try:
            folder = Path(self.source_text)
            self.gps_path = load_gps_path(folder)
            self.runs = detect_gps_runs(self.gps_path)
            self.turn_intervals = load_turn_intervals(folder)
            if not self.runs and self.turn_intervals:
                self.segment_mode = "intervals"
        except DataLoadError as exc:
            self.load_error = str(exc)
        except Exception as exc:
            self.load_error = f"Failed to load map data: {exc}"

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
                padding: 7px 14px;
                font-size: 13px;
                font-weight: 600;
            }
            QPushButton:hover {
                background-color: #33414e;
            }
            QPushButton:disabled {
                color: #6f7a85;
                border-color: #313941;
            }
            """
        )

        root = QVBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(8)

        top_frame = QFrame()
        top_frame.setStyleSheet(top_bar_frame_stylesheet(14))
        top_bar = QHBoxLayout(top_frame)
        top_bar.setContentsMargins(12, 10, 12, 10)
        top_bar.setSpacing(8)

        self.btn_prev_interval = QPushButton("←")
        self.btn_prev_interval.clicked.connect(self._show_prev_interval)
        self.btn_prev_interval.setMinimumWidth(46)
        self.btn_prev_interval.setStyleSheet(neutral_button_stylesheet())

        self.btn_next_interval = QPushButton("→")
        self.btn_next_interval.clicked.connect(self._show_next_interval)
        self.btn_next_interval.setMinimumWidth(46)
        self.btn_next_interval.setStyleSheet(neutral_button_stylesheet())

        self.interval_label = QLabel("--/--")
        self.interval_label.setMinimumWidth(92)
        self.interval_label.setAlignment(Qt.AlignCenter)
        self.interval_label.setStyleSheet(info_label_stylesheet())

        self.btn_mode = QPushButton("Runs")
        self.btn_mode.clicked.connect(self._toggle_mode)
        self.btn_mode.setMinimumWidth(92)
        self.btn_mode.setStyleSheet(neutral_button_stylesheet())

        self.btn_reset_view = QPushButton("Reset view")
        self.btn_reset_view.clicked.connect(self._reset_view)
        self.btn_reset_view.setMinimumWidth(104)
        self.btn_reset_view.setStyleSheet(neutral_button_stylesheet())

        self.btn_scope = QPushButton("Run")
        self.btn_scope.clicked.connect(self._toggle_scope)
        self.btn_scope.setMinimumWidth(72)
        self.btn_scope.setStyleSheet(neutral_button_stylesheet())

        self.btn_color = QPushButton("Accuracy")
        self.btn_color.clicked.connect(self._cycle_color_mode)
        self.btn_color.setMinimumWidth(76)
        self.btn_color.setStyleSheet(neutral_button_stylesheet())

        top_bar.addWidget(self.btn_prev_interval)
        top_bar.addWidget(self.btn_next_interval)
        top_bar.addWidget(self.interval_label)
        top_bar.addWidget(self.btn_mode)
        top_bar.addWidget(self.btn_scope)
        top_bar.addWidget(self.btn_color)
        top_bar.addWidget(self.btn_reset_view)
        top_bar.addStretch()
        root.addWidget(top_frame)

        self.scene_map = TrackMapScene()
        self.scene_map.setMinimumHeight(560)
        root.addWidget(self.scene_map, 1)

        self.info_label = QLabel("")
        self.info_label.setWordWrap(True)
        self.info_label.setStyleSheet(info_label_stylesheet())
        root.addWidget(self.info_label)

    def _active_segments(self):
        return self.turn_intervals if self.segment_mode == "intervals" else self.runs

    def _current_segment_index(self) -> int:
        return self.current_turn_interval_index if self.segment_mode == "intervals" else self.current_run_index

    def _set_current_segment_index(self, index: int):
        if self.segment_mode == "intervals":
            self.current_turn_interval_index = index
        else:
            self.current_run_index = index

    def _selection_name(self, *, plural: bool = False) -> str:
        if self.segment_mode == "intervals":
            return "Intervals" if plural else "Interval"
        return "Runs" if plural else "Run"

    def _scope_button_text(self) -> str:
        return self._selection_name(plural=False) if self.show_full_map else "Full"

    def _current_interval(self):
        active_segments = self._active_segments()
        if not active_segments:
            return None
        current_index = max(0, min(self._current_segment_index(), len(active_segments) - 1))
        self._set_current_segment_index(current_index)
        return active_segments[current_index]

    def _show_prev_interval(self):
        current_index = self._current_segment_index()
        if current_index <= 0:
            return
        self._set_current_segment_index(current_index - 1)
        self._refresh_view()

    def _show_next_interval(self):
        active_segments = self._active_segments()
        current_index = self._current_segment_index()
        if current_index >= len(active_segments) - 1:
            return
        self._set_current_segment_index(current_index + 1)
        self._refresh_view()

    def _reset_view(self):
        self.scene_map.reset_view()

    def _toggle_mode(self):
        if not self.runs and not self.turn_intervals:
            return
        if not self.runs:
            self.segment_mode = "intervals"
        elif not self.turn_intervals:
            self.segment_mode = "runs"
        else:
            self.segment_mode = "intervals" if self.segment_mode == "runs" else "runs"
        self.btn_mode.setText(self._selection_name(plural=True))
        self.btn_scope.setText(self._scope_button_text())
        self._refresh_view()

    def _toggle_scope(self):
        self.show_full_map = not self.show_full_map
        self.btn_scope.setText(self._scope_button_text())
        self._refresh_view()

    def _cycle_color_mode(self):
        self.map_color_mode = "speed" if self.map_color_mode == "accuracy" else "accuracy"
        self.btn_color.setText("Speed" if self.map_color_mode == "speed" else "Accuracy")
        self._refresh_view()

    def _refresh_view(self):
        interval = self._current_interval()
        active_segments = self._active_segments()
        current_index = self._current_segment_index()

        self.btn_mode.setText(self._selection_name(plural=True))
        self.btn_mode.setEnabled(bool(self.runs) and bool(self.turn_intervals))
        self.btn_scope.setText(self._scope_button_text())

        has_intervals = interval is not None
        self.btn_prev_interval.setEnabled(has_intervals and current_index > 0)
        self.btn_next_interval.setEnabled(has_intervals and current_index < len(active_segments) - 1)

        if self.gps_path is None:
            self.interval_label.setText("--/--")
            self.info_label.setText(self.load_error or "No GPS path available.")
            self.scene_map.update_map(
                gps_path=None,
                run_path=None,
                show_full_route=self.show_full_map,
                color_mode=self.map_color_mode,
            )
            return

        if interval is None:
            self.interval_label.setText("Full" if self.show_full_map else "--/--")
            self.info_label.setText(
                f"No {self._selection_name(plural=True).lower()} available. Showing the full GPS route."
            )
            self.scene_map.update_map(
                gps_path=self.gps_path,
                run_path=None,
                show_full_route=True,
                color_mode=self.map_color_mode,
            )
            return

        interval_path = slice_gps_path_to_interval(
            self.gps_path, interval.time_start, interval.time_stop
        )

        if self.segment_mode == "intervals":
            selected_number = getattr(interval, "interval_index", current_index + 1)
            distance_km = _optional_float(interval.stats.get("distance"))
            drop_m = _optional_float(interval.stats.get("elevationloss"))
            if distance_km is None:
                distance_km = _gps_distance_km(interval_path)
            if drop_m is None:
                drop_m = _gps_drop_m(interval_path)
        else:
            selected_number = getattr(interval, "run_index", current_index + 1)
            distance_km = _optional_float(getattr(interval, "distance_km", None))
            drop_m = _optional_float(getattr(interval, "altitude_drop_m", None))
            if distance_km is None:
                distance_km = _gps_distance_km(interval_path)
            if drop_m is None:
                drop_m = _gps_drop_m(interval_path)

        if self.show_full_map:
            full_distance_km = _gps_distance_km(self.gps_path)
            full_drop_m = _gps_drop_m(self.gps_path)
            self.interval_label.setText("Full")
            self.info_label.setText(
                f"showing full route    selected {self._selection_name(plural=False).lower()}: "
                f"{selected_number}/{len(active_segments)}    "
                f"route distance: {full_distance_km:.3f} km    "
                f"route drop: {full_drop_m:.1f} m"
            )
        else:
            self.interval_label.setText(f"{selected_number}/{len(active_segments)}")
            self.info_label.setText(
                f"{self._selection_name(plural=False).lower()}: {selected_number}/{len(active_segments)}    "
                f"time: {interval.time_start:.3f}s -> {interval.time_stop:.3f}s    "
                f"duration: {interval.time_stop - interval.time_start:.3f}s    "
                f"distance: {distance_km:.3f} km    "
                f"drop: {drop_m:.1f} m"
            )
        self.scene_map.update_map(
            gps_path=self.gps_path,
            run_path=interval_path,
            show_full_route=self.show_full_map,
            color_mode=self.map_color_mode,
        )
