# -*- coding: utf-8 -*-
"""
L-Object test suite. Must be run with Cinema 4D's c4dpy, with the plugin loaded:
see run_tests.bat
"""

import os
import sys
import math
import random
import unittest
import importlib.machinery
import importlib.util

import c4d
from c4d import Vector, HandleInfo

PLUGIN_ID = 1027130
PLUGIN_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'L-Object')
PLUGIN_FILE = os.path.join(PLUGIN_DIR, 'L-Object.pyp')
DESCRIPTION_HEADER = os.path.join(PLUGIN_DIR, 'res', 'description', 'olobject.h')
EPSILON = 1e-3


def read_description_ids():
    """Returns {name: id} from the olobject.h enum."""
    with open(DESCRIPTION_HEADER) as f:
        content = f.read()
    body = content[content.index('{') + 1:content.index('}')]
    ids, current = {}, None
    for entry in body.split(','):
        entry = entry.strip()
        if not entry:
            continue
        if '=' in entry:
            name, value = (s.strip() for s in entry.split('='))
            current = int(value)
        else:
            name, current = entry, current + 1
        ids[name] = current
    return ids


DESCRIPTION_IDS = read_description_ids()


def load_plugin_module():
    """
    Loads L-Object.pyp as a module (without registering the plugin again).
    The description symbols (c4d.FRONT_HEIGHT...) are hidden during the load, as they
    do not exist yet when Cinema 4D executes the plugin file at startup.
    """
    saved = dict((name, getattr(c4d, name)) for name in DESCRIPTION_IDS if hasattr(c4d, name))
    for name in saved:
        delattr(c4d, name)
    try:
        loader = importlib.machinery.SourceFileLoader('lobject_plugin', PLUGIN_FILE)
        spec = importlib.util.spec_from_loader(loader.name, loader)
        module = importlib.util.module_from_spec(spec)
        loader.exec_module(module)
        return module
    finally:
        for name, value in saved.items():
            setattr(c4d, name, value)


lobject = load_plugin_module()

SHAPE_PARAMS = list(lobject.SHAPE_DEFAULTS.keys())
FRONT_HEIGHT, WALL_HEIGHT, WIDTH = lobject.FRONT_HEIGHT, lobject.WALL_HEIGHT, lobject.WIDTH
FLOOR_DEPTH, TOP_DEPTH = lobject.FLOOR_DEPTH, lobject.TOP_DEPTH
FRONT_RADIUS, BACK_RADIUS, TOP_RADIUS = lobject.FRONT_RADIUS, lobject.BACK_RADIUS, lobject.TOP_RADIUS
WIDTH_SEGMENTS = lobject.WIDTH_SEGMENTS


def assert_invariants(test, v):
    for param_id in SHAPE_PARAMS:
        test.assertGreaterEqual(v[param_id], 0., 'negative value for %d' % param_id)
    test.assertLessEqual(v[FRONT_RADIUS], v[FRONT_HEIGHT] + EPSILON)
    test.assertLessEqual(v[FRONT_RADIUS] + v[BACK_RADIUS], v[FLOOR_DEPTH] + EPSILON)
    test.assertLessEqual(v[BACK_RADIUS] + v[TOP_RADIUS], v[WALL_HEIGHT] + EPSILON)
    test.assertLessEqual(v[TOP_RADIUS], v[TOP_DEPTH] + EPSILON)


def bounding_box(obj):
    points = [obj.GetMg() * p for p in obj.GetAllPoints()]
    vmin = Vector(min(p.x for p in points), min(p.y for p in points), min(p.z for p in points))
    vmax = Vector(max(p.x for p in points), max(p.y for p in points), max(p.z for p in points))
    return vmin, vmax


def polygon_center_and_normal(obj, poly):
    a, b, c, d = (obj.GetPoint(i) for i in (poly.a, poly.b, poly.c, poly.d))
    center = (a + b + c + d) * 0.25 if poly.c != poly.d else (a + b + c) / 3.
    normal = (b - a).Cross(d - a) if poly.c != poly.d else (b - a).Cross(c - a)
    return center, normal.GetNormalized()


class SceneTestCase(unittest.TestCase):
    """Base class providing a fresh document holding an L-Object."""

    def setUp(self):
        self.doc = c4d.documents.BaseDocument()
        self.op = c4d.BaseObject(PLUGIN_ID)
        self.assertIsNotNone(self.op, 'L-Object plugin is not registered')
        self.doc.InsertObject(self.op)

    def build(self):
        self.assertTrue(self.doc.ExecutePasses(None, True, True, True, c4d.BUILDFLAGS_NONE))
        cache = self.op.GetCache()
        # Exceptions raised in GetVirtualObjects are only printed by Cinema 4D: no cache
        self.assertIsNotNone(cache, 'no cache (exception in GetVirtualObjects?)')
        return cache

    def values(self):
        return dict((param_id, self.op[param_id]) for param_id in SHAPE_PARAMS)

    def set_raw(self, param_id, value):
        """Writes a value without any message, like an animation track would."""
        self.op.GetDataInstance().SetFloat(param_id, value)
        self.op.SetDirty(c4d.DIRTYFLAGS_DATA)

    def post_set_parameter(self, param_id, value):
        """Simulates a user edit in the Attribute Manager."""
        self.set_raw(param_id, value)
        self.op.Message(c4d.MSG_DESCRIPTION_POSTSETPARAMETER, {'descid': c4d.DescID(c4d.DescLevel(param_id))})

    def node_data(self):
        data = self.op.GetNodeData()
        self.assertIsNotNone(data)
        return data


# ---------------------------------------------------------------------------
# Module
# ---------------------------------------------------------------------------

class ModuleTest(unittest.TestCase):

    def test_ids_match_description_header(self):
        param_ids = dict((k, v) for k, v in DESCRIPTION_IDS.items() if not k.startswith('SEPARATOR_'))
        self.assertEqual(len(param_ids), 17)
        for name, value in param_ids.items():
            self.assertEqual(getattr(lobject, name), value, name)

    def test_ids_are_compatible_with_v2_scenes(self):
        # Parameter IDs must never change, or scenes saved with older versions lose their values
        v2_ids = {'FRONT_HEIGHT': 1000, 'WALL_HEIGHT': 1001, 'WIDTH': 1002, 'FLOOR_DEPTH': 1003,
                  'TOP_DEPTH': 1004, 'FRONT_RADIUS': 1005, 'BACK_RADIUS': 1006, 'TOP_RADIUS': 1007,
                  'WIDTH_SEGMENTS': 1008}
        for name, value in v2_ids.items():
            self.assertEqual(DESCRIPTION_IDS[name], value, name)

    def test_ids_match_registered_description_symbols(self):
        for name, value in DESCRIPTION_IDS.items():
            self.assertEqual(getattr(c4d, name), value, name)

    def test_every_shape_param_has_a_handle(self):
        self.assertEqual(sorted(lobject.HANDLE_PARAMS), sorted(SHAPE_PARAMS))


# ---------------------------------------------------------------------------
# Constraint logic (pure python)
# ---------------------------------------------------------------------------

