from PySide6.QtGui import QColor, QPalette

APP_BG = "#1c1d21"
SURFACE_0 = "#202228"
SURFACE_1 = "#24262d"
SURFACE_2 = "#2a2d35"
SURFACE_3 = "#30343d"
SURFACE_SOFT = "#1a1b1f"
BORDER = "#3a3d45"
BORDER_STRONG = "#505560"
TEXT_PRIMARY = "#f2f3f5"
TEXT_SECONDARY = "#d8dce3"
TEXT_MUTED = "#a3a9b4"
TEXT_DIM = "#7f8692"
ACCENT_WARM = "#c8ad84"
LEFT_SKI = "#ff9a3d"
RIGHT_SKI = "#5aa9ff"
SUCCESS_BG = "#314028"
SUCCESS_BORDER = "#718c52"
SUCCESS_TEXT = "#e3f0d1"
NAV_ACTIVE_BG = "#383229"
NAV_ACTIVE_BORDER = "#8f7a58"


def apply_dark_palette(widget):
    widget.setStyleSheet(
        f"""
        QMainWindow, QWidget {{
            background-color: {APP_BG};
            color: {TEXT_PRIMARY};
        }}
        QPushButton {{
            background-color: {SURFACE_2};
            color: {TEXT_PRIMARY};
            border: 1px solid {BORDER};
            border-radius: 10px;
            padding: 8px 14px;
            font-size: 13px;
            font-weight: 600;
        }}
        QPushButton:hover {{
            background-color: {SURFACE_3};
            border-color: {BORDER_STRONG};
        }}
        QPushButton:disabled {{
            color: {TEXT_DIM};
            border-color: {BORDER};
        }}
        QPushButton:checked {{
            background-color: {SURFACE_3};
            border: 1px solid {BORDER_STRONG};
            color: {TEXT_PRIMARY};
        }}
        QLabel {{
            background: transparent;
        }}
        """
    )

    pal = widget.palette()
    pal.setColor(QPalette.Window, QColor(APP_BG))
    pal.setColor(QPalette.WindowText, QColor(TEXT_PRIMARY))
    pal.setColor(QPalette.Base, QColor(SURFACE_SOFT))
    pal.setColor(QPalette.AlternateBase, QColor(SURFACE_0))
    pal.setColor(QPalette.Text, QColor(TEXT_PRIMARY))
    pal.setColor(QPalette.Button, QColor(SURFACE_2))
    pal.setColor(QPalette.ButtonText, QColor(TEXT_PRIMARY))
    widget.setPalette(pal)


def nav_button_stylesheet() -> str:
    return f"""
    QPushButton {{
        background-color: {SURFACE_1};
        color: {TEXT_SECONDARY};
        border: 1px solid {BORDER};
        border-radius: 12px;
        padding: 8px 16px;
        font-size: 13px;
        font-weight: 700;
    }}
    QPushButton:hover {{
        background-color: {SURFACE_2};
        border-color: {BORDER_STRONG};
    }}
    QPushButton:checked {{
        background-color: {NAV_ACTIVE_BG};
        border: 1px solid {NAV_ACTIVE_BORDER};
        color: {TEXT_PRIMARY};
    }}
    """


def neutral_button_stylesheet() -> str:
    return f"""
    QPushButton {{
        background-color: {SURFACE_2};
        color: {TEXT_PRIMARY};
        border: 1px solid {BORDER};
        border-radius: 10px;
        padding: 7px 14px;
        font-size: 13px;
        font-weight: 600;
    }}
    QPushButton:hover {{
        background-color: {SURFACE_3};
        border-color: {BORDER_STRONG};
    }}
    QPushButton:disabled {{
        color: {TEXT_DIM};
        border-color: {BORDER};
    }}
    QPushButton:checked {{
        background-color: {SURFACE_3};
        border: 1px solid {BORDER_STRONG};
        color: {TEXT_PRIMARY};
    }}
    """


def cursor_button_stylesheet() -> str:
    return f"""
    QPushButton {{
        background-color: {SURFACE_2};
        color: {TEXT_PRIMARY};
        border: 1px solid {BORDER};
        border-radius: 10px;
        padding: 7px 14px;
        font-size: 13px;
        font-weight: 600;
    }}
    QPushButton:hover {{
        background-color: {SURFACE_3};
        border-color: {BORDER_STRONG};
    }}
    QPushButton:checked {{
        background-color: {SUCCESS_BG};
        color: {SUCCESS_TEXT};
        border: 1px solid {SUCCESS_BORDER};
    }}
    """


def ski_toggle_stylesheet(color_hex: str, checked_text: str = "#151515") -> str:
    return f"""
    QPushButton {{
        background-color: {SURFACE_2};
        color: {color_hex};
        border: 1px solid {color_hex};
        border-radius: 10px;
        padding: 7px 14px;
        font-size: 13px;
        font-weight: 700;
    }}
    QPushButton:hover {{
        background-color: {SURFACE_3};
    }}
    QPushButton:checked {{
        background-color: {color_hex};
        color: {checked_text};
        border: 1px solid {color_hex};
    }}
    """


def pill_label_stylesheet() -> str:
    return f"""
    QLabel {{
        color: {TEXT_PRIMARY};
        background-color: {SURFACE_SOFT};
        border: 1px solid {BORDER};
        border-radius: 10px;
        padding: 8px 12px;
        font-size: 13px;
        font-weight: 700;
    }}
    """


def info_label_stylesheet() -> str:
    return f"""
    QLabel {{
        color: {TEXT_SECONDARY};
        background-color: {SURFACE_0};
        border: 1px solid {BORDER};
        border-radius: 10px;
        padding: 7px 10px;
        font-size: 13px;
    }}
    """


def status_chip_stylesheet() -> str:
    return f"""
    QLabel {{
        color: {TEXT_SECONDARY};
        background-color: {SURFACE_1};
        border: 1px solid {BORDER};
        border-radius: 10px;
        padding: 7px 12px;
        font-size: 12px;
        font-weight: 600;
    }}
    """


def top_bar_frame_stylesheet(radius: int = 16) -> str:
    return f"""
    QFrame {{
        background-color: {SURFACE_0};
        border: 1px solid {BORDER};
        border-radius: {radius}px;
    }}
    """


def outer_card_stylesheet(radius: int = 24) -> str:
    return f"""
    QFrame {{
        background-color: {SURFACE_0};
        border: 1px solid {BORDER};
        border-radius: {radius}px;
    }}
    """


def inner_card_stylesheet(radius: int = 18) -> str:
    return f"""
    QFrame {{
        background-color: {SURFACE_1};
        border: 1px solid {BORDER};
        border-radius: {radius}px;
    }}
    """


def toolbar_stylesheet() -> str:
    return f"""
    QToolBar {{
        background: {SURFACE_1};
        border: 1px solid {BORDER};
        border-radius: 10px;
        spacing: 6px;
        padding: 4px;
    }}
    QToolButton {{
        background: {SURFACE_2};
        color: {TEXT_PRIMARY};
        border: 1px solid {BORDER};
        border-radius: 8px;
        padding: 6px;
        margin: 1px;
    }}
    QToolButton:hover {{
        background: {SURFACE_3};
        border-color: {BORDER_STRONG};
    }}
    """
