"""PySide UI for the Motion Manager Python Panel.

Works with both PySide2 (Houdini 19.0-20.0) and PySide6 (Houdini 20.5+).

The panel is split into two parts:

* **Copy / Paste easing** - grab the easing off the active channel and stamp
  it onto other channels, just like AE's "copy / paste velocity".
* **Preset library** - a one-click list of built-in and user-saved motion
  presets, with buttons to apply, save the current selection, or delete.

Use it through Houdini:  Windows > Python Panel > Motion Manager, or via the
shelf tool installed with this package.
"""

from __future__ import annotations

# --- Qt import shim (PySide6 first, then PySide2) --------------------------
try:
    from PySide6 import QtCore, QtWidgets  # type: ignore
except ImportError:  # pragma: no cover
    from PySide2 import QtCore, QtWidgets  # type: ignore

try:  # pragma: no cover - only inside Houdini
    import hou
except ImportError:  # pragma: no cover
    hou = None  # type: ignore

from . import core, presets
from .curve_widget import CurvePreview


def _selected_parms():
    """Parameters the user wants to act on, with a friendly error if none."""
    parms = core.scoped_parms()
    if not parms:
        raise core.MotionManagerError(
            "No animated channels found.\n\n"
            "Scope one or more channels in the Animation Editor, or select "
            "node(s) with keyframed parameters, then try again."
        )
    return parms


