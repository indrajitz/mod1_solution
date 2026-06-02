"""Core keyframe / easing operations for the Motion Manager.

This module captures the "shape" of an animation curve segment (the easing)
from Houdini keyframes and re-applies it elsewhere.  In Houdini a parameter's
animation is described by a list of ``hou.Keyframe`` objects.  The easing of a
segment between two keys is defined by:

    * the interpolation expression  (e.g. ``bezier()``, ``linear()`` ...)
    * the in / out slopes (tangent direction)
    * the in / out accel (tangent length / "influence")
    * the auto-slope and tied-tangent flags

We serialise those properties into plain dictionaries so they can be copied
between channels or stored on disk as JSON presets.

The module is written so it can be imported *without* the ``hou`` module
present (e.g. for unit testing the serialisation helpers).  Any function that
actually touches Houdini will raise a clear error if ``hou`` is unavailable.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence

try:  # pragma: no cover - exercised only inside Houdini
    import hou
except ImportError:  # pragma: no cover
    hou = None  # type: ignore


# Properties we read from / write to a hou.Keyframe.  Each entry is
# (preset_key, getter_name, setter_name).  Getters/setters are looked up with
# getattr so the code keeps working across Houdini versions that may add or
# rename a method - anything missing is simply skipped.
_KEYFRAME_PROPS = (
    ("slope", "slope", "setSlope"),
    ("in_slope", "inSlope", "setInSlope"),
    ("accel", "accel", "setAccel"),
    ("in_accel", "inAccel", "setInAccel"),
)

_KEYFRAME_FLAGS = (
    ("slope_auto", "isSlopeAuto", "setSlopeAuto"),
    ("in_slope_auto", "isInSlopeAuto", "setInSlopeAuto"),
    ("slope_tied", "isSlopeTied", "setSlopeTied"),
    ("accel_tied", "isAccelTied", "setAccelTied"),
    ("accel_as_ratio", "interpretAccelAsRatio", "setInterpretAccelAsRatio"),
)


class MotionManagerError(RuntimeError):
    """Raised for any recoverable Motion Manager problem."""


def _require_hou():
    if hou is None:  # pragma: no cover - only outside Houdini
        raise MotionManagerError(
            "This operation requires Houdini's 'hou' module and must be run "
            "from inside Houdini."
        )
    return hou


def _safe_call(obj: Any, method_name: str, *args):
    """Call ``obj.method_name(*args)`` if it exists, else return None.

    Houdini's keyframe API differs slightly between major versions; rather than
    hard-failing on a missing method we degrade gracefully.
    """
    method = getattr(obj, method_name, None)
    if method is None:
        return None
    try:
        return method(*args)
    except (hou.OperationFailed, TypeError, ValueError):  # type: ignore[union-attr]
        return None


# ---------------------------------------------------------------------------
# Capture / apply a single keyframe
# ---------------------------------------------------------------------------
def capture_keyframe(kf, include_value: bool = True) -> Dict[str, Any]:
    """Return a serialisable dict describing the easing of ``kf``.

    Parameters
    ----------
    kf:
        A ``hou.Keyframe`` instance.
    include_value:
        Store the keyframe value / frame too.  Useful for full copy-paste,
        unwanted when saving a reusable easing preset.
    """
    _require_hou()
    data: Dict[str, Any] = {}

    expr = _safe_call(kf, "expression")
    if expr is not None:
        data["expression"] = expr

    for preset_key, getter, _setter in _KEYFRAME_PROPS:
        value = _safe_call(kf, getter)
        if value is not None:
            data[preset_key] = float(value)

    for preset_key, getter, _setter in _KEYFRAME_FLAGS:
        value = _safe_call(kf, getter)
        if value is not None:
            data[preset_key] = bool(value)

    if include_value:
        frame = _safe_call(kf, "frame")
        if frame is not None:
            data["frame"] = float(frame)
        value = _safe_call(kf, "value")
        if value is not None:
            data["value"] = float(value)

    return data


def apply_keyframe(kf, data: Dict[str, Any], set_value: bool = False) -> None:
    """Apply easing ``data`` (from :func:`capture_keyframe`) onto ``kf``.

    ``set_value`` controls whether the stored frame/value is written; when
    pasting easing onto existing animation you usually want to keep the
    original timing and only transfer the curve shape, so it defaults to False.
    """
    _require_hou()

    if set_value:
        if "frame" in data:
            _safe_call(kf, "setFrame", float(data["frame"]))
        if "value" in data:
            _safe_call(kf, "setValue", float(data["value"]))

    if "expression" in data:
        _safe_call(kf, "setExpression", data["expression"])

    # Flags first (auto-slope must be turned off before an explicit slope
    # value will "stick").
    for preset_key, _getter, setter in _KEYFRAME_FLAGS:
        if preset_key in data:
            _safe_call(kf, setter, bool(data[preset_key]))

    for preset_key, _getter, setter in _KEYFRAME_PROPS:
        if preset_key in data:
            _safe_call(kf, setter, float(data[preset_key]))


# ---------------------------------------------------------------------------
# Parameter helpers
# ---------------------------------------------------------------------------
def _keyframes(parm) -> List:
    return list(_safe_call(parm, "keyframes") or [])


def capture_channel(parm, normalize_time: bool = True) -> Dict[str, Any]:
    """Capture every keyframe of ``parm`` into a serialisable clip dict.

    With ``normalize_time`` the keys store frames relative to the first key,
    which lets the clip be pasted at any point on the timeline.
    """
    _require_hou()
    keys = _keyframes(parm)
    if not keys:
        raise MotionManagerError(
            "Parameter '%s' has no keyframes to copy." % parm.name()
        )

    first_frame = _safe_call(keys[0], "frame") or 0.0
    captured = []
    for kf in keys:
        entry = capture_keyframe(kf, include_value=True)
        if normalize_time and "frame" in entry:
            entry["frame"] = entry["frame"] - first_frame
        captured.append(entry)

    return {
        "type": "clip",
        "key_count": len(captured),
        "keys": captured,
    }


# Module level "clipboard" used by the simple copy / paste buttons.
_CLIPBOARD: Dict[str, Any] = {}


def copy_easing(parm) -> Dict[str, Any]:
    """Copy the easing of every keyframe on ``parm`` to the clipboard."""
    clip = capture_channel(parm, normalize_time=True)
    _CLIPBOARD.clear()
    _CLIPBOARD.update(clip)
    return clip


def get_clipboard() -> Dict[str, Any]:
    return dict(_CLIPBOARD)


def has_clipboard() -> bool:
    return bool(_CLIPBOARD.get("keys"))


def paste_easing(parms: Sequence, clip: Optional[Dict[str, Any]] = None) -> int:
    """Apply a copied clip's easing onto each parameter in ``parms``.

    The keyframes already present on each target parameter are matched to the
    clip *in order* and only their easing (not their timing or value) is
    overwritten.  Extra keys on either side are ignored.

    Returns the number of parameters that were modified.
    """
    _require_hou()
    clip = clip or get_clipboard()
    keys = clip.get("keys") if clip else None
    if not keys:
        raise MotionManagerError("Nothing to paste - copy an easing first.")

    modified = 0
    for parm in parms:
        target_keys = _keyframes(parm)
        if not target_keys:
            continue
        for kf, data in zip(target_keys, keys):
            apply_keyframe(kf, data, set_value=False)
            parm.setKeyframe(kf)
        modified += 1

    if not modified:
        raise MotionManagerError(
            "No target parameters had keyframes to paste onto."
        )
    return modified


# ---------------------------------------------------------------------------
# Normalized cubic-bezier easing (Cinema 4D Motion Manager model)
# ---------------------------------------------------------------------------
# A preset's easing is described as a unit-square curve: two knots at (0,0) and
# (1,1), each with handle offsets expressed as fractions of the segment's width
# (time) and height (value).  Applying it to a real segment scales those
# fractions by the segment's frame-delta (dx) and value-delta (dy) and converts
# the resulting handle vector into a Houdini keyframe slope + accel.
#
# Houdini's bezier handle endpoint, relative to a key, is
#   (accel_frames, slope * accel_frames)
# so a target handle vector of (hx*dx, hy*dy) gives
#   accel_frames = hx*dx   and   slope = (hy*dy) / (hx*dx).
# A near-zero hx (a vertical handle, e.g. the Circ presets) can't be exactly
# represented - Houdini has no infinite tangent - so we clamp hx to MIN_HANDLE_X
# which keeps the handle's height exact and only approximates its steepness.

MIN_HANDLE_X = 0.02


def bezier_control_points(knots: Sequence[Dict[str, Any]]):
    """Return the four cubic-bezier control points for a 2-knot preset.

    ``P0`` = first knot, ``P1`` = first knot + its right handle,
    ``P2`` = last knot + its left handle, ``P3`` = last knot.  Used both to
    apply the easing and to draw its preview, so the math stays in one place.
    """
    k0, k1 = knots[0], knots[-1]
    p0 = (float(k0.get("x", 0.0)), float(k0.get("y", 0.0)))
    p3 = (float(k1.get("x", 1.0)), float(k1.get("y", 1.0)))
    p1 = (p0[0] + float(k0.get("rx", 0.0)), p0[1] + float(k0.get("ry", 0.0)))
    p2 = (p3[0] + float(k1.get("lx", 0.0)), p3[1] + float(k1.get("ly", 0.0)))
    return p0, p1, p2, p3


def _handle_to_tangent(hx: float, hy: float, dx: float, dy: float):
    """Convert a normalized handle offset to (accel_frames, slope)."""
    hx = abs(float(hx))
    dx = abs(float(dx))
    accel = max(hx, MIN_HANDLE_X) * dx
    handle_y = float(hy) * float(dy)
    slope = handle_y / accel if accel else 0.0
    return accel, slope


def apply_bezier_easing(
    parm,
    knot0: Dict[str, Any],
    knot1: Dict[str, Any],
    frame_range: Optional[Sequence[float]] = None,
) -> int:
    """Apply a normalized 2-knot bezier ease to every segment of ``parm``.

    ``knot0`` supplies the out-handle (rx, ry) used on the leaving side of each
    key; ``knot1`` supplies the in-handle (lx, ly) used on the arriving side of
    the next key.  The shape is re-fitted to each segment's own frame/value
    range, so the same preset reads identically regardless of timing or scale.

    Returns the number of keyframes touched.
    """
    _require_hou()
    keys = _keyframes(parm)
    if len(keys) < 2:
        raise MotionManagerError(
            "Need at least two keyframes to apply a bezier easing."
        )

    if frame_range is not None:
        lo, hi = frame_range
        keys = [k for k in keys if lo <= (_safe_call(k, "frame") or 0.0) <= hi]
        if len(keys) < 2:
            raise MotionManagerError(
                "Less than two keyframes fall inside the given range."
            )

    rx, ry = knot0.get("rx", 0.0), knot0.get("ry", 0.0)
    lx, ly = knot1.get("lx", 0.0), knot1.get("ly", 0.0)

    touched = 0
    for index, kf in enumerate(keys):
        frame = _safe_call(kf, "frame") or 0.0
        value = _safe_call(kf, "value") or 0.0

        # Out side -> shaped by the next segment.
        if index < len(keys) - 1:
            nxt = keys[index + 1]
            dx = (_safe_call(nxt, "frame") or 0.0) - frame
            dy = (_safe_call(nxt, "value") or 0.0) - value
            if dx:
                accel, slope = _handle_to_tangent(rx, ry, dx, dy)
                apply_keyframe(
                    kf,
                    {
                        "expression": "bezier()",
                        "slope_auto": False,
                        "slope": slope,
                        "accel": accel,
                    },
                    set_value=False,
                )

        # In side -> shaped by the previous segment.
        if index > 0:
            prv = keys[index - 1]
            dx = frame - (_safe_call(prv, "frame") or 0.0)
            dy = value - (_safe_call(prv, "value") or 0.0)
            if dx:
                accel, slope = _handle_to_tangent(lx, ly, dx, dy)
                apply_keyframe(
                    kf,
                    {
                        "expression": "bezier()",
                        "in_slope_auto": False,
                        "in_slope": slope,
                        "in_accel": accel,
                    },
                    set_value=False,
                )

        parm.setKeyframe(kf)
        touched += 1

    return touched


# ---------------------------------------------------------------------------
# Applying a 2-point easing preset across a selection of segments
# ---------------------------------------------------------------------------
def apply_segment_easing(
    parm,
    out_data: Dict[str, Any],
    in_data: Dict[str, Any],
    frame_range: Optional[Sequence[float]] = None,
) -> int:
    """Apply an AE-style ease to every segment of ``parm``.

    ``out_data`` is applied to the *leaving* (out) side of each key and
    ``in_data`` to the *arriving* (in) side of the next key, which is exactly
    how an "ease" preset shapes a segment between two keys.

    Returns the number of keyframes touched.
    """
    _require_hou()
    keys = _keyframes(parm)
    if len(keys) < 2:
        raise MotionManagerError(
            "Need at least two keyframes to apply a segment easing."
        )

    if frame_range is not None:
        lo, hi = frame_range
        keys = [k for k in keys if lo <= (_safe_call(k, "frame") or 0.0) <= hi]
        if len(keys) < 2:
            raise MotionManagerError(
                "Less than two keyframes fall inside the given range."
            )

    touched = 0
    for index, kf in enumerate(keys):
        is_first = index == 0
        is_last = index == len(keys) - 1

        # Out side of every key except the last.
        if not is_last and out_data:
            apply_keyframe(kf, _out_side(out_data), set_value=False)
        # In side of every key except the first.
        if not is_first and in_data:
            apply_keyframe(kf, _in_side(in_data), set_value=False)

        parm.setKeyframe(kf)
        touched += 1

    return touched


def _out_side(data: Dict[str, Any]) -> Dict[str, Any]:
    """Translate a generic easing dict to only affect the out tangent."""
    out: Dict[str, Any] = {}
    if "expression" in data:
        out["expression"] = data["expression"]
    if "slope" in data:
        out["slope"] = data["slope"]
    if "accel" in data:
        out["accel"] = data["accel"]
    if "slope_auto" in data:
        out["slope_auto"] = data["slope_auto"]
    return out


def _in_side(data: Dict[str, Any]) -> Dict[str, Any]:
    """Translate a generic easing dict to only affect the in tangent."""
    out: Dict[str, Any] = {}
    if "expression" in data:
        out["expression"] = data["expression"]
    if "in_slope" in data:
        out["in_slope"] = data["in_slope"]
    elif "slope" in data:
        out["in_slope"] = data["slope"]
    if "in_accel" in data:
        out["in_accel"] = data["in_accel"]
    elif "accel" in data:
        out["in_accel"] = data["accel"]
    if "in_slope_auto" in data:
        out["in_slope_auto"] = data["in_slope_auto"]
    elif "slope_auto" in data:
        out["in_slope_auto"] = data["slope_auto"]
    return out


# ---------------------------------------------------------------------------
# Selection helpers (best-effort, version tolerant)
# ---------------------------------------------------------------------------
def scoped_parms() -> List:
    """Return the parameters currently scoped in the Animation Editor.

    Falls back to the keyframed parameters of the selected nodes when no
    scoped channel list is available.
    """
    _require_hou()

    # Newer builds expose the scoped channels via the playbar's channel list.
    channel_list = _safe_call(hou.playbar, "channelList")
    if channel_list is not None:
        parms = _safe_call(channel_list, "parms")
        if parms:
            return list(parms)

    # Fallback: keyframed parameters on the currently selected nodes.
    parms: List = []
    for node in hou.selectedNodes():
        for parm in node.parms():
            if _keyframes(parm):
                parms.append(parm)
    return parms
