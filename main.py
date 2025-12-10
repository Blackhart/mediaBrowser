"""Entrypoint for a minimal PySide6 window.

:raises SystemExit: If the Qt application terminates with a non-zero code.
"""
from __future__ import print_function
from PySide6.QtWidgets import (
    QApplication,
    QPushButton,
    QHBoxLayout,
    QFrame,
    QGridLayout,
    QLabel,
    QLineEdit,
    QScrollArea,
    QCheckBox,
    QSizePolicy,
    QSplitter,
    QVBoxLayout,
    QWidget,
    QTreeWidget,
    QTreeWidgetItem,
)
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer, QVideoSink
from PySide6.QtGui import QPixmap, QPainter, QColor, QImage
from PySide6.QtCore import Qt, QTimer, QUrl, Signal
import requests

import os
import sys
from pathlib import Path
from datetime import date, timedelta

# Désactive le décodage matériel pour éviter les erreurs CUDA
os.environ.setdefault("QT_MEDIA_BACKEND", "ffmpeg")
os.environ.setdefault("QT_MEDIA_FFMPEG_HWACCEL", "none")
os.environ.setdefault("QT_MEDIA_HARDWARE_DECODING", "0")
os.environ.setdefault("QT_MEDIA_FFMPEG_LOGLEVEL", "quiet")


def load_play_icon(icon_path, size=48):
    """Load the play icon PNG and scale it."""
    if not icon_path or not icon_path.exists():
        return None
    img = QImage(str(icon_path))
    if img.isNull():
        return None
    # Convert near-white background to transparent to respect alpha
    img = img.convertToFormat(QImage.Format_ARGB32)
    bg_threshold = 250  # adjust if needed
    for y in range(img.height()):
        scan = img.scanLine(y)
        ptr = memoryview(scan)
        for x in range(img.width()):
            offset = x * 4
            b, g, r, a = ptr[offset], ptr[offset +
                                          1], ptr[offset + 2], ptr[offset + 3]
            if r >= bg_threshold and g >= bg_threshold and b >= bg_threshold:
                ptr[offset + 3] = 0  # set alpha to 0
    pixmap = QPixmap.fromImage(img)
    if pixmap.isNull():
        return None
    return pixmap.scaled(size, size, Qt.KeepAspectRatio, Qt.SmoothTransformation)