class MotionManagerWidget(QtWidgets.QWidget):
    """The main Motion Manager panel widget."""

    def __init__(self, parent=None):
        super(MotionManagerWidget, self).__init__(parent)
        self.library = presets.PresetLibrary()
        self._build_ui()
        self.refresh_presets()
        self._update_clipboard_label()

    # -- UI construction -----------------------------------------------
    def _build_ui(self):
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        layout.addWidget(self._build_copy_group())
        layout.addWidget(self._build_preset_group(), 1)

        self.status = QtWidgets.QLabel("")
        self.status.setWordWrap(True)
        self.status.setStyleSheet("color: #9aa0a6;")
        layout.addWidget(self.status)

    def _build_copy_group(self):
        group = QtWidgets.QGroupBox("Copy / Paste Easing")
        v = QtWidgets.QVBoxLayout(group)

        row = QtWidgets.QHBoxLayout()
        self.copy_btn = QtWidgets.QPushButton("Copy Easing")
        self.copy_btn.setToolTip(
            "Copy the easing of the active scoped channel to the clipboard."
        )
        self.paste_btn = QtWidgets.QPushButton("Paste Easing")
        self.paste_btn.setToolTip(
            "Apply the copied easing onto the keyframes of the scoped channels."
        )
        self.copy_btn.clicked.connect(self.on_copy)
        self.paste_btn.clicked.connect(self.on_paste)
        row.addWidget(self.copy_btn)
        row.addWidget(self.paste_btn)
        v.addLayout(row)

        self.clipboard_label = QtWidgets.QLabel("Clipboard: empty")
        self.clipboard_label.setStyleSheet("color: #9aa0a6;")
        v.addWidget(self.clipboard_label)
        return group

    def _build_preset_group(self):
        group = QtWidgets.QGroupBox("Motion Presets")
        v = QtWidgets.QVBoxLayout(group)

        self.preset_list = QtWidgets.QListWidget()
        self.preset_list.setAlternatingRowColors(True)
        self.preset_list.itemDoubleClicked.connect(lambda _i: self.on_apply())
        self.preset_list.currentItemChanged.connect(self._on_select_preset)
        v.addWidget(self.preset_list, 1)

        # Visual preview of the selected preset's easing curve.
        self.curve_preview = CurvePreview()
        v.addWidget(self.curve_preview)

        self.preset_desc = QtWidgets.QLabel("")
        self.preset_desc.setWordWrap(True)
        self.preset_desc.setStyleSheet("color: #9aa0a6; font-style: italic;")
        v.addWidget(self.preset_desc)

        row1 = QtWidgets.QHBoxLayout()
        self.apply_btn = QtWidgets.QPushButton("Apply to Selection")
        self.apply_btn.clicked.connect(self.on_apply)
        row1.addWidget(self.apply_btn)
        v.addLayout(row1)

        row2 = QtWidgets.QHBoxLayout()
        self.save_curve_btn = QtWidgets.QPushButton("Save Curve…")
        self.save_curve_btn.setToolTip(
            "Save the active channel's first-segment easing as a reusable "
            "(C4D-compatible) bezier preset."
        )
        self.save_clip_btn = QtWidgets.QPushButton("Save Clip…")
        self.save_clip_btn.setToolTip(
            "Save the full keyframe sequence of the active channel as a preset."
        )
        self.fav_btn = QtWidgets.QPushButton("☆ Favorite")
        self.fav_btn.setToolTip("Toggle favorite on the selected user preset.")
        self.delete_btn = QtWidgets.QPushButton("Delete")
        self.save_curve_btn.clicked.connect(self.on_save_curve)
        self.save_clip_btn.clicked.connect(self.on_save_clip)
        self.fav_btn.clicked.connect(self.on_toggle_favorite)
        self.delete_btn.clicked.connect(self.on_delete)
        row2.addWidget(self.save_curve_btn)
        row2.addWidget(self.save_clip_btn)
        row2.addWidget(self.fav_btn)
        row2.addWidget(self.delete_btn)
        v.addLayout(row2)

        row3 = QtWidgets.QHBoxLayout()
        self.import_btn = QtWidgets.QPushButton("Import C4D…")
        self.import_btn.setToolTip(
            "Import a Cinema 4D Motion Manager presets.txt file."
        )
        self.export_btn = QtWidgets.QPushButton("Export C4D…")
        self.export_btn.setToolTip(
            "Export the library to a Cinema 4D compatible presets.txt file."
        )
        refresh = QtWidgets.QPushButton("Refresh")
        self.import_btn.clicked.connect(self.on_import_c4d)
        self.export_btn.clicked.connect(self.on_export_c4d)
        refresh.clicked.connect(self.refresh_presets)
        row3.addWidget(self.import_btn)
        row3.addWidget(self.export_btn)
        row3.addWidget(refresh)
        v.addLayout(row3)
        return group

    # -- helpers --------------------------------------------------------
    def _set_status(self, text: str, error: bool = False):
        self.status.setText(text)
        self.status.setStyleSheet(
            "color: #e06c75;" if error else "color: #9aa0a6;"
        )

    def _update_clipboard_label(self):
        if core.has_clipboard():
            n = core.get_clipboard().get("key_count", 0)
            self.clipboard_label.setText("Clipboard: easing of %d keyframe(s)" % n)
        else:
            self.clipboard_label.setText("Clipboard: empty")

    def _active_parm(self):
        parms = _selected_parms()
        return parms[0]

    def _report_error(self, exc: Exception):
        self._set_status(str(exc), error=True)
        if hou is not None:
            try:
                hou.ui.setStatusMessage(
                    "Motion Manager: %s" % exc,
                    severity=hou.severityType.Warning,
                )
            except Exception:  # pragma: no cover
                pass

    # -- preset list ----------------------------------------------------
    def refresh_presets(self):
        self.preset_list.clear()
        # Favorites first, then everything else, each group alphabetical-ish.
        presets_all = self.library.all_presets()
        favs = [p for p in presets_all if p.get("favorite")]
        rest = [p for p in presets_all if not p.get("favorite")]
        for preset in favs + rest:
            label = preset.get("name", "?")
            star = "★ " if preset.get("favorite") else ""
            tag = "  ·  builtin" if preset.get("builtin") else ""
            ptype = preset.get("type", "bezier")
            item = QtWidgets.QListWidgetItem(
                "%s%s   [%s]%s" % (star, label, ptype, tag)
            )
            item.setData(QtCore.Qt.UserRole, preset)
            self.preset_list.addItem(item)
        self._set_status("Loaded %d preset(s)." % self.preset_list.count())

    def _current_preset(self):
        item = self.preset_list.currentItem()
        if item is None:
            return None
        return item.data(QtCore.Qt.UserRole)

    def _on_select_preset(self, current, _previous=None):
        preset = current.data(QtCore.Qt.UserRole) if current else None
        self.preset_desc.setText(preset.get("description", "") if preset else "")
        self.curve_preview.set_preset(preset)

    # -- actions --------------------------------------------------------
    def on_copy(self):
        try:
            parm = self._active_parm()
            core.copy_easing(parm)
            self._update_clipboard_label()
            self._set_status("Copied easing from '%s'." % parm.name())
        except Exception as exc:  # noqa: BLE001 - surfaced to the user
            self._report_error(exc)

    def on_paste(self):
        try:
            parms = _selected_parms()
            n = core.paste_easing(parms)
            self._set_status("Pasted easing onto %d channel(s)." % n)
        except Exception as exc:  # noqa: BLE001
            self._report_error(exc)

    def on_apply(self):
        preset = self._current_preset()
        if not preset:
            self._set_status("Select a preset first.", error=True)
            return
        try:
            parms = _selected_parms()
            n = presets.PresetLibrary.apply(preset, parms)
            self._set_status(
                "Applied '%s' to %d channel(s)." % (preset.get("name"), n)
            )
        except Exception as exc:  # noqa: BLE001
            self._report_error(exc)

    def _ask_name(self, title: str):
        name, ok = QtWidgets.QInputDialog.getText(self, title, "Preset name:")
        if not ok or not name.strip():
            return None
        return name.strip()

    def on_save_curve(self):
        name = self._ask_name("Save Curve Preset")
        if not name:
            return
        try:
            parm = self._active_parm()
            preset = presets.PresetLibrary.bezier_from_parm(parm, name)
            self.library.save(preset)
            self.refresh_presets()
            self._set_status("Saved curve preset '%s'." % name)
        except Exception as exc:  # noqa: BLE001
            self._report_error(exc)

    def on_toggle_favorite(self):
        preset = self._current_preset()
        if not preset:
            self._set_status("Select a preset first.", error=True)
            return
        if preset.get("builtin"):
            self._set_status(
                "Built-in presets can't be favorited - save your own copy.",
                error=True,
            )
            return
        new_state = not preset.get("favorite")
        if self.library.set_favorite(preset.get("name", ""), new_state):
            self.refresh_presets()
            self._set_status(
                "%s '%s'." % ("Favorited" if new_state else "Unfavorited",
                              preset.get("name"))
            )
        else:
            self._set_status("Could not update favorite.", error=True)

    def on_import_c4d(self):
        path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, "Import Cinema 4D presets", "", "Presets (*.txt);;All files (*)"
        )
        if not path:
            return
        try:
            n = self.library.import_c4d_file(path)
            self.refresh_presets()
            self._set_status("Imported %d preset(s) from Cinema 4D." % n)
        except Exception as exc:  # noqa: BLE001
            self._report_error(exc)

    def on_export_c4d(self):
        path, _ = QtWidgets.QFileDialog.getSaveFileName(
            self, "Export Cinema 4D presets", "presets.txt",
            "Presets (*.txt);;All files (*)"
        )
        if not path:
            return
        try:
            n = self.library.export_c4d_file(path)
            self._set_status("Exported %d preset(s) to '%s'." % (n, path))
        except Exception as exc:  # noqa: BLE001
            self._report_error(exc)

    def on_save_clip(self):
        name = self._ask_name("Save Clip Preset")
        if not name:
            return
        try:
            parm = self._active_parm()
            preset = presets.PresetLibrary.clip_from_parm(parm, name)
            self.library.save(preset)
            self.refresh_presets()
            self._set_status("Saved clip preset '%s'." % name)
        except Exception as exc:  # noqa: BLE001
            self._report_error(exc)

    def on_delete(self):
        preset = self._current_preset()
        if not preset:
            self._set_status("Select a preset first.", error=True)
            return
        if preset.get("builtin"):
            self._set_status("Built-in presets cannot be deleted.", error=True)
            return
        if self.library.delete(preset.get("name", "")):
            self.refresh_presets()
            self._set_status("Deleted preset '%s'." % preset.get("name"))
        else:
            self._set_status("Could not delete preset.", error=True)


# ---------------------------------------------------------------------------
# Python Panel entry point
# ---------------------------------------------------------------------------
def create_interface():
    """Entry point referenced by motion_manager.pypanel."""
    return MotionManagerWidget()


def show_window():
    """Open the Motion Manager as a standalone window (shelf tool entry)."""
    widget = MotionManagerWidget()
    widget.setWindowTitle("Motion Manager")
    widget.resize(360, 520)
    if hou is not None:
        try:
            widget.setParent(hou.qt.mainWindow(), QtCore.Qt.Window)
        except Exception:  # pragma: no cover
            pass
    widget.show()
    return widget
