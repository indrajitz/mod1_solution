# Houdini Motion Manager

A small toolkit for **copying easing ("easy curves") between animated channels**
and for building a **reusable library of motion / curve presets** in Houdini.

It brings the [aescripts *Motion Manager*](https://aescripts.com/motion-manager/)
workflow — copy keyframe velocity/easing and apply one-click motion presets —
to Houdini's keyframe (channel) animation system, and is **preset-compatible
with the Cinema 4D Motion Manager** (import/export its `presets.txt`).

---

## Features

- **Copy / Paste Easing** — grab the easing (interpolation, tangents/slopes and
  accel "influence") off the active channel and stamp it onto other channels,
  keeping their original timing and values.
- **Motion Preset Library** — a one-click list of presets:
  - **Built-ins:** the full Penner easing set, identical to the Cinema 4D tool —
    Sine, Quad, Cubic, Quart, Quint, Expo, Circ (each *In* / *Out* / *In-Out*)
    and Linear.
  - **Your own:** save a channel's easing as a portable bezier curve
    (*Save Curve*) or a whole keyframe sequence such as a bounce/overshoot
    (*Save Clip*).
- **Favorites** — star the presets you use most; they sort to the top.
- **Cinema 4D import / export** — read and write the C4D `presets.txt` format,
  so presets move freely between C4D and Houdini.
- **Apply to selection** of scoped channels (or selected keyframed nodes).
- Presets are plain **JSON** files — easy to share, version, or hand-edit.
- Works in **PySide2** (Houdini 19.0–20.0) and **PySide6** (Houdini 20.5+).

---

## How easing is represented

Presets use the same model as the Cinema 4D Motion Manager: a **normalized
cubic-bezier** on a unit square, described by two `knots` at `(0,0)` and
`(1,1)`, each carrying left/right tangent-handle offsets:

```python
{'name': 'Sine', 'type': 'bezier',
 'knots': [{'x': 0, 'y': 0, 'lx': 0,     'ly': 0,    'rx': 0.37, 'ry': 0.0},
           {'x': 1, 'y': 1, 'lx': -0.37, 'ly': -0.0, 'rx': 0,    'ry': 0}],
 'favorite': False}
```

`rx/ry` and `lx/ly` are handle offsets as **fractions of the segment's width
(time) and height (value)**. When you apply a preset, the curve is re-fitted to
each segment's own frame/value range and converted to Houdini keyframe tangents:

```
accel_frames = handle_x_fraction * segment_frames
slope        = (handle_y_fraction * segment_value_delta) / accel_frames
```

so the same preset reads identically regardless of timing or scale.

Two other preset `type`s exist for completeness: **`ease`** (raw slope/accel)
and **`clip`** (a full, time-normalised keyframe sequence).

> **Caveat — vertical handles.** A handle with zero width (e.g. the `Circ`
> presets' near-vertical tangent) cannot be represented exactly, since Houdini
> has no infinite keyframe slope. Those are clamped to a small, steep finite
> handle (`core.MIN_HANDLE_X`) — visually almost identical.

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
- **Save Curve…** — captures the active channel's *first segment* easing as a
  portable bezier preset (the same format C4D uses).
- **Save Clip…** — captures the active channel's *entire* keyframe sequence.
- **☆ Favorite** — star/unstar the selected user preset.

Saved presets are written to
`$HOUDINI_USER_PREF_DIR/motion_manager_presets/` (override with the
`MOTION_MANAGER_PRESETS` environment variable).

### Cinema 4D presets
- **Import C4D…** — load a Cinema 4D Motion Manager `presets.txt` into your
  Houdini library.
- **Export C4D…** — write your Houdini library back out as a C4D `presets.txt`.

A copy of the C4D default library ships in
[`presets/c4d_default_presets.txt`](presets/c4d_default_presets.txt) for
reference (these values are also the Houdini built-ins).

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
lib.apply(lib.find("Cubic Out"), [hou.parm("/obj/geo1/tx")])

# Save the current channel's easing as a reusable (C4D-compatible) preset
my_preset = presets.PresetLibrary.bezier_from_parm(src, "My Snappy Ease")
lib.save(my_preset)

# Move presets between Cinema 4D and Houdini
lib.import_c4d_file("/path/to/c4d/presets.txt")
lib.export_c4d_file("/path/to/export/presets.txt")
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
├── presets/
│   └── c4d_default_presets.txt   # C4D default library (reference / import)
├── tests/
│   └── test_presets.py
└── README.md
```