class GridItemWidget(QWidget):
    """Widget representing a single item in the grid with image and title."""

    clicked = Signal(object, bool)  # self, ctrl_pressed

    def __init__(self, title, pixmap, is_video=False, play_icon=None, video_path=None, parent=None):
        """Initialize the grid item widget.

        :param title: The title text to display below the image.
        :type title: str
        :param pixmap: The pixmap to display for the item.
        :type pixmap: QPixmap
        :param is_video: Flag indicating if the item represents a video.
        :type is_video: bool
        :param play_icon: Optional pixmap for a play icon overlay.
        :type play_icon: QPixmap, optional
        :param video_path: Optional path to the video file for hover preview.
        :type video_path: str, optional
        :param parent: Parent widget.
        :type parent: QWidget, optional
        """
        super(GridItemWidget, self).__init__(parent)
        self._selected = False
        self.outer_frame = QFrame()
        self.outer_frame.setStyleSheet(
            """
            QFrame {
                border: 1px solid #3a3a3a;
                border-radius: 10px;
                background-color: #242424;
            }
            """
        )

        frame_layout = QVBoxLayout()
        frame_layout.setContentsMargins(4, 4, 4, 4)
        frame_layout.setSpacing(5)
        frame_layout.setAlignment(Qt.AlignTop | Qt.AlignHCenter)

        # Container to allow selection border around whole item
        if is_video and video_path:
            try:
                image_label = VideoHoverPreview(
                    video_path, base_pixmap=pixmap, play_icon=play_icon)
            except Exception:
                image_label = QLabel()
                image_label.setPixmap(pixmap)
                image_label.setScaledContents(True)
                image_label.setFixedSize(200, 140)
                image_label.setAlignment(Qt.AlignCenter)
                image_label.setStyleSheet(
                    "border: none; background: transparent;")
        else:
            image_label = QLabel()
            image_label.setPixmap(pixmap)
            image_label.setScaledContents(True)
            image_label.setFixedSize(200, 140)
            image_label.setAlignment(Qt.AlignCenter)
            image_label.setStyleSheet("border: none; background: transparent;")

        title_label = QLabel(title)
        title_label.setAlignment(Qt.AlignCenter)
        title_label.setWordWrap(True)
        title_label.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Minimum)
        title_label.setStyleSheet("background: transparent; border: none;")

        frame_layout.addWidget(image_label)
        frame_layout.addWidget(title_label)
        self.outer_frame.setLayout(frame_layout)

        outer_layout = QVBoxLayout()
        outer_layout.setContentsMargins(0, 0, 0, 0)
        outer_layout.addWidget(self.outer_frame)

        self.setLayout(outer_layout)
        self.setFixedSize(220, 180)
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)

        # Selection checkbox (top-left)
        self._checkbox = QCheckBox(self.outer_frame)
        self._checkbox.setStyleSheet(
            """
            QCheckBox { 
                background: transparent;
                color: #e6e6e6;
                border-radius: 2px;
            }
            QCheckBox::indicator {
                width: 16px;
                height: 16px;
                border: 1px solid #3a7bd5;
                border-radius: 2px;
                background: transparent;
            }
            QCheckBox::indicator:checked {
                background: #3a7bd5;
                border: 1px solid #3a7bd5;
            }
            """
        )
        self._checkbox.setFixedSize(18, 18)
        self._checkbox.move(6, 6)
        self._checkbox.setVisible(False)
        self._checkbox.setFocusPolicy(Qt.NoFocus)
        self._checkbox.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self._checkbox.stateChanged.connect(self._on_checkbox_changed)

    def set_selected(self, value):
        self._selected = value
        # Keep a subtle border; selection reflected by checkbox
        if value:
            self.outer_frame.setStyleSheet(
                """
                QFrame {
                    border: 2px solid #3a7bd5;
                    border-radius: 10px;
                    background-color: #2b2b2b;
                }
                """
            )
        else:
            self.outer_frame.setStyleSheet(
                """
                QFrame {
                    border: 1px solid #3a3a3a;
                    border-radius: 10px;
                    background-color: #242424;
                }
                """
            )
        blocker = self._checkbox.blockSignals(True)
        self._checkbox.setChecked(value)
        self._checkbox.blockSignals(blocker)
        self._checkbox.setVisible(value)

    def mousePressEvent(self, event):
        ctrl = bool(event.modifiers() & Qt.ControlModifier)
        self.clicked.emit(self, ctrl)
        return super(GridItemWidget, self).mousePressEvent(event)

    def _on_checkbox_changed(self, state):
        ctrl = bool(QApplication.keyboardModifiers() & Qt.ControlModifier)
        self.clicked.emit(self, ctrl)


class VideoHoverPreview(QLabel):
    """Preview video frames on hover; map mouse X to frame position."""

    def __init__(self, video_path, base_pixmap=None, play_icon=None, parent=None):
        super(VideoHoverPreview, self).__init__(parent)
        self.setFixedSize(200, 140)
        self.setScaledContents(True)
        self.setAlignment(Qt.AlignCenter)
        self.setMouseTracking(True)
        self.setStyleSheet("border: none; background: transparent;")
        self._base_pixmap = base_pixmap
        if base_pixmap is not None:
            self.setPixmap(base_pixmap)

        self._player = QMediaPlayer(self)
        self._audio = QAudioOutput(self)
        self._audio.setVolume(0.0)
        self._player.setAudioOutput(self._audio)
        self._sink = QVideoSink(self)
        self._player.setVideoSink(self._sink)
        self._sink.videoFrameChanged.connect(self._on_frame)
        self._player.setSource(QUrl.fromLocalFile(str(video_path)))
        self._duration = 0
        self._player.durationChanged.connect(self._on_duration)

        # Play icon overlay
        self._overlay = QLabel(self)
        self._overlay.setAlignment(Qt.AlignCenter)
        self._overlay.setFixedSize(48, 48)
        self._overlay.setScaledContents(True)
        self._overlay.setStyleSheet("background: transparent; border: none;")
        self._overlay.move(
            (self.width() - self._overlay.width()) // 2,
            (self.height() - self._overlay.height()) // 2,
        )
        if play_icon and not play_icon.isNull():
            self._overlay.setPixmap(play_icon)
        else:
            self._overlay.setText("▶")
            self._overlay.setStyleSheet(
                "color: white; background: rgba(0,0,0,80%); border-radius: 16px; font-size: 24px; padding: 6px;"
            )

    def _on_duration(self, dur):
        self._duration = dur
        self._player.pause()
        self._player.setPosition(0)

    def _on_frame(self, frame):
        if frame.isValid():
            image = frame.toImage().convertToFormat(QImage.Format_ARGB32)
            pix = QPixmap.fromImage(image)
            if not pix.isNull():
                self.setPixmap(pix)

    def enterEvent(self, event):
        self._player.pause()
        self._player.setPosition(0)
        return super(VideoHoverPreview, self).enterEvent(event)

    def leaveEvent(self, event):
        self._player.pause()
        if self._base_pixmap is not None:
            self.setPixmap(self._base_pixmap)
        return super(VideoHoverPreview, self).leaveEvent(event)

    def mouseMoveEvent(self, event):
        if self._duration <= 0:
            return super(VideoHoverPreview, self).mouseMoveEvent(event)
        x = event.position().x() if hasattr(event, "position") else event.x()
        ratio = max(0.0, min(1.0, x / float(self.width())))
        target = int(self._duration * ratio)
        self._player.pause()
        self._player.setPosition(target)
        return super(VideoHoverPreview, self).mouseMoveEvent(event)


