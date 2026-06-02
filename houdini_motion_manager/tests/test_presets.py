"""Unit tests that exercise the parts of Motion Manager that don't need hou.

Run with:  python -m pytest houdini_motion_manager/tests
or simply:  python houdini_motion_manager/tests/test_presets.py
"""

import json
import os
import sys
import tempfile
import unittest

# Make the package importable when run directly.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from motion_manager import core, presets  # noqa: E402


class TestBuiltinPresets(unittest.TestCase):
    def test_builtins_are_valid_beziers(self):
        self.assertTrue(presets.BUILTIN_PRESETS)
        for preset in presets.BUILTIN_PRESETS:
            presets.validate_preset(preset)  # should not raise
            self.assertTrue(preset["builtin"])
            self.assertEqual(preset["type"], "bezier")
            self.assertEqual(len(preset["knots"]), 2)

    def test_penner_set_present(self):
        names = {p["name"] for p in presets.BUILTIN_PRESETS}
        for expected in ("Sine", "Quad In", "Cubic Out", "Expo", "Circ Out",
                         "Linear", "Quint In"):
            self.assertIn(expected, names)

    def test_builtin_names_unique(self):
        names = [p["name"] for p in presets.BUILTIN_PRESETS]
        self.assertEqual(len(names), len(set(names)))


class TestC4DInterop(unittest.TestCase):
    SAMPLE = (
        "{'name': 'Sine', 'knots': [{'x': 0, 'y': 0, 'lx': 0, 'ly': 0, "
        "'rx': 0.37, 'ry': 0.0}, {'x': 1, 'y': 1, 'lx': -0.37, 'ly': -0.0, "
        "'rx': 0, 'ry': 0}], 'favorite': True}\n"
        "garbage line that should be skipped\n"
        "\n"
        "{'name': 'Linear', 'knots': [{'x': 0, 'y': 0, 'lx': 0, 'ly': 0, "
        "'rx': 0.0, 'ry': 0.0}, {'x': 1, 'y': 1, 'lx': -0.0, 'ly': -0.0, "
        "'rx': 0, 'ry': 0}], 'favorite': False}\n"
    )

    def test_parse_skips_garbage_and_sets_type(self):
        parsed = presets.parse_c4d_presets(self.SAMPLE)
        self.assertEqual(len(parsed), 2)
        self.assertEqual(parsed[0]["name"], "Sine")
        self.assertEqual(parsed[0]["type"], "bezier")
        self.assertTrue(parsed[0]["favorite"])
        self.assertFalse(parsed[1]["favorite"])

    def test_round_trip_text(self):
        parsed = presets.parse_c4d_presets(self.SAMPLE)
        text = presets.format_c4d_presets(parsed)
        reparsed = presets.parse_c4d_presets(text)
        self.assertEqual(
            [p["name"] for p in parsed], [p["name"] for p in reparsed]
        )
        self.assertEqual(
            parsed[0]["knots"][0]["rx"], reparsed[0]["knots"][0]["rx"]
        )

    def test_import_export_files(self):
        tmp = tempfile.mkdtemp(prefix="mm_c4d_")
        src = os.path.join(tmp, "presets.txt")
        with open(src, "w") as fh:
            fh.write(self.SAMPLE)

        lib = presets.PresetLibrary(directory=os.path.join(tmp, "lib"))
        n = lib.import_c4d_file(src)
        self.assertEqual(n, 2)
        self.assertIsNotNone(lib.find("Sine"))

        out = os.path.join(tmp, "out.txt")
        written = lib.export_c4d_file(out, include_builtins=False)
        self.assertEqual(written, 2)
        # Exported file re-parses cleanly.
        with open(out) as fh:
            self.assertEqual(len(presets.parse_c4d_presets(fh.read())), 2)


class TestValidation(unittest.TestCase):
    def test_missing_name(self):
        with self.assertRaises(core.MotionManagerError):
            presets.validate_preset({"type": "bezier", "knots": [{}, {}]})

    def test_bad_type(self):
        with self.assertRaises(core.MotionManagerError):
            presets.validate_preset({"name": "x", "type": "wat"})

    def test_bezier_needs_two_knots(self):
        with self.assertRaises(core.MotionManagerError):
            presets.validate_preset(
                {"name": "x", "type": "bezier", "knots": [{}]}
            )

    def test_clip_needs_keys(self):
        with self.assertRaises(core.MotionManagerError):
            presets.validate_preset({"name": "x", "type": "clip", "keys": []})


