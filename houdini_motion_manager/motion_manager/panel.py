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
        self.save_ease_btn = QtWidgets.QPushButton("Save Ease…")
        self.save_ease_btn.setToolTip(
            "Save the easing of the active channel's first segment as a preset."
        )
        self.save_clip_btn = QtWidgets.QPushButton("Save Clip…")
        self.save_clip_btn.setToolTip(
            "Save the full keyframe sequence of the active channel as a preset."
        )
        self.delete_btn = QtWidgets.QPushButton("Delete")
        self.save_ease_btn.clicked.connect(self.on_save_ease)
        self.save_clip_btn.clicked.connect(self.on_save_clip)
        self.delete_btn.clicked.connect(self.on_delete)
        row2.addWidget(self.save_ease_btn)
        row2.addWidget(self.save_clip_btn)
        row2.addWidget(self.delete_btn)
        v.addLayout(row2)

        refresh = QtWidgets.QPushButton("Refresh")
        refresh.clicked.connect(self.refresh_presets)
        v.addWidget(refresh)
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
        for preset in self.library.all_presets():
            label = preset.get("name", "?")
            tag = "  ·  builtin" if preset.get("builtin") else ""
            ptype = preset.get("type", "ease")
            item = QtWidgets.QListWidgetItem("%s   [%s]%s" % (label, ptype, tag))
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

    def on_save_ease(self):
        name = self._ask_name("Save Ease Preset")
        if not name:
            return
        try:
            parm = self._active_parm()
            preset = presets.PresetLibrary.ease_from_parm(parm, name)
            self.library.save(preset)
            self.refresh_presets()
            self._set_status("Saved ease preset '%s'." % name)
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