class ConstrainTest(unittest.TestCase):

    def defaults(self, **overrides):
        v = dict(lobject.SHAPE_DEFAULTS)
        for name, value in overrides.items():
            v[getattr(lobject, name)] = value
        return v

    def test_defaults_are_valid(self):
        v = self.defaults()
        assert_invariants(self, v)
        self.assertEqual(lobject.Helper.constrain(v, None), v)

    def test_valid_values_are_untouched_whatever_the_edited_param(self):
        v = self.defaults()
        for param_id in SHAPE_PARAMS + [None]:
            self.assertEqual(lobject.Helper.constrain(v, param_id), v)

    def test_height_0_reduces_curve_offset_0(self):
        v = lobject.Helper.constrain(self.defaults(FRONT_HEIGHT=50.), FRONT_HEIGHT)
        self.assertEqual(v[FRONT_HEIGHT], 50.)
        self.assertEqual(v[FRONT_RADIUS], 50.)

    def test_curve_offset_0_grows_height_0_and_depth_0(self):
        v = lobject.Helper.constrain(self.defaults(FRONT_RADIUS=1400.), FRONT_RADIUS)
        self.assertEqual(v[FRONT_RADIUS], 1400.)
        self.assertEqual(v[FRONT_HEIGHT], 1400.)
        self.assertEqual(v[FLOOR_DEPTH], 1400. + 250.)

    def test_depth_0_reduces_curve_offsets(self):
        v = lobject.Helper.constrain(self.defaults(FLOOR_DEPTH=200.), FLOOR_DEPTH)
        self.assertEqual(v[FLOOR_DEPTH], 200.)
        self.assertEqual(v[FRONT_RADIUS], 100.)
        self.assertEqual(v[BACK_RADIUS], 100.)

    def test_depth_0_smaller_than_curve_offset_0_never_gives_negative_values(self):
        # Regression: the V2.0 logic produced BACK_RADIUS = -20 here
        v = lobject.Helper.constrain(self.defaults(FLOOR_DEPTH=30.), FLOOR_DEPTH)
        self.assertEqual(v[FLOOR_DEPTH], 30.)
        self.assertEqual(v[FRONT_RADIUS], 30.)
        self.assertEqual(v[BACK_RADIUS], 0.)
        assert_invariants(self, v)

    def test_depth_0_does_not_over_shrink_curve_offsets(self):
        # Regression: the V2.0 logic reduced both curve offsets using a stale value
        v = lobject.Helper.constrain(self.defaults(FLOOR_DEPTH=300., BACK_RADIUS=250.), FLOOR_DEPTH)
        self.assertEqual(v[FRONT_RADIUS] + v[BACK_RADIUS], 300.)

    def test_curve_offset_1_grows_depth_0_and_height_1(self):
        v = lobject.Helper.constrain(self.defaults(BACK_RADIUS=1500.), BACK_RADIUS)
        self.assertEqual(v[BACK_RADIUS], 1500.)
        self.assertEqual(v[FLOOR_DEPTH], 1600.)
        self.assertEqual(v[WALL_HEIGHT], 1750.)

    def test_curve_offset_2_grows_height_1_and_depth_1(self):
        v = lobject.Helper.constrain(self.defaults(TOP_RADIUS=1100.), TOP_RADIUS)
        self.assertEqual(v[TOP_RADIUS], 1100.)
        self.assertEqual(v[WALL_HEIGHT], 1350.)
        self.assertEqual(v[TOP_DEPTH], 1100.)

    def test_height_1_reduces_curve_offsets(self):
        v = lobject.Helper.constrain(self.defaults(WALL_HEIGHT=100.), WALL_HEIGHT)
        self.assertEqual(v[WALL_HEIGHT], 100.)
        self.assertEqual(v[BACK_RADIUS] + v[TOP_RADIUS], 100.)
        assert_invariants(self, v)

    def test_depth_1_reduces_curve_offset_2(self):
        v = lobject.Helper.constrain(self.defaults(TOP_DEPTH=10.), TOP_DEPTH)
        self.assertEqual(v[TOP_DEPTH], 10.)
        self.assertEqual(v[TOP_RADIUS], 10.)

    def test_width_is_independent(self):
        v = lobject.Helper.constrain(self.defaults(WIDTH=0.), WIDTH)
        self.assertEqual(v, self.defaults(WIDTH=0.))

    def test_negative_values_are_clamped(self):
        v = lobject.Helper.constrain(dict((p, -10.) for p in SHAPE_PARAMS), None)
        self.assertTrue(all(value == 0. for value in v.values()))

    def test_input_is_not_mutated(self):
        v = self.defaults(FLOOR_DEPTH=10.)
        copy = dict(v)
        lobject.Helper.constrain(v, FLOOR_DEPTH)
        self.assertEqual(v, copy)

    def test_fuzz_invariants_and_edited_value_priority(self):
        rng = random.Random(1027130)
        for _ in range(5000):
            v = dict((p, rng.choice([0., rng.uniform(-100., 3000.)])) for p in SHAPE_PARAMS)
            changed = rng.choice(SHAPE_PARAMS + [None])
            result = lobject.Helper.constrain(v, changed)
            assert_invariants(self, result)
            if changed is not None:
                self.assertAlmostEqual(result[changed], max(0., v[changed]))
            # Constraining a valid state is a no-op
            self.assertEqual(lobject.Helper.constrain(result, changed), result)


# ---------------------------------------------------------------------------
# Plugin object in a scene
# ---------------------------------------------------------------------------

class DescriptionTest(SceneTestCase):

    # Attribute Manager order and labels
    EXPECTED = [
        ('SEPARATOR_PRESETS', 'Presets'),
        ('WIDTH', 'Width'),
        ('THICKNESS', 'Thickness'),
        ('LEFT_SIDE', 'Left Side'),
        ('RIGHT_SIDE', 'Right Side'),
        ('SEPARATOR_FLOOR', 'Floor'),
        ('FLOOR_DEPTH', 'Floor Depth'),
        ('FRONT_HEIGHT', 'Front Height'),
        ('FRONT_RADIUS', 'Front Curve Radius'),
        ('SEPARATOR_WALL', 'Back Wall'),
        ('WALL_HEIGHT', 'Wall Height'),
        ('BACK_RADIUS', 'Back Curve Radius'),
        ('SEPARATOR_TOP', 'Top'),
        ('TOP_DEPTH', 'Top Depth'),
        ('TOP_RADIUS', 'Top Curve Radius'),
        ('SEPARATOR_SUBDIVISION', 'Subdivision'),
        ('WIDTH_SEGMENTS', 'Width Segments'),
        ('CURVE_SEGMENTS', 'Curve Segments'),
    ]

    PRESET_BUTTONS = [('PRESET_L', 'L'), ('PRESET_C', 'C'), ('PRESET_CYCLO', 'Cyclo'), ('PRESET_TABLE', 'Table')]

    def object_properties(self):
        """Returns [(id, label)] of the Object tab, in display order."""
        entries = []
        for bc, descid, groupid in self.op.GetDescription(c4d.DESCFLAGS_DESC_NONE):
            if groupid.GetDepth() and groupid[0].id == c4d.ID_OBJECTPROPERTIES:
                entries.append((descid[0].id, bc[c4d.DESC_NAME]))
        return entries

    def test_labels_and_order(self):
        expected = [(DESCRIPTION_IDS[name], label) for name, label in self.EXPECTED]
        own = [entry for entry in self.object_properties() if entry[0] in DESCRIPTION_IDS.values()]
        self.assertEqual(own, expected)

    def test_single_group_so_that_fields_are_aligned(self):
        # Each Attribute Manager group has its own label column: sub-groups would misalign the fields.
        # Only the preset buttons (no label) are in a sub-group, to be on a single row
        buttons = [DESCRIPTION_IDS[name] for name, _ in self.PRESET_BUTTONS]
        for bc, descid, groupid in self.op.GetDescription(c4d.DESCFLAGS_DESC_NONE):
            if descid[0].id in DESCRIPTION_IDS.values() and descid[0].id not in buttons:
                self.assertNotEqual(descid[0].dtype, c4d.DTYPE_GROUP, descid[0].id)
                self.assertEqual(groupid[0].id, c4d.ID_OBJECTPROPERTIES, descid[0].id)

    def test_attribute_manager_header(self):
        # Displayed as "Stage Object [L-Object]", like "Sphere Object [Sphere]"
        description = self.op.GetDescription(c4d.DESCFLAGS_DESC_NONE)  # Must outlive the container
        root = description.GetParameterI(c4d.DESCID_ROOT, None)
        self.assertEqual(root[c4d.DESC_NAME], 'Stage Object')
        self.assertEqual(self.op.GetName(), 'L-Object')

    def test_preset_buttons(self):
        entries = {}
        for bc, descid, groupid in self.op.GetDescription(c4d.DESCFLAGS_DESC_NONE):
            entries[descid[0].id] = (descid[0].dtype, bc[c4d.DESC_NAME])
        for name, label in self.PRESET_BUTTONS:
            self.assertEqual(entries.get(DESCRIPTION_IDS[name]), (c4d.DTYPE_BUTTON, label), name)


