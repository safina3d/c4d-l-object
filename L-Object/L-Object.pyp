# -*- coding: utf-8 -*-

# Author: safina3d
# Version: 3.0
# Url: https://safina3d.blogspot.com

import os
import math
import c4d
from c4d import plugins, bitmaps, Vector, HandleInfo

PLUGIN_ID = 1027130

FRONT_HEIGHT = 1000
WALL_HEIGHT = 1001
WIDTH = 1002
FLOOR_DEPTH = 1003
TOP_DEPTH = 1004
FRONT_RADIUS = 1005
BACK_RADIUS = 1006
TOP_RADIUS = 1007
WIDTH_SEGMENTS = 1008
THICKNESS = 1009
CURVE_SEGMENTS = 1010
LEFT_SIDE = 1011
RIGHT_SIDE = 1012

PRESET_L = 1100
PRESET_C = 1101
PRESET_CYCLO = 1102
PRESET_TABLE = 1103

SHAPE_DEFAULTS = {
    FRONT_HEIGHT: 300.,
    WALL_HEIGHT: 1200.,
    WIDTH: 1500.,
    FLOOR_DEPTH: 1500.,
    TOP_DEPTH: 1000.,
    FRONT_RADIUS: 100.,
    BACK_RADIUS: 250.,
    TOP_RADIUS: 250.,
}
WIDTH_SEGMENTS_DEFAULT = 1
CURVE_SEGMENTS_DEFAULT = 12
THICKNESS_DEFAULT = 0.

# Preset shapes (WIDTH and the other options are kept)
PRESETS = {
    PRESET_L: {
        FRONT_HEIGHT: 0., FRONT_RADIUS: 0., FLOOR_DEPTH: 1500., BACK_RADIUS: 0.,
        WALL_HEIGHT: 1200., TOP_RADIUS: 0., TOP_DEPTH: 0.
    },
    PRESET_C: dict((k, v) for k, v in SHAPE_DEFAULTS.items() if k != WIDTH),
    PRESET_CYCLO: {
        FRONT_HEIGHT: 0., FRONT_RADIUS: 0., FLOOR_DEPTH: 2000., BACK_RADIUS: 600.,
        WALL_HEIGHT: 1500., TOP_RADIUS: 0., TOP_DEPTH: 0.
    },
    PRESET_TABLE: {
        FRONT_HEIGHT: 400., FRONT_RADIUS: 150., FLOOR_DEPTH: 1000., BACK_RADIUS: 400.,
        WALL_HEIGHT: 800., TOP_RADIUS: 0., TOP_DEPTH: 0.
    },
}

# Polygon selection tags
PART_FRONT = 'Front'
PART_FLOOR = 'Floor'
PART_WALL = 'Wall'
PART_TOP = 'Top'
PART_SIDES = 'Sides'
PART_OUTSIDE = 'Outside'
PARTS = [PART_FRONT, PART_FLOOR, PART_WALL, PART_TOP, PART_SIDES, PART_OUTSIDE]

# Parameter driven by each handle (index = handle index)
HANDLE_PARAMS = [
    FRONT_HEIGHT, WALL_HEIGHT, WIDTH, FLOOR_DEPTH, TOP_DEPTH,
    FRONT_RADIUS, BACK_RADIUS, TOP_RADIUS
]

# WIDTH and FLOOR_DEPTH are centered: their handle sits at half the value,
# so a handle move of d changes the parameter by 2 * d
HANDLE_SCALE = {WIDTH: 2., FLOOR_DEPTH: 2.}

# Viewport handles, in pixels
HANDLE_SIZE = 9.
HANDLE_SIZE_HIGHLIGHT = 13.
HANDLE_PICK_RADIUS = 16.
HANDLE_ARROW_LENGTH = 36.
HANDLE_ARROW_HEAD = 7.
HANDLE_COLOR_RADIUS = Vector(0.54, 0.758, 0.984)

# Beyond its maximum, a dragged radius keeps growing (pushing the other parameters),
# but slower than the mouse
RADIUS_OVERFLOW_DAMPING = 0.33

EPSILON = 1e-6

# Objects are named with obj[c4d.ID_BASELIST_NAME] = name: SetName() leaks memory at each
# call in Cinema 4D 2023, and the cache is rebuilt at each change


