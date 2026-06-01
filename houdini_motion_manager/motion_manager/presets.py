"""Motion / easing preset library for the Motion Manager.

A *preset* is a small JSON document describing the easing of a curve segment
or a whole keyframe clip.  Two kinds are supported:

``ease``
    A two-sided segment easing (an "easy curve"): ``out`` shapes the leaving
    tangent of a key and ``in`` shapes the arriving tangent of the next key.
    This is the bread-and-butter AE-style easing preset.

``clip``
    A full sequence of keyframes captured from a channel (see
    :func:`core.capture_channel`).  Lets you store and re-stamp a complete
    motion such as a bounce or an overshoot.

Built-in presets are defined in :data:`BUILTIN_PRESETS`.  User presets live as
``*.json`` files in the user preset directory, which defaults to
``$HOUDINI_USER_PREF_DIR/motion_manager_presets`` and can be overridden with
the ``MOTION_MANAGER_PRESETS`` environment variable.
"""

from __future__ import annotations

import json
import os
import re
from typing import Any, Dict, List, Optional

try:  # pragma: no cover - only inside Houdini
    import hou
except ImportError:  # pragma: no cover
    hou = None  # type: ignore

from . import core


PRESET_VERSION = 1


# ---------------------------------------------------------------------------
# Built-in presets
# ---------------------------------------------------------------------------
# Slope is expressed in value-units / frame.  A slope of 0 produces a flat
# (horizontal) tangent - the classic "ease".  ``accel`` controls how far the
# tangent handle reaches and therefore the "influence" of the ease.
def _ease(name: str, out: Dict[str, Any], in_: Dict[str, Any], desc: str = ""):
    return {
        "name": name,
        "type": "ease",
        "version": PRESET_VERSION,
        "builtin": True,
        "description": desc,
        "out": out,
        "in": in_,
    }


_FLAT = {"expression": "bezier()", "slope": 0.0, "slope_auto": False}
_SOFT = {"accel": 0.20}
_MED = {"accel": 0.33}
_STRONG = {"accel": 0.55}


BUILTIN_PRESETS: List[Dict[str, Any]] = [
    _ease(
        "Linear",
        {"expression": "linear()", "slope_auto": False},
        {"expression": "linear()", "slope_auto": False},
        "Constant velocity, no easing.",
    ),
    _ease(
        "Hold",
        {"expression": "constant()"},
        {"expression": "constant()"},
        "Stepped / held value until the next key.",
    ),
    _ease(
        "Smooth (Auto)",
        {"expression": "bezier()", "slope_auto": True},
        {"expression": "bezier()", "in_slope_auto": True},
        "Houdini's automatic smooth tangents.",
    ),
    _ease(
        "Ease In",
        {"expression": "bezier()", "slope_auto": True},
        dict(_FLAT, **_MED),
        "Accelerates out, eases into the next key.",
    ),
    _ease(
        "Ease Out",
        dict(_FLAT, **_MED),
        {"expression": "bezier()", "in_slope_auto": True},
        "Eases away from the key, then continues.",
    ),
    _ease(
        "Ease In-Out",
        dict(_FLAT, **_MED),
        dict({"expression": "bezier()", "in_slope": 0.0, "in_slope_auto": False}, **{"in_accel": _MED["accel"]}),
        "Soft on both ends - the default 'easy ease'.",
    ),
    _ease(
        "Soft Ease",
        dict(_FLAT, **_SOFT),
        dict({"expression": "bezier()", "in_slope": 0.0, "in_slope_auto": False}, **{"in_accel": _SOFT["accel"]}),
        "Gentle ease with low influence.",
    ),
    _ease(
        "Strong Ease",
        dict(_FLAT, **_STRONG),
        dict({"expression": "bezier()", "in_slope": 0.0, "in_slope_auto": False}, **{"in_accel": _STRONG["accel"]}),
        "Heavy ease with high influence / slow middle.",
    ),
]


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
            data["builtin"] = False
            data["_path"] = path
            presets.append(data)
        return presets

    def all_presets(self) -> List[Dict[str, Any]]:
        return list(BUILTIN_PRESETS) + self.user_presets()

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

    # -- creating presets from the scene -------------------------------
    @staticmethod
    def ease_from_parm(parm, name: str, description: str = "") -> Dict[str, Any]:
        """Build an ``ease`` preset from the first segment of ``parm``.

        Reads the out-tangent of the first key and the in-tangent of the
        second key - exactly the data that defines a reusable easy curve.
        """
        core._require_hou()
        keys = list(parm.keyframes())
        if len(keys) < 2:
            raise core.MotionManagerError(
                "Select a channel with at least two keyframes to capture an ease."
            )
        first = core.capture_keyframe(keys[0], include_value=False)
        second = core.capture_keyframe(keys[1], include_value=False)
        return {
            "name": name,
            "type": "ease",
            "version": PRESET_VERSION,
            "description": description,
            "out": core._out_side(first),
            "in": core._in_side(second),
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
        ptype = preset.get("type", "ease")
        affected = 0
        if ptype == "ease":
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
    ptype = preset.get("type", "ease")
    if ptype == "ease":
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