class TestLibraryRoundTrip(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="mm_test_")
        self.lib = presets.PresetLibrary(directory=self.tmp)

    def _bezier(self, name, favorite=False):
        return {
            "name": name,
            "type": "bezier",
            "favorite": favorite,
            "knots": [
                {"x": 0, "y": 0, "lx": 0, "ly": 0, "rx": 0.4, "ry": 0.0},
                {"x": 1, "y": 1, "lx": -0.4, "ly": -0.0, "rx": 0, "ry": 0},
            ],
        }

    def test_save_and_reload(self):
        path = self.lib.save(self._bezier("My Ease"))
        self.assertTrue(os.path.exists(path))
        loaded = self.lib.find("My Ease")
        self.assertIsNotNone(loaded)
        self.assertEqual(loaded["type"], "bezier")
        self.assertFalse(loaded["builtin"])
        self.assertEqual(loaded["knots"][0]["rx"], 0.4)

        all_names = [p["name"] for p in self.lib.all_presets()]
        self.assertIn("My Ease", all_names)
        self.assertIn("Sine", all_names)  # built-ins still present

    def test_favorites(self):
        self.lib.save(self._bezier("Fav", favorite=True))
        self.lib.save(self._bezier("Plain"))
        fav_names = [p["name"] for p in self.lib.favorites()]
        self.assertIn("Fav", fav_names)
        self.assertNotIn("Plain", fav_names)
        # Toggle off
        self.assertTrue(self.lib.set_favorite("Fav", False))
        self.assertNotIn("Fav", [p["name"] for p in self.lib.favorites()])

    def test_cannot_favorite_builtin(self):
        self.assertFalse(self.lib.set_favorite("Sine", True))

    def test_delete(self):
        self.lib.save(self._bezier("Temp"))
        self.assertTrue(self.lib.delete("Temp"))
        self.assertIsNone(self.lib.find("Temp"))

    def test_cannot_delete_builtin(self):
        self.assertFalse(self.lib.delete("Linear"))

    def test_saved_file_is_valid_json(self):
        path = self.lib.save(self._bezier("JSON Check"))
        with open(path) as fh:
            data = json.load(fh)
        self.assertEqual(data["name"], "JSON Check")
        self.assertEqual(data["version"], presets.PRESET_VERSION)


class TestControlPoints(unittest.TestCase):
    def test_control_points_from_handles(self):
        knots = [
            {"x": 0, "y": 0, "lx": 0, "ly": 0, "rx": 0.37, "ry": 0.0},
            {"x": 1, "y": 1, "lx": -0.37, "ly": -0.0, "rx": 0, "ry": 0},
        ]
        p0, p1, p2, p3 = core.bezier_control_points(knots)
        self.assertEqual(p0, (0.0, 0.0))
        self.assertEqual(p3, (1.0, 1.0))
        self.assertAlmostEqual(p1[0], 0.37)
        self.assertAlmostEqual(p1[1], 0.0)
        self.assertAlmostEqual(p2[0], 0.63)  # 1 + (-0.37)
        self.assertAlmostEqual(p2[1], 1.0)

    def test_every_builtin_renders_control_points(self):
        for preset in presets.BUILTIN_PRESETS:
            pts = core.bezier_control_points(preset["knots"])
            self.assertEqual(len(pts), 4)


class TestTangentMath(unittest.TestCase):
    def test_flat_handle_gives_zero_slope(self):
        # Sine knot0 out-handle: rx=0.37, ry=0 over a 24f/100v segment.
        accel, slope = core._handle_to_tangent(0.37, 0.0, 24.0, 100.0)
        self.assertAlmostEqual(slope, 0.0)
        self.assertAlmostEqual(accel, 0.37 * 24.0)

    def test_steep_handle_gives_large_slope(self):
        # Expo-In arrival handle ly=-1.0 over the segment -> steep.
        _accel, slope = core._handle_to_tangent(-0.16, -1.0, 24.0, 100.0)
        self.assertLess(slope, -10.0)

    def test_vertical_handle_is_clamped(self):
        # Circ-Out out-handle rx=0 -> clamped to MIN_HANDLE_X, finite slope.
        accel, slope = core._handle_to_tangent(0.0, 0.55, 24.0, 100.0)
        self.assertAlmostEqual(accel, core.MIN_HANDLE_X * 24.0)
        self.assertTrue(abs(slope) < float("inf"))
        self.assertGreater(slope, 0.0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