class ResizableGridWidget(QWidget):
    """Widget that handles resize events to recalculate grid layout."""

    def __init__(self, populate_callback, parent=None):
        """Initialize the resizable grid widget.

        :param populate_callback: Callback function to repopulate grid.
        :type populate_callback: callable
        :param parent: Parent widget.
        :type parent: QWidget, optional
        """
        super(ResizableGridWidget, self).__init__(parent)
        self.populate_callback = populate_callback
        self.resize_timer = QTimer()
        self.resize_timer.setSingleShot(True)
        self.resize_timer.timeout.connect(self._on_resize_timeout)

    def resizeEvent(self, event):
        """Handle resize event with debouncing."""
        super(ResizableGridWidget, self).resizeEvent(event)
        self.resize_timer.start(100)  # Wait 100ms before recalculating

    def _on_resize_timeout(self):
        """Callback when resize timer expires."""
        if self.populate_callback:
            self.populate_callback()


def main():
    """Create and display a split window with left navigation and right grid."""
    app = QApplication(sys.argv)

    app.setStyleSheet(
        """
        QWidget {
            background-color: #1f1f1f;
            color: #e6e6e6;
            font-size: 14px;
        }
        QListWidget {
            background-color: #252525;
            border: 1px solid #333;
        }
        QListWidget::item {
            padding: 8px;
        }
        QListWidget::item:selected {
            background-color: #3a7bd5;
            color: #ffffff;
        }
        QLineEdit {
            background-color: #2b2b2b;
            border: 1px solid #3a3a3a;
            padding: 6px 8px;
            border-radius: 4px;
            selection-background-color: #3a7bd5;
        }
        QScrollArea {
            border: none;
            background-color: #1f1f1f;
        }
        QLabel {
            color: #e6e6e6;
        }
        """
    )

    window = QWidget()
    window.setWindowTitle("Media Browser")

    splitter = QSplitter(Qt.Horizontal)

    # Compute dates for Client Review
    today = date.today()
    last_monday = today - timedelta(days=today.weekday() + 7)
    today_str = today.strftime("%Y-%m-%d")
    last_monday_str = last_monday.strftime("%Y-%m-%d")

    left = QTreeWidget()
    left.setHeaderHidden(True)
    left.setMinimumWidth(180)

    def add_node(label, parent=None, data=None):
        item = QTreeWidgetItem([label])
        if data:
            item.setData(0, Qt.UserRole, data)
        if parent is None:
            left.addTopLevelItem(item)
        else:
            parent.addChild(item)
        return item

    # Order: All, Shots, Assets, My Work, Dept, Client Review
    node_all = add_node("All", data={"type": "all"})
    node_shots = add_node("Shots", data={"category": "Shots"})
    node_assets = add_node("Assets", data={"category": "Assets"})

    node_my_work = add_node("My Work", data={"section": "My Work"})

    node_dept = add_node("Dept", data={"section": "Dept"})
    add_node("Compo", parent=node_dept, data={
             "section": "Dept", "subsection": "Compo"})
    add_node("Layout", parent=node_dept, data={
             "section": "Dept", "subsection": "Layout"})

    node_client = add_node("Client Review", data={"section": "Client Review"})
    add_node(today_str, parent=node_client, data={
             "section": "Client Review", "subsection": today_str})
    add_node(last_monday_str, parent=node_client, data={
             "section": "Client Review", "subsection": last_monday_str})

    left.expandAll()

    # Left panel with collapse/expand buttons
    left_panel = QWidget()
    left_panel_layout = QVBoxLayout()
    left_panel_layout.setContentsMargins(0, 0, 0, 0)
    left_panel_layout.setSpacing(6)

    btn_bar = QHBoxLayout()
    btn_bar.setContentsMargins(6, 6, 6, 0)
    btn_bar.setSpacing(6)
    btn_collapse = QPushButton("Collapse")
    btn_expand = QPushButton("Expand")
    btn_collapse.clicked.connect(left.collapseAll)
    btn_expand.clicked.connect(left.expandAll)
    btn_bar.addWidget(btn_collapse)
    btn_bar.addWidget(btn_expand)
    btn_bar.addStretch()

    left_panel_layout.addLayout(btn_bar)
    left_panel_layout.addWidget(left)
    left_panel.setLayout(left_panel_layout)

    # Right panel with search + grid
    right_container = QWidget()
    right_layout = QVBoxLayout()
    right_layout.setContentsMargins(10, 10, 10, 10)
    right_layout.setSpacing(10)

    search_input = QLineEdit()
    search_input.setPlaceholderText("Rechercher...")
    search_input.setClearButtonEnabled(True)
    right_layout.addWidget(search_input)

    scroll_area = QScrollArea()
    scroll_area.setWidgetResizable(True)
    scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
    scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
    scroll_area.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

    grid_layout = QGridLayout()
    grid_layout.setSpacing(15)
    grid_layout.setContentsMargins(15, 15, 15, 15)
    grid_layout.setAlignment(Qt.AlignTop | Qt.AlignLeft)

    # Prepare directories
    base_dir = Path(__file__).resolve().parent
    images_dir = base_dir / "images"
    videos_dir = base_dir / "videos"
    icons_dir = base_dir / "icons"
    images_dir.mkdir(exist_ok=True)
    videos_dir.mkdir(exist_ok=True)
    icons_dir.mkdir(exist_ok=True)

    play_icon_path = icons_dir / "play.png"

    # Preload play icon
    play_icon_pixmap = load_play_icon(play_icon_path, size=48)
    selected_widgets = []
    selected_keys = set()
    selection_anchor = [None]

    # Add sample items (3 vidéos + images). Shots = items 2,3,4 (vidéos).
    sample_items = [
        {"title": "Item 1", "category": "Assets", "kind": "image",
            "image_url": "https://picsum.photos/seed/asset1/400/300", "filename": "asset1.jpg"},
        {
            "title": "Item 2 (Video)",
            "category": "Shots",
            "kind": "video",
            "video_file": str(videos_dir / "video1.mp4"),
            "thumb_file": "video1_thumb.jpg",
            "image_url": None,
            "filename": "video1_thumb.jpg",
        },
        {
            "title": "Item 3 (Video)",
            "category": "Shots",
            "kind": "video",
            "video_file": str(videos_dir / "video2.mp4"),
            "thumb_file": "video2_thumb.jpg",
            "image_url": None,
            "filename": "video2_thumb.jpg",
        },
        {
            "title": "Item 4 (Video)",
            "category": "Shots",
            "kind": "video",
            "video_file": str(videos_dir / "video3.mp4"),
            "thumb_file": "video3_thumb.jpg",
            "image_url": None,
            "filename": "video3_thumb.jpg",
        },
        {"title": "Item 5", "category": "Assets", "kind": "image",
            "image_url": "https://picsum.photos/seed/asset5/400/300", "filename": "asset5.jpg"},
        {"title": "Item 6", "category": "Assets", "kind": "image",
            "image_url": "https://picsum.photos/seed/asset6/400/300", "filename": "asset6.jpg"},
        {"title": "Item 7 (Compo)", "category": "Assets", "kind": "image", "section": "Dept", "subsection": "Compo",
         "image_url": "https://picsum.photos/seed/asset7/400/300", "filename": "asset7.jpg"},
        {"title": "Item 8 (Layout)", "category": "Assets", "kind": "image", "section": "Dept", "subsection": "Layout",
         "image_url": "https://picsum.photos/seed/asset8/400/300", "filename": "asset8.jpg"},
        {"title": "Item 9 (My Work)", "category": "Assets", "kind": "image", "section": "My Work",
         "image_url": "https://picsum.photos/seed/asset9/400/300", "filename": "asset9.jpg"},
        {"title": "Item 10 (Client Today)", "category": "Assets", "kind": "image", "section": "Client Review",
         "subsection": today_str, "image_url": "https://picsum.photos/seed/asset10/400/300", "filename": "asset10.jpg"},
        {"title": "Item 11 (Client Last Monday)", "category": "Assets", "kind": "image", "section": "Client Review",
         "subsection": last_monday_str, "image_url": "https://picsum.photos/seed/asset11/400/300", "filename": "asset11.jpg"},
        {"title": "Item 12", "category": "Assets", "kind": "image",
            "image_url": "https://picsum.photos/seed/asset12/400/300", "filename": "asset12.jpg"},
    ]

    # Store current category and search text for repopulation on resize
    current_category = ["All"]
    current_search = [""]

    def calculate_items_per_row():
        """Calculate how many items can fit per row based on available width."""
        item_width = 216  # Fixed width of GridItemWidget
        spacing = 15  # Grid spacing
        margins = 30  # Left + right margins (15 each)

        viewport_width = scroll_area.viewport().width()
        available_width = viewport_width - \
            margins if viewport_width > 0 else grid_widget.width() - margins
        if available_width < item_width:
            return 1

        items_per_row = int((available_width + spacing) /
                            (item_width + spacing))
        return max(1, items_per_row)

    def fetch_pixmap(url, title, filename):
        """Download an image (cached locally) and return a QPixmap; fallback to placeholder."""
        placeholder_colors = [
            QColor("#3a7bd5"),
            QColor("#d55c3a"),
            QColor("#6fbf73"),
            QColor("#c19be0"),
            QColor("#e0a63b"),
            QColor("#5cc3d5"),
            QColor("#d53a7b"),
            QColor("#7c8ae6"),
        ]
        img_path = images_dir / filename if filename else None

        if url and img_path and not img_path.exists():
            try:
                headers = {
                    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
                }
                resp = requests.get(url, timeout=6, headers=headers)
                resp.raise_for_status()
                with open(img_path, "wb") as f:
                    f.write(resp.content)
            except Exception:
                pass

        if img_path:
            pixmap = QPixmap(str(img_path))
            if not pixmap.isNull():
                return pixmap.scaled(
                    200, 140, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation
                )

        # Fallback placeholder with color and title
        color = placeholder_colors[abs(hash(url)) % len(placeholder_colors)]
        pixmap = QPixmap(200, 140)
        pixmap.fill(color)
        painter = QPainter(pixmap)
        painter.setPen(QColor(255, 255, 255))
        painter.drawRect(0, 0, 199, 139)
        painter.setPen(QColor(240, 240, 240))
        painter.drawText(pixmap.rect(), Qt.AlignCenter, title)
        painter.end()
        return pixmap

    def pixmap_for_item(item):
        """Return a pixmap for the given item (image or video thumbnail)."""
        # Prefer local thumbnail if provided
        thumb_file = item.get("thumb_file")
        if thumb_file:
            thumb_path = images_dir / thumb_file
            pm = QPixmap(str(thumb_path))
            if not pm.isNull():
                return pm.scaled(
                    200, 140, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation
                )

        # Otherwise fetch from remote image_url
        return fetch_pixmap(item.get("image_url"), item["title"], item["filename"])

    def populate_grid(filter_data=None, search_text=None):
        """Rebuild grid content based on selected filter."""
        if filter_data is None:
            filter_data = current_category[0]
        else:
            current_category[0] = filter_data
        if search_text is None:
            search_text = current_search[0]
        else:
            current_search[0] = search_text

        # Clear existing widgets
        while grid_layout.count():
            item = grid_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)

        # Filter items
        def match(item, filt):
            if not filt or filt.get("type") == "all":
                return True
            if "category" in filt and item.get("category") == filt["category"]:
                return True
            if "section" in filt:
                if item.get("section") != filt["section"]:
                    return False
                if "subsection" in filt:
                    return item.get("subsection") == filt["subsection"]
                return True
            return False

        filtered = [it for it in sample_items if match(it, filter_data)]

        # Apply search filter
        query = search_text.strip().lower()
        if query:
            filtered = [it for it in filtered if query in it["title"].lower()]

        # Calculate items per row dynamically
        items_per_row = calculate_items_per_row()

        # Helper to clear selection widgets (keys are managed separately)
        def clear_selection_widgets():
            for w in selected_widgets[:]:
                w.set_selected(False)
            selected_widgets[:] = []

        # Selection helpers
        def item_key(data):
            return (
                data.get("title"),
                data.get("category"),
                data.get("section"),
                data.get("subsection"),
                data.get("kind"),
                data.get("video_file"),
                data.get("filename"),
            )

        # clear previous widget references; keep selected_keys and anchor
        selected_widgets[:] = []
        current_keys = []
        key_to_widget = {}

        for idx, item_data in enumerate(filtered):
            row = idx // items_per_row
            col = idx % items_per_row
            pixmap = pixmap_for_item(item_data)
            is_video = item_data.get("kind") == "video"
            item_widget = GridItemWidget(
                item_data["title"],
                pixmap,
                is_video=is_video,
                play_icon=play_icon_pixmap if is_video else None,
                video_path=item_data.get("video_file") if is_video else None,
            )
            key = item_key(item_data)
            item_widget._sel_key = key
            current_keys.append(key)
            key_to_widget[key] = item_widget
            if key in selected_keys:
                item_widget.set_selected(True)
                selected_widgets.append(item_widget)
            grid_layout.addWidget(item_widget, row, col)

        def handle_click(widget, ctrl):
            key = getattr(widget, "_sel_key", None)
            if key is None:
                return
            shift = bool(QApplication.keyboardModifiers() & Qt.ShiftModifier)

            if shift and selection_anchor[0] in key_to_widget:
                try:
                    anchor_idx = current_keys.index(selection_anchor[0])
                    click_idx = current_keys.index(key)
                except ValueError:
                    anchor_idx = click_idx = 0
                start, end = sorted((anchor_idx, click_idx))
                range_keys = set(current_keys[start: end + 1])
                selected_keys.clear()
                selected_keys.update(range_keys)
                clear_selection_widgets()
                for rk in range_keys:
                    w = key_to_widget.get(rk)
                    if w:
                        w.set_selected(True)
                        selected_widgets.append(w)
                selection_anchor[0] = key
                return

            if not ctrl:
                selected_keys.clear()
                selected_keys.add(key)
                clear_selection_widgets()
                widget.set_selected(True)
                selected_widgets.append(widget)
                selection_anchor[0] = key
            else:
                if key in selected_keys:
                    selected_keys.remove(key)
                    widget.set_selected(False)
                    if widget in selected_widgets:
                        selected_widgets.remove(widget)
                else:
                    selected_keys.add(key)
                    widget.set_selected(True)
                    selected_widgets.append(widget)
                selection_anchor[0] = key

        # connect clicks after widgets are created
        for k in current_keys:
            w = key_to_widget[k]
            w.clicked.connect(handle_click)

        # If anchor is no longer visible, reset
        if selection_anchor[0] not in key_to_widget:
            selection_anchor[0] = None

    grid_widget = ResizableGridWidget(lambda: populate_grid())
    grid_widget.setLayout(grid_layout)
    grid_widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
    scroll_area.setWidget(grid_widget)
    right_layout.addWidget(scroll_area)

    left.setMaximumWidth(220)
    left.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

    right_container.setLayout(right_layout)
    splitter.addWidget(left_panel)
    splitter.addWidget(right_container)
    splitter.setSizes([1, 3])  # 1/4 vs 3/4
    splitter.setStretchFactor(0, 0)
    splitter.setStretchFactor(1, 1)

    def on_category_changed(current, previous):
        """Handle tree selection change and repopulate grid."""
        data = current.data(0, Qt.UserRole) if current else {"type": "all"}
        populate_grid(data)

    def on_search_changed(text):
        """Handle search change and repopulate grid."""
        populate_grid(search_text=text)

    left.currentItemChanged.connect(on_category_changed)
    search_input.textChanged.connect(on_search_changed)
    left.setCurrentItem(node_all)

    layout = QVBoxLayout()
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(0)
    layout.addWidget(splitter, stretch=1)

    # Footer with Open / Close buttons (minimal height)
    footer = QWidget()
    footer_layout = QHBoxLayout()
    footer_layout.setContentsMargins(10, 6, 10, 6)
    footer_layout.setSpacing(8)
    footer_layout.addStretch()

    btn_open = QPushButton("Open")
    btn_close = QPushButton("Close")

    def on_open():
        window.close()

    btn_open.clicked.connect(on_open)
    btn_close.clicked.connect(window.close)

    footer_layout.addWidget(btn_open)
    footer_layout.addWidget(btn_close)
    footer.setLayout(footer_layout)
    footer.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
    footer.setMinimumHeight(40)

    layout.addWidget(footer, stretch=0)

    window.setLayout(layout)
    window.resize(800, 500)
    window.show()

    # Initial population after window is shown to ensure correct width
    QTimer.singleShot(200, lambda: populate_grid({"type": "all"}))

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
