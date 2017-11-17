# -*- coding: utf-8 -*-

# Author: safina3d
# Url: https://safina3d.blogspot.com

import os
import c4d
from c4d import plugins, bitmaps, BaseObject, SplineObject, Vector, HandleInfo

PLUGIN_ID = 1027130


class Helper:

    VECTOR_ZERO = Vector(0)
    VECTOR_ONE_X = Vector(1, 0, 0)
    VECTOR_ONE_Y = Vector(0, 1, 0)
    VECTOR_ONE_Z = Vector(0, 0, 1)

    DEFAULT_COLOR = c4d.GetViewColor(c4d.VIEWCOLOR_ACTIVEPOINT)
    ACTIVE_COLOR = c4d.GetViewColor(c4d.VIEWCOLOR_SELECTION_PREVIEW)

    def __init__(self): pass


class LObject(plugins.ObjectData):

    def Init(self, op):
        self.SetOptimizeCache(True)

        # Initialization
        self.InitAttr(op, float, [c4d.L_OBJECT_HEIGHT])
        self.InitAttr(op, float, [c4d.L_OBJECT_DEPTH])
        self.InitAttr(op, float, [c4d.L_OBJECT_WIDTH])
        self.InitAttr(op, float, [c4d.L_OBJECT_CURVE_OFFSET])
        self.InitAttr(op, float, [c4d.L_OBJECT_WIDTH_SEGMENTS])
        self.InitAttr(op, bool, [c4d.L_OBJECT_ENABLE_PHONG_TAG])
        self.InitAttr(op, bool, [c4d.L_OBJECT_ANGLE_LIMIT])
        self.InitAttr(op, float, [c4d.L_OBJECT_PHONG_ANGLE])

        # Default values
        op[c4d.L_OBJECT_HEIGHT] = 1000
        op[c4d.L_OBJECT_DEPTH] = 300
        op[c4d.L_OBJECT_WIDTH] = 750
        op[c4d.L_OBJECT_CURVE_OFFSET] = 100
        op[c4d.L_OBJECT_WIDTH_SEGMENTS] = 1
        op[c4d.L_OBJECT_ENABLE_PHONG_TAG] = True
        op[c4d.L_OBJECT_ANGLE_LIMIT] = False
        op[c4d.L_OBJECT_PHONG_ANGLE] = 1.0472

        return True

    def GetDimension(self, op, mp, rad):
        rad.x = op[c4d.L_OBJECT_WIDTH]
        rad.y = 0.5 * (op[c4d.L_OBJECT_HEIGHT] + op[c4d.L_OBJECT_CURVE_OFFSET])
        rad.z = 500 + op[c4d.L_OBJECT_DEPTH] * 0.5
        mp.y = rad.y
        mp.z = op[c4d.L_OBJECT_DEPTH] * 0.5

    def GetHandleCount(self, op):
        return 3

    def GetHandle(self, op, handle_index, handle_info):
        l_object_depth = op[c4d.L_OBJECT_DEPTH] + 500 if op[c4d.L_OBJECT_DEPTH] is not None else 800
        l_object_width = op[c4d.L_OBJECT_WIDTH] if op[c4d.L_OBJECT_WIDTH] is not None else 750
        l_object_height = op[c4d.L_OBJECT_HEIGHT] if op[c4d.L_OBJECT_HEIGHT] is not None else 500

        if handle_index == 0:
            handle_info.position = Vector(l_object_width, 0, 0)
            handle_info.direction = Helper.VECTOR_ONE_X
        elif handle_index == 1:
            handle_info.position = Vector(0, l_object_height, l_object_depth)
            handle_info.direction = Helper.VECTOR_ONE_Y
        elif handle_index == 2:
            handle_info.position = Vector(0, 0, l_object_depth)
            handle_info.direction = Helper.VECTOR_ONE_Z

        handle_info.type = c4d.HANDLECONSTRAINTTYPE_LINEAR

    def SetHandle(self, op, handle_index, handle_position, handle_info):
        handle_origin = HandleInfo()
        self.GetHandle(op, handle_index, handle_origin)

        value = (handle_position - handle_origin.position) * handle_info.direction

        if handle_index == 0:
            op[c4d.L_OBJECT_WIDTH] += value
            op[c4d.L_OBJECT_WIDTH] = op[c4d.L_OBJECT_WIDTH] if op[c4d.L_OBJECT_WIDTH] > 0 else 0.0001
        elif handle_index == 1:
            op[c4d.L_OBJECT_HEIGHT] += value
        elif handle_index == 2:
            op[c4d.L_OBJECT_DEPTH] += value

    def Draw(self, op, drawpass, bd, bh):
        if drawpass != c4d.DRAWPASS_HANDLES:
            return c4d.DRAWRESULT_SKIP

        bd.SetMatrix_Matrix(op, bh.GetMg())
        hitid = op.GetHighlightHandle(bd)

        self.__draw_handle(bd, op, 0, 0 == hitid, Helper.VECTOR_ZERO)
        self.__draw_handle(bd, op, 1, 1 == hitid, Vector(0, 0, 500 + op[c4d.L_OBJECT_DEPTH]))
        self.__draw_handle(bd, op, 2, 2 == hitid, Helper.VECTOR_ZERO)

        return c4d.DRAWRESULT_OK

    def GetVirtualObjects(self, op, hh):
        extrude_object = BaseObject(c4d.Oextrude)
        spline_object = SplineObject(4, c4d.SPLINETYPE_BEZIER)

        LObject.__create_spline_object(spline_object, op)

        extrude_object[c4d.EXTRUDEOBJECT_MOVE] = Vector(op[c4d.L_OBJECT_WIDTH] * 2, 0, 0)
        extrude_object[c4d.EXTRUDEOBJECT_SUB] = int(op[c4d.L_OBJECT_WIDTH_SEGMENTS])
        extrude_object.SetPhong(
            op[c4d.L_OBJECT_ENABLE_PHONG_TAG],
            op[c4d.L_OBJECT_ANGLE_LIMIT],
            op[c4d.L_OBJECT_PHONG_ANGLE]
        )
        spline_object.InsertUnder(extrude_object)
        return extrude_object

    def GetDEnabling(self, node, id, t_data, flags, itemdesc):
        data = node.GetDataInstance()
        if data is None:
            return
        current_id = id[0].id
        if c4d.L_OBJECT_PHONG_ANGLE == current_id or c4d.L_OBJECT_ANGLE_LIMIT == current_id:
            return 1 == data.GetLong(c4d.L_OBJECT_ENABLE_PHONG_TAG)
        return True

    def __draw_handle(self, bd, op, handle_index, handle_is_selected, start_position):
        bd.SetPen(Helper.ACTIVE_COLOR if handle_is_selected else Helper.DEFAULT_COLOR)
        handle_info = HandleInfo()
        self.GetHandle(op, handle_index, handle_info)
        bd.DrawHandle(handle_info.position, c4d.DRAWHANDLE_BIG, 0)
        bd.DrawLine(start_position, handle_info.position, 0)

    @staticmethod
    def __create_spline_object(spline_object, op):
        height = op[c4d.L_OBJECT_HEIGHT] + op[c4d.L_OBJECT_CURVE_OFFSET]
        depth = op[c4d.L_OBJECT_DEPTH]
        curve_offset = op[c4d.L_OBJECT_CURVE_OFFSET]
        width = op[c4d.L_OBJECT_WIDTH]

        spline_object.SetPoint(0, Vector(0, 0, -depth))
        spline_object.SetPoint(1, Vector(0, 0, 1000 - curve_offset))
        spline_object.SetPoint(2, Vector(0, curve_offset, 1000))
        spline_object.SetPoint(3, Vector(0, height, 1000))

        spline_object.SetTangent(1, Helper.VECTOR_ZERO, Vector(0, 0, curve_offset * 0.5))
        spline_object.SetTangent(2, Vector(0, -curve_offset * 0.5, 0), Helper.VECTOR_ZERO)

        spline_object.SetAbsPos(Vector(-width, 0, depth - 500))
        spline_object.Message(c4d.MSG_UPDATE)


if __name__ == "__main__":
    icon = bitmaps.BaseBitmap()
    icon.InitWith(os.path.join(os.path.dirname(__file__), 'res', 'lobject.png'))
    plugins.RegisterObjectPlugin(PLUGIN_ID, 'L-Object', LObject, 'lobject', c4d.OBJECT_GENERATOR, icon)
