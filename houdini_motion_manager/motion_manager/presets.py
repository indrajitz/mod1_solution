"""Motion / easing preset library for the Motion Manager.

The preset model matches the Cinema 4D *Motion Manager* so presets are portable
between the two.  A preset describes a normalized cubic-bezier easing on a unit
square via two ``knots``::

    {
        'name': 'Sine',
        'type': 'bezier',
        'knots': [
            {'x': 0, 'y': 0, 'lx': 0,     'ly': 0,    'rx': 0.37, 'ry': 0.0},
            {'x': 1, 'y': 1, 'lx': -0.37, 'ly': -0.0, 'rx': 0,    'ry': 0},
        ],
        'favorite': False,
    }

``lx/ly`` and ``rx/ry`` are the left/right tangent-handle offsets expressed as
fractions of the segment's width (time) and height (value).  When applied to a
real Houdini segment the handles are re-fitted to that segment - see
:func:`core.apply_bezier_easing`.

Three preset ``type`` s are supported:

``bezier``
    The C4D-style normalized easing above (the default / portable kind).
``ease``
    A lower-level slope/accel easing (``out`` / ``in`` dicts) used internally.
``clip``
    A full, time-normalised keyframe sequence captured from a channel.

Built-in presets are the classic Penner easing set (Sine, Quad, Cubic, Quart,
Quint, Expo, Circ - each In/Out/In-Out - plus Linear), with the exact handle
values shipped by the Cinema 4D tool.  User presets live as ``*.json`` files in
``$HOUDINI_USER_PREF_DIR/motion_manager_presets`` (override with the
``MOTION_MANAGER_PRESETS`` environment variable).
"""

from __future__ import annotations

import ast
import json
import os
import re
from typing import Any, Dict, List, Optional

try:  # pragma: no cover - only inside Houdini
    import hou
except ImportError:  # pragma: no cover
    hou = None  # type: ignore

from . import core


PRESET_VERSION = 2