class InitTest(SceneTestCase):

    def test_default_values(self):
        for param_id, value in lobject.SHAPE_DEFAULTS.items():
            self.assertEqual(self.op[param_id], value)
        self.assertEqual(self.op[WIDTH_SEGMENTS], lobject.WIDTH_SEGMENTS_DEFAULT)
        self.assertEqual(self.op[lobject.CURVE_SEGMENTS], lobject.CURVE_SEGMENTS_DEFAULT)
        self.assertEqual(self.op[lobject.THICKNESS], lobject.THICKNESS_DEFAULT)
        self.assertFalse(self.op[lobject.LEFT_SIDE])
        self.assertFalse(self.op[lobject.RIGHT_SIDE])

    def test_clone_keeps_values(self):
        self.op[WALL_HEIGHT] = 777.
        clone = self.op.GetClone()
        self.assertEqual(clone[WALL_HEIGHT], 777.)


class GenerationTest(SceneTestCase):

    def assert_bbox(self, cache):
        v = lobject.Helper.constrain(self.values(), None)
        vmin, vmax = bounding_box(cache)
        # The top overhang (TOP_DEPTH) may go further than the floor
        expected_min = Vector(-v[WIDTH] * 0.5, -v[FRONT_HEIGHT], min(-v[FLOOR_DEPTH] * 0.5, v[FLOOR_DEPTH] * 0.5 - v[TOP_DEPTH]))
        expected_max = Vector(v[WIDTH] * 0.5, v[WALL_HEIGHT], v[FLOOR_DEPTH] * 0.5)
        for axis in ('x', 'y', 'z'):
            self.assertAlmostEqual(getattr(vmin, axis), getattr(expected_min, axis), delta=EPSILON)
            self.assertAlmostEqual(getattr(vmax, axis), getattr(expected_max, axis), delta=EPSILON)

    def test_generates_polygon_object(self):
        cache = self.build()
        self.assertIsNotNone(cache)
        self.assertTrue(cache.IsInstanceOf(c4d.Opolygon))
        self.assertGreater(cache.GetPolygonCount(), 0)

    def test_bounding_box_matches_parameters(self):
        self.assert_bbox(self.build())

    def test_bounding_box_after_edit(self):
        self.build()
        for param_id, value in ((WIDTH, 400.), (FRONT_HEIGHT, 120.), (WALL_HEIGHT, 900.), (FLOOR_DEPTH, 2000.)):
            self.op[param_id] = value
        self.assert_bbox(self.build())

    def test_top_overhang_depth(self):
        cache = self.build()
        top = [p for p in cache.GetAllPoints() if abs(p.y - self.op[WALL_HEIGHT]) < EPSILON]
        self.assertTrue(top)
        self.assertAlmostEqual(min(p.z for p in top), self.op[FLOOR_DEPTH] * 0.5 - self.op[TOP_DEPTH], delta=EPSILON)

    def test_width_segments(self):
        self.op[WIDTH_SEGMENTS] = 1
        count_1 = self.build().GetPolygonCount()
        self.op[WIDTH_SEGMENTS] = 4
        count_4 = self.build().GetPolygonCount()
        self.assertEqual(count_4, count_1 * 4)

    def test_zero_width_segments_does_not_break(self):
        self.op[WIDTH_SEGMENTS] = 0
        cache = self.build()
        self.assertIsNotNone(cache)
        self.assertGreater(cache.GetPolygonCount(), 0)

    def test_normals_face_the_inside_of_the_stage(self):
        cache = self.build()
        half_floor_depth = self.op[FLOOR_DEPTH] * 0.5
        checked = set()
        for poly in cache.GetAllPolygons():
            center, normal = polygon_center_and_normal(cache, poly)
            if abs(center.y) < EPSILON and abs(center.z) < half_floor_depth - 300.:
                self.assertGreater(normal.y, 0.99, 'floor')
                checked.add('floor')
            elif abs(center.z - half_floor_depth) < EPSILON and 300. < center.y < 900.:
                self.assertLess(normal.z, -0.99, 'back wall')
                checked.add('back wall')
            elif abs(center.z + half_floor_depth) < EPSILON and center.y < -150.:
                self.assertLess(normal.z, -0.99, 'front drop')
                checked.add('front drop')
            elif abs(center.y - self.op[WALL_HEIGHT]) < EPSILON:
                self.assertLess(normal.y, -0.99, 'ceiling')
                checked.add('ceiling')
        self.assertEqual(checked, {'floor', 'back wall', 'front drop', 'ceiling'})

    def test_inconsistent_values_still_give_valid_geometry(self):
        # Values set from a script / animation bypass the Attribute Manager constraints
        self.set_raw(FRONT_HEIGHT, 10.)
        self.set_raw(FRONT_RADIUS, 500.)
        self.set_raw(FLOOR_DEPTH, 100.)
        self.set_raw(TOP_RADIUS, 5000.)
        cache = self.build()
        self.assertIsNotNone(cache)
        self.assert_bbox(cache)

    def test_overhang_deeper_than_floor(self):
        self.set_raw(TOP_DEPTH, 2000.)
        self.assert_bbox(self.build())

    def test_negative_values_from_script_are_clamped(self):
        self.set_raw(WIDTH, -100.)
        self.set_raw(WALL_HEIGHT, -100.)
        cache = self.build()
        self.assertIsNotNone(cache)
        vmin, vmax = bounding_box(cache)
        self.assertAlmostEqual(vmax.x - vmin.x, 0., delta=EPSILON)
        self.assertAlmostEqual(vmax.y, 0., delta=EPSILON)

    def test_all_zero_does_not_crash(self):
        for param_id in SHAPE_PARAMS:
            self.op[param_id] = 0.
        self.build()

    def test_cache_is_reused_when_nothing_changes(self):
        first = self.build()
        self.assertIsNotNone(first)
        self.assertTrue(first.IsAlive())
        second = self.build()
        self.assertEqual(first, second)

    def test_cache_is_rebuilt_after_change(self):
        self.build()
        self.op[WIDTH] = 300.
        cache = self.build()
        vmin, vmax = bounding_box(cache)
        self.assertAlmostEqual(vmax.x - vmin.x, 300., delta=EPSILON)

    def test_no_memory_growth_on_rebuild(self):
        # Regression: SetName() leaks at each call in Cinema 4D 2023
        import gc
        import tracemalloc
        self.op[THICKNESS] = 10.
        self.op[LEFT_SIDE] = True

        def rebuild(i):
            self.op[WIDTH] = 1000. + i % 20
            self.build()

        for i in range(20):
            rebuild(i)
        gc.collect()
        tracemalloc.start()
        before = tracemalloc.take_snapshot()
        for i in range(300):
            rebuild(i)
        gc.collect()
        after = tracemalloc.take_snapshot()
        tracemalloc.stop()
        growth = sum(s.size_diff for s in after.compare_to(before, 'filename') if 'L-Object' in s.traceback[0].filename)
        self.assertLess(growth, 10 * 1024)

    def test_cache_name_matches_object(self):
        self.op.SetName('Stage')
        self.assertEqual(self.build().GetName(), 'Stage')

    def test_does_not_depend_on_active_document(self):
        active = c4d.documents.GetActiveDocument()
        self.assertNotEqual(active, self.doc)
        active_objects = len(active.GetObjects())
        self.assertIsNotNone(self.build())
        self.assertEqual(len(active.GetObjects()), active_objects)

    def test_generation_does_not_modify_the_generator(self):
        self.assertEqual(self.op.GetTags(), [])
        self.build()
        self.assertEqual(self.op.GetTags(), [])

    def test_render(self):
        rd = self.doc.GetActiveRenderData()
        rd[c4d.RDATA_RENDERENGINE] = c4d.RDATA_RENDERENGINE_STANDARD
        rd[c4d.RDATA_XRES] = 64
        rd[c4d.RDATA_YRES] = 64
        bmp = c4d.bitmaps.BaseBitmap()
        self.assertEqual(bmp.Init(64, 64), c4d.IMAGERESULT_OK)
        result = c4d.documents.RenderDocument(self.doc, rd.GetData(), bmp, c4d.RENDERFLAGS_EXTERNAL | c4d.RENDERFLAGS_NODOCUMENTCLONE)
        self.assertEqual(result, c4d.RENDERRESULT_OK)


