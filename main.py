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
    QToolButton,
    QVBoxLayout,
    QWidget,
    QTreeWidget,
    QTreeWidgetItem,
    QStyledItemDelegate,
    QStyle,
    QStyleOptionViewItem,
    QAbstractItemView,
    QInputDialog,
    QFormLayout,
)
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer, QVideoSink
from PySide6.QtGui import QPixmap, QPainter, QColor, QImage, QIcon, QPolygonF, QPalette, QPen
from PySide6.QtCore import (
    Qt, QTimer, QUrl, Signal, QPointF, QSize, QPoint, QEvent, QRect, QObject,
)
import requests

import os
import sys
from pathlib import Path
from datetime import date, timedelta

# Disable hardware decoding to avoid CUDA errors
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


def create_filter_icon(size=20):
    """Draw a simple funnel/filter icon."""
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)
    color = QColor("#e6e6e6")
    painter.setPen(Qt.NoPen)
    painter.setBrush(color)

    margin = size * 0.12
    top_width = size - 2 * margin
    bottom_width = size * 0.35
    height = size - 2 * margin
    top_y = margin
    bottom_y = margin + height

    points = [
        (margin, top_y),
        (margin + top_width, top_y),
        (margin + (top_width + bottom_width) / 2, bottom_y),
        (margin + (top_width - bottom_width) / 2, bottom_y),
    ]
    polygon = QPolygonF([QPointF(x, y) for x, y in points])
    painter.drawPolygon(polygon)
    stem_width = size * 0.12
    stem_x = (size - stem_width) / 2
    stem_top = bottom_y
    stem_bottom = size - margin * 0.5
    painter.drawRect(int(stem_x), int(stem_top), int(stem_width), int(stem_bottom - stem_top))
    painter.end()
    return QIcon(pixmap)


