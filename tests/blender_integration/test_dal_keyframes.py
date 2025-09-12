# SPDX-FileCopyrightText: 2025 Harri Kaimio
#
# SPDX-License-Identifier: BSD-3-Clause

import bpy
import pytest
from pose_editor.blender import dal

@pytest.fixture
def setup_blender_scene(request):
    """Set up a clean Blender scene for each test."""
    bpy.ops.wm.read_factory_settings(use_empty=True)

    # Create a cube to animate
    bpy.ops.mesh.primitive_cube_add()
    obj = bpy.context.object
    obj.name = "TestObject"
    
    # Create an action and link it
    action = bpy.data.actions.new("TestAction")
    obj.animation_data_create()
    obj.animation_data.action = action

    # Add some initial keyframes to the X location
    fcurve = action.fcurves.new(data_path="location", index=0)
    fcurve.keyframe_points.insert(1, 1.0)
    fcurve.keyframe_points.insert(10, 10.0)
    fcurve.keyframe_points.insert(20, 20.0)
    fcurve.keyframe_points.insert(30, 30.0)
    fcurve.update()

    return obj, fcurve


def test_get_fcurve_keyframes_in_range(setup_blender_scene):
    # Arrange
    obj, fcurve = setup_blender_scene

    # Act
    keyframes = dal.get_fcurve_keyframes_in_range(fcurve, 9, 21)

    # Assert
    assert len(keyframes) == 2
    assert keyframes[0] == (10.0, 10.0)
    assert keyframes[1] == (20.0, 20.0)


def test_get_fcurve_keyframes_in_range_no_match(setup_blender_scene):
    # Arrange
    obj, fcurve = setup_blender_scene

    # Act
    keyframes = dal.get_fcurve_keyframes_in_range(fcurve, 100, 200)

    # Assert
    assert len(keyframes) == 0


def test_replace_fcurve_keyframes_in_range(setup_blender_scene):
    # Arrange
    obj, fcurve = setup_blender_scene
    new_kps = [(12.0, 120.0), (18.0, 180.0)]

    # Act
    dal.replace_fcurve_keyframes_in_range(fcurve, 10, 20, new_kps)
    all_keyframes = dal.get_fcurve_keyframes(fcurve)

    # Assert
    assert len(all_keyframes) == 4
    # Check that the old keyframes at 10 and 20 are gone
    assert (10.0, 10.0) not in all_keyframes
    assert (20.0, 20.0) not in all_keyframes
    # Check that the new keyframes are present
    assert (12.0, 120.0) in all_keyframes
    assert (18.0, 180.0) in all_keyframes
    # Check that the keyframes outside the range are untouched
    assert (1.0, 1.0) in all_keyframes
    assert (30.0, 30.0) in all_keyframes