class TagTest(SceneTestCase):

    def test_menu_prepare_adds_phong_tag(self):
        self.op.Message(c4d.MSG_MENUPREPARE, self.doc)
        phong = self.op.GetTag(c4d.Tphong)
        self.assertIsNotNone(phong)
        self.assertTrue(phong[c4d.PHONGTAG_PHONG_ANGLELIMIT])
        self.assertFalse(phong[c4d.PHONGTAG_PHONG_USEEDGES])

    def test_menu_prepare_is_idempotent(self):
        self.op.Message(c4d.MSG_MENUPREPARE, self.doc)
        self.op.Message(c4d.MSG_MENUPREPARE, self.doc)
        self.assertEqual(len([t for t in self.op.GetTags() if t.CheckType(c4d.Tphong)]), 1)

    def test_cache_uses_generator_phong_tag(self):
        self.op.Message(c4d.MSG_MENUPREPARE, self.doc)
        self.op.GetTag(c4d.Tphong)[c4d.PHONGTAG_PHONG_ANGLE] = 0.5
        cache = self.build()
        phongs = [t for t in cache.GetTags() if t.CheckType(c4d.Tphong)]
        self.assertEqual(len(phongs), 1)
        self.assertAlmostEqual(phongs[0][c4d.PHONGTAG_PHONG_ANGLE], 0.5)

    def test_cache_without_generator_phong_tag_has_none(self):
        cache = self.build()
        self.assertFalse([t for t in cache.GetTags() if t.CheckType(c4d.Tphong)])

    def selection_names(self):
        return [t.GetName() for t in self.build().GetTags() if t.CheckType(c4d.Tpolygonselection)]

    def test_selection_tags_of_existing_parts_only(self):
        parts = [lobject.PART_FRONT, lobject.PART_FLOOR, lobject.PART_WALL, lobject.PART_TOP]
        self.assertEqual(self.selection_names(), parts)
        self.op[lobject.LEFT_SIDE] = True
        self.assertEqual(self.selection_names(), parts + [lobject.PART_SIDES])
        self.op[lobject.THICKNESS] = 10.
        self.assertEqual(self.selection_names(), lobject.PARTS)
        self.assertFalse([t for t in self.op.GetCache().GetTags() if t.CheckType(c4d.Tedgeselection)])

    def test_l_preset_has_no_front_and_top_selections(self):
        self.op.Message(c4d.MSG_DESCRIPTION_COMMAND, {'id': c4d.DescID(c4d.DescLevel(lobject.PRESET_L))})
        self.assertEqual(self.selection_names(), [lobject.PART_FLOOR, lobject.PART_WALL])

    def test_no_empty_selection_tag(self):
        for preset, t, (left, right) in CONFIGS:
            obj = build_mesh(preset_values(preset), 1, 4, t, left, right)[1]
            for tag in obj.GetTags():
                if tag.CheckType(c4d.Tpolygonselection):
                    self.assertGreater(tag.GetBaseSelect().GetCount(), 0, (preset, t, left, right, tag.GetName()))

    def test_cache_has_uvw_tag(self):
        cache = self.build()
        uvw = cache.GetTag(c4d.Tuvw)
        self.assertIsNotNone(uvw)
        self.assertEqual(uvw.GetDataCount(), cache.GetPolygonCount())


class MessageTest(SceneTestCase):

    def test_post_set_parameter_applies_constraints(self):
        self.post_set_parameter(FLOOR_DEPTH, 30.)
        v = self.values()
        self.assertEqual(v[FLOOR_DEPTH], 30.)
        assert_invariants(self, v)

    def test_python_assignment_applies_constraints_once(self):
        # op[id] = value sends MSG_DESCRIPTION_POSTSETPARAMETER. Regression: the constraints
        # re-entered themselves with stale values and FLOOR_DEPTH ended at 280 instead of 30
        self.op[FLOOR_DEPTH] = 30.
        v = self.values()
        self.assertEqual((v[FLOOR_DEPTH], v[FRONT_RADIUS], v[BACK_RADIUS]), (30., 30., 0.))

    def test_post_set_parameter_on_each_param(self):
        rng = random.Random(42)
        for _ in range(200):
            self.post_set_parameter(rng.choice(SHAPE_PARAMS), rng.uniform(0., 3000.))
            assert_invariants(self, self.values())

    def test_post_set_parameter_on_other_params_is_ignored(self):
        before = self.values()
        self.op[c4d.ID_BASEOBJECT_REL_POSITION] = Vector(10)
        self.op.Message(c4d.MSG_DESCRIPTION_POSTSETPARAMETER,
                        {'descid': c4d.DescID(c4d.DescLevel(c4d.ID_BASEOBJECT_REL_POSITION))})
        self.post_set_parameter(WIDTH_SEGMENTS, 3)
        self.assertEqual(self.values(), before)


class HandleTest(SceneTestCase):

    def get_handle(self, index):
        info = HandleInfo()
        self.node_data().GetHandle(self.op, index, info)
        return info

    def drag(self, index, distance):
        """A whole drag (from the current state) of `distance` along the handle direction."""
        info = self.get_handle(index)
        self.node_data()._move_handle(self.op, self.op.GetClone(), index, info.position + info.direction * distance)

    def test_handle_count(self):
        self.assertEqual(self.node_data().GetHandleCount(self.op), 8)

    def test_handles_are_on_the_shape(self):
        vmin, vmax = bounding_box(self.build())
        for i in range(8):
            p = self.get_handle(i).position
            for axis in ('x', 'y', 'z'):
                self.assertGreaterEqual(getattr(p, axis), getattr(vmin, axis) - EPSILON)
                self.assertLessEqual(getattr(p, axis), getattr(vmax, axis) + EPSILON)

    def test_each_handle_drives_its_parameter_and_follows_the_mouse(self):
        for index, param_id in enumerate(lobject.HANDLE_PARAMS):
            self.setUp()
            before = self.get_handle(index).position
            value_before = self.op[param_id]
            self.drag(index, 100.)
            scale = lobject.HANDLE_SCALE.get(param_id, 1.)
            self.assertAlmostEqual(self.op[param_id], value_before + 100. * scale, msg='handle %d' % index)
            after = self.get_handle(index)
            self.assertAlmostEqual((after.position - before).GetLength(), 100., msg='handle %d' % index)
            assert_invariants(self, self.values())

    def test_handles_cannot_go_negative(self):
        for index, param_id in enumerate(lobject.HANDLE_PARAMS):
            self.setUp()
            self.drag(index, -100000.)
            self.assertEqual(self.op[param_id], 0., 'handle %d' % index)
            assert_invariants(self, self.values())

    def test_handles_apply_constraints(self):
        rng = random.Random(7)
        for _ in range(300):
            self.drag(rng.randrange(8), rng.uniform(-2000., 2000.))
            assert_invariants(self, self.values())
        self.assertIsNotNone(self.build())

    def test_invalid_handle_index_is_ignored(self):
        before = self.values()
        bd = c4d.documents.GetActiveDocument().GetActiveBaseDraw()
        for index in (8, -1):
            self.assertFalse(self.node_data().MoveHandle(self.op, self.op.GetClone(), Vector(10, 10, 0), index, 0, bd))
        self.assertEqual(self.values(), before)

    def test_handle_label_names_are_cached(self):
        data = self.node_data()
        data._handle_label(self.op, 0)
        self.assertEqual(sorted(type(data)._param_names), sorted(lobject.HANDLE_PARAMS))