class FilterToolButton(QToolButton):
    """Filter toggle button with an optional in-button count badge."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("filterButton")
        self._badge = QLabel("1", self)
        self._badge.setObjectName("filterCountBadge")
        self._badge.setAlignment(Qt.AlignCenter)
        self._badge.setVisible(False)
        self._badge.setAttribute(Qt.WA_TransparentForMouseEvents, True)

    def set_filter_active(self, active):
        self.setProperty("filtered", active)
        self._badge.setVisible(active)
        self.style().unpolish(self)
        self.style().polish(self)
        self._position_badge()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._position_badge()

    def _position_badge(self):
        if not self._badge.isVisible():
            return
        self._badge.adjustSize()
        x = self.width() - self._badge.width() - 6
        y = (self.height() - self._badge.height()) // 2
        self._badge.move(max(x, 0), y)


class SectionHeader(QWidget):
    """Clickable header row for a collapsible filter section."""

    clicked = Signal()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)


class CollapsibleFilterSection(QWidget):
    """Foldable filter group with title and horizontal separator."""

    resized = Signal()
    add_requested = Signal()

    def __init__(self, title, parent=None, add_button=False, description=None):
        super().__init__(parent)
        self.setObjectName("filterSection")
        self._expanded = True
        self._description = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        self._header = SectionHeader()
        header_layout = QHBoxLayout(self._header)
        header_layout.setContentsMargins(2, 4, 2, 2)
        header_layout.setSpacing(6)

        self._toggle = QToolButton()
        self._toggle.setArrowType(Qt.DownArrow)
        self._toggle.setAutoRaise(True)
        self._toggle.setFixedSize(18, 18)
        self._toggle.clicked.connect(self.toggle)

        self._title = QLabel(title)
        self._title.setObjectName("filterSectionTitle")
        self._title.setStyleSheet(
            "font-weight: bold; color: #b0b0b0; background: transparent;"
        )

        header_layout.addWidget(self._toggle)
        header_layout.addWidget(self._title)
        header_layout.addStretch()

        if add_button:
            self._add_btn = QToolButton()
            self._add_btn.setObjectName("sectionAddButton")
            self._add_btn.setText("+")
            self._add_btn.setAutoRaise(True)
            self._add_btn.setFixedSize(18, 18)
            self._add_btn.setToolTip("Add personal filter")
            self._add_btn.clicked.connect(self.add_requested.emit)
            header_layout.addWidget(self._add_btn)

        self._header.clicked.connect(self.toggle)

        if description:
            self._description = QLabel(description)
            self._description.setObjectName("filterSectionDesc")
            self._description.setWordWrap(True)

        self._separator = QFrame()
        self._separator.setFrameShape(QFrame.HLine)
        self._separator.setFixedHeight(1)
        self._separator.setStyleSheet(
            "background-color: #4a4a4a; border: none; margin: 0;"
        )

        self._body = QWidget()
        self._body_layout = QVBoxLayout(self._body)
        self._body_layout.setContentsMargins(0, 0, 0, 2)
        self._body_layout.setSpacing(0)

        layout.addWidget(self._header)
        if self._description is not None:
            layout.addWidget(self._description)
        layout.addWidget(self._separator)
        layout.addWidget(self._body)
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Maximum)

    def set_body_widget(self, widget):
        """Add the filter tree widget inside the section body."""
        widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self._body_layout.addWidget(widget)

    def toggle(self):
        """Expand or collapse the section content."""
        self._expanded = not self._expanded
        self._body.setVisible(self._expanded)
        self._separator.setVisible(self._expanded)
        if self._description is not None:
            self._description.setVisible(self._expanded)
        self._toggle.setArrowType(
            Qt.DownArrow if self._expanded else Qt.RightArrow
        )
        self.updateGeometry()
        self.resized.emit()

    def collapse(self):
        if self._expanded:
            self.toggle()

    def expand(self):
        if not self._expanded:
            self.toggle()


def make_section_divider():
    """Return a horizontal line separating filter sections."""
    line = QFrame()
    line.setFrameShape(QFrame.HLine)
    line.setFixedHeight(1)
    line.setStyleSheet("background-color: #3a3a3a; border: none; margin: 4px 0;")
    return line


def fit_tree_to_contents(tree):
    """Resize a filter tree to the height of its visible rows."""
    if tree.topLevelItemCount() == 0:
        tree.setFixedHeight(0)
        return

    row_height = tree.visualItemRect(tree.topLevelItem(0)).height()
    if row_height <= 0:
        row_height = tree.fontMetrics().height() + 8

    def count_visible(item):
        count = 1
        if item.isExpanded():
            for i in range(item.childCount()):
                count += count_visible(item.child(i))
        return count

    visible_rows = sum(
        count_visible(tree.topLevelItem(i))
        for i in range(tree.topLevelItemCount())
    )
    tree.setFixedHeight(visible_rows * row_height + 4)
    tree.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)


STATUS_LABELS = {
    "fin": "Final",
    "rev": "Revision",
    "ip": "In Progress",
    "wtg": "Waiting to Start",
    "apr": "Approved",
    "omt": "Omitted",
    "na": "N/A",
    "vwd": "Viewed",
}

STATUS_COLORS = {
    "fin": ("#4a8f5c", "#ffffff"),
    "apr": ("#3d8f7a", "#ffffff"),
    "rev": ("#c9a227", "#1a1a1a"),
    "ip": ("#4a82b0", "#ffffff"),
    "wtg": ("#6b6b6b", "#e6e6e6"),
    "omt": ("#8b4a5a", "#ffffff"),
    "na": ("#555555", "#cccccc"),
    "vwd": ("#7b6ba8", "#ffffff"),
}


class StatusBadge(QLabel):
    """Colored capsule badge for ShotGrid-style status codes."""

    def __init__(self, status_code, parent=None):
        super().__init__(parent)
        label = STATUS_LABELS.get(status_code, str(status_code))
        bg, fg = STATUS_COLORS.get(status_code, ("#555555", "#ffffff"))
        self.setText(label)
        self.setAlignment(Qt.AlignCenter)
        self.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
        self.setStyleSheet(
            f"""
            background-color: {bg};
            color: {fg};
            border-radius: 10px;
            padding: 3px 10px;
            font-size: 11px;
            font-weight: bold;
            """
        )


NOTE_TYPE_LABELS = {
    "note": "Note",
    "review": "Review",
}

NOTE_TYPE_COLORS = {
    "note": ("#4a5568", "#e6e6e6"),
    "review": ("#5a4a7b", "#ffffff"),
}


def note_entry(entry_type, author, date, body, subject=None, status=None):
    """Build a ShotGrid-style note or review entry."""
    entry = {
        "type": entry_type,
        "author": author,
        "date": date,
        "body": body,
    }
    if subject:
        entry["subject"] = subject
    if status:
        entry["status"] = status
    return entry


class TypeBadge(QLabel):
    """Small badge for note vs review type."""

    def __init__(self, entry_type, parent=None):
        super().__init__(parent)
        label = NOTE_TYPE_LABELS.get(entry_type, entry_type.title())
        bg, fg = NOTE_TYPE_COLORS.get(entry_type, ("#555555", "#ffffff"))
        self.setText(label)
        self.setAlignment(Qt.AlignCenter)
        self.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
        self.setStyleSheet(
            f"""
            background-color: {bg};
            color: {fg};
            border-radius: 8px;
            padding: 2px 8px;
            font-size: 10px;
            font-weight: bold;
            """
        )


class NoteReviewCard(QFrame):
    """Card displaying a single note or review entry."""

    def __init__(self, entry, parent=None):
        super().__init__(parent)
        self.setObjectName("noteReviewCard")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(6)

        header = QHBoxLayout()
        header.setSpacing(6)
        header.addWidget(TypeBadge(entry.get("type", "note")))
        if entry.get("status"):
            header.addWidget(StatusBadge(entry["status"]))
        header.addStretch()
        date_lbl = QLabel(entry.get("date", ""))
        date_lbl.setObjectName("noteReviewDate")
        header.addWidget(date_lbl)
        layout.addLayout(header)

        author_lbl = QLabel(entry.get("author", ""))
        author_lbl.setObjectName("noteReviewAuthor")
        layout.addWidget(author_lbl)

        subject = entry.get("subject")
        if subject:
            subject_lbl = QLabel(subject)
            subject_lbl.setObjectName("noteReviewSubject")
            subject_lbl.setWordWrap(True)
            layout.addWidget(subject_lbl)

        body_lbl = QLabel(entry.get("body", ""))
        body_lbl.setObjectName("noteReviewBody")
        body_lbl.setWordWrap(True)
        body_lbl.setTextInteractionFlags(Qt.TextSelectableByMouse)
        layout.addWidget(body_lbl)


SHOTGRID_BASE_URL = os.environ.get(
    "SHOTGRID_URL", "https://studio.shotgrid.autodesk.com"
).rstrip("/")


def shotgrid_detail_url(entity_type, entity_id):
    """Build a ShotGrid detail page URL for an entity type and id."""
    return f"{SHOTGRID_BASE_URL}/detail/{entity_type}/{entity_id}"


def playlist_entry(name, shotgrid_id):
    """Build a playlist metadata entry with ShotGrid link target."""
    return {"name": name, "shotgrid_id": shotgrid_id}


class ShotGridLink(QLabel):
    """Clickable label that opens a ShotGrid page in the browser."""

    def __init__(self, text, url, parent=None):
        super().__init__(parent)
        self.setText(
            f'<a href="{url}" style="color: #6ba3c7; text-decoration: underline;">'
            f"{text}</a>"
        )
        self.setOpenExternalLinks(True)
        self.setTextInteractionFlags(Qt.TextBrowserInteraction)
        self.setWordWrap(True)
        self.setObjectName("mediaInfoFieldValue")


class PlaylistLinksWidget(QWidget):
    """List of playlist names linked to their ShotGrid pages."""

    def __init__(self, playlists, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        for entry in playlists:
            if isinstance(entry, dict):
                name = entry.get("name", "")
                sg_id = entry.get("shotgrid_id")
            else:
                name = str(entry)
                sg_id = None
            if not name:
                continue
            if sg_id:
                url = shotgrid_detail_url("Playlist", sg_id)
                layout.addWidget(ShotGridLink(name, url))
            else:
                label = QLabel(name)
                label.setObjectName("mediaInfoFieldValue")
                layout.addWidget(label)


def format_media_field(key, value):
    """Format a metadata value for display in the info panel."""
    if value is None or value == "":
        return None
    if key in ("technical_status", "artistic_status"):
        return STATUS_LABELS.get(value, str(value))
    if key == "kind":
        if value == "video":
            return "Video"
        if value == "image":
            return "Image"
    if key == "playlists" and isinstance(value, (list, tuple)):
        names = []
        for entry in value:
            if isinstance(entry, dict):
                names.append(entry.get("name", ""))
            else:
                names.append(str(entry))
        joined = ", ".join(n for n in names if n)
        return joined if joined else None
    if key == "tags" and isinstance(value, (list, tuple)):
        return ", ".join(value) if value else None
    return str(value)


MULTI_SUMMARY_FIELDS = (
    ("department", "Department"),
    ("resolution", "Resolution"),
    ("codec", "Codec"),
    ("container", "Container"),
    ("lut", "LUT"),
    ("artist", "Artist"),
)


def _collect_values(items, key):
    values = set()
    for item in items:
        value = item.get(key)
        if value is not None and value != "":
            values.add(value)
    return values


def shared_field_value(items, key):
    """Return a shared value across items, or a mixed-value label."""
    values = _collect_values(items, key)
    if not values:
        return None
    if len(values) == 1:
        return next(iter(values))
    return f"Mixed ({len(values)} values)"


def status_counts(items, key):
    """Count occurrences of each status code across selected items."""
    counts = {}
    for item in items:
        value = item.get(key)
        if value:
            counts[value] = counts.get(value, 0) + 1
    return counts


class StatusCountBadge(QLabel):
    """Status badge with an occurrence count for multi-select summaries."""

    def __init__(self, status_code, count, parent=None):
        super().__init__(parent)
        label = STATUS_LABELS.get(status_code, str(status_code))
        bg, fg = STATUS_COLORS.get(status_code, ("#555555", "#ffffff"))
        self.setText(f"{label} ×{count}")
        self.setAlignment(Qt.AlignCenter)
        self.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
        self.setStyleSheet(
            f"""
            background-color: {bg};
            color: {fg};
            border-radius: 10px;
            padding: 3px 10px;
            font-size: 11px;
            font-weight: bold;
            """
        )


class StatusCountRow(QWidget):
    """Wrapping rows of status count badges."""

    MAX_ROW_WIDTH = 268

    def __init__(self, counts, parent=None):
        super().__init__(parent)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(4)

        row_layout = None
        row_width = 0
        spacing = 6

        for code, count in sorted(counts.items(), key=lambda x: (-x[1], x[0])):
            badge = StatusCountBadge(code, count)
            badge_width = badge.sizeHint().width() + spacing

            if row_layout is None or row_width + badge_width > self.MAX_ROW_WIDTH:
                row = QWidget()
                row_layout = QHBoxLayout(row)
                row_layout.setContentsMargins(0, 0, 0, 0)
                row_layout.setSpacing(spacing)
                row_layout.setAlignment(Qt.AlignLeft)
                outer.addWidget(row)
                row_width = 0

            row_layout.addWidget(badge)
            row_width += badge_width


class SelectedItemRow(QWidget):
    """One line in the multi-select items list."""

    def __init__(self, item_data, parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 2, 0, 2)
        layout.setSpacing(8)

        title = item_data.get("title") or "—"
        version = item_data.get("version") or ""
        label = f"{title} — {version}" if version else title
        version_id = item_data.get("version_shotgrid_id")
        if version_id:
            link = ShotGridLink(label, shotgrid_detail_url("Version", version_id))
        else:
            link = QLabel(label)
            link.setObjectName("mediaInfoFieldValue")
            link.setWordWrap(True)
        layout.addWidget(link, stretch=1)

        tech_status = item_data.get("technical_status")
        if tech_status:
            layout.addWidget(StatusBadge(tech_status))


MEDIA_INFO_SECTIONS = (
    ("Version", (
        ("version", "Version"),
        ("entity", "Entity"),
        ("task", "Task"),
        ("date", "Date"),
        ("description", "Description"),
    )),
    ("Status", (
        ("technical_status", "Technical status"),
        ("artistic_status", "Artistic status"),
    )),
    ("Team", (
        ("department", "Department"),
        ("artist", "Artist"),
    )),
    ("Media", (
        ("kind", "Type"),
        ("resolution", "Resolution"),
        ("codec", "Codec"),
        ("container", "Container"),
        ("frame_in", "Frame in"),
        ("frame_out", "Frame out"),
        ("duration", "Duration"),
        ("frame_count", "Frame count"),
        ("fps", "FPS"),
    )),
    ("Colorimetry", (
        ("lut", "LUT"),
    )),
    ("Organization", (
        ("category", "Category"),
        ("section", "Section"),
        ("subsection", "Subsection"),
        ("playlists", "Playlists"),
        ("tags", "Tags"),
    )),
    ("Files", (
        ("filename", "File"),
        ("thumb_file", "Thumbnail"),
        ("video_file", "Video file"),
        ("image_url", "Image URL"),
        ("path_to_frames", "Frames path"),
    )),
)


class UserFilterActionHandler(QObject):
    """Track hover and clicks on painted edit/delete controls in the user filter tree."""

    delete_requested = Signal(object)
    edit_requested = Signal(object)

    def __init__(self, tree):
        super().__init__(tree)
        self._tree = tree
        self._hover_item = None
        self._hover_zone = None
        self._edit_width = 30
        self._btn_size = 20
        self._btn_gap = 0

    def actions_width(self):
        return self._edit_width + self._btn_gap + self._btn_size + 2

    def delete_rect_for_item(self, item):
        rect = self._tree.visualItemRect(item)
        return QRect(
            rect.right() - self._btn_size - 2,
            rect.center().y() - self._btn_size // 2,
            self._btn_size,
            self._btn_size,
        )

    def edit_rect_for_item(self, item):
        delete_rect = self.delete_rect_for_item(item)
        return QRect(
            delete_rect.left() - self._btn_gap - self._edit_width,
            delete_rect.top(),
            self._edit_width,
            delete_rect.height(),
        )

    def zone_at(self, pos):
        item = self._tree.itemAt(pos)
        if item is None:
            return None, None
        if self.delete_rect_for_item(item).contains(pos):
            return item, "delete"
        if self.edit_rect_for_item(item).contains(pos):
            return item, "edit"
        return None, None

    def is_edit_hovered(self, item):
        return self._hover_item is item and self._hover_zone == "edit"

    def is_delete_hovered(self, item):
        return self._hover_item is item and self._hover_zone == "delete"

    def _repaint_item(self, item):
        if item is not None:
            self._tree.viewport().update(self._tree.visualItemRect(item))

    def update_hover(self, pos):
        item, zone = self.zone_at(pos)
        hover_item = item if zone else None
        if hover_item != self._hover_item or zone != self._hover_zone:
            previous = self._hover_item
            self._hover_item = hover_item
            self._hover_zone = zone
            self._repaint_item(previous)
            self._repaint_item(hover_item)

    def clear_hover(self):
        previous = self._hover_item
        self._hover_item = None
        self._hover_zone = None
        self._repaint_item(previous)

    def handle_press(self, pos):
        _item, zone = self.zone_at(pos)
        return zone in ("edit", "delete")

    def handle_release(self, pos):
        item, zone = self.zone_at(pos)
        if zone == "delete":
            self.delete_requested.emit(item)
            return True
        if zone == "edit":
            self.edit_requested.emit(item)
            return True
        return False


class UserFilterActionDelegate(QStyledItemDelegate):
    """Delegate that keeps native Qt tree rendering and paints edit/delete buttons."""

    def __init__(self, tree, action_handler, parent=None):
        super().__init__(parent or tree)
        self._tree = tree
        self._handler = action_handler
        self._btn_size = 22

    def _draw_edit_label(self, painter, rect, hovered, is_selected):
        if hovered:
            color = "#6ba3c7"
        elif is_selected:
            color = "#ffffff"
        else:
            color = "#cccccc"
        painter.setPen(QColor(color))
        font = painter.font()
        font.setPointSize(9)
        painter.setFont(font)
        painter.drawText(rect, Qt.AlignCenter, "edit")

    def paint(self, painter, option, index):
        item = self._tree.itemFromIndex(index)
        is_selected = bool(option.state & QStyle.State_Selected)
        is_hover = bool(option.state & QStyle.State_MouseOver)
        show_actions = is_hover or self._handler._hover_item is item
        right_margin = self._handler.actions_width() if show_actions else 0

        if right_margin:
            right_strip = QRect(
                option.rect.right() - right_margin,
                option.rect.top(),
                right_margin,
                option.rect.height(),
            )
            if is_selected:
                painter.fillRect(right_strip, QColor("#4a82b0"))
            elif is_hover:
                painter.fillRect(right_strip, QColor("#333333"))
            else:
                painter.fillRect(right_strip, QColor("#252525"))

        opt = QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)
        if right_margin:
            opt.rect = option.rect.adjusted(0, 0, -right_margin, 0)
        super().paint(painter, opt, index)

        if not show_actions:
            return

        edit_rect = self._handler.edit_rect_for_item(item)
        delete_rect = self._handler.delete_rect_for_item(item)

        self._draw_edit_label(
            painter, edit_rect, self._handler.is_edit_hovered(item), is_selected
        )

        if self._handler.is_delete_hovered(item):
            minus_color = "#ff7b7b"
        elif is_selected:
            minus_color = "#ffffff"
        else:
            minus_color = "#cccccc"
        painter.setPen(QColor(minus_color))
        font = painter.font()
        font.setBold(True)
        font.setPointSize(12)
        painter.setFont(font)
        painter.drawText(delete_rect, Qt.AlignCenter, "−")


class UserFilterTree(QTreeWidget):
    """User filter tree with painted row actions handled in-viewport (no child widgets)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._action_handler = UserFilterActionHandler(self)
        self.setMouseTracking(True)
        self.viewport().setMouseTracking(True)
        self.setAttribute(Qt.WA_DontCreateNativeAncestors, True)
        self.viewport().setAttribute(Qt.WA_DontCreateNativeAncestors, True)
        self.setItemDelegate(UserFilterActionDelegate(self, self._action_handler))

    def viewportEvent(self, event):
        handler = self._action_handler
        if event.type() == QEvent.MouseMove:
            handler.update_hover(event.pos())
        elif event.type() == QEvent.Leave:
            handler.clear_hover()
        elif event.type() == QEvent.MouseButtonPress and event.button() == Qt.LeftButton:
            if handler.handle_press(event.pos()):
                return True
        elif event.type() == QEvent.MouseButtonRelease and event.button() == Qt.LeftButton:
            if handler.handle_release(event.pos()):
                return True
        return super().viewportEvent(event)


class ShelfFilterPopup(QFrame):
    """Floating overlay panel for shelf selection, anchored inside the main window."""

    closed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("shelfPanel")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self._layout = QVBoxLayout()
        self._layout.setContentsMargins(10, 10, 10, 10)
        self._layout.setSpacing(8)
        self.setLayout(self._layout)

    def set_content(self, header_widget, body_widget):
        """Populate the popup with header controls and shelf body."""
        while self._layout.count():
            item = self._layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.setParent(None)
                widget.deleteLater()
        self._layout.addWidget(header_widget)
        self._layout.addWidget(body_widget)

    def show_below(self, anchor):
        """Show the popup anchored below the given widget."""
        self.setFixedWidth(300)
        self.adjustSize()
        anchor_bottom = anchor.mapToGlobal(QPoint(0, anchor.height()))
        parent = self.parentWidget()
        if parent is not None:
            local = parent.mapFromGlobal(anchor_bottom)
            x = local.x() + anchor.width() - self.width()
            y = local.y() + 4
            self.move(x, y)
        else:
            x = anchor_bottom.x() + anchor.width() - self.width()
            y = anchor_bottom.y() + 4
            self.move(x, y)
        self.show()
        self.raise_()

    def hideEvent(self, event):
        super().hideEvent(event)
        self.closed.emit()


class MediaInfoPanel(QFrame):
    """Right-side panel showing ShotGrid-style Version metadata."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("mediaInfoPanel")
        self.setFixedWidth(320)
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Expanding)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(12)

        self._heading = QLabel("Details")
        self._heading.setObjectName("mediaInfoHeading")

        self._preview = QLabel()
        self._preview.setFixedHeight(170)
        self._preview.setAlignment(Qt.AlignCenter)
        self._preview.setScaledContents(True)
        self._preview.setObjectName("mediaInfoPreview")

        self._placeholder = QLabel()
        self._placeholder.setWordWrap(True)
        self._placeholder.setObjectName("mediaInfoPlaceholder")
        self._placeholder.hide()

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.NoFrame)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        self._fields_widget = QWidget()
        self._fields_layout = QFormLayout(self._fields_widget)
        self._fields_layout.setContentsMargins(0, 0, 0, 0)
        self._fields_layout.setSpacing(10)
        self._fields_layout.setLabelAlignment(Qt.AlignLeft | Qt.AlignTop)
        self._scroll.setWidget(self._fields_widget)

        layout.addWidget(self._heading)
        layout.addWidget(self._preview)
        layout.addWidget(self._scroll, stretch=1)
        layout.addWidget(self._placeholder, stretch=1)

        self.clear()

    def _clear_fields(self):
        while self._fields_layout.count():
            item = self._fields_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

    def _add_section_title(self, title):
        section_lbl = QLabel(title)
        section_lbl.setObjectName("mediaInfoSectionTitle")
        self._fields_layout.addRow(section_lbl)

    def _add_text_row(self, label, text, muted=False):
        name_lbl = QLabel(label)
        name_lbl.setObjectName("mediaInfoFieldLabel")
        value_lbl = QLabel(text)
        value_lbl.setWordWrap(True)
        value_lbl.setObjectName(
            "mediaInfoFieldValueMuted" if muted else "mediaInfoFieldValue"
        )
        self._fields_layout.addRow(name_lbl, value_lbl)

    def clear(self):
        self._heading.setText("Details")
        self._preview.hide()
        self._scroll.hide()
        self._placeholder.hide()
        self._clear_fields()
        self.hide()

    def set_multiple_summary(self, items):
        """Show aggregated summary when multiple media are selected."""
        self._placeholder.hide()
        self._preview.hide()
        self._scroll.show()
        self._clear_fields()

        count = len(items)
        self._heading.setText(f"{count} items selected")

        videos = sum(1 for item in items if item.get("kind") == "video")
        images = sum(1 for item in items if item.get("kind") == "image")
        type_parts = []
        if videos:
            type_parts.append(f"{videos} video{'s' if videos != 1 else ''}")
        if images:
            type_parts.append(f"{images} image{'s' if images != 1 else ''}")

        self._add_section_title("Summary")
        if type_parts:
            self._add_text_row("Types", ", ".join(type_parts))

        entities = _collect_values(items, "entity")
        if entities:
            entity_text = next(iter(entities)) if len(entities) == 1 else (
                f"Mixed ({len(entities)} entities)"
            )
            self._add_text_row("Entities", entity_text, muted=len(entities) > 1)

        for status_key, section_label in (
            ("technical_status", "Technical status"),
            ("artistic_status", "Artistic status"),
        ):
            counts = status_counts(items, status_key)
            if not counts:
                continue
            self._add_section_title(section_label)
            self._fields_layout.addRow(StatusCountRow(counts))

        shared_rows = []
        for key, label in MULTI_SUMMARY_FIELDS:
            value = shared_field_value(items, key)
            if value is not None:
                shared_rows.append((label, value))
        if shared_rows:
            self._add_section_title("Shared")
            for label, value in shared_rows:
                self._add_text_row(label, value, muted=value.startswith("Mixed"))

        self._add_section_title("Items")
        items_container = QWidget()
        items_layout = QVBoxLayout(items_container)
        items_layout.setContentsMargins(0, 0, 0, 0)
        items_layout.setSpacing(4)
        for item_data in sorted(items, key=lambda d: d.get("title") or ""):
            items_layout.addWidget(SelectedItemRow(item_data))
        self._fields_layout.addRow(items_container)

        self.show()

    def set_item(self, item_data, pixmap=None):
        self._placeholder.hide()
        self._scroll.show()
        self._preview.show()

        if pixmap is not None and not pixmap.isNull():
            self._preview.setPixmap(
                pixmap.scaled(
                    272, 170, Qt.KeepAspectRatio, Qt.SmoothTransformation
                )
            )
        else:
            self._preview.clear()

        self._clear_fields()
        title = item_data.get("title") or item_data.get("code") or "—"
        self._heading.setText(title)

        for section_title, fields in MEDIA_INFO_SECTIONS:
            rows = []
            for key, label in fields:
                raw = item_data.get(key)
                if raw is None or raw == "" or raw == []:
                    continue
                rows.append((label, key, raw))
            if not rows:
                continue

            section_lbl = QLabel(section_title)
            section_lbl.setObjectName("mediaInfoSectionTitle")
            self._fields_layout.addRow(section_lbl)

            for field_label, key, raw in rows:
                name_lbl = QLabel(field_label)
                name_lbl.setObjectName("mediaInfoFieldLabel")
                if key in ("technical_status", "artistic_status"):
                    value_widget = StatusBadge(raw)
                elif key == "entity":
                    entity_type = item_data.get("entity_type")
                    entity_id = item_data.get("entity_shotgrid_id")
                    if entity_type and entity_id:
                        url = shotgrid_detail_url(entity_type, entity_id)
                        value_widget = ShotGridLink(str(raw), url)
                    else:
                        value_widget = QLabel(str(raw))
                        value_widget.setWordWrap(True)
                        value_widget.setTextInteractionFlags(Qt.TextSelectableByMouse)
                        value_widget.setObjectName("mediaInfoFieldValue")
                elif key == "version":
                    version_id = item_data.get("version_shotgrid_id")
                    if version_id:
                        url = shotgrid_detail_url("Version", version_id)
                        value_widget = ShotGridLink(str(raw), url)
                    else:
                        value_widget = QLabel(str(raw))
                        value_widget.setWordWrap(True)
                        value_widget.setTextInteractionFlags(Qt.TextSelectableByMouse)
                        value_widget.setObjectName("mediaInfoFieldValue")
                elif key == "playlists":
                    value_widget = PlaylistLinksWidget(raw)
                else:
                    formatted = format_media_field(key, raw)
                    if not formatted:
                        continue
                    value_widget = QLabel(formatted)
                    value_widget.setWordWrap(True)
                    value_widget.setTextInteractionFlags(Qt.TextSelectableByMouse)
                    value_widget.setObjectName("mediaInfoFieldValue")
                self._fields_layout.addRow(name_lbl, value_widget)

        notes = item_data.get("notes_reviews") or []
        if notes:
            section_lbl = QLabel("Notes & Reviews")
            section_lbl.setObjectName("mediaInfoSectionTitle")
            self._fields_layout.addRow(section_lbl)

            notes_container = QWidget()
            notes_layout = QVBoxLayout(notes_container)
            notes_layout.setContentsMargins(0, 0, 0, 0)
            notes_layout.setSpacing(8)
            for entry in notes:
                notes_layout.addWidget(NoteReviewCard(entry))
            self._fields_layout.addRow(notes_container)

        self.show()


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
                border: 1px solid #4a82b0;
                border-radius: 2px;
                background: transparent;
            }
            QCheckBox::indicator:checked {
                background: #4a82b0;
                border: 1px solid #4a82b0;
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
                    border: 2px solid #4a82b0;
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
            background-color: #4a82b0;
            color: #ffffff;
        }
        QLineEdit {
            background-color: #2b2b2b;
            border: 1px solid #3a3a3a;
            padding: 6px 8px;
            border-radius: 4px;
            selection-background-color: #4a82b0;
        }
        QToolButton#filterButton {
            background-color: #2b2b2b;
            border: 1px solid #3a3a3a;
            border-radius: 4px;
            padding: 0px 10px 0px 6px;
        }
        QToolButton#filterButton[filtered="true"] {
            padding-right: 28px;
        }
        QToolButton#filterButton:hover {
            background-color: #333333;
            border-color: #4a4a4a;
        }
        QToolButton#filterButton:checked {
            background-color: #4a82b0;
            border-color: #4a82b0;
            color: #ffffff;
        }
        QLabel#filterCountBadge {
            background-color: #e74c3c;
            color: #ffffff;
            border-radius: 8px;
            padding: 1px 7px;
            font-size: 10px;
            font-weight: bold;
        }
        QFrame#shelfPanel {
            background-color: #252525;
            border: 1px solid #4a4a4a;
            border-radius: 6px;
        }
        QTreeWidget {
            background-color: #252525;
            border: none;
            outline: none;
            show-decoration-selected: 1;
        }
        QTreeWidget::viewport {
            background-color: #252525;
        }
        QTreeWidget::item {
            padding: 4px 2px;
            border: none;
        }
        QTreeWidget::item:selected {
            background-color: #4a82b0;
            color: #ffffff;
        }
        QTreeWidget::item:selected:hover {
            background-color: #4a82b0;
            color: #ffffff;
        }
        QTreeWidget::item:hover {
            background-color: #333333;
        }
        QScrollArea#shelfScroll {
            border: none;
            background-color: #252525;
        }
        QWidget#shelfBody {
            background-color: #252525;
        }
        QWidget#filterSection {
            background-color: #252525;
        }
        QToolButton#sectionAddButton {
            color: #cccccc;
            background: transparent;
            border: none;
            font-size: 16px;
            font-weight: bold;
            padding: 0;
        }
        QToolButton#sectionAddButton:hover {
            color: #6ba3c7;
        }
        QLabel#filterSectionDesc {
            color: #888888;
            font-size: 11px;
            padding: 0 4px 2px 26px;
            background: transparent;
        }
        QScrollBar:vertical {
            background: #252525;
            width: 10px;
            border: none;
            margin: 0;
        }
        QScrollBar::handle:vertical {
            background: #4a4a4a;
            border-radius: 4px;
            min-height: 20px;
        }
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
            height: 0;
            background: none;
            border: none;
        }
        QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {
            background: none;
        }
        QScrollArea {
            border: none;
            background-color: #1f1f1f;
        }
        QLabel {
            color: #e6e6e6;
        }
        QFrame#mediaInfoPanel {
            background-color: #252525;
            border-left: 1px solid #3a3a3a;
        }
        QLabel#mediaInfoHeading {
            font-weight: bold;
            font-size: 15px;
            color: #cccccc;
        }
        QLabel#mediaInfoSectionTitle {
            font-weight: bold;
            font-size: 12px;
            color: #6ba3c7;
            margin-top: 8px;
            padding-top: 4px;
            border-top: 1px solid #3a3a3a;
        }
        QLabel#mediaInfoPreview {
            background-color: #1a1a1a;
            border: 1px solid #3a3a3a;
            border-radius: 6px;
        }
        QLabel#mediaInfoPlaceholder {
            color: #888888;
        }
        QLabel#mediaInfoFieldLabel {
            color: #888888;
            font-size: 12px;
        }
        QLabel#mediaInfoFieldValue {
            color: #e6e6e6;
            font-size: 13px;
        }
        QLabel#mediaInfoFieldValueMuted {
            color: #999999;
            font-size: 13px;
            font-style: italic;
        }
        QFrame#noteReviewCard {
            background-color: #1e1e1e;
            border: 1px solid #3a3a3a;
            border-radius: 6px;
        }
        QLabel#noteReviewDate {
            color: #888888;
            font-size: 11px;
        }
        QLabel#noteReviewAuthor {
            color: #6ba3c7;
            font-size: 12px;
            font-weight: bold;
        }
        QLabel#noteReviewSubject {
            color: #e6e6e6;
            font-size: 12px;
            font-weight: bold;
        }
        QLabel#noteReviewBody {
            color: #cccccc;
            font-size: 12px;
        }
        """
    )

    window = QWidget()
    window.setWindowTitle("Media Browser")

    # Compute dates for Client Review
    today = date.today()
    last_monday = today - timedelta(days=today.weekday() + 7)
    today_str = today.strftime("%Y-%m-%d")
    last_monday_str = last_monday.strftime("%Y-%m-%d")

    filter_trees = []

    def make_filter_tree(with_delete=False):
        tree = UserFilterTree() if with_delete else QTreeWidget()
        tree.setHeaderHidden(True)
        tree.setIndentation(14)
        tree.setFrameShape(QFrame.NoFrame)
        tree.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        tree.setSelectionBehavior(QAbstractItemView.SelectRows)
        tree.setFocusPolicy(Qt.NoFocus)
        tree.setRootIsDecorated(True)
        tree.setAutoFillBackground(True)
        palette = tree.palette()
        palette.setColor(QPalette.Base, QColor("#252525"))
        palette.setColor(QPalette.Highlight, QColor("#4a82b0"))
        tree.setPalette(palette)
        tree.viewport().setAutoFillBackground(True)
        tree.viewport().setPalette(palette)
        if with_delete:
            tree._shelf_handler = tree._action_handler
        filter_trees.append(tree)
        return tree

    def add_node(tree, label, parent=None, data=None):
        item = QTreeWidgetItem([label])
        if data:
            item.setData(0, Qt.UserRole, data)
        if parent is None:
            tree.addTopLevelItem(item)
        else:
            parent.addChild(item)
        return item

    global_tree = make_filter_tree()
    node_all = add_node(global_tree, "All", data={"type": "all"})
    add_node(global_tree, "Assets", data={"category": "Assets"})
    add_node(global_tree, "Shots", data={"category": "Shots"})

    studio_tree = make_filter_tree()
    node_dept = add_node(studio_tree, "Dept", data={"section": "Dept"})
    add_node(studio_tree, "Compo", parent=node_dept, data={
             "section": "Dept", "subsection": "Compo"})
    add_node(studio_tree, "Layout", parent=node_dept, data={
             "section": "Dept", "subsection": "Layout"})
    add_node(studio_tree, "Animation", parent=node_dept, data={
             "section": "Dept", "subsection": "Animation"})
    node_roles = add_node(studio_tree, "Roles", data={"section": "Roles"})
    add_node(studio_tree, "CG Sup", parent=node_roles, data={
             "section": "Roles", "subsection": "CG Sup"})
    add_node(studio_tree, "Leads", parent=node_roles, data={
             "section": "Roles", "subsection": "Leads"})
    add_node(studio_tree, "Artists", parent=node_roles, data={
             "section": "Roles", "subsection": "Artists"})
    node_tasks = add_node(studio_tree, "Assigned Tasks", data={
             "section": "Assigned Tasks"})
    add_node(studio_tree, "Assigned to me", parent=node_tasks, data={
             "section": "Assigned Tasks", "subsection": "Assigned to me"})
    add_node(studio_tree, "To review", parent=node_tasks, data={
             "section": "Assigned Tasks", "subsection": "To review"})

    user_tree = make_filter_tree(with_delete=True)

    def add_user_node(label, parent=None, data=None):
        item = QTreeWidgetItem([label])
        item.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled)
        if data:
            item.setData(0, Qt.UserRole, data)
        if parent is None:
            user_tree.addTopLevelItem(item)
        else:
            parent.addChild(item)
        return item

    node_client = add_user_node("Client Review", data={"section": "Client Review"})
    add_user_node(today_str, parent=node_client, data={
             "section": "Client Review", "subsection": today_str})
    add_user_node(last_monday_str, parent=node_client, data={
             "section": "Client Review", "subsection": last_monday_str})

    for tree in filter_trees:
        tree.expandAll()
        fit_tree_to_contents(tree)
        tree.itemExpanded.connect(lambda _item, t=tree: fit_tree_to_contents(t))
        tree.itemCollapsed.connect(lambda _item, t=tree: fit_tree_to_contents(t))

    section_global = CollapsibleFilterSection(
        "Global",
        description="Built-in filters defined by the application (read-only).",
    )
    section_global.set_body_widget(global_tree)

    section_studio = CollapsibleFilterSection(
        "Studio",
        description="Studio filters from the ShotGrid preset packages (read-only).",
    )
    section_studio.set_body_widget(studio_tree)

    section_user = CollapsibleFilterSection(
        "User",
        add_button=True,
        description="Personal filters — editable and saved per user in ShotGrid.",
    )
    section_user.set_body_widget(user_tree)

    filter_sections = [section_global, section_studio, section_user]

    shelf_body = QWidget()
    shelf_body.setObjectName("shelfBody")
    shelf_body.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Maximum)
    shelf_body_layout = QVBoxLayout()
    shelf_body_layout.setContentsMargins(0, 0, 0, 0)
    shelf_body_layout.setSpacing(0)
    shelf_body_layout.setAlignment(Qt.AlignTop)
    shelf_body_layout.addWidget(section_global)
    shelf_body_layout.addWidget(make_section_divider())
    shelf_body_layout.addWidget(section_studio)
    shelf_body_layout.addWidget(make_section_divider())
    shelf_body_layout.addWidget(section_user)
    shelf_body.setLayout(shelf_body_layout)

    shelf_scroll = QScrollArea()
    shelf_scroll.setObjectName("shelfScroll")
    shelf_scroll.setWidgetResizable(True)
    shelf_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
    shelf_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
    shelf_scroll.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Maximum)
    shelf_scroll.setWidget(shelf_body)

    shelf_header = QWidget()
    shelf_header_layout = QHBoxLayout()
    shelf_header_layout.setContentsMargins(0, 0, 0, 0)
    shelf_header_layout.setSpacing(6)

    shelf_title = QLabel("Shelves")
    shelf_title.setStyleSheet("font-weight: bold; color: #cccccc;")

    shelf_header_layout.addWidget(shelf_title)
    shelf_header.setLayout(shelf_header_layout)

    shelf_popup = ShelfFilterPopup(window)
    shelf_popup.set_content(shelf_header, shelf_scroll)
    shelf_popup.hide()

    def refresh_shelf_popup_size():
        for tree in filter_trees:
            fit_tree_to_contents(tree)
        shelf_body.adjustSize()
        if shelf_popup.isVisible():
            shelf_popup.adjustSize()

    for section in filter_sections:
        section.resized.connect(refresh_shelf_popup_size)

    # Main content with search + grid
    right_container = QWidget()
    right_layout = QVBoxLayout()
    right_layout.setContentsMargins(10, 10, 10, 10)
    right_layout.setSpacing(10)

    search_input = QLineEdit()
    search_input.setPlaceholderText("Search...")
    search_input.setClearButtonEnabled(True)

    filter_button = FilterToolButton()
    filter_button.setCheckable(True)
    filter_button.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
    filter_button.setText("filter")
    filter_button.setToolTip("Filters / Shelves")
    filter_button.setIcon(create_filter_icon())
    filter_button.setIconSize(QSize(20, 20))

    def sync_filter_button_height():
        height = search_input.sizeHint().height()
        filter_button.setFixedHeight(height)

    sync_filter_button_height()

    def update_filter_badge(filter_data):
        is_active = not (filter_data and filter_data.get("type") == "all")
        filter_button.set_filter_active(is_active)

    search_row = QHBoxLayout()
    search_row.setSpacing(8)
    search_row.setAlignment(Qt.AlignVCenter)
    search_row.addWidget(search_input, stretch=1)
    search_row.addWidget(filter_button)

    right_layout.addLayout(search_row)

    scroll_area = QScrollArea()
    scroll_area.setWidgetResizable(True)
    scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
    scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
    scroll_area.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

    info_panel = MediaInfoPanel()
    info_panel.hide()

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

    # ShotGrid-style Version metadata for sample items.
    def version_meta(
        version,
        technical_status,
        artistic_status,
        date,
        department,
        artist,
        resolution,
        version_shotgrid_id=None,
        entity=None,
        entity_type=None,
        entity_shotgrid_id=None,
        task=None,
        frame_in=None,
        frame_out=None,
        duration=None,
        frame_count=None,
        fps=None,
        playlists=None,
        tags=None,
        description=None,
        path_to_frames=None,
        notes_reviews=None,
        codec=None,
        container=None,
        lut=None,
    ):
        meta = {
            "version": version,
            "technical_status": technical_status,
            "artistic_status": artistic_status,
            "date": date,
            "department": department,
            "artist": artist,
            "resolution": resolution,
        }
        optional = {
            "version_shotgrid_id": version_shotgrid_id,
            "entity": entity,
            "entity_type": entity_type,
            "entity_shotgrid_id": entity_shotgrid_id,
            "task": task,
            "frame_in": frame_in,
            "frame_out": frame_out,
            "duration": duration,
            "frame_count": frame_count,
            "fps": fps,
            "playlists": playlists or [],
            "tags": tags or [],
            "description": description,
            "path_to_frames": path_to_frames,
            "notes_reviews": notes_reviews or [],
            "codec": codec,
            "container": container,
            "lut": lut,
        }
        meta.update({k: v for k, v in optional.items() if v})
        return meta

    def pl(name, shotgrid_id):
        return playlist_entry(name, shotgrid_id)

    # Sample items (3 videos + images). Shots = items 2,3,4 (videos).
    sample_items = [
        {
            "title": "Item 1",
            "category": "Assets",
            "kind": "image",
            "image_url": "https://picsum.photos/seed/asset1/400/300",
            "filename": "asset1.jpg",
            **version_meta(
                "v001", "fin", "apr", "2026-07-01", "Modeling", "Alice Martin",
                "2048x1556", version_shotgrid_id=3001, entity="prop_chair_01", entity_type="Asset",
                entity_shotgrid_id=4501, task="Model",
                codec="JPEG", container="JPEG",
                lut="sRGB",
                playlists=[pl("Assets Review", 1101), pl("Dailies", 1001)],
                tags=["hero", "approved"],
                description="Final model approved for the main set.",
                notes_reviews=[
                    note_entry(
                        "review", "Mark Lead", "2026-07-01",
                        "Clean topology, approved for surfacing handoff.",
                        subject="Model final review", status="apr",
                    ),
                    note_entry(
                        "note", "Alice Martin", "2026-06-28",
                        "Fixed minor n-gons on the armrest.",
                        subject="Topology fix",
                    ),
                ],
            ),
        },
        {
            "title": "Item 2 (Video)",
            "category": "Shots",
            "kind": "video",
            "video_file": str(videos_dir / "video1.mp4"),
            "thumb_file": "video1_thumb.jpg",
            "image_url": None,
            "filename": "video1_thumb.jpg",
            **version_meta(
                "v003", "fin", "apr", "2026-07-03", "Animation", "Bob Dupont",
                "1920x1080", version_shotgrid_id=3002, entity="sh010", entity_type="Shot",
                entity_shotgrid_id=2010, task="Anim",
                codec="H.264", container="MP4",
                lut="show_rec709_v2.cube",
                frame_in=1001, frame_out=1120, duration="00:00:05:00",
                frame_count=120, fps=24,
                playlists=[
                    pl("Dailies", 1001), pl("Client Review", 1002),
                    pl("Editorial Selects", 1105),
                ],
                tags=["final", "client"],
                description="Final animation shot 010 — client approval.",
                path_to_frames="/projects/show/shots/sh010/anim/v003",
                notes_reviews=[
                    note_entry(
                        "review", "Sarah Director", "2026-07-03",
                        "Timing feels great. Approved for editorial.",
                        subject="Animation client review", status="apr",
                    ),
                    note_entry(
                        "review", "Tom Supervisor", "2026-07-02",
                        "Watch elbow pop frame 1055. Otherwise good to go.",
                        subject="Animation supervisor review", status="rev",
                    ),
                    note_entry(
                        "note", "Bob Dupont", "2026-07-01",
                        "Updated spline on entrance, ready for review.",
                        subject="Spline pass update",
                    ),
                ],
            ),
        },
        {
            "title": "Item 3 (Video)",
            "category": "Shots",
            "kind": "video",
            "video_file": str(videos_dir / "video2.mp4"),
            "thumb_file": "video2_thumb.jpg",
            "image_url": None,
            "filename": "video2_thumb.jpg",
            **version_meta(
                "v002", "rev", "rev", "2026-07-05", "Comp", "Claire Nguyen",
                "1920x1080", version_shotgrid_id=3003, entity="sh020", entity_type="Shot",
                entity_shotgrid_id=2020, task="Comp",
                codec="ProRes 422 HQ", container="MOV",
                lut="ACEScct_to_Rec709_v3.cube",
                frame_in=1001, frame_out=1088, duration="00:00:03:16",
                frame_count=88, fps=24,
                playlists=[pl("Comp Review", 1201), pl("Dailies", 1001)],
                tags=["wip", "review"],
                description="Comp in revision — supervisor notes from 07/05.",
                path_to_frames="/projects/show/shots/sh020/comp/v002",
                notes_reviews=[
                    note_entry(
                        "review", "Jane Supervisor", "2026-07-05",
                        "Fix edge blending frame 1024–1040. Matte lines visible on left.",
                        subject="Comp review v002", status="rev",
                    ),
                    note_entry(
                        "note", "Claire Nguyen", "2026-07-04",
                        "Updated roto pass, ready for review.",
                        subject="Roto update",
                    ),
                    note_entry(
                        "review", "Jane Supervisor", "2026-07-03",
                        "Good progress. Watch highlight blowout on frame 1012.",
                        subject="Comp review v001", status="rev",
                    ),
                ],
            ),
        },
        {
            "title": "Item 4 (Video)",
            "category": "Shots",
            "kind": "video",
            "video_file": str(videos_dir / "video3.mp4"),
            "thumb_file": "video3_thumb.jpg",
            "image_url": None,
            "filename": "video3_thumb.jpg",
            **version_meta(
                "v001", "ip", "wtg", "2026-07-07", "Layout", "David Kim",
                "1920x1080", version_shotgrid_id=3004, entity="sh030", entity_type="Shot",
                entity_shotgrid_id=2030, task="Layout",
                codec="H.264", container="MP4",
                lut="show_rec709_v2.cube",
                frame_in=1001, frame_out=1048, duration="00:00:02:00",
                frame_count=48, fps=24,
                playlists=[pl("Layout Dailies", 1301)],
                tags=["wip"],
                description="First layout — camera and blocking.",
                path_to_frames="/projects/show/shots/sh030/layout/v001",
                notes_reviews=[
                    note_entry(
                        "review", "Tom Supervisor", "2026-07-07",
                        "Camera angle works. Push hero 10cm screen-right.",
                        subject="Layout review v001", status="rev",
                    ),
                ],
            ),
        },
        {
            "title": "Item 5",
            "category": "Assets",
            "kind": "image",
            "image_url": "https://picsum.photos/seed/asset5/400/300",
            "filename": "asset5.jpg",
            **version_meta(
                "v002", "rev", "rev", "2026-06-28", "Surfacing", "Eva Lopez",
                "4096x4096", version_shotgrid_id=3005, entity="env_forest", entity_type="Asset",
                entity_shotgrid_id=4601, task="Lookdev",
                codec="JPEG", container="JPEG",
                lut="sRGB",
                playlists=[pl("Assets Review", 1101), pl("Lookdev", 1401)],
                tags=["texture", "review"],
                description="Forest lookdev — lighting revision.",
                notes_reviews=[
                    note_entry(
                        "review", "Mark Lead", "2026-06-28",
                        "Moss reads too flat. Add more spec breakup.",
                        subject="Lookdev review", status="rev",
                    ),
                ],
            ),
        },
        {
            "title": "Item 6",
            "category": "Assets",
            "kind": "image",
            "image_url": "https://picsum.photos/seed/asset6/400/300",
            "filename": "asset6.jpg",
            **version_meta(
                "v001", "wtg", "wtg", "2026-06-20", "Concept", "Frank Weber",
                "1920x1080", version_shotgrid_id=3006, entity="char_hero", entity_type="Asset",
                entity_shotgrid_id=4701, task="Concept",
                codec="JPEG", container="JPEG",
                lut="sRGB",
                playlists=[pl("Art Department", 1501)],
                tags=["concept"],
                description="Main character concept art.",
            ),
        },
        {
            "title": "Item 7 (Compo)",
            "category": "Assets",
            "kind": "image",
            "section": "Dept",
            "subsection": "Compo",
            "image_url": "https://picsum.photos/seed/asset7/400/300",
            "filename": "asset7.jpg",
            **version_meta(
                "v004", "fin", "apr", "2026-07-02", "Comp", "Claire Nguyen",
                "1920x1080", version_shotgrid_id=3007, entity="sh015", entity_type="Shot",
                entity_shotgrid_id=2015, task="Comp",
                codec="JPEG", container="JPEG",
                lut="sRGB",
                playlists=[
                    pl("Comp Review", 1201), pl("Client Review", 1002),
                    pl("Dept — Compo", 1601),
                ],
                tags=["final"],
                description="Final comp asset overlay.",
            ),
        },
        {
            "title": "Item 8 (Layout)",
            "category": "Assets",
            "kind": "image",
            "section": "Dept",
            "subsection": "Layout",
            "image_url": "https://picsum.photos/seed/asset8/400/300",
            "filename": "asset8.jpg",
            **version_meta(
                "v002", "rev", "ip", "2026-06-30", "Layout", "David Kim",
                "1920x1080", version_shotgrid_id=3008, entity="sh040", entity_type="Shot",
                entity_shotgrid_id=2040, task="Layout",
                codec="JPEG", container="JPEG",
                lut="sRGB",
                playlists=[pl("Layout Dailies", 1301), pl("Dept — Layout", 1602)],
                tags=["layout", "review"],
                description="Revised layout — camera adjustment.",
            ),
        },
        {
            "title": "Item 9 (Assigned to me)",
            "category": "Assets",
            "kind": "image",
            "section": "Assigned Tasks",
            "subsection": "Assigned to me",
            "image_url": "https://picsum.photos/seed/asset9/400/300",
            "filename": "asset9.jpg",
            **version_meta(
                "v001", "ip", "wtg", "2026-07-08", "Rigging", "Alice Martin",
                "1920x1080", version_shotgrid_id=3009, entity="char_hero", entity_type="Asset",
                entity_shotgrid_id=4701, task="Rig",
                codec="PNG", container="PNG",
                lut="sRGB",
                playlists=[pl("Assigned to me", 1701), pl("Rigging", 1702)],
                tags=["rig", "wip"],
                description="Rig in progress — facial controls.",
            ),
        },
        {
            "title": "Item 10 (Client Today)",
            "category": "Assets",
            "kind": "image",
            "section": "Client Review",
            "subsection": today_str,
            "image_url": "https://picsum.photos/seed/asset10/400/300",
            "filename": "asset10.jpg",
            **version_meta(
                "v003", "fin", "apr", today_str, "Comp", "Claire Nguyen",
                "1920x1080", version_shotgrid_id=3010, entity="sh050", entity_type="Shot",
                entity_shotgrid_id=2050, task="Comp",
                codec="JPEG", container="JPEG",
                lut="sRGB",
                playlists=[
                    pl("Client Review", 1002),
                    pl(f"Client Review — {today_str}", 1003),
                ],
                tags=["client", "approved"],
                description="Version presented to client today.",
                notes_reviews=[
                    note_entry(
                        "review", "Client — Studio X", today_str,
                        "Approved with minor notes on color grade.",
                        subject="Client review", status="apr",
                    ),
                    note_entry(
                        "note", "Claire Nguyen", "2026-07-08",
                        "Pushed grade tweak before client session.",
                        subject="Pre-client grade pass",
                    ),
                ],
            ),
        },
        {
            "title": "Item 11 (Client Last Monday)",
            "category": "Assets",
            "kind": "image",
            "section": "Client Review",
            "subsection": last_monday_str,
            "image_url": "https://picsum.photos/seed/asset11/400/300",
            "filename": "asset11.jpg",
            **version_meta(
                "v002", "rev", "rev", last_monday_str, "Lighting", "Eva Lopez",
                "1920x1080", version_shotgrid_id=3011, entity="sh060", entity_type="Shot",
                entity_shotgrid_id=2060, task="Light",
                codec="JPEG", container="JPEG",
                lut="sRGB",
                playlists=[
                    pl("Client Review", 1002),
                    pl(f"Client Review — {last_monday_str}", 1004),
                ],
                tags=["client", "review"],
                description="Lighting review — client feedback from Monday.",
                notes_reviews=[
                    note_entry(
                        "review", "Client — Studio X", last_monday_str,
                        "Reduce rim light intensity by 20%.",
                        subject="Client lighting notes", status="rev",
                    ),
                    note_entry(
                        "review", "Jane Supervisor", last_monday_str,
                        "Agree with client. Match key to ref plate.",
                        subject="Supervisor follow-up", status="rev",
                    ),
                ],
            ),
        },
        {
            "title": "Item 12",
            "category": "Assets",
            "kind": "image",
            "image_url": "https://picsum.photos/seed/asset12/400/300",
            "filename": "asset12.jpg",
            **version_meta(
                "v001", "omt", "na", "2026-05-15", "FX", "Bob Dupont",
                "1920x1080", version_shotgrid_id=3012, entity="sh070", entity_type="Shot",
                entity_shotgrid_id=2070, task="FX",
                codec="JPEG", container="JPEG",
                lut="sRGB",
                playlists=[pl("Archive", 1801), pl("FX Library", 1802)],
                tags=["omitted"],
                description="Omitted version — not used in final.",
            ),
        },
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
            QColor("#4a82b0"),
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
                data.get("version"),
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
        key_to_data = {}

        def update_info_panel():
            if len(selected_keys) == 0:
                info_panel.clear()
            elif len(selected_keys) == 1:
                key = next(iter(selected_keys))
                data = key_to_data.get(key)
                if data is not None:
                    info_panel.set_item(data, pixmap_for_item(data))
                else:
                    info_panel.clear()
            else:
                selected = [
                    key_to_data[k] for k in selected_keys if k in key_to_data
                ]
                info_panel.set_multiple_summary(selected)

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
            item_widget._item_data = item_data
            current_keys.append(key)
            key_to_widget[key] = item_widget
            key_to_data[key] = item_data
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
                update_info_panel()
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

            update_info_panel()

        # connect clicks after widgets are created
        for k in current_keys:
            w = key_to_widget[k]
            w.clicked.connect(handle_click)

        # If anchor is no longer visible, reset
        if selection_anchor[0] not in key_to_widget:
            selection_anchor[0] = None

        update_info_panel()

    grid_widget = ResizableGridWidget(lambda: populate_grid())
    grid_widget.setLayout(grid_layout)
    grid_widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
    scroll_area.setWidget(grid_widget)

    content_row = QHBoxLayout()
    content_row.setSpacing(0)
    content_row.setContentsMargins(0, 0, 0, 0)
    content_row.addWidget(scroll_area, stretch=1)
    content_row.addWidget(info_panel)
    right_layout.addLayout(content_row)
    right_container.setLayout(right_layout)

    def toggle_shelf_popup():
        if shelf_popup.isVisible():
            shelf_popup.hide()
        else:
            refresh_shelf_popup_size()
            shelf_popup.show_below(filter_button)
            filter_button.setChecked(True)

    def on_shelf_popup_closed():
        filter_button.setChecked(False)

    filter_button.clicked.connect(toggle_shelf_popup)
    shelf_popup.closed.connect(on_shelf_popup_closed)

    def on_category_changed(tree, current, previous):
        """Handle tree selection change and repopulate grid."""
        if current is None:
            return
        for other_tree in filter_trees:
            if other_tree is not tree:
                other_tree.blockSignals(True)
                other_tree.clearSelection()
                other_tree.setCurrentItem(None)
                other_tree.blockSignals(False)
        data = current.data(0, Qt.UserRole) if current else {"type": "all"}
        update_filter_badge(data)
        populate_grid(data)

    def on_search_changed(text):
        """Handle search change and repopulate grid."""
        populate_grid(search_text=text)

    for tree in filter_trees:
        tree.currentItemChanged.connect(
            lambda current, previous, t=tree: on_category_changed(t, current, previous)
        )
    search_input.textChanged.connect(on_search_changed)
    global_tree.setCurrentItem(node_all)

    def collect_tree_items(tree_item):
        items = [tree_item]
        for i in range(tree_item.childCount()):
            items.extend(collect_tree_items(tree_item.child(i)))
        return items

    def remove_user_tree_item(tree_item):
        for i in range(tree_item.childCount() - 1, -1, -1):
            remove_user_tree_item(tree_item.child(i))
        parent = tree_item.parent()
        if parent is None:
            index = user_tree.indexOfTopLevelItem(tree_item)
            if index >= 0:
                user_tree.takeTopLevelItem(index)
        else:
            parent.removeChild(tree_item)

    def delete_user_item(tree_item):
        targets = collect_tree_items(tree_item)
        was_selected = user_tree.currentItem() in targets
        remove_user_tree_item(tree_item)

        if was_selected:
            global_tree.setCurrentItem(node_all)
            populate_grid({"type": "all"})
        else:
            populate_grid()

        refresh_shelf_popup_size()

    def edit_user_item(tree_item):
        current_name = tree_item.text(0)
        new_name, ok = QInputDialog.getText(
            window,
            "Edit filter",
            "Filter name:",
            text=current_name,
        )
        if ok and new_name.strip():
            tree_item.setText(0, new_name.strip())
            refresh_shelf_popup_size()

    def add_user_filter():
        new_name, ok = QInputDialog.getText(
            window,
            "Add filter",
            "Filter name:",
        )
        if ok and new_name.strip():
            name = new_name.strip()
            item = QTreeWidgetItem([name])
            item.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled)
            item.setData(0, Qt.UserRole, {"section": "User", "subsection": name})
            user_tree.addTopLevelItem(item)
            user_tree.expandAll()
            fit_tree_to_contents(user_tree)
            refresh_shelf_popup_size()

    user_tree._shelf_handler.delete_requested.connect(delete_user_item)
    user_tree._shelf_handler.edit_requested.connect(edit_user_item)
    section_user.add_requested.connect(add_user_filter)

    layout = QVBoxLayout()
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(0)
    layout.addWidget(right_container, stretch=1)

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

    QTimer.singleShot(0, sync_filter_button_height)
    QTimer.singleShot(200, lambda: populate_grid({"type": "all"}))

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
