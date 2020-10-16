# -*- coding: utf-8 -*-

# Author: safina3d
# Version: 2.0
# Url: https://safina3d.blogspot.com

import os
import c4d
from c4d import plugins, bitmaps, BaseObject, SplineObject, Vector, HandleInfo, utils, documents

PLUGIN_ID = 1027130


class Helper(object):

    VEC_ZERO = Vector(0)
    VEC_ONE_X = Vector(1, 0, 0)
    VEC_ONE_Y = Vector(0, 1, 0)
    VEC_ONE_Z = Vector(0, 0, 1)

    DEFAULT_COLOR = c4d.GetViewColor(c4d.VIEWCOLOR_ACTIVEPOINT)
    DEFAULT_COLOR_BIS = Vector(0.54, 0.758, 0.984)
    ACTIVE_COLOR = c4d.GetViewColor(c4d.VIEWCOLOR_SELECTION_PREVIEW)


class LObject(plugins.ObjectData):

    def __init__(self):
        self.SetOptimizeCache(True)

    def Init(self, op):

        # Parameter Initialization
        param_list = [
            c4d.HEIGHT_0, c4d.HEIGHT_1, c4d.WIDTH, c4d.DEPTH_0,
            c4d.DEPTH_1, c4d.CURVE_OFFSET_0, c4d.CURVE_OFFSET_1,
            c4d.CURVE_OFFSET_2
        ]
        default_values = [300., 1200., 1500., 1500., 1000., 100., 250., 250., 1]
        param_count = len(param_list)

        for i in range(param_count):
            param_id = param_list[i]
            self.InitAttr(op, float, [param_id])
            op[param_id] = default_values[i]

        self.InitAttr(op, int, [c4d.WIDTH_SEGMENTS])
        op[c4d.WIDTH_SEGMENTS] = default_values[param_count]

        return True

    def GetHandleCount(self, op):
        return 8

    def GetHandle(self, op, handle_index, handle_info):
        h0 = op[c4d.HEIGHT_0]
        h1 = op[c4d.HEIGHT_1]
        half_width = op[c4d.WIDTH] * 0.5
        half_depth_0 = op[c4d.DEPTH_0] * 0.5
        d1 = op[c4d.DEPTH_1]
        c0 = op[c4d.CURVE_OFFSET_0]
        c1 = op[c4d.CURVE_OFFSET_1]
        c2 = op[c4d.CURVE_OFFSET_2]

        handles_position = [
            Vector(0, -h0, -half_depth_0),
            Vector(0, h1, half_depth_0),
            Vector(half_width, 0, 0),
            Vector(0, 0, -half_depth_0),
            Vector(0, h1, half_depth_0 - d1),
            Vector(half_width, -c0, -half_depth_0),
            Vector(half_width, c1, half_depth_0),
            Vector(half_width, h1, half_depth_0 - c2)
        ]

        handles_direction = [
            -Helper.VEC_ONE_Y,
            Helper.VEC_ONE_Y,
            Helper.VEC_ONE_X,
            -Helper.VEC_ONE_Z,
            -Helper.VEC_ONE_Z,
            -Helper.VEC_ONE_Y,
            Helper.VEC_ONE_Y,
            -Helper.VEC_ONE_Z
        ]

        handle_info.position = handles_position[handle_index]
        handle_info.direction = handles_direction[handle_index]
        handle_info.type = c4d.HANDLECONSTRAINTTYPE_LINEAR

    def SetHandle(self, op, handle_index, handle_position, handle_info):
        handle_origin = HandleInfo()
        self.GetHandle(op, handle_index, handle_origin)
        value = (handle_position - handle_origin.position) * handle_info.direction

        handle_count = self.GetHandleCount(op)
        param_list = [
            c4d.HEIGHT_0, c4d.HEIGHT_1, c4d.WIDTH, c4d.DEPTH_0, c4d.DEPTH_1,
            c4d.CURVE_OFFSET_0, c4d.CURVE_OFFSET_1, c4d.CURVE_OFFSET_2
        ]
        # Update node params
        if handle_index < handle_count:
            parameter = param_list[handle_index]
            op[parameter] += value

    def Draw(self, op, drawpass, bd, bh):
        if drawpass != c4d.DRAWPASS_HANDLES:
            return c4d.DRAWRESULT_SKIP

        bd.SetMatrix_Matrix(op, bh.GetMg())
        handle_id = op.GetHighlightHandle(bd)
        handle_count = self.GetHandleCount(op)

        for i in range(handle_count):
            self._draw_handle(bd, op, i, handle_id == i)

        return c4d.DRAWRESULT_OK

    def GetVirtualObjects(self, op, hh):

        extrude_object = BaseObject(c4d.Oextrude)
        spline_object = SplineObject(8, c4d.SPLINETYPE_BEZIER)

        LObject._create_spline_object(spline_object, op)

        # R23 Fix
        if c4d.GetC4DVersion() >= 23000:
            extrude_object[c4d.EXTRUDEOBJECT_DIRECTION] = 5

        extrude_object[c4d.EXTRUDEOBJECT_MOVE] = Vector(op[c4d.WIDTH], 0, 0)
        extrude_object[c4d.EXTRUDEOBJECT_SUB] = op[c4d.WIDTH_SEGMENTS]
        extrude_object[c4d.EXTRUDEOBJECT_FLIPNORMALS] = True

        spline_object.InsertUnder(extrude_object)

        # Convert to polygon object
        result = utils.SendModelingCommand(c4d.MCOMMAND_CURRENTSTATETOOBJECT, doc=documents.GetActiveDocument(), list=[extrude_object])
        if not result:
            return None

        result = result[0]

        # Remove selection tags
        tags = result.GetTags()
        for tag in tags:
            tag_type = tag.GetType()
            if tag_type == c4d.Tpolygonselection or tag_type == c4d.Tedgeselection:
                tag.Remove()

        # Add phong tag
        phong = op.GetTag(c4d.Tphong)
        if phong is None:
            phong = op.MakeTag(c4d.Tphong)

        if phong is not None:
            phong[c4d.PHONGTAG_PHONG_ANGLELIMIT] = True
            phong[c4d.PHONGTAG_PHONG_USEEDGES] = False
            result.InsertTag(phong.GetClone())

        return result

    def Message(self, node, type, data):
        if type == c4d.MSG_DESCRIPTION_POSTSETPARAMETER:
            current_id = data['descid'][0].id
            current_value = node[current_id]

            h0 = node[c4d.HEIGHT_0] or 0
            h1 = node[c4d.HEIGHT_1] or 0
            d0 = node[c4d.DEPTH_0] or 0
            d1 = node[c4d.DEPTH_1] or 0
            c0 = node[c4d.CURVE_OFFSET_0] or 0
            c1 = node[c4d.CURVE_OFFSET_1] or 0
            c2 = node[c4d.CURVE_OFFSET_2] or 0

            if current_id == c4d.HEIGHT_0:
                if current_value < c0:
                    node[c4d.CURVE_OFFSET_0] = current_value

            elif current_id == c4d.CURVE_OFFSET_0:
                if current_value > h0:
                    node[c4d.HEIGHT_0] = current_value
                if current_value > (d0 - c1):
                    node[c4d.DEPTH_0] = current_value + c1

            elif current_id == c4d.DEPTH_0:
                if current_value - c0 < c1:
                    node[c4d.CURVE_OFFSET_1] = current_value - c0
                if current_value - c1 < c0:
                    node[c4d.CURVE_OFFSET_0] = current_value - c1

            elif current_id == c4d.CURVE_OFFSET_1:
                if current_value > (d0 - c0):
                    node[c4d.DEPTH_0] = current_value + c0
                if current_value > (h1 - c2):
                    node[c4d.HEIGHT_1] = current_value + c2

            elif current_id == c4d.CURVE_OFFSET_2:
                if current_value > (h1 - c1):
                    node[c4d.HEIGHT_1] = current_value + c1
                if current_value > d1:
                    node[c4d.DEPTH_1] = current_value

            elif current_id == c4d.HEIGHT_1:
                if current_value - c2 < c1:
                    node[c4d.CURVE_OFFSET_1] = current_value - c2
                if current_value - c1 < c2:
                    node[c4d.CURVE_OFFSET_2] = current_value - c1

            elif current_id == c4d.DEPTH_1:
                if current_value < c2:
                    node[c4d.CURVE_OFFSET_2] = current_value

        return True

    def _draw_handle(self, bd, op, handle_index, handle_is_selected):
        if handle_index < 5:
            bd.SetPen(Helper.ACTIVE_COLOR if handle_is_selected else Helper.DEFAULT_COLOR)
        else:
            bd.SetPen(Helper.ACTIVE_COLOR if handle_is_selected else Helper.DEFAULT_COLOR_BIS)

        handle = HandleInfo()
        self.GetHandle(op, handle_index, handle)
        bd.DrawHandle(handle.position, c4d.DRAWHANDLE_BIG, 0)
        bd.DrawLine(handle.position + handle.direction * 50, handle.position, 0)

    @staticmethod
    def _create_spline_object(spline, op):

        h0 = op[c4d.HEIGHT_0]
        h1 = op[c4d.HEIGHT_1]
        w = op[c4d.WIDTH] * 0.5
        d0 = op[c4d.DEPTH_0] * 0.5
        d1 = op[c4d.DEPTH_1]
        c0 = op[c4d.CURVE_OFFSET_0]
        c1 = op[c4d.CURVE_OFFSET_1]
        c2 = op[c4d.CURVE_OFFSET_2]

        point_list = [
            Vector(0, -h0, -d0), Vector(0, -c0, -d0), Vector(0, 0, -(d0 - c0)), Vector(0, 0, d0 - c1),
            Vector(0, c1, d0), Vector(0, h1 - c2, d0), Vector(0, h1, d0 - c2), Vector(0, h1, d0 - d1)
        ]

        for i, p in enumerate(point_list):
            spline.SetPoint(i, p)

        # SetTangent for points 1 & 2
        spline.SetTangent(1, Helper.VEC_ZERO, Vector(0, c0 * 0.5, 0))
        spline.SetTangent(2, Vector(0, 0, -c0 * 0.5), Helper.VEC_ZERO)

        # SetTangent for points 3 & 4
        spline.SetTangent(3, Helper.VEC_ZERO, Vector(0, 0, c1 * 0.5))
        spline.SetTangent(4, Vector(0, -c1 * 0.5, 0), Helper.VEC_ZERO)

        # SetTangent for points 5 & 6
        spline.SetTangent(5, Helper.VEC_ZERO, Vector(0, c2 * 0.5, 0))
        spline.SetTangent(6, Vector(0, 0, c2 * 0.5), Helper.VEC_ZERO)

        spline.SetAbsPos(Vector(-w, 0, 0))
        spline.Message(c4d.MSG_UPDATE)


if __name__ == "__main__":
    icon = bitmaps.BaseBitmap()
    icon.InitWith(os.path.join(os.path.dirname(__file__), 'res', 'lobject.png'))
    plugins.RegisterObjectPlugin(PLUGIN_ID, 'L-Object', LObject, 'olobject', c4d.OBJECT_GENERATOR, icon)