class Helper(object):

    @staticmethod
    def get_shape_values(node):
        """Returns {param_id: float} for all shape parameters (None/negative -> 0)."""
        return dict((param_id, max(0., float(node[param_id] or 0.))) for param_id in SHAPE_DEFAULTS)

    @staticmethod
    def constrain(values, changed_id):
        """
        Resolves conflicts after the parameter `changed_id` was edited, giving priority
        to the edited value. Returns a new dict where all values are >= 0 and:
          front_radius <= front_height
          front_radius + back_radius <= floor_depth
          back_radius + top_radius <= wall_height
          top_radius <= top_depth
        """
        v = dict((k, max(0., val)) for k, val in values.items())
        front_height, wall_height = v[FRONT_HEIGHT], v[WALL_HEIGHT]
        floor_depth, top_depth = v[FLOOR_DEPTH], v[TOP_DEPTH]
        front_radius, back_radius, top_radius = v[FRONT_RADIUS], v[BACK_RADIUS], v[TOP_RADIUS]

        if changed_id == FRONT_HEIGHT:
            front_radius = min(front_radius, front_height)

        elif changed_id == FRONT_RADIUS:
            front_height = max(front_height, front_radius)
            floor_depth = max(floor_depth, front_radius + back_radius)

        elif changed_id == FLOOR_DEPTH:
            back_radius = max(0., min(back_radius, floor_depth - front_radius))
            front_radius = min(front_radius, floor_depth - back_radius)

        elif changed_id == BACK_RADIUS:
            floor_depth = max(floor_depth, front_radius + back_radius)
            wall_height = max(wall_height, back_radius + top_radius)

        elif changed_id == TOP_RADIUS:
            wall_height = max(wall_height, back_radius + top_radius)
            top_depth = max(top_depth, top_radius)

        elif changed_id == WALL_HEIGHT:
            back_radius = max(0., min(back_radius, wall_height - top_radius))
            top_radius = min(top_radius, wall_height - back_radius)

        elif changed_id == TOP_DEPTH:
            top_radius = min(top_radius, top_depth)

        # Safety net for inconsistent input values (scripts, animation)
        front_radius = min(front_radius, front_height, floor_depth)
        back_radius = min(back_radius, floor_depth - front_radius, wall_height)
        top_radius = min(top_radius, top_depth, wall_height - back_radius)

        v.update({
            FRONT_HEIGHT: front_height, WALL_HEIGHT: wall_height,
            FLOOR_DEPTH: floor_depth, TOP_DEPTH: top_depth,
            FRONT_RADIUS: front_radius, BACK_RADIUS: back_radius, TOP_RADIUS: top_radius
        })
        return v

    @staticmethod
    def max_radius(values, radius_id):
        """Largest value of a radius that fits without pushing the other parameters."""
        if radius_id == FRONT_RADIUS:
            return min(values[FRONT_HEIGHT], values[FLOOR_DEPTH] - values[BACK_RADIUS])
        if radius_id == BACK_RADIUS:
            return min(values[FLOOR_DEPTH] - values[FRONT_RADIUS], values[WALL_HEIGHT] - values[TOP_RADIUS])
        if radius_id == TOP_RADIUS:
            return min(values[TOP_DEPTH], values[WALL_HEIGHT] - values[BACK_RADIUS])
        return None

    @staticmethod
    def damp_radius_overflow(start_values, param_id, value):
        """Damps a radius `value` beyond its maximum at drag start (`start_values`)."""
        maximum = Helper.max_radius(Helper.constrain(start_values, None), param_id)
        if maximum is None or value <= maximum:
            return value
        return maximum + (value - maximum) * RADIUS_OVERFLOW_DAMPING

    @staticmethod
    def apply_constraints(node, changed_id, values=None):
        """
        Constrains node parameters after `changed_id` was edited (`values` defaults to the
        node's current values). Values are written in the data container: node[id] = value
        would send MSG_DESCRIPTION_POSTSETPARAMETER and re-enter the constraints with stale values.
        """
        if values is None:
            values = Helper.get_shape_values(node)
        data = node.GetDataInstance()
        changed = False
        for param_id, value in Helper.constrain(values, changed_id).items():
            if data.GetFloat(param_id) != value:
                data.SetFloat(param_id, value)
                changed = True
        if changed:
            node.SetDirty(c4d.DIRTYFLAGS_DATA)

    @staticmethod
    def apply_preset(node, preset_id):
        doc = node.GetDocument()
        if doc is not None:
            doc.StartUndo()
            doc.AddUndo(c4d.UNDOTYPE_CHANGE_SMALL, node)
        values = Helper.get_shape_values(node)
        values.update(PRESETS[preset_id])
        Helper.apply_constraints(node, None, values)
        if doc is not None:
            doc.EndUndo()