class RadiusOverflowTest(SceneTestCase):
    """Radius handles dragged beyond the radius maximum: damped (see RADIUS_OVERFLOW_DAMPING)."""

    TOP_RADIUS_HANDLE = 7  # Direction -Z

    def move(self, handle_index, distance, undo=None):
        """Drags a handle by `distance` (along its direction) from the drag start state `undo`."""
        undo = undo or self.op.GetClone()
        info = HandleInfo()
        self.node_data().GetHandle(undo, handle_index, info)
        self.node_data()._move_handle(self.op, undo, handle_index, info.position + info.direction * distance)
        return undo

    def test_max_radius(self):
        v = dict(lobject.SHAPE_DEFAULTS)
        self.assertEqual(lobject.Helper.max_radius(v, FRONT_RADIUS), 300.)   # Front height
        self.assertEqual(lobject.Helper.max_radius(v, BACK_RADIUS), 950.)    # Wall height - top radius
        self.assertEqual(lobject.Helper.max_radius(v, TOP_RADIUS), 950.)     # Wall height - back radius
        self.assertIsNone(lobject.Helper.max_radius(v, WIDTH))

    def test_damping_only_beyond_maximum(self):
        v = dict(lobject.SHAPE_DEFAULTS)
        damp = lobject.Helper.damp_radius_overflow
        k = lobject.RADIUS_OVERFLOW_DAMPING
        self.assertEqual(damp(v, TOP_RADIUS, 600.), 600.)
        self.assertEqual(damp(v, TOP_RADIUS, 950.), 950.)
        self.assertEqual(damp(v, TOP_RADIUS, 1350.), 950. + 400. * k)
        self.assertEqual(damp(v, WALL_HEIGHT, 5000.), 5000.)
        self.assertEqual(damp(v, FLOOR_DEPTH, 5000.), 5000.)

    def test_follows_the_mouse_below_maximum(self):
        self.move(self.TOP_RADIUS_HANDLE, 500.)
        self.assertEqual(self.op[TOP_RADIUS], 750.)
        self.assertEqual(self.op[WALL_HEIGHT], 1200.)

    def test_wall_rises_slowly_beyond_maximum(self):
        self.move(self.TOP_RADIUS_HANDLE, 1100.)  # 250 + 1100 = 1350, i.e. 400 beyond 950
        radius = 950. + 400. * lobject.RADIUS_OVERFLOW_DAMPING
        self.assertEqual(self.op[TOP_RADIUS], radius)
        self.assertEqual(self.op[WALL_HEIGHT], 250. + radius)
        self.assertEqual(self.op[TOP_DEPTH], max(1000., radius))
        assert_invariants(self, self.values())

    def test_no_drift_when_the_mouse_stays(self):
        undo = self.move(self.TOP_RADIUS_HANDLE, 1100.)
        first = self.values()
        for _ in range(20):
            self.move(self.TOP_RADIUS_HANDLE, 1100., undo)
        self.assertEqual(self.values(), first)

    def test_dragging_back_restores_pushed_parameters(self):
        undo = self.move(self.TOP_RADIUS_HANDLE, 1100.)
        self.assertGreater(self.op[WALL_HEIGHT], 1200.)
        self.move(self.TOP_RADIUS_HANDLE, 0., undo)
        self.assertEqual(self.values(), dict(lobject.SHAPE_DEFAULTS))

    def test_progressive_drag(self):
        # Successive mouse moves of the same drag: monotonic, never faster than the mouse
        undo = self.op.GetClone()
        previous = self.op[TOP_RADIUS]
        for step in range(1, 41):
            self.move(self.TOP_RADIUS_HANDLE, step * 50., undo)
            radius = self.op[TOP_RADIUS]
            self.assertGreaterEqual(radius, previous)
            self.assertLessEqual(radius - previous, 50. + EPSILON)
            if radius > 950.:
                self.assertLessEqual(radius - previous, 50. * lobject.RADIUS_OVERFLOW_DAMPING + EPSILON)
            previous = radius
            assert_invariants(self, self.values())

    def test_each_radius_handle_is_damped(self):
        for index, param_id in ((5, FRONT_RADIUS), (6, BACK_RADIUS), (7, TOP_RADIUS)):
            self.setUp()
            maximum = lobject.Helper.max_radius(self.values(), param_id)
            self.move(index, maximum - self.op[param_id] + 400.)
            self.assertAlmostEqual(self.op[param_id], maximum + 400. * lobject.RADIUS_OVERFLOW_DAMPING,
                                   msg='handle %d' % index)
            assert_invariants(self, self.values())

    def test_other_handles_are_not_damped(self):
        for index, param_id in enumerate(lobject.HANDLE_PARAMS):
            if param_id in (FRONT_RADIUS, BACK_RADIUS, TOP_RADIUS):
                continue
            self.setUp()
            value = self.op[param_id]
            self.move(index, 3000.)
            self.assertEqual(self.op[param_id], value + 3000. * lobject.HANDLE_SCALE.get(param_id, 1.))

    def test_move_handle_with_real_viewport(self):
        # Smoke test: c4dpy views have no size, the resulting position is meaningless
        bd = c4d.documents.GetActiveDocument().GetActiveBaseDraw()
        data = self.node_data()
        self.assertTrue(data.MoveHandle(self.op, self.op.GetClone(), Vector(10, 10, 0), 7, 0, bd))
        self.assertFalse(data.MoveHandle(self.op, self.op.GetClone(), Vector(10, 10, 0), 8, 0, bd))
        assert_invariants(self, self.values())


# ---------------------------------------------------------------------------
# Mesh
# ---------------------------------------------------------------------------

THICKNESS, CURVE_SEGMENTS = lobject.THICKNESS, lobject.CURVE_SEGMENTS
LEFT_SIDE, RIGHT_SIDE = lobject.LEFT_SIDE, lobject.RIGHT_SIDE
Geometry = lobject.Geometry


def triangles(obj):
    points = obj.GetAllPoints()
    for poly in obj.GetAllPolygons():
        a, b, c, d = (points[i] for i in (poly.a, poly.b, poly.c, poly.d))
        yield a, b, c
        if poly.c != poly.d:
            yield a, c, d


def signed_volume(obj):
    """Divergence theorem: the volume if the mesh is closed with outward normals."""
    return sum(a.Dot(b.Cross(c)) for a, b, c in triangles(obj)) / 6.


def polygon_area(obj, index):
    points = obj.GetAllPoints()
    poly = obj.GetPolygon(index)
    a, b, c, d = (points[i] for i in (poly.a, poly.b, poly.c, poly.d))
    area = (b - a).Cross(c - a).GetLength() * 0.5
    if poly.c != poly.d:
        area += (c - a).Cross(d - a).GetLength() * 0.5
    return area


def polygon_normal(obj, index):
    points = obj.GetAllPoints()
    poly = obj.GetPolygon(index)
    a, b, c, d = (points[i] for i in (poly.a, poly.b, poly.c, poly.d))
    normal = (b - a).Cross(c - a)
    if poly.c != poly.d:
        normal += (c - a).Cross(d - a)
    return normal.GetNormalized()


