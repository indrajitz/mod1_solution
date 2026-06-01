# Houdini Motion Manager

A small toolkit for **copying easing ("easy curves") between animated channels**
and for building a **reusable library of motion / curve presets** in Houdini.

It brings the [aescripts *Motion Manager*](https://aescripts.com/motion-manager/)
workflow — copy keyframe velocity/easing and apply one-click motion presets —
to Houdini's keyframe (channel) animation system.

---

## Features

- **Copy / Paste Easing** — grab the easing (interpolation, tangents/slopes and
  accel "influence") off the active channel and stamp it onto other channels,
  keeping their original timing and values.
- **Motion Preset Library** — a one-click list of presets:
  - **Built-ins:** Linear, Hold, Smooth (Auto), Ease In, Ease Out,
    Ease In-Out, Soft Ease, Strong Ease.
  - **Your own:** save the easing of a segment (*Save Ease*) or a whole
    keyframe sequence such as a bounce/overshoot (*Save Clip*).
- **Apply to selection** of scoped channels (or selected keyframed nodes).
- Presets are plain **JSON** files — easy to share, version, or hand-edit.
- Works in **PySide2** (Houdini 19.0–20.0) and **PySide6** (Houdini 20.5+).

---

## How easing is represented

A Houdini animation curve is a list of `hou.Keyframe`s. The "shape" of a
segment between two keys is defined by:

| Property        | Meaning                                             |
|-----------------|-----------------------------------------------------|
| `expression`    | interpolation function (`bezier()`, `linear()`, …)  |
| `slope`/`in_slope` | tangent direction leaving / entering the key     |
| `accel`/`in_accel` | tangent length — the "influence" of the ease     |
| auto / tied flags | Houdini's auto-slope and tied-tangent behaviour   |

An **ease** preset stores the *out* side of a key and the *in* side of the next
key — exactly what defines an easy curve. A **clip** preset stores a full,
time-normalised keyframe sequence.

---

## Installation

1. Copy the whole `houdini_motion_manager/` folder somewhere permanent, e.g.
   `~/houdini_tools/houdini_motion_manager`.

2. Tell Houdini about it with the included package file:
   - Copy `packages/motion_manager.json` into your
     `$HOUDINI_USER_PREF_DIR/packages/` folder
     (e.g. `~/houdini20.5/packages/` on Linux/Mac,
     `C:\Users\<you>\Documents\houdini20.5\packages\` on Windows).
   - Edit the copied file and set `MOTION_MANAGER_ROOT` to the **absolute path**
     of the `houdini_motion_manager` folder from step 1.

3. Restart Houdini.

The package adds the `motion_manager` Python module to `PYTHONPATH` and registers
the `python_panels/` and `toolbar/` definitions.

> Manual alternative (no package file): copy `python_panels/motion_manager.pypanel`
> into `$HOUDINI_USER_PREF_DIR/python_panels/`, copy
> `toolbar/motion_manager.shelf` into `$HOUDINI_USER_PREF_DIR/toolbar/`, and add
> the `houdini_motion_manager` folder to `PYTHONPATH`.

---

## Usage

Open the panel via **Windows ▸ Python Panel ▸ Motion Manager**, or click the
**Motion Manager** tool on the *Motion* shelf.

### Copy an easy curve between channels
1. In the **Animation Editor**, scope the channel you like the easing of.
2. Click **Copy Easing**.
3. Scope the target channel(s).
4. Click **Paste Easing** — the easing is transferred; timing and values stay.

### Apply a preset
1. Scope the channel(s) you want to affect.
2. Select a preset in the list and click **Apply to Selection**
   (or double-click the preset).

### Save your own preset
- **Save Ease…** — captures the easing of the active channel's *first segment*.
- **Save Clip…** — captures the active channel's *entire* keyframe sequence.

Saved presets are written to
`$HOUDINI_USER_PREF_DIR/motion_manager_presets/` (override with the
`MOTION_MANAGER_PRESETS` environment variable).

---

## Scripting API

Everything the panel does is available from Python (e.g. in the shelf, in
PDG, or in your own tools):

```python
import hou
from motion_manager import core, presets

# Copy easing from one parm to others
src = hou.parm("/obj/geo1/tx")
core.copy_easing(src)
core.paste_easing([hou.parm("/obj/geo1/ty"), hou.parm("/obj/geo1/tz")])

# Apply a built-in preset to a selection of channels
lib = presets.PresetLibrary()
ease_in_out = lib.find("Ease In-Out")
lib.apply(ease_in_out, [hou.parm("/obj/geo1/tx")])

# Save the current channel's easing as a reusable preset
my_preset = presets.PresetLibrary.ease_from_parm(src, "My Snappy Ease")
lib.save(my_preset)
```

---

## Development / tests

The serialisation, validation and preset-library logic don't depend on
Houdini and are unit-tested:

```bash
python3 houdini_motion_manager/tests/test_presets.py
# or
python3 -m pytest houdini_motion_manager/tests
```

The keyframe-touching code in `core.py` is written defensively (every
`hou.Keyframe` method is looked up by name and skipped if absent) so it stays
compatible across Houdini versions.

---

## Layout

```
houdini_motion_manager/
├── motion_manager/          # Python package
│   ├── core.py              # keyframe capture / apply, copy / paste
│   ├── presets.py           # preset library + built-in eases
│   └── panel.py             # PySide UI (Python Panel)
├── python_panels/
│   └── motion_manager.pypanel
├── toolbar/
│   └── motion_manager.shelf
├── packages/
│   └── motion_manager.json  # Houdini package definition
├── tests/
│   └── test_presets.py
└── README.md
```