# ---------------------------------------------------------------------------
# Built-in presets - the Cinema 4D Motion Manager default library (Penner set).
# Stored in the native C4D text format and parsed below, which guarantees the
# values stay identical to the C4D tool and that round-tripping works.
# ---------------------------------------------------------------------------
_C4D_DEFAULT_PRESETS = """
{'name': 'Sine',        'knots': [{'x': 0, 'y': 0, 'lx': 0, 'ly': 0, 'rx': 0.37, 'ry': 0.00}, {'x': 1, 'y': 1, 'lx': -0.37, 'ly': -0.00, 'rx': 0, 'ry': 0}], 'favorite': False}
{'name': 'Sine In',     'knots': [{'x': 0, 'y': 0, 'lx': 0, 'ly': 0, 'rx': 0.12, 'ry': 0.00}, {'x': 1, 'y': 1, 'lx': -0.61, 'ly': -1.00, 'rx': 0, 'ry': 0}], 'favorite': False}
{'name': 'Sine Out',    'knots': [{'x': 0, 'y': 0, 'lx': 0, 'ly': 0, 'rx': 0.61, 'ry': 1.00}, {'x': 1, 'y': 1, 'lx': -0.12, 'ly': -0.00, 'rx': 0, 'ry': 0}], 'favorite': False}
{'name': 'Quad',        'knots': [{'x': 0, 'y': 0, 'lx': 0, 'ly': 0, 'rx': 0.45, 'ry': 0.00}, {'x': 1, 'y': 1, 'lx': -0.45, 'ly': -0.00, 'rx': 0, 'ry': 0}], 'favorite': False}
{'name': 'Quad In',     'knots': [{'x': 0, 'y': 0, 'lx': 0, 'ly': 0, 'rx': 0.11, 'ry': 0.00}, {'x': 1, 'y': 1, 'lx': -0.50, 'ly': -1.00, 'rx': 0, 'ry': 0}], 'favorite': False}
{'name': 'Quad Out',    'knots': [{'x': 0, 'y': 0, 'lx': 0, 'ly': 0, 'rx': 0.50, 'ry': 1.00}, {'x': 1, 'y': 1, 'lx': -0.11, 'ly': -0.00, 'rx': 0, 'ry': 0}], 'favorite': False}
{'name': 'Cubic',       'knots': [{'x': 0, 'y': 0, 'lx': 0, 'ly': 0, 'rx': 0.65, 'ry': 0.00}, {'x': 1, 'y': 1, 'lx': -0.65, 'ly': -0.00, 'rx': 0, 'ry': 0}], 'favorite': False}
{'name': 'Cubic In',    'knots': [{'x': 0, 'y': 0, 'lx': 0, 'ly': 0, 'rx': 0.32, 'ry': 0.00}, {'x': 1, 'y': 1, 'lx': -0.33, 'ly': -1.00, 'rx': 0, 'ry': 0}], 'favorite': False}
{'name': 'Cubic Out',   'knots': [{'x': 0, 'y': 0, 'lx': 0, 'ly': 0, 'rx': 0.33, 'ry': 1.00}, {'x': 1, 'y': 1, 'lx': -0.32, 'ly': -0.00, 'rx': 0, 'ry': 0}], 'favorite': False}
{'name': 'Quart',       'knots': [{'x': 0, 'y': 0, 'lx': 0, 'ly': 0, 'rx': 0.76, 'ry': 0.00}, {'x': 1, 'y': 1, 'lx': -0.76, 'ly': -0.00, 'rx': 0, 'ry': 0}], 'favorite': False}
{'name': 'Quart In',    'knots': [{'x': 0, 'y': 0, 'lx': 0, 'ly': 0, 'rx': 0.50, 'ry': 0.00}, {'x': 1, 'y': 1, 'lx': -0.25, 'ly': -1.00, 'rx': 0, 'ry': 0}], 'favorite': False}
{'name': 'Quart Out',   'knots': [{'x': 0, 'y': 0, 'lx': 0, 'ly': 0, 'rx': 0.25, 'ry': 1.00}, {'x': 1, 'y': 1, 'lx': -0.50, 'ly': -0.00, 'rx': 0, 'ry': 0}], 'favorite': False}
{'name': 'Quint',       'knots': [{'x': 0, 'y': 0, 'lx': 0, 'ly': 0, 'rx': 0.83, 'ry': 0.00}, {'x': 1, 'y': 1, 'lx': -0.83, 'ly': -0.00, 'rx': 0, 'ry': 0}], 'favorite': False}
{'name': 'Quint In',    'knots': [{'x': 0, 'y': 0, 'lx': 0, 'ly': 0, 'rx': 0.64, 'ry': 0.00}, {'x': 1, 'y': 1, 'lx': -0.22, 'ly': -1.00, 'rx': 0, 'ry': 0}], 'favorite': False}
{'name': 'Quint Out',   'knots': [{'x': 0, 'y': 0, 'lx': 0, 'ly': 0, 'rx': 0.22, 'ry': 1.00}, {'x': 1, 'y': 1, 'lx': -0.64, 'ly': -0.00, 'rx': 0, 'ry': 0}], 'favorite': False}
{'name': 'Expo',        'knots': [{'x': 0, 'y': 0, 'lx': 0, 'ly': 0, 'rx': 0.87, 'ry': 0.00}, {'x': 1, 'y': 1, 'lx': -0.87, 'ly': -0.00, 'rx': 0, 'ry': 0}], 'favorite': False}
{'name': 'Expo In',     'knots': [{'x': 0, 'y': 0, 'lx': 0, 'ly': 0, 'rx': 0.70, 'ry': 0.00}, {'x': 1, 'y': 1, 'lx': -0.16, 'ly': -1.00, 'rx': 0, 'ry': 0}], 'favorite': False}
{'name': 'Expo Out',    'knots': [{'x': 0, 'y': 0, 'lx': 0, 'ly': 0, 'rx': 0.16, 'ry': 1.00}, {'x': 1, 'y': 1, 'lx': -0.70, 'ly': -0.00, 'rx': 0, 'ry': 0}], 'favorite': False}
{'name': 'Circ',        'knots': [{'x': 0, 'y': 0, 'lx': 0, 'ly': 0, 'rx': 0.85, 'ry': 0.00}, {'x': 1, 'y': 1, 'lx': -0.85, 'ly': -0.00, 'rx': 0, 'ry': 0}], 'favorite': False}
{'name': 'Circ In',     'knots': [{'x': 0, 'y': 0, 'lx': 0, 'ly': 0, 'rx': 0.55, 'ry': 0.00}, {'x': 1, 'y': 1, 'lx': -0.00, 'ly': -0.55, 'rx': 0, 'ry': 0}], 'favorite': False}
{'name': 'Circ Out',    'knots': [{'x': 0, 'y': 0, 'lx': 0, 'ly': 0, 'rx': 0.00, 'ry': 0.55}, {'x': 1, 'y': 1, 'lx': -0.55, 'ly': -0.00, 'rx': 0, 'ry': 0}], 'favorite': False}
{'name': 'Linear',      'knots': [{'x': 0, 'y': 0, 'lx': 0, 'ly': 0, 'rx': 0.00, 'ry': 0.00}, {'x': 1, 'y': 1, 'lx': -0.00, 'ly': -0.00, 'rx': 0, 'ry': 0}], 'favorite': False}
"""