def selection(obj, name):
    """Polygon indices of a selection tag, None if there is no such tag."""
    for tag in obj.GetTags():
        if tag.CheckType(c4d.Tpolygonselection) and tag.GetName() == name:
            bs = tag.GetBaseSelect()
            return [i for i in range(obj.GetPolygonCount()) if bs.IsSelected(i)]
    return None


def segments_intersect(a, b, c, d):
    """Proper intersection of segments ab and cd (touching end points do not count)."""
    def cross(o, p, q):
        return (p[0] - o[0]) * (q[1] - o[1]) - (p[1] - o[1]) * (q[0] - o[0])
    d1, d2, d3, d4 = cross(c, d, a), cross(c, d, b), cross(a, b, c), cross(a, b, d)
    return d1 * d2 < -1e-9 and d3 * d4 < -1e-9


def is_simple_polygon(polygon):
    count = len(polygon)
    for i in range(count):
        for j in range(i + 2, count):
            if i == 0 and j == count - 1:
                continue  # Adjacent (closing edge)
            if segments_intersect(polygon[i], polygon[(i + 1) % count], polygon[j], polygon[(j + 1) % count]):
                return False
    return True


def preset_values(preset_id):
    v = dict(lobject.SHAPE_DEFAULTS)
    v.update(lobject.PRESETS[preset_id])
    return v


# Configurations covering the front corner cases (thickness vs front radius / height)
CONFIGS = []
for _preset in sorted(lobject.PRESETS):
    for _t in (0., 50., 120., 350., 600.):
        for _sides in ((False, False), (True, False), (False, True), (True, True)):
            CONFIGS.append((_preset, _t, _sides))


def build_mesh(values, width_segments=1, curve_segments=12, thickness=0., left=False, right=False):
    mesh = Geometry.build(values, width_segments, curve_segments, thickness, left, right)
    return mesh, mesh.to_polygon_object()


class TriangulateTest(unittest.TestCase):

    def area(self, polygon, tris):
        return sum(abs(Geometry.signed_area([polygon[i] for i in tri])) for tri in tris)

    def test_square(self):
        square = [(0, 0), (1, 0), (1, 1), (0, 1)]
        tris = Geometry.triangulate(square)
        self.assertEqual(len(tris), 2)
        self.assertAlmostEqual(self.area(square, tris), 1.)

    def test_concave_both_orientations(self):
        shape = [(0, 0), (4, 0), (4, 1), (1, 1), (1, 4), (0, 4)]  # L shape, area 7
        for polygon in (shape, shape[::-1]):
            tris = Geometry.triangulate(polygon)
            self.assertEqual(len(tris), 4)
            self.assertAlmostEqual(self.area(polygon, tris), 7.)

    def test_collinear_points(self):
        polygon = [(0, 0), (1, 0), (2, 0), (2, 2), (0, 2), (0, 1)]
        self.assertAlmostEqual(self.area(polygon, Geometry.triangulate(polygon)), 4.)

    def test_degenerate(self):
        self.assertEqual(Geometry.triangulate([(0, 0), (1, 1)]), [])
        self.assertEqual(Geometry.triangulate([(0, 0), (1, 1), (2, 2)]), [])

    def test_arc_polygons(self):
        for preset in lobject.PRESETS:
            side = Geometry.profiles(preset_values(preset), 16, 0.)[3]
            self.assertAlmostEqual(self.area(side, Geometry.triangulate(side)),
                                   abs(Geometry.signed_area(side)), delta=1e-3)


class ProfileTest(unittest.TestCase):

    def test_true_circular_arcs(self):
        v = dict(lobject.SHAPE_DEFAULTS)
        n = 12
        inner = Geometry.profiles(v, n, 0.)[0]
        half_floor = v[FLOOR_DEPTH] * 0.5
        arcs = [
            ((-half_floor + v[FRONT_RADIUS], -v[FRONT_RADIUS]), v[FRONT_RADIUS]),
            ((half_floor - v[BACK_RADIUS], v[BACK_RADIUS]), v[BACK_RADIUS]),
            ((half_floor - v[TOP_RADIUS], v[WALL_HEIGHT] - v[TOP_RADIUS]), v[TOP_RADIUS]),
        ]
        for center, radius in arcs:
            on_arc = [p for p in inner if abs(math.hypot(p[0] - center[0], p[1] - center[1]) - radius) < 1e-6]
            self.assertEqual(len(on_arc), n + 1, center)

    def test_profile_ends(self):
        v = dict(lobject.SHAPE_DEFAULTS)
        inner = Geometry.profiles(v, 12, 0.)[0]
        half_floor = v[FLOOR_DEPTH] * 0.5
        self.assertEqual(inner[0], (-half_floor, -v[FRONT_HEIGHT]))
        self.assertEqual(inner[-1], (half_floor - v[TOP_DEPTH], v[WALL_HEIGHT]))

    def test_no_duplicated_points(self):
        for preset, t, _ in CONFIGS:
            inner, _, outer, side, _, _ = Geometry.profiles(preset_values(preset), 12, t)
            for points in (inner, outer or [], side):
                for a, b in zip(points, points[1:]):
                    self.assertGreater(math.hypot(b[0] - a[0], b[1] - a[1]), 1e-6, (preset, t))

    def test_thickness_band_and_side_are_simple_polygons(self):
        for preset, t, _ in CONFIGS:
            inner, _, outer, side, _, _ = Geometry.profiles(preset_values(preset), 12, t)
            self.assertTrue(is_simple_polygon(side), (preset, t))
            if outer:
                self.assertTrue(is_simple_polygon(inner + outer[::-1]), (preset, t))

    def test_parts(self):
        v = dict(lobject.SHAPE_DEFAULTS)
        inner, parts, _, _, _, _ = Geometry.profiles(v, 12, 0.)
        self.assertEqual(len(parts), len(inner) - 1)
        # Each part is a continuous range, in profile order
        order = [p for i, p in enumerate(parts) if i == 0 or parts[i - 1] != p]
        self.assertEqual(order, [lobject.PART_FRONT, lobject.PART_FLOOR, lobject.PART_WALL, lobject.PART_TOP])
        # Arcs are split in their middle
        self.assertEqual(parts.count(lobject.PART_FRONT), 1 + 6)
        self.assertEqual(parts.count(lobject.PART_TOP), 6 + 1)