class Geometry(object):
    """Mesh generation. Profiles are lists of 2D points (z, y)."""

    @staticmethod
    def arc(center, radius, angle_start, angle_end, segments):
        return [(center[0] + radius * math.cos(a), center[1] + radius * math.sin(a))
                for a in (angle_start + (angle_end - angle_start) * k / float(segments)
                          for k in range(segments + 1))]

    @staticmethod
    def arc_parts(segments, first_part, second_part):
        """Arcs are split in their middle between the two parts they join."""
        return [first_part if 2 * k + 1 < segments else second_part for k in range(segments)]

    @staticmethod
    def pieces(values, curve_segments, thickness):
        """
        Returns the profile pieces, from the front bottom edge to the top front edge:
        [(inner points, outer points, parts per inner segment)]. Outer points (inner profile
        offset by `thickness` on the outer side) are None when there is no thickness.
        """
        fh, wh = values[FRONT_HEIGHT], values[WALL_HEIGHT]
        hf, td = values[FLOOR_DEPTH] * 0.5, values[TOP_DEPTH]
        fr, br, tr = values[FRONT_RADIUS], values[BACK_RADIUS], values[TOP_RADIUS]
        t = thickness
        n = curve_segments
        arc, arc_parts = Geometry.arc, Geometry.arc_parts
        pi = math.pi

        pieces = [
            ([(-hf, -fh), (-hf, -fr)], [PART_FRONT]),
            (arc((-hf + fr, -fr), fr, pi, pi * 0.5, n), arc_parts(n, PART_FRONT, PART_FLOOR)),
            ([(-hf + fr, 0.), (hf - br, 0.)], [PART_FLOOR]),
            (arc((hf - br, br), br, pi * 1.5, pi * 2., n), arc_parts(n, PART_FLOOR, PART_WALL)),
            ([(hf, br), (hf, wh - tr)], [PART_WALL]),
            (arc((hf - tr, wh - tr), tr, 0., pi * 0.5, n), arc_parts(n, PART_WALL, PART_TOP)),
            ([(hf - tr, wh), (hf - td, wh)], [PART_TOP]),
        ]

        if t <= EPSILON:
            return [(inner, None, parts) for inner, parts in pieces]

        # The front corner is concave on the outer side: its offset shrinks and may collapse
        if fr >= t:
            front = [
                [(-hf + t, -fh), (-hf + t, -fr)],
                arc((-hf + fr, -fr), fr - t, pi, pi * 0.5, n),
                [(-hf + fr, -t), (hf - br, -t)],
            ]
        elif fh >= t:
            front = [[(-hf + t, -fh), (-hf + t, -t)], [], [(-hf + t, -t), (hf - br, -t)]]
        else:
            front = [[], [], [(-hf, -t), (hf - br, -t)]]

        outer = front + [
            arc((hf - br, br), br + t, pi * 1.5, pi * 2., n),
            [(hf + t, br), (hf + t, wh - tr)],
            arc((hf - tr, wh - tr), tr + t, 0., pi * 0.5, n),
            [(hf - tr, wh + t), (hf - td, wh + t)],
        ]
        return [(inner, outer[i], parts) for i, (inner, parts) in enumerate(pieces)]

    @staticmethod
    def polyline(point_lists, part_lists=None):
        """Concatenates point lists, removing duplicated points. Returns (points, parts per segment)."""
        points, parts = [], []
        for i, point_list in enumerate(point_lists):
            for k, p in enumerate(point_list):
                if points and abs(p[0] - points[-1][0]) <= EPSILON and abs(p[1] - points[-1][1]) <= EPSILON:
                    continue
                if points:
                    parts.append(part_lists[i][max(0, k - 1)] if part_lists else None)
                points.append(p)
        return points, parts

    @staticmethod
    def length(points):
        return sum(math.hypot(b[0] - a[0], b[1] - a[1]) for a, b in zip(points, points[1:]))

    @staticmethod
    def profiles(values, curve_segments, thickness):
        """
        Returns (inner points, inner parts, outer points, side points, side closing index, side start):
        - outer points: None without thickness
        - side points: polygon of the side panels, i.e. the area enclosed by the profile (without
          the front drop), closed on the front. Edges from the closing index are the closing edges.
        - side start: index of the inner point where the side panels start (after the front drop)
        """
        pieces = Geometry.pieces(values, curve_segments, thickness)

        # Null pieces at the profile ends are removed with their outer offset,
        # so that the ends of the thickness follow the last visible piece
        visible = [i for i, (inner, _, _) in enumerate(pieces) if Geometry.length(inner) > EPSILON]
        if not visible:
            return [], [], None, [], 0, 0
        pieces = pieces[visible[0]:visible[-1] + 1]

        inner, parts = Geometry.polyline([p[0] for p in pieces], [p[2] for p in pieces])
        outer = None
        if pieces[0][1] is not None:
            outer, _ = Geometry.polyline([p[1] for p in pieces])

        side_pieces = pieces[1:] if visible[0] == 0 else pieces
        side, _ = Geometry.polyline([p[0] for p in side_pieces])
        closing_index = max(0, len(side) - 1)
        if len(side) >= 2:
            start, end = side[0], side[-1]
            front_z = min(start[0], end[0])
            side, _ = Geometry.polyline([side, [(front_z, end[1]), (front_z, start[1])]])
            if abs(side[-1][0] - start[0]) <= EPSILON and abs(side[-1][1] - start[1]) <= EPSILON:
                side.pop()

        side_start = 1 if visible[0] == 0 else 0  # The front drop is a single segment
        return inner, parts, outer, side, closing_index, side_start

    @staticmethod
    def signed_area(polygon):
        return 0.5 * sum(a[0] * b[1] - b[0] * a[1] for a, b in zip(polygon, polygon[1:] + polygon[:1]))

    @staticmethod
    def triangulate(polygon):
        """Ear clipping triangulation of a simple polygon. Returns [(i, j, k)]."""
        count = len(polygon)
        area = Geometry.signed_area(polygon) if count >= 3 else 0.
        if abs(area) <= EPSILON:
            return []
        orientation = 1. if area > 0 else -1.

        def cross(a, b, c):
            return ((b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])) * orientation

        def inside(p, a, b, c):
            return cross(a, b, p) >= -EPSILON and cross(b, c, p) >= -EPSILON and cross(c, a, p) >= -EPSILON

        indices = list(range(count))

        def convexity(k):
            size = len(indices)
            return cross(polygon[indices[k - 1]], polygon[indices[k]], polygon[indices[(k + 1) % size]])

        # Only reflex vertices can be inside an ear: they are tracked as the polygon shrinks
        reflex = set(indices[k] for k in range(count) if convexity(k) < -EPSILON)

        def remove(k):
            reflex.discard(indices.pop(k))
            size = len(indices)
            for neighbor in ((k - 1) % size, k % size):
                if convexity(neighbor) < -EPSILON:
                    reflex.add(indices[neighbor])
                else:
                    reflex.discard(indices[neighbor])

        triangles = []
        k, misses = 0, 0
        while len(indices) > 3 and misses < len(indices):
            size = len(indices)
            k %= size
            i0, i1, i2 = indices[k - 1], indices[k], indices[(k + 1) % size]
            a, b, c = polygon[i0], polygon[i1], polygon[i2]
            value = cross(a, b, c)
            if abs(value) <= EPSILON:
                remove(k)  # Collinear point
                misses = 0
            elif value > 0 and not any(inside(polygon[i], a, b, c) and polygon[i] not in (a, b, c)
                                       for i in reflex if i not in (i0, i1, i2)):
                triangles.append((i0, i1, i2))
                remove(k)
                misses = 0
            else:
                k += 1
                misses += 1
        # A full round without ear: not a simple polygon, the remaining part is given up
        if len(indices) == 3 and abs(cross(*(polygon[i] for i in indices))) > EPSILON:
            triangles.append(tuple(indices))
        return triangles

    @staticmethod
    def build(values, width_segments, curve_segments, thickness, left_side, right_side):
        mesh = MeshBuilder()
        inner, parts, outer, side, side_closing, side_start = Geometry.profiles(values, curve_segments, thickness)
        if len(inner) < 2:
            return mesh

        t = thickness if outer is not None else 0.
        half_width = values[WIDTH] * 0.5
        inner_columns = [-half_width + values[WIDTH] * k / float(width_segments) for k in range(width_segments + 1)]
        # With thickness, the stage goes under the side panels
        columns = list(inner_columns)
        if left_side and t > 0:
            columns.insert(0, -half_width - t)
        if right_side and t > 0:
            columns.append(half_width + t)
        x_range = (columns[0], columns[-1])

        # Under the side panels, only the front drop of the inner surface is visible
        normals = Geometry.air_normals(inner)
        if side_start > 0 and columns != inner_columns:
            mesh.add_strip(inner, columns, parts, normals, 0, side_start, x_range)
            mesh.add_strip(inner, inner_columns, parts, normals, side_start, len(inner) - 1, x_range)
        else:
            mesh.add_strip(inner, inner_columns, parts, normals, x_range=x_range)

        if outer is not None and len(outer) >= 2:
            normals = [-n for n in Geometry.air_normals(outer)]
            mesh.add_strip(outer, columns, [PART_OUTSIDE] * (len(outer) - 1), normals)
            # Profile ends: the band between the inner and the outer profile
            band = inner + outer[::-1]
            mesh.add_strip([inner[0], outer[0]], columns, [PART_OUTSIDE],
                           [Geometry.edge_normal(band, len(band) - 1)])
            mesh.add_strip([inner[-1], outer[-1]], columns, [PART_OUTSIDE],
                           [Geometry.edge_normal(band, len(inner) - 1)])
            band_triangles = Geometry.triangulate(band)
            mesh.add_cap(band, columns[0], Vector(-1, 0, 0), PART_OUTSIDE, band_triangles)
            mesh.add_cap(band, columns[-1], Vector(1, 0, 0), PART_OUTSIDE, band_triangles)

        if len(side) >= 3 and (left_side or right_side):
            side_triangles = Geometry.triangulate(side)
            for enabled, sign in ((left_side, -1.), (right_side, 1.)):
                if enabled:
                    Geometry.add_side_panel(mesh, side, side_triangles, side_closing, half_width * sign, t, sign)

        return mesh

    @staticmethod
    def add_side_panel(mesh, side, triangles, closing_index, x, thickness, sign):
        """Side panel at `x`, facing the stage, extruded outward (toward `sign`) by `thickness`."""
        outward = Vector(sign, 0, 0)
        mesh.add_cap(side, x, -outward, PART_SIDES, triangles)
        if thickness > EPSILON:
            mesh.add_cap(side, x + sign * thickness, outward, PART_SIDES, triangles)
            # Rim along the closing edges only: the rest of the panel lies on the stage
            columns = sorted([x, x + sign * thickness])
            for i in range(closing_index, len(side)):
                a, b = side[i], side[(i + 1) % len(side)]
                mesh.add_strip([a, b], columns, [PART_SIDES], [Geometry.edge_normal(side, i)])

    @staticmethod
    def edge_normal(polygon, index):
        """Outward normal (3D, x = 0) of the edge `index` -> `index + 1` of a closed polygon."""
        a, b = polygon[index], polygon[(index + 1) % len(polygon)]
        orientation = 1. if Geometry.signed_area(polygon) > 0 else -1.
        return Vector(0, a[0] - b[0], b[1] - a[1]) * orientation

    @staticmethod
    def air_normals(points):
        """Normal of each segment of a profile, on the stage (air) side."""
        return [Vector(0, b[0] - a[0], a[1] - b[1]) for a, b in zip(points, points[1:])]


