# SPDX-FileCopyrightText: 2025 Harri Kaimio
#
# SPDX-License-Identifier: BSD-3-Clause

import bpy

from . import drivers

bl_info = {
    "name": "Pose Editor",
    "author": "Harri Kaimio",
    "version": (0, 1, 0),
    "blender": (4, 0, 0),
    "location": "View3D > Sidebar > Pose Editor Tab",
    "description": "Add-on for editing motion capture data.",
    "warning": "",
    "doc_url": "",
    "category": "Animation",
}


def register():
    bpy.app.driver_namespace["get_quality_driven_color_component"] = drivers.get_quality_driven_color_component
    print("Pose Editor Addon Registered")


def unregister():
    if "get_quality_driven_color_component" in bpy.app.driver_namespace:
        del bpy.app.driver_namespace["get_quality_driven_color_component"]
    print("Pose Editor Addon Unregistered")
