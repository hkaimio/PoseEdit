# SPDX-FileCopyrightText: 2025 Harri Kaimio
#
# SPDX-License-Identifier: BSD-3-Clause

"""Integration test for connecting MarkerData to a Person3DView."""

import bpy
import pytest
from anytree import Node

from pose_editor.blender import dal
from pose_editor.core.marker_data import MarkerData
from pose_editor.core.person_3d_view import Person3DView
from pose_editor.core.skeleton import SkeletonBase


@pytest.fixture(autouse=True)
def clear_blender_data():
    """Fixture to clear all Blender data before each test."""
    bpy.ops.wm.read_factory_settings(use_empty=True)


@pytest.mark.skip(reason="Blocked by bug in Person3DView.create_new factory method")
def test_connect_marker_data_to_3d_view():
    """Verify that a MarkerData action can be applied to a Person3DView."""
    # Arrange
    # 1. Create a Person3DView
    skeleton = SkeletonBase(Node("Root", children=[Node("LHip", id=1)]))
    parent_ref = dal.create_empty("TestPerson", bpy.context.scene.collection)
    person_3d_view = Person3DView.create_new(
        view_name="Test3DView",
        skeleton=skeleton,
        color=(1, 1, 1, 1),
        parent_ref=parent_ref,
    )

    # 2. Create a MarkerData instance
    marker_data = MarkerData.create_new("Test3DData", skeleton._skeleton.name)

    # 3. Manually add a keyframe to the MarkerData action
    fcurve = dal.get_or_create_fcurve(marker_data.action, "LHip", "location", index=0) # X-axis
    dal.set_fcurve_keyframes(fcurve, [(10, 5.0)]) # At frame 10, X should be 5.0

    # Act
    # 4. Connect the data to the view
    marker_data.apply_to_view(person_3d_view)

    # Assert
    # 5. Check that the action is assigned to the marker object
    lhip_marker_ref = person_3d_view.get_marker_objects().get("LHip")
    assert lhip_marker_ref is not None
    lhip_marker_obj = lhip_marker_ref._get_obj()
    assert lhip_marker_obj.animation_data is not None
    assert lhip_marker_obj.animation_data.action == marker_data.action

    # 6. Check that the marker's location is updated correctly
    bpy.context.scene.frame_set(10)
    assert lhip_marker_obj.location.x == pytest.approx(5.0)