"""Houdini Motion Manager.

A small toolkit for copying keyframe easing ("easy curves") between animated
parameters and for building a reusable library of motion / curve presets.

Inspired by the After Effects "Motion Manager" workflow, ported to Houdini's
keyframe (channel) animation system.

Public API
----------
- core.copy_easing / core.paste_easing      -> copy easing between channels
- core.capture_keyframe / core.apply_keyframe
- presets.PresetLibrary                      -> save / load / apply presets
- panel.create_interface                     -> Python Panel entry point
"""

__version__ = "1.0.0"
__author__ = "Motion Manager"

from . import core  # noqa: F401
from . import presets  # noqa: F401

__all__ = ["core", "presets", "__version__"]