class MeshTest(unittest.TestCase):

    def test_curve_segments(self):
        v = dict(lobject.SHAPE_DEFAULTS)
        for n in (1, 2, 12, 64):
            for width_segments in (1, 3):
                obj = build_mesh(v, width_segments, n)[1]
                # Front drop, floor, wall and top + 3 arcs of n segments
                self.assertEqual(obj.GetPolygonCount(), (4 + 3 * n) * width_segments)

    def test_sharp_corners_have_no_curve_polygons(self):
        obj = build_mesh(preset_values(lobject.PRESET_L), 1, 12)[1]
        self.assertEqual(obj.GetPolygonCount(), 2)  # Floor and wall

    def test_no_degenerate_polygons(self):
        for preset, t, (left, right) in CONFIGS:
            obj = build_mesh(preset_values(preset), 2, 6, t, left, right)[1]
            self.assertGreater(obj.GetPolygonCount(), 0)
            for i in range(obj.GetPolygonCount()):
                self.assertGreater(polygon_area(obj, i), 1e-6, (preset, t, left, right, i))

    def test_thickness_mesh_is_closed_with_outward_normals(self):
        for preset, t, (left, right) in CONFIGS:
            if t == 0:
                continue
            values = preset_values(preset)
            inner, _, outer, side, _, _ = Geometry.profiles(values, 12, t)
            band_area = abs(Geometry.signed_area(inner + outer[::-1]))
            side_area = abs(Geometry.signed_area(side))
            sides = int(left) + int(right)
            expected = band_area * (values[WIDTH] + t * sides) + side_area * t * sides
            obj = build_mesh(values, 2, 12, t, left, right)[1]
            self.assertAlmostEqual(signed_volume(obj) / expected, 1., places=6, msg=(preset, t, left, right))

    def test_thickness_volume_analytic(self):
        # L shape (sharp corner): floor and wall slabs, the outer corner is a quarter circle
        values = preset_values(lobject.PRESET_L)
        t, n = 50., 12
        quarter = n * 0.5 * t * t * math.sin(math.pi / 2. / n)  # Polygonal quarter circle
        band = values[FLOOR_DEPTH] * t + values[WALL_HEIGHT] * t + quarter
        obj = build_mesh(values, 1, n, t)[1]
        self.assertAlmostEqual(signed_volume(obj), band * values[WIDTH], delta=1e-3 * band)

    def test_thickness_bounding_box(self):
        v = dict(lobject.SHAPE_DEFAULTS)
        t = 40.
        obj = build_mesh(v, 1, 12, t, True, True)[1]
        vmin, vmax = bounding_box(obj)
        half_floor = v[FLOOR_DEPTH] * 0.5
        self.assertAlmostEqual(vmin.x, -v[WIDTH] * 0.5 - t)
        self.assertAlmostEqual(vmax.x, v[WIDTH] * 0.5 + t)
        self.assertAlmostEqual(vmin.y, -v[FRONT_HEIGHT])
        self.assertAlmostEqual(vmax.y, v[WALL_HEIGHT] + t)
        self.assertAlmostEqual(vmin.z, -half_floor)
        self.assertAlmostEqual(vmax.z, half_floor + t)

    def test_thickness_larger_than_front_height(self):
        v = dict(lobject.SHAPE_DEFAULTS)
        obj = build_mesh(v, 1, 12, 500.)[1]
        self.assertAlmostEqual(bounding_box(obj)[0].y, -500.)

    def test_selections_cover_each_polygon_once(self):
        for preset, t, (left, right) in CONFIGS[::3]:
            obj = build_mesh(preset_values(preset), 2, 6, t, left, right)[1]
            selected = sorted(i for part in lobject.PARTS for i in selection(obj, part) or [])
            self.assertEqual(selected, list(range(obj.GetPolygonCount())))

    def test_selection_contents(self):
        v = dict(lobject.SHAPE_DEFAULTS)
        obj = build_mesh(v, 1, 12)[1]
        self.assertIsNone(selection(obj, lobject.PART_SIDES))
        self.assertIsNone(selection(obj, lobject.PART_OUTSIDE))
        expected_normals = {
            lobject.PART_FRONT: Vector(0, 0, -1), lobject.PART_FLOOR: Vector(0, 1, 0),
            lobject.PART_WALL: Vector(0, 0, -1), lobject.PART_TOP: Vector(0, -1, 0),
        }
        for part, normal in expected_normals.items():
            polygons = selection(obj, part)
            self.assertTrue(polygons, part)
            # The flat part of each selection faces the stage
            self.assertTrue(any(polygon_normal(obj, i).Dot(normal) > 0.999 for i in polygons), part)

        obj = build_mesh(v, 1, 12, 30., True, True)[1]
        self.assertTrue(selection(obj, lobject.PART_SIDES))
        self.assertTrue(selection(obj, lobject.PART_OUTSIDE))

    def test_side_panels_without_thickness(self):
        v = dict(lobject.SHAPE_DEFAULTS)
        n = 128
        obj = build_mesh(v, 1, n, 0., True, True)[1]
        half_width = v[WIDTH] * 0.5
        sides = selection(obj, lobject.PART_SIDES)
        areas = {-1: 0., 1: 0.}
        for i in sides:
            poly = obj.GetPolygon(i)
            x = obj.GetPoint(poly.a).x
            self.assertAlmostEqual(abs(x), half_width)
            sign = 1 if x > 0 else -1
            self.assertLess(polygon_normal(obj, i).x * sign, -0.999)  # Facing the stage
            areas[sign] += polygon_area(obj, i)
        # Floor to wall height rectangle, minus the back and top rounded corners, plus the front one
        corner = 1. - math.pi / 4.
        expected = (v[FLOOR_DEPTH] * v[WALL_HEIGHT] - corner * (v[BACK_RADIUS] ** 2 + v[TOP_RADIUS] ** 2)
                    + corner * v[FRONT_RADIUS] ** 2)
        for sign in (-1, 1):
            self.assertAlmostEqual(areas[sign], expected, delta=expected * 1e-4)

    def test_side_panel_with_deep_top(self):
        # Top deeper than the floor: the side panel goes to the top front edge
        v = dict(lobject.SHAPE_DEFAULTS)
        v[TOP_DEPTH] = 2500.
        obj = build_mesh(v, 1, 12, 0., True, False)[1]
        side_points = [obj.GetPoint(j) for i in selection(obj, lobject.PART_SIDES)
                       for j in (obj.GetPolygon(i).a, obj.GetPolygon(i).b, obj.GetPolygon(i).c)]
        self.assertAlmostEqual(min(p.z for p in side_points), v[FLOOR_DEPTH] * 0.5 - 2500.)

    def test_uvs_in_unit_square(self):
        for preset, t, (left, right) in CONFIGS[::5]:
            mesh = build_mesh(preset_values(preset), 2, 6, t, left, right)[0]
            for uvs in mesh.uvs:
                for uv in uvs:
                    self.assertTrue(-1e-9 <= uv.x <= 1 + 1e-9 and -1e-9 <= uv.y <= 1 + 1e-9)

    def test_inner_surface_uvs_follow_the_profile(self):
        mesh = build_mesh(dict(lobject.SHAPE_DEFAULTS), 1, 12)[0]
        v_values = sorted(set(round(uv.y, 9) for uvs in mesh.uvs for uv in uvs))
        self.assertEqual((v_values[0], v_values[-1]), (0., 1.))

    def test_performance(self):
        import time
        start = time.perf_counter()
        obj = build_mesh(dict(lobject.SHAPE_DEFAULTS), 100, 64, 20., True, True)[1]
        elapsed = time.perf_counter() - start
        sys.stderr.write('\n  heavy mesh: %d polygons in %.0f ms ' % (obj.GetPolygonCount(), elapsed * 1000))
        self.assertLess(elapsed, 2.)


class OptionsTest(SceneTestCase):

    def test_thickness_parameter(self):
        self.op[THICKNESS] = 25.
        vmin, vmax = bounding_box(self.build())
        self.assertAlmostEqual(vmax.y, self.op[WALL_HEIGHT] + 25.)
        self.assertTrue(selection(self.op.GetCache(), lobject.PART_OUTSIDE))

    def test_side_parameters(self):
        self.op[LEFT_SIDE] = True
        cache = self.build()
        xs = [cache.GetPoint(cache.GetPolygon(i).a).x for i in selection(cache, lobject.PART_SIDES)]
        self.assertTrue(xs)
        self.assertTrue(all(x < 0 for x in xs))
        self.op[RIGHT_SIDE] = True
        cache = self.build()
        xs = [cache.GetPoint(cache.GetPolygon(i).a).x for i in selection(cache, lobject.PART_SIDES)]
        self.assertTrue(any(x > 0 for x in xs))

    def test_curve_segments_parameter(self):
        self.op[CURVE_SEGMENTS] = 4
        self.assertEqual(self.build().GetPolygonCount(), 4 + 3 * 4)
        self.op[CURVE_SEGMENTS] = 0
        self.assertEqual(self.build().GetPolygonCount(), 4 + 3 * 1)

    def test_negative_thickness_is_ignored(self):
        self.set_raw(THICKNESS, -10.)
        self.assertIsNone(selection(self.build(), lobject.PART_OUTSIDE))


