# SPDX-FileCopyrightText: 2025 Harri Kaimio
#
# SPDX-License-Identifier: BSD-3-Clause

"""Integration tests for the dal3d module."""

import bpy
import pytest

from pose_editor.blender import dal, dal3d


@pytest.fixture(autouse=True)
def clear_blender_data():
    """Fixture to clear all Blender data before each test."""
    bpy.ops.wm.read_factory_settings(use_empty=True)


def test_create_sphere_marker():
    """Test that create_sphere_marker creates a sphere with the correct properties."""
    # Arrange
    parent_obj = dal.create_empty(name="TestParent", collection=bpy.context.scene.collection)
    color = (0.8, 0.2, 0.1, 1.0)

    # Act
    marker_ref = dal3d.create_sphere_marker(
        parent=parent_obj,
        name="TestSphere",
        color=color,
        collection=bpy.context.scene.collection,
        radius=0.5,
    )
    marker_obj = marker_ref._get_obj()

    # Assert
    assert marker_obj is not None
    assert marker_obj.type == "MESH"
    assert "TestSphere" in marker_obj.name
    assert marker_obj.parent == parent_obj._get_obj()
    assert len(marker_obj.data.materials) > 0
    assert tuple(marker_obj.data.materials[0].diffuse_color[:3]) == pytest.approx(color[:3])
    assert marker_obj.dimensions.x == pytest.approx(1.0) # Diameter


def test_add_object_driver():
    """Test that add_object_driver correctly creates a driver and variables."""
    # Arrange
    source1 = dal.create_empty(name="Source1", collection=bpy.context.scene.collection)
    source2 = dal.create_empty(name="Source2", collection=bpy.context.scene.collection)
    target = dal.create_empty(name="Target", collection=bpy.context.scene.collection)

    source1._get_obj().location.x = 10.0
    source2._get_obj().location.x = 20.0

    expression = "(var1 + var2) / 2"
    variables = [
        ("var1", "TRANSFORMS", source1.name, "location.x"),
        ("var2", "TRANSFORMS", source2.name, "location.x"),
    ]

    # Act
    dal3d.add_object_driver(target, "location", expression, variables, index=0)

    # Assert
    # Check driver exists
    driver = target._get_obj().animation_data.drivers.find("location", index=0)
    assert driver is not None
    assert driver.driver.expression == expression
    assert len(driver.driver.variables) == 2
    assert driver.driver.variables[0].name == "var1"
    assert driver.driver.variables[1].targets[0].id == source2._get_obj()

    # Check if the driver works
    bpy.context.view_layer.update()
    assert target._get_obj().location.x == pytest.approx(15.0)

    # Check if it updates
    source1._get_obj().location.x = 30.0
    bpy.context.view_layer.update()
    assert target._get_obj().location.x == pytest.approx(25.0)