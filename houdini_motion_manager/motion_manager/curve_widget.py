"""A small PySide widget that draws a preset's easing curve.

Renders the normalized cubic-bezier (the same ``knots`` model used by the
preset library) inside a unit square, so presets can be picked by their shape
rather than by name - mirroring the Cinema 4D Motion Manager's curve view.

The widget is pure Qt and has no dependency on ``hou``; it can be dropped into
any PySide2 / PySide6 layout.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

try:
    from PySide6 import QtCore, QtGui, QtWidgets  # type: ignore
except ImportError:  # pragma: no cover
    from PySide2 import QtCore, QtGui, QtWidgets  # type: ignore

from .core import bezier_control_points


class CurvePreview(QtWidgets.QWidget):
    """Draws the easing curve of a single bezier preset."""

    def __init__(self, parent=None, show_handles: bool = True):
        super(CurvePreview, self).__init__(parent)
        self._knots: Optional[List[Dict[str, Any]]] = None
        self._title = ""
        self._show_handles = show_handles
        self.setMinimumHeight(140)
        self.setSizePolicy(
            QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Preferred
        )

    # -- API ------------------------------------------------------------
    def set_preset(self, preset: Optional[Dict[str, Any]]):
        """Show ``preset``; only ``bezier`` presets render a curve."""
        if preset and preset.get("type", "bezier") == "bezier" and preset.get(
            "knots"
        ):
            self._knots = preset["knots"]
            self._title = preset.get("name", "")
        else:
            self._knots = None
            self._title = preset.get("name", "") if preset else ""
        self.update()

    # -- painting -------------------------------------------------------
    def _to_screen(self, rect: QtCore.QRectF, x: float, y: float):
        """Map normalized (x, y in 0..1) to screen coords (y flipped)."""
        sx = rect.left() + x * rect.width()
        sy = rect.bottom() - y * rect.height()
        return QtCore.QPointF(sx, sy)

    def paintEvent(self, _event):
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.Antialiasing, True)

        full = QtCore.QRectF(self.rect())
        painter.fillRect(full, QtGui.QColor(43, 43, 43))

        # Plot area with padding (extra room top/bottom for overshoot curves).
        pad = 16.0
        area = full.adjusted(pad, pad, -pad, -pad)

        # Frame + grid.
        painter.setPen(QtGui.QPen(QtGui.QColor(70, 70, 70), 1))
        painter.drawRect(area)
        for i in range(1, 4):
            t = i / 4.0
            x = area.left() + t * area.width()
            y = area.top() + t * area.height()
            painter.drawLine(QtCore.QPointF(x, area.top()),
                             QtCore.QPointF(x, area.bottom()))
            painter.drawLine(QtCore.QPointF(area.left(), y),
                             QtCore.QPointF(area.right(), y))

        # Diagonal reference (the "linear" line).
        painter.setPen(QtGui.QPen(QtGui.QColor(90, 90, 90), 1, QtCore.Qt.DashLine))
        painter.drawLine(self._to_screen(area, 0.0, 0.0),
                         self._to_screen(area, 1.0, 1.0))

        if not self._knots:
            painter.setPen(QtGui.QColor(140, 140, 140))
            painter.drawText(area, QtCore.Qt.AlignCenter,
                             "No curve preview")
            painter.end()
            return

        p0, p1, p2, p3 = bezier_control_points(self._knots)
        s0 = self._to_screen(area, *p0)
        s1 = self._to_screen(area, *p1)
        s2 = self._to_screen(area, *p2)
        s3 = self._to_screen(area, *p3)

        # Tangent handles.
        if self._show_handles:
            painter.setPen(QtGui.QPen(QtGui.QColor(110, 110, 110), 1))
            painter.drawLine(s0, s1)
            painter.drawLine(s3, s2)
            painter.setBrush(QtGui.QColor(150, 150, 150))
            for pt in (s1, s2):
                painter.drawEllipse(pt, 2.5, 2.5)

        # The easing curve itself.
        path = QtGui.QPainterPath(s0)
        path.cubicTo(s1, s2, s3)
        painter.setPen(QtGui.QPen(QtGui.QColor(90, 170, 255), 2))
        painter.setBrush(QtCore.Qt.NoBrush)
        painter.drawPath(path)

        # End knots.
        painter.setBrush(QtGui.QColor(230, 230, 230))
        painter.setPen(QtCore.Qt.NoPen)
        for pt in (s0, s3):
            painter.drawEllipse(pt, 3.0, 3.0)

        # Title.
        if self._title:
            painter.setPen(QtGui.QColor(200, 200, 200))
            painter.drawText(
                full.adjusted(6, 4, -6, 0),
                QtCore.Qt.AlignTop | QtCore.Qt.AlignLeft,
                self._title,
            )
        painter.end()
