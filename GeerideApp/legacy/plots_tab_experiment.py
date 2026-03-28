from PySide6.QtWidgets import QSizePolicy, QVBoxLayout, QWidget

import numpy as np
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.backends.backend_qtagg import NavigationToolbar2QT as NavigationToolbar
from matplotlib.figure import Figure


class PlotsTab(QWidget):
    def __init__(self, right=None, left=None, coord_callback=None, parent=None):
        super().__init__(parent)

        self.right = right
        self.left = left
        self.coord_callback = coord_callback

        self.show_right = right is not None
        self.show_left = left is not None
        self.max_points = 12000

        self._build_ui()
        self._plot_all()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        self.figure = Figure(facecolor="#1e1e1e")
        self.canvas = FigureCanvas(self.figure)
        self.canvas.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        self.toolbar = NavigationToolbar(self.canvas, self)

        for action in self.toolbar.actions():
            text = action.text().strip().lower()
            if text in {"subplots", "customize", "configure subplots"}:
                self.toolbar.removeAction(action)

        if hasattr(self.toolbar, "locLabel"):
            self.toolbar.locLabel.hide()

        self.toolbar.set_message = lambda s: None

        self.toolbar.setStyleSheet(
            """
            QToolBar {
                background: #2b2b2b;
                border: 1px solid #3a3a3a;
                spacing: 6px;
            }
            QToolButton {
                background: #2b2b2b;
                color: #eaeaea;
                border: 1px solid #4a4a4a;
                border-radius: 4px;
                padding: 4px;
            }
            QToolButton:hover {
                background: #3a3a3a;
            }
            """
        )

        layout.addWidget(self.toolbar)
        layout.addWidget(self.canvas)

        self.ax_roll = self.figure.add_subplot(311)
        self.ax_pitch = self.figure.add_subplot(312, sharex=self.ax_roll)
        self.ax_yaw = self.figure.add_subplot(313, sharex=self.ax_roll)
        self.axes = [self.ax_roll, self.ax_pitch, self.ax_yaw]

        self._style_axes()
        self.canvas.mpl_connect("motion_notify_event", self._on_mouse_move)

    def _style_axes(self):
        for ax in self.axes:
            ax.set_facecolor("#1e1e1e")
            ax.grid(True, color="#3a3a3a", alpha=0.9, linewidth=0.8)
            ax.tick_params(colors="#d8d8d8", labelsize=10)
            for spine in ax.spines.values():
                spine.set_color("#555555")

        self.ax_roll.set_ylabel("roll [deg]", color="#eaeaea")
        self.ax_pitch.set_ylabel("pitch [deg]", color="#eaeaea")
        self.ax_yaw.set_ylabel("yaw [deg]", color="#eaeaea")
        self.ax_yaw.set_xlabel("time [s]", color="#eaeaea")

    def _decimate_xy(self, x, y):
        n = len(x)
        if n <= self.max_points:
            return x, y

        idx = np.linspace(0, n - 1, self.max_points).astype(int)
        idx = np.unique(idx)
        return x[idx], y[idx]

    def _plot_one(self, ax, ski, attr, color):
        x = np.asarray(ski.time)
        y = np.asarray(getattr(ski, attr))
        x2, y2 = self._decimate_xy(x, y)
        ax.plot(x2, y2, color=color, linewidth=1.0)

    def _plot_all(self):
        for ax in self.axes:
            ax.clear()

        self._style_axes()

        for ax in self.axes:
            ax.axhline(0, color="#7a7a7a", linewidth=1.0, linestyle="-", label="_nolegend_")

        if self.show_right and self.right is not None:
            self._plot_one(self.ax_roll, self.right, "roll", "#4f8cff")
            self._plot_one(self.ax_pitch, self.right, "pitch", "#4f8cff")
            self._plot_one(self.ax_yaw, self.right, "yaw", "#4f8cff")

        if self.show_left and self.left is not None:
            self._plot_one(self.ax_roll, self.left, "roll", "#ff8c42")
            self._plot_one(self.ax_pitch, self.left, "pitch", "#ff8c42")
            self._plot_one(self.ax_yaw, self.left, "yaw", "#ff8c42")

        self.figure.tight_layout()
        self.canvas.draw_idle()

    def set_left_visible(self, visible: bool):
        self.show_left = visible
        self._plot_all()

    def set_right_visible(self, visible: bool):
        self.show_right = visible
        self._plot_all()

    def _on_mouse_move(self, event):
        if self.coord_callback is None:
            return

        if event.inaxes is None or event.xdata is None or event.ydata is None:
            self.coord_callback("t: -, deg: -")
            return

        self.coord_callback(f"t: {event.xdata:.3f}   deg: {event.ydata:.3f}")
