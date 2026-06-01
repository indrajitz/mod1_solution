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
    def test_builtins_are_valid(self):
        self.assertTrue(presets.BUILTIN_PRESETS)
        for preset in presets.BUILTIN_PRESETS:
            # Should not raise.
            presets.validate_preset(preset)
            self.assertTrue(preset["builtin"])
            self.assertIn(preset["type"], ("ease", "clip"))

    def test_builtin_names_unique(self):
        names = [p["name"] for p in presets.BUILTIN_PRESETS]
        self.assertEqual(len(names), len(set(names)))


class TestValidation(unittest.TestCase):
    def test_missing_name(self):
        with self.assertRaises(core.MotionManagerError):
            presets.validate_preset({"type": "ease", "out": {}, "in": {}})

    def test_bad_type(self):
        with self.assertRaises(core.MotionManagerError):
            presets.validate_preset({"name": "x", "type": "wat"})

    def test_clip_needs_keys(self):
        with self.assertRaises(core.MotionManagerError):
            presets.validate_preset({"name": "x", "type": "clip", "keys": []})

    def test_ease_needs_dicts(self):
        with self.assertRaises(core.MotionManagerError):
            presets.validate_preset(
                {"name": "x", "type": "ease", "out": [], "in": {}}
            )


class TestLibraryRoundTrip(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="mm_test_")
        self.lib = presets.PresetLibrary(directory=self.tmp)

    def test_save_and_reload(self):
        preset = {
            "name": "My Ease",
            "type": "ease",
            "out": {"expression": "bezier()", "slope": 0.0, "accel": 0.4},
            "in": {"expression": "bezier()", "in_slope": 0.0, "in_accel": 0.4},
            "description": "round trip",
        }
        path = self.lib.save(preset)
        self.assertTrue(os.path.exists(path))

        # Reloaded from disk.
        loaded = self.lib.find("My Ease")
        self.assertIsNotNone(loaded)
        self.assertEqual(loaded["type"], "ease")
        self.assertFalse(loaded["builtin"])
        self.assertEqual(loaded["out"]["accel"], 0.4)

        # And it shows up alongside the built-ins.
        all_names = [p["name"] for p in self.lib.all_presets()]
        self.assertIn("My Ease", all_names)
        self.assertIn("Linear", all_names)

    def test_delete(self):
        self.lib.save(
            {"name": "Temp", "type": "ease", "out": {}, "in": {}}
        )
        self.assertTrue(self.lib.delete("Temp"))
        self.assertIsNone(self.lib.find("Temp"))

    def test_cannot_delete_builtin(self):
        self.assertFalse(self.lib.delete("Linear"))

    def test_saved_file_is_valid_json(self):
        path = self.lib.save(
            {"name": "JSON Check", "type": "ease", "out": {}, "in": {}}
        )
        with open(path) as fh:
            data = json.load(fh)
        self.assertEqual(data["name"], "JSON Check")
        self.assertEqual(data["version"], presets.PRESET_VERSION)


class TestSideHelpers(unittest.TestCase):
    def test_out_side_filters(self):
        data = {
            "expression": "bezier()",
            "slope": 1.0,
            "in_slope": 2.0,
            "accel": 0.3,
            "in_accel": 0.6,
        }
        out = core._out_side(data)
        self.assertEqual(out.get("slope"), 1.0)
        self.assertEqual(out.get("accel"), 0.3)
        self.assertNotIn("in_slope", out)
        self.assertNotIn("in_accel", out)

    def test_in_side_falls_back_to_out_values(self):
        data = {"expression": "bezier()", "slope": 1.0, "accel": 0.3}
        in_side = core._in_side(data)
        # No explicit in_* keys -> derive from the out values.
        self.assertEqual(in_side.get("in_slope"), 1.0)
        self.assertEqual(in_side.get("in_accel"), 0.3)


if __name__ == "__main__":
    unittest.main(verbosity=2)