class PresetTest(SceneTestCase):

    def press(self, preset_id):
        self.op.Message(c4d.MSG_DESCRIPTION_COMMAND, {'id': c4d.DescID(c4d.DescLevel(preset_id))})

    def test_presets_are_valid(self):
        for preset in lobject.PRESETS:
            v = preset_values(preset)
            self.assertEqual(lobject.Helper.constrain(v, None), v, preset)

    def test_c_preset_is_the_default_shape(self):
        self.assertEqual(preset_values(lobject.PRESET_C), dict(lobject.SHAPE_DEFAULTS))

    def test_buttons_apply_presets_and_keep_options(self):
        self.op[WIDTH] = 777.
        self.op[THICKNESS] = 12.
        self.op[LEFT_SIDE] = True
        for preset, shape in lobject.PRESETS.items():
            self.press(preset)
            for param_id, value in shape.items():
                self.assertEqual(self.op[param_id], value, (preset, param_id))
            self.assertEqual(self.op[WIDTH], 777.)
            self.assertEqual(self.op[THICKNESS], 12.)
            self.assertTrue(self.op[LEFT_SIDE])
            self.assertGreater(self.build().GetPolygonCount(), 0)

    def test_preset_undo(self):
        self.op[WALL_HEIGHT] = 555.
        self.press(lobject.PRESET_CYCLO)
        self.assertEqual(self.op[WALL_HEIGHT], 1500.)
        self.assertTrue(self.doc.DoUndo())
        self.assertEqual(self.op[WALL_HEIGHT], 555.)

    def test_other_commands_are_ignored(self):
        before = self.values()
        self.press(WIDTH)
        self.assertEqual(self.values(), before)


class FakeBaseDraw(object):
    """
    Front orthographic view (looking along +Z, 1 unit = 0.1 pixel, origin at (500, 500)),
    recording the drawing calls. Needed because c4dpy views have no size: WS() returns 0.
    """

    def __init__(self):
        self.calls = []

    def WS(self, p):
        return Vector(500. + p.x * 0.1, 500. - p.y * 0.1, p.z)

    def __getattr__(self, name):
        def record(*args):
            self.calls.append((name,) + args)
        return record

    def called(self, name):
        return [call[1:] for call in self.calls if call[0] == name]


class HandleViewportTest(SceneTestCase):

    def screen_position(self, index):
        info = HandleInfo()
        self.node_data().GetHandle(self.op, index, info)
        return FakeBaseDraw().WS(self.op.GetMg() * info.position)

    def detect(self, x, y, qualifier=0):
        return self.node_data().DetectHandle(self.op, FakeBaseDraw(), x, y, qualifier)

    # Default values, front view (pixels): 0 (500, 530), 1 & 4 (500, 380) overlapping,
    # 2 (575, 500), 3 (500, 500), 5 (575, 510), 6 (575, 475), 7 (575, 380)

    def test_detects_handle_under_mouse(self):
        for index in (0, 2, 3, 5, 6, 7):
            p = self.screen_position(index)
            self.assertEqual(self.detect(p.x, p.y), index)

    def test_overlapping_handles_front_one_wins(self):
        # Wall height (1, z = 750) and top depth (4, z = -250) handles project on the same pixel
        p = self.screen_position(1)
        self.assertEqual((p.x, p.y), (self.screen_position(4).x, self.screen_position(4).y))
        self.assertEqual(self.detect(p.x, p.y), 4)

    def test_pick_radius(self):
        p = self.screen_position(0)
        radius = lobject.HANDLE_PICK_RADIUS
        self.assertEqual(self.detect(p.x - radius + 1, p.y), 0)
        self.assertEqual(self.detect(p.x, p.y + radius - 1), 0)
        self.assertEqual(self.detect(p.x, p.y + radius + 1), c4d.NOTOK)
        self.assertEqual(self.detect(p.x - radius - 1, p.y), c4d.NOTOK)

    def test_closest_handle_wins(self):
        # Width (2) and front radius (5) handles are only 10 pixels away: both are in range,
        # the default implementation would always pick the first one
        a, b = self.screen_position(2), self.screen_position(5)
        self.assertLess(abs(a.y - b.y), lobject.HANDLE_PICK_RADIUS)
        self.assertEqual(self.detect(a.x, a.y + 2), 2)
        self.assertEqual(self.detect(b.x, b.y - 2), 5)

    def test_ctrl_disables_handles(self):
        p = self.screen_position(0)
        self.assertEqual(self.detect(p.x, p.y, c4d.QUALIFIER_CTRL), c4d.NOTOK)

    def test_moved_object(self):
        self.op.SetAbsPos(Vector(2000, 0, 0))
        p = self.screen_position(0)
        self.assertEqual(p.x, 700.)
        self.assertEqual(self.detect(p.x, p.y), 0)
        self.assertEqual(self.detect(500., 530.), c4d.NOTOK)

    def test_draw_handles(self):
        bd = FakeBaseDraw()
        self.node_data()._draw_handles(self.op, bd, self.op.GetMg(), 3)
        handles = bd.called('DrawHandle')
        self.assertEqual(len(handles), 8)
        self.assertTrue(all(h[1] == c4d.DRAWHANDLE_CUSTOM for h in handles))
        sizes = [s[0] for s in bd.called('SetPointSize')]
        self.assertEqual(sizes.count(lobject.HANDLE_SIZE_HIGHLIGHT), 1)
        self.assertEqual(sizes.index(lobject.HANDLE_SIZE_HIGHLIGHT), 3)
        # 3 lines per arrow, except the depth handles (3, 4, 7) pointing to the camera
        self.assertEqual(len(bd.called('DrawLine2D')), 3 * 5)
        for start, end in bd.called('DrawLine2D')[::3]:
            self.assertAlmostEqual((end - start).GetLength(), lobject.HANDLE_ARROW_LENGTH)
        texts = bd.called('DrawHUDText')
        self.assertEqual(len(texts), 1)
        self.assertEqual(texts[0][2], self.node_data()._handle_label(self.op, 3))

    def test_no_label_without_highlight(self):
        bd = FakeBaseDraw()
        self.node_data()._draw_handles(self.op, bd, self.op.GetMg(), c4d.NOTOK)
        self.assertEqual(bd.called('DrawHUDText'), [])
        self.assertNotIn(lobject.HANDLE_SIZE_HIGHLIGHT, [s[0] for s in bd.called('SetPointSize')])

    def test_handle_labels(self):
        data = self.node_data()
        self.assertEqual(data._handle_label(self.op, 3), 'Floor Depth: 1500 cm')
        self.assertEqual(data._handle_label(self.op, 7), 'Top Curve Radius: 250 cm')
        self.assertEqual([data._handle_label(self.op, i).split(':')[0] for i in range(8)],
                         ['Front Height', 'Wall Height', 'Width', 'Floor Depth', 'Top Depth',
                          'Front Curve Radius', 'Back Curve Radius', 'Top Curve Radius'])

    def test_draw_in_real_viewport(self):
        # Smoke test with a real (headless) BaseDraw
        doc = c4d.documents.GetActiveDocument()
        op = c4d.BaseObject(PLUGIN_ID)
        doc.InsertObject(op)
        try:
            bd = doc.GetActiveBaseDraw()
            bh = c4d.plugins.BaseDrawHelp(bd, doc)
            data = op.GetNodeData()
            self.assertEqual(data.Draw(op, c4d.DRAWPASS_HANDLES, bd, bh), c4d.DRAWRESULT_OK)
            self.assertEqual(data.Draw(op, c4d.DRAWPASS_OBJECT, bd, bh), c4d.DRAWRESULT_SKIP)
            data._draw_handles(op, bd, op.GetMg(), 2)
            self.assertIsInstance(data.DetectHandle(op, bd, 0, 0, 0), int)
        finally:
            op.Remove()


if __name__ == '__main__':
    result = unittest.main(argv=[sys.argv[0], '-v'], exit=False).result
    # c4dpy returns 1 on any SystemExit, even sys.exit(0): only exit on failure
    if not result.wasSuccessful():
        sys.exit(1)