class MeshBuilder(object):
    """Accumulates points and polygons (each with UVs and a part name)."""

    def __init__(self):
        self.points = []
        self.polygons = []
        self.uvs = []
        self.parts = []

    def add_point(self, p):
        self.points.append(p)
        return len(self.points) - 1

    def add_polygon(self, indices, uvs, part, normal):
        """Adds a triangle or quad, reversed if needed to face `normal`."""
        a, b, c = (self.points[i] for i in indices[:3])
        face_normal = (b - a).Cross(c - a)
        if len(indices) == 4 and face_normal.GetLength() <= EPSILON:
            face_normal = (c - a).Cross(self.points[indices[3]] - a)
        if face_normal.Dot(normal) < 0:
            indices, uvs = indices[::-1], uvs[::-1]
        self.polygons.append(indices)
        self.uvs.append(uvs)
        self.parts.append(part)

    def add_strip(self, profile, columns, parts, normals, first=0, last=None, x_range=None):
        """
        Extrudes the segments `first` to `last` of a 2D profile (z, y) along X through `columns`,
        as a grid of quads. UVs: U along X (over `x_range`), V along the whole profile.
        """
        last = len(profile) - 1 if last is None else last
        lengths = [0.]
        for a, b in zip(profile, profile[1:]):
            lengths.append(lengths[-1] + math.hypot(b[0] - a[0], b[1] - a[1]))
        total_length = lengths[-1] or 1.
        x_min, x_max = x_range or (columns[0], columns[-1])
        x_size = (x_max - x_min) or 1.
        u = [(x - x_min) / x_size for x in columns]

        grid = dict((i, [self.add_point(Vector(x, profile[i][1], profile[i][0])) for x in columns])
                    for i in range(first, last + 1))
        for i in range(first, last):
            v0, v1 = lengths[i] / total_length, lengths[i + 1] / total_length
            for j in range(len(columns) - 1):
                self.add_polygon(
                    [grid[i][j], grid[i + 1][j], grid[i + 1][j + 1], grid[i][j + 1]],
                    [Vector(u[j], v0, 0), Vector(u[j], v1, 0), Vector(u[j + 1], v1, 0), Vector(u[j + 1], v0, 0)],
                    parts[i], normals[i])

    def add_cap(self, polygon, x, normal, part, triangles):
        """Flat polygon (z, y) at `x` from its triangulation, with planar UVs."""
        if not triangles:
            return
        z_min = min(p[0] for p in polygon)
        y_min = min(p[1] for p in polygon)
        size = max(max(p[0] for p in polygon) - z_min, max(p[1] for p in polygon) - y_min) or 1.
        indices = [self.add_point(Vector(x, p[1], p[0])) for p in polygon]
        uv = [Vector((p[0] - z_min) / size, (p[1] - y_min) / size, 0) for p in polygon]
        for tri in triangles:
            self.add_polygon([indices[i] for i in tri], [uv[i] for i in tri], part, normal)

    def to_polygon_object(self):
        obj = c4d.PolygonObject(len(self.points), len(self.polygons))
        if self.points:
            obj.SetAllPoints(self.points)

        uvw = c4d.UVWTag(len(self.polygons))
        selections = dict((part, c4d.BaseSelect()) for part in PARTS)
        for i, (indices, uvs, part) in enumerate(zip(self.polygons, self.uvs, self.parts)):
            if len(indices) == 3:
                indices, uvs = indices + indices[2:], uvs + uvs[2:]
            obj.SetPolygon(i, c4d.CPolygon(*indices))
            uvw.SetSlow(i, *uvs)
            selections[part].Select(i)

        obj.InsertTag(uvw)
        for part in reversed(PARTS):
            if selections[part].GetCount() == 0:
                continue  # E.g. no "Sides" selection without side panels
            tag = c4d.SelectionTag(c4d.Tpolygonselection)
            tag[c4d.ID_BASELIST_NAME] = part
            selections[part].CopyTo(tag.GetBaseSelect())
            obj.InsertTag(tag)

        obj.Message(c4d.MSG_UPDATE)
        return obj