# ---------------------------------------------------------------------------
# Cinema 4D text format <-> preset dicts
# ---------------------------------------------------------------------------
def parse_c4d_presets(text: str) -> List[Dict[str, Any]]:
    """Parse Cinema 4D ``presets.txt`` content into a list of preset dicts.

    Each non-empty line is a Python-literal dict ``{'name':..., 'knots':[...],
    'favorite':...}``.  Malformed lines are skipped.  ``type`` is set to
    ``bezier`` and ``favorite`` is coerced to a real bool.
    """
    presets: List[Dict[str, Any]] = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            data = ast.literal_eval(line)
        except (ValueError, SyntaxError):
            continue
        if not isinstance(data, dict) or "knots" not in data:
            continue
        data["type"] = "bezier"
        data["favorite"] = bool(data.get("favorite"))
        presets.append(data)
    return presets


def format_c4d_presets(presets: List[Dict[str, Any]]) -> str:
    """Serialise bezier presets back to the Cinema 4D ``presets.txt`` format."""
    lines = []
    for preset in presets:
        if preset.get("type", "bezier") != "bezier":
            continue
        out = {
            "name": preset["name"],
            "knots": preset["knots"],
            "favorite": bool(preset.get("favorite")),
        }
        lines.append(repr(out))
    return "\n".join(lines) + ("\n" if lines else "")


def _load_builtins() -> List[Dict[str, Any]]:
    presets = parse_c4d_presets(_C4D_DEFAULT_PRESETS)
    for preset in presets:
        preset["version"] = PRESET_VERSION
        preset["builtin"] = True
    return presets


BUILTIN_PRESETS: List[Dict[str, Any]] = _load_builtins()


