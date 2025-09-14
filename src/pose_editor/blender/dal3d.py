# SPDX-FileCopyrightText: 2025 Harri Kaimio
#
# SPDX-License-Identifier: BSD-3-Clause

"""Temporary DAL module for 3D-related functions."""

import bpy

from .dal import BlenderObjRef


def create_sphere_marker(
    parent: BlenderObjRef,
    name: str,
    color: tuple[float, float, float, float],
    collection: bpy.types.Collection,
    radius: float = 0.02,
) -> BlenderObjRef:
    """Creates a new UV sphere object to be used as a 3D marker."""
    parent_obj = parent._get_obj()
    if not parent_obj:
        raise ValueError(f"Parent object with ID {parent._id} not found.")

    # Create a UV sphere mesh and object
    bpy.ops.mesh.primitive_uv_sphere_add(radius=radius, location=(0, 0, 0), segments=16, ring_count=8)
    marker_obj = bpy.context.active_object
    marker_obj.name = f"{parent_obj.name}_{name}"

    # Create a simple material with the given color
    mat = bpy.data.materials.new(name=f"Mat_{marker_obj.name}")
    mat.use_nodes = False
    mat.diffuse_color = color
    marker_obj.data.materials.append(mat)

    # Link to collection and set parent
    if collection:
        # Unlink from default scene collection if necessary
        if marker_obj.name in bpy.context.scene.collection.objects:
            bpy.context.scene.collection.objects.unlink(marker_obj)
        collection.objects.link(marker_obj)

    marker_obj.parent = parent_obj
    marker_obj.matrix_parent_inverse.identity()

    return BlenderObjRef(marker_obj.name)


def add_object_driver(
    target_obj_ref: BlenderObjRef,
    data_path: str,
    expression: str,
    variables: list[tuple[str, str, str, str]],
    index: int = -1,
) -> None:
    """Adds a driver to an object property."""
    target_obj = target_obj_ref._get_obj()
    if not target_obj:
        raise ValueError(f"Target object with ID {target_obj_ref._id} not found.")

    driver = target_obj.driver_add(data_path, index).driver
    driver.type = "SCRIPTED"
    driver.expression = expression

    for var_name, var_type, target_id, target_data_path in variables:
        var = driver.variables.new()
        var.name = var_name
        var.type = var_type
        var.targets[0].id = bpy.data.objects.get(target_id)
        var.targets[0].data_path = target_data_path
