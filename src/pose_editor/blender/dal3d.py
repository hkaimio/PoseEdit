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
    variables: list[tuple[str, str, str, str, str]],
    index: int = -1,
) -> None:
    """Adds a driver to an object property.

    Args:
        target_obj_ref: The object to add the driver to.
        data_path: The property to be driven (e.g., "location").
        expression: The driver expression.
        variables: A list of tuples, where each tuple defines a driver variable:
                   (var_name, var_type, target_id, data_path, transform_type)
        index: The array index for vector properties (0=X, 1=Y, 2=Z).
    """
    target_obj = target_obj_ref._get_obj()
    if not target_obj:
        raise ValueError(f"Target object with ID {target_obj_ref._id} not found.")

    driver = target_obj.driver_add(data_path, index).driver
    driver.type = "SCRIPTED"
    driver.expression = expression

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
    """Adds a driver to an object property, based on the working example.

    Args:
        target_obj_ref: The object to add the driver to.
        data_path: The property to be driven (e.g., "location").
        expression: The driver expression.
        variables: A list of tuples, where each tuple defines a driver variable:
                   (var_name, var_type, target_id, transform_type)
        index: The array index for vector properties (0=X, 1=Y, 2=Z).
    """
    target_obj = target_obj_ref._get_obj()
    if not target_obj:
        raise ValueError(f"Target object with ID {target_obj_ref._id} not found.")

    fcurve = target_obj.driver_add(data_path, index)
    driver = fcurve.driver
    driver.type = "SCRIPTED"
    driver.expression = expression

    # Clear any existing variables to ensure a clean slate
    for var in driver.variables:
        driver.variables.remove(var)

    # Add and configure new variables based on the working pattern
    for var_name, var_type, target_id, transform_type in variables:
        var = driver.variables.new()
        var.name = var_name
        var.type = var_type

        target = var.targets[0]
        target.id = bpy.data.objects.get(target_id)
        if var.type == "TRANSFORMS":
            target.transform_type = transform_type
            target.transform_space = "WORLD_SPACE"
        # Note: We intentionally do not set target.data_path for TRANSFORMS type
        # as this was found to be the cause of the issue.


def add_midpoint_driver(
    target_obj_ref: BlenderObjRef, source_a_ref: BlenderObjRef, source_b_ref: BlenderObjRef
) -> None:
    """Adds a driver to compute the midpoint between two source objects."""
    target_obj = target_obj_ref._get_obj()
    source_a = source_a_ref._get_obj()
    source_b = source_b_ref._get_obj()

    if not all([target_obj, source_a, source_b]):
        print("Warning: Could not create midpoint driver, one or more objects not found.")
        return

    # Add drivers to X, Y, Z location of the target object
    for i, axis in enumerate(["LOC_X", "LOC_Y", "LOC_Z"]):
        fcurve = target_obj.driver_add("location", i)
        driver = fcurve.driver
        driver.type = "SCRIPTED"

        # Clear existing variables
        for var in driver.variables:
            driver.variables.remove(var)

        # Variable for source_a
        var_a = driver.variables.new()
        var_a.name = "a"
        var_a.type = "TRANSFORMS"
        var_a.targets[0].id = source_a
        var_a.targets[0].transform_type = axis
        var_a.targets[0].transform_space = "WORLD_SPACE"

        # Variable for source_b
        var_b = driver.variables.new()
        var_b.name = "b"
        var_b.type = "TRANSFORMS"
        var_b.targets[0].id = source_b
        var_b.targets[0].transform_type = axis
        var_b.targets[0].transform_space = "WORLD_SPACE"

        # Expression to compute midpoint
        driver.expression = "(a + b) / 2"