def _slug(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", name.strip().lower()).strip("_")
    return slug or "preset"


# ---------------------------------------------------------------------------
# Library
# ---------------------------------------------------------------------------
class PresetLibrary:
    """Loads, saves and applies motion presets."""

    def __init__(self, directory: Optional[str] = None):
        self.directory = directory or self.default_directory()

    # -- locations ------------------------------------------------------
    @staticmethod
    def default_directory() -> str:
        env = os.environ.get("MOTION_MANAGER_PRESETS")
        if env:
            return env
        if hou is not None:
            try:
                base = hou.expandString("$HOUDINI_USER_PREF_DIR")
                if base:
                    return os.path.join(base, "motion_manager_presets")
            except Exception:  # pragma: no cover - defensive
                pass
        return os.path.join(os.path.expanduser("~"), ".motion_manager_presets")

    def _ensure_dir(self) -> str:
        if not os.path.isdir(self.directory):
            os.makedirs(self.directory)
        return self.directory

    # -- listing --------------------------------------------------------
    def user_presets(self) -> List[Dict[str, Any]]:
        presets: List[Dict[str, Any]] = []
        if not os.path.isdir(self.directory):
            return presets
        for fname in sorted(os.listdir(self.directory)):
            if not fname.lower().endswith(".json"):
                continue
            path = os.path.join(self.directory, fname)
            try:
                with open(path, "r") as fh:
                    data = json.load(fh)
            except (OSError, ValueError):
                continue
            data.setdefault("name", os.path.splitext(fname)[0])
            data.setdefault("type", "bezier")
            data["builtin"] = False
            data["_path"] = path
            presets.append(data)
        return presets

    def all_presets(self) -> List[Dict[str, Any]]:
        return list(BUILTIN_PRESETS) + self.user_presets()

    def favorites(self) -> List[Dict[str, Any]]:
        return [p for p in self.all_presets() if p.get("favorite")]

    def find(self, name: str) -> Optional[Dict[str, Any]]:
        for preset in self.all_presets():
            if preset.get("name") == name:
                return preset
        return None

    # -- persistence ----------------------------------------------------
    def save(self, preset: Dict[str, Any], overwrite: bool = True) -> str:
        """Validate and write ``preset`` to disk; return the file path."""
        validate_preset(preset)
        self._ensure_dir()
        preset = dict(preset)
        preset.pop("builtin", None)
        preset.pop("_path", None)
        preset.setdefault("version", PRESET_VERSION)
        path = os.path.join(self.directory, _slug(preset["name"]) + ".json")
        if os.path.exists(path) and not overwrite:
            raise core.MotionManagerError(
                "A preset named '%s' already exists." % preset["name"]
            )
        with open(path, "w") as fh:
            json.dump(preset, fh, indent=2, sort_keys=True)
        return path

    def delete(self, name: str) -> bool:
        preset = self.find(name)
        if not preset or preset.get("builtin") or "_path" not in preset:
            return False
        try:
            os.remove(preset["_path"])
            return True
        except OSError:
            return False

    def set_favorite(self, name: str, favorite: bool = True) -> bool:
        """Toggle the favorite flag on a *user* preset (built-ins are fixed)."""
        preset = self.find(name)
        if not preset or preset.get("builtin"):
            return False
        preset = dict(preset)
        preset["favorite"] = bool(favorite)
        self.save(preset)
        return True

    # -- Cinema 4D interop ---------------------------------------------
    def import_c4d_file(self, path: str, overwrite: bool = True) -> int:
        """Import a Cinema 4D ``presets.txt`` file; return number imported."""
        with open(path, "r") as fh:
            presets = parse_c4d_presets(fh.read())
        count = 0
        for preset in presets:
            preset["version"] = PRESET_VERSION
            try:
                self.save(preset, overwrite=overwrite)
                count += 1
            except core.MotionManagerError:
                continue
        return count

    def export_c4d_file(self, path: str, include_builtins: bool = True) -> int:
        """Export bezier presets to a Cinema 4D compatible ``presets.txt``.

        Returns the number of presets written.
        """
        source = self.all_presets() if include_builtins else self.user_presets()
        beziers = [p for p in source if p.get("type", "bezier") == "bezier"]
        with open(path, "w") as fh:
            fh.write(format_c4d_presets(beziers))
        return len(beziers)

    # -- creating presets from the scene -------------------------------
    @staticmethod
    def bezier_from_parm(
        parm, name: str, favorite: bool = False
    ) -> Dict[str, Any]:
        """Capture a normalized bezier preset from ``parm``'s first segment.

        Reads the out-handle of the first key and the in-handle of the second
        key and expresses them as fractions of the segment, producing a preset
        in the portable C4D format.
        """
        core._require_hou()
        keys = list(parm.keyframes())
        if len(keys) < 2:
            raise core.MotionManagerError(
                "Select a channel with at least two keyframes to capture a curve."
            )
        a, b = keys[0], keys[1]
        fa, va = a.frame(), a.value()
        fb, vb = b.frame(), b.value()
        dx = (fb - fa) or 1.0
        dy = (vb - va) or 1.0

        out_accel = core._safe_call(a, "accel") or 0.0
        out_slope = core._safe_call(a, "slope") or 0.0
        in_accel = core._safe_call(b, "inAccel") or 0.0
        in_slope = core._safe_call(b, "inSlope") or 0.0

        rx = out_accel / dx
        ry = (out_slope * out_accel) / dy
        lx = -in_accel / dx
        ly = -(in_slope * in_accel) / dy

        return {
            "name": name,
            "type": "bezier",
            "version": PRESET_VERSION,
            "favorite": bool(favorite),
            "knots": [
                {"x": 0, "y": 0, "lx": 0, "ly": 0, "rx": rx, "ry": ry},
                {"x": 1, "y": 1, "lx": lx, "ly": ly, "rx": 0, "ry": 0},
            ],
        }

    @staticmethod
    def clip_from_parm(parm, name: str, description: str = "") -> Dict[str, Any]:
        """Build a ``clip`` preset from the full keyframe sequence of ``parm``."""
        clip = core.capture_channel(parm, normalize_time=True)
        clip["name"] = name
        clip["version"] = PRESET_VERSION
        clip["description"] = description
        return clip

    # -- applying presets ----------------------------------------------
    @staticmethod
    def apply(preset: Dict[str, Any], parms, frame_range=None) -> int:
        """Apply ``preset`` to each parameter in ``parms``.

        Returns the number of parameters affected.
        """
        validate_preset(preset)
        ptype = preset.get("type", "bezier")
        affected = 0
        if ptype == "bezier":
            knots = preset["knots"]
            knot0, knot1 = knots[0], knots[-1]
            for parm in parms:
                try:
                    core.apply_bezier_easing(parm, knot0, knot1, frame_range)
                    affected += 1
                except core.MotionManagerError:
                    continue
        elif ptype == "ease":
            out_data = preset.get("out", {})
            in_data = preset.get("in", {})
            for parm in parms:
                try:
                    core.apply_segment_easing(parm, out_data, in_data, frame_range)
                    affected += 1
                except core.MotionManagerError:
                    continue
        elif ptype == "clip":
            affected = core.paste_easing(parms, preset)
        else:
            raise core.MotionManagerError("Unknown preset type: %r" % ptype)

        if not affected:
            raise core.MotionManagerError(
                "Preset could not be applied - do the channels have keyframes?"
            )
        return affected


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------
def validate_preset(preset: Dict[str, Any]) -> None:
    """Raise :class:`core.MotionManagerError` if ``preset`` is malformed."""
    if not isinstance(preset, dict):
        raise core.MotionManagerError("Preset must be a dictionary.")
    if not preset.get("name"):
        raise core.MotionManagerError("Preset is missing a 'name'.")
    ptype = preset.get("type", "bezier")
    if ptype == "bezier":
        knots = preset.get("knots")
        if not isinstance(knots, list) or len(knots) < 2:
            raise core.MotionManagerError(
                "A 'bezier' preset needs a 'knots' list with two entries."
            )
        for knot in (knots[0], knots[-1]):
            if not isinstance(knot, dict):
                raise core.MotionManagerError("Each knot must be a dictionary.")
    elif ptype == "ease":
        if not isinstance(preset.get("out", {}), dict) or not isinstance(
            preset.get("in", {}), dict
        ):
            raise core.MotionManagerError(
                "An 'ease' preset needs 'out' and 'in' dictionaries."
            )
    elif ptype == "clip":
        keys = preset.get("keys")
        if not isinstance(keys, list) or not keys:
            raise core.MotionManagerError(
                "A 'clip' preset needs a non-empty 'keys' list."
            )
    else:
        raise core.MotionManagerError("Unknown preset type: %r" % ptype)