class LObject(plugins.ObjectData):

    # Attribute Manager names of the handle parameters, see _handle_label
    _param_names = {}

    def __init__(self):
        self.SetOptimizeCache(True)

    def Init(self, op):
        # Written in the data container: op[id] = value would run the constraints for each value
        data = op.GetDataInstance()
        for param_id, value in SHAPE_DEFAULTS.items():
            self.InitAttr(op, float, [param_id])
            data.SetFloat(param_id, value)
        self.InitAttr(op, float, [THICKNESS])
        data.SetFloat(THICKNESS, THICKNESS_DEFAULT)
        self.InitAttr(op, int, [WIDTH_SEGMENTS])
        data.SetInt32(WIDTH_SEGMENTS, WIDTH_SEGMENTS_DEFAULT)
        self.InitAttr(op, int, [CURVE_SEGMENTS])
        data.SetInt32(CURVE_SEGMENTS, CURVE_SEGMENTS_DEFAULT)
        self.InitAttr(op, bool, [LEFT_SIDE])
        data.SetBool(LEFT_SIDE, False)
        self.InitAttr(op, bool, [RIGHT_SIDE])
        data.SetBool(RIGHT_SIDE, False)
        return True

    @staticmethod
    def _handles(op):
        """Returns the [(position, direction)] of all handles."""
        v = Helper.constrain(Helper.get_shape_values(op), None)
        half_width = v[WIDTH] * 0.5
        half_floor = v[FLOOR_DEPTH] * 0.5
        wall_height = v[WALL_HEIGHT]
        up, front, right = Vector(0, 1, 0), Vector(0, 0, -1), Vector(1, 0, 0)
        return [
            (Vector(0, -v[FRONT_HEIGHT], -half_floor), -up),
            (Vector(0, wall_height, half_floor), up),
            (Vector(half_width, 0, 0), right),
            (Vector(0, 0, -half_floor), front),
            (Vector(0, wall_height, half_floor - v[TOP_DEPTH]), front),
            (Vector(half_width, -v[FRONT_RADIUS], -half_floor), -up),
            (Vector(half_width, v[BACK_RADIUS], half_floor), up),
            (Vector(half_width, wall_height, half_floor - v[TOP_RADIUS]), front),
        ]

    def GetHandleCount(self, op):
        return len(HANDLE_PARAMS)

    def GetHandle(self, op, handle_index, handle_info):
        handle_info.position, handle_info.direction = LObject._handles(op)[handle_index]
        handle_info.type = c4d.HANDLECONSTRAINTTYPE_LINEAR

    def MoveHandle(self, op, undo, mouse_pos, hit_id, qualifier, bd):
        # Replaces the default implementation (which calls SetHandle with the current state):
        # the value is computed from the drag start state (`undo`), so that it can be damped
        if not 0 <= hit_id < len(HANDLE_PARAMS):
            return False

        info = HandleInfo()
        self.GetHandle(undo, hit_id, info)
        position = info.CalculateNewPosition(bd, op.GetUpMg() * undo.GetMl(), mouse_pos)
        self._move_handle(op, undo, hit_id, position)
        return True

    def _move_handle(self, op, undo, handle_index, handle_position):
        """Moves a handle to `handle_position` (local space), `undo` being the drag start state."""
        start_position, direction = LObject._handles(undo)[handle_index]
        parameter = HANDLE_PARAMS[handle_index]
        start_values = Helper.get_shape_values(undo)

        offset = (handle_position - start_position).Dot(direction)
        value = start_values[parameter] + offset * HANDLE_SCALE.get(parameter, 1.)

        values = dict(start_values)
        values[parameter] = Helper.damp_radius_overflow(start_values, parameter, value)
        Helper.apply_constraints(op, parameter, values)

    def DetectHandle(self, op, bd, x, y, qualifier):
        # Default implementation with a larger pick radius, and picking the closest
        # handle to the mouse (then to the camera) instead of the first one in range
        if qualifier & c4d.QUALIFIER_CTRL:
            return c4d.NOTOK

        mg = op.GetMg()
        closest, closest_key = c4d.NOTOK, None
        for i, (position, _) in enumerate(LObject._handles(op)):
            screen = bd.WS(mg * position)
            distance = math.hypot(screen.x - x, screen.y - y)
            if distance > HANDLE_PICK_RADIUS:
                continue
            key = (round(distance), screen.z)
            if closest_key is None or key < closest_key:
                closest, closest_key = i, key
        return closest

    def Draw(self, op, drawpass, bd, bh):
        if drawpass != c4d.DRAWPASS_HANDLES:
            return c4d.DRAWRESULT_SKIP

        self._draw_handles(op, bd, bh.GetMg(), op.GetHighlightHandle(bd))
        return c4d.DRAWRESULT_OK

    def GetVirtualObjects(self, op, hh):
        values = Helper.constrain(Helper.get_shape_values(op), None)
        mesh = Geometry.build(
            values,
            width_segments=max(1, op[WIDTH_SEGMENTS] or 1),
            curve_segments=max(1, op[CURVE_SEGMENTS] or 1),
            thickness=max(0., op[THICKNESS] or 0.),
            left_side=bool(op[LEFT_SIDE]),
            right_side=bool(op[RIGHT_SIDE]))

        result = mesh.to_polygon_object()
        result[c4d.ID_BASELIST_NAME] = op.GetName()

        # The generator's phong tag (added on creation, see Message)
        phong = op.GetTag(c4d.Tphong)
        if phong is not None:
            result.InsertTag(phong.GetClone())

        return result

    def Message(self, node, type, data):
        if type == c4d.MSG_MENUPREPARE:
            if node.GetTag(c4d.Tphong) is None:
                phong = node.MakeTag(c4d.Tphong)
                if phong is not None:
                    phong[c4d.PHONGTAG_PHONG_ANGLELIMIT] = True
                    phong[c4d.PHONGTAG_PHONG_USEEDGES] = False

        elif type == c4d.MSG_DESCRIPTION_POSTSETPARAMETER and data:
            current_id = data['descid'][0].id
            if current_id in SHAPE_DEFAULTS:
                Helper.apply_constraints(node, current_id)

        elif type == c4d.MSG_DESCRIPTION_COMMAND and data:
            command_id = data['id'][0].id
            if command_id in PRESETS:
                Helper.apply_preset(node, command_id)
                c4d.EventAdd()

        return True

    def _draw_handles(self, op, bd, mg, highlight):
        handles = LObject._handles(op)

        # Size in pixels, whatever the zoom
        bd.SetMatrix_Matrix(op, mg)
        for i, (position, _) in enumerate(handles):
            bd.SetPen(LObject._handle_color(i, i == highlight))
            bd.SetPointSize(HANDLE_SIZE_HIGHLIGHT if i == highlight else HANDLE_SIZE)
            bd.DrawHandle(position, c4d.DRAWHANDLE_CUSTOM, 0)

        # Direction arrows, in screen space so that they keep the same length
        bd.SetMatrix_Screen()
        for i, (position, direction) in enumerate(handles):
            start = bd.WS(mg * position)
            end = bd.WS(mg * (position + direction))
            arrow = Vector(end.x - start.x, end.y - start.y, 0)
            if arrow.GetLength() < EPSILON:
                continue  # Pointing to the camera
            arrow.Normalize()
            start = Vector(start.x, start.y, 0)
            tip = start + arrow * HANDLE_ARROW_LENGTH
            side = Vector(-arrow.y, arrow.x, 0)
            bd.SetPen(LObject._handle_color(i, i == highlight))
            bd.DrawLine2D(start, tip)
            bd.DrawLine2D(tip, tip - (arrow - side * 0.5) * HANDLE_ARROW_HEAD)
            bd.DrawLine2D(tip, tip - (arrow + side * 0.5) * HANDLE_ARROW_HEAD)

        if 0 <= highlight < len(handles):
            screen = bd.WS(mg * handles[highlight][0])
            bd.DrawHUDText(int(screen.x + HANDLE_SIZE_HIGHLIGHT), int(screen.y - 2 * HANDLE_SIZE_HIGHLIGHT),
                           LObject._handle_label(op, highlight))

    @staticmethod
    def _handle_color(handle_index, highlighted):
        if highlighted:
            return c4d.GetViewColor(c4d.VIEWCOLOR_SELECTION_PREVIEW)
        if handle_index < 5:
            return c4d.GetViewColor(c4d.VIEWCOLOR_ACTIVEPOINT)
        return HANDLE_COLOR_RADIUS

    @staticmethod
    def _handle_label(op, handle_index):
        """Returns 'Parameter Name: value', with the Attribute Manager name and units."""
        param_id = HANDLE_PARAMS[handle_index]
        # Building the description is costly: the names are read once
        if not LObject._param_names:
            description = op.GetDescription(c4d.DESCFLAGS_DESC_NONE)
            for bc, descid, _ in description:
                if descid[0].id in HANDLE_PARAMS:
                    LObject._param_names[descid[0].id] = bc[c4d.DESC_NAME]
        doc = op.GetDocument()
        fps = doc.GetFps() if doc is not None else 30
        value = c4d.utils.FormatNumber(op[param_id] or 0., c4d.FORMAT_METER, fps)
        return '%s: %s' % (LObject._param_names.get(param_id, param_id), value)


if __name__ == "__main__":
    icon = bitmaps.BaseBitmap()
    icon.InitWith(os.path.join(os.path.dirname(__file__), 'res', 'lobject.png'))
    plugins.RegisterObjectPlugin(PLUGIN_ID, 'L-Object', LObject, 'olobject', c4d.OBJECT_GENERATOR, icon)
