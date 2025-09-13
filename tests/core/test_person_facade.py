# SPDX-FileCopyrightText: 2025 Harri Kaimio
#
# SPDX-License-Identifier: BSD-3-Clause

from unittest.mock import MagicMock, patch

import pytest
import numpy as np
from anytree import Node

from pose_editor.core.marker_data import MarkerData


# By patching the dal module where it is imported, we can control its behavior
# for all classes that use it, like RealPersonInstanceFacade and MarkerData.


@pytest.fixture
def mock_skeleton():
    """Creates a mock SkeletonBase object with a simple hierarchy."""
    mock_skeleton = MagicMock()
    mock_skeleton._skeleton = Node("COCO-133", id=-1, children=[Node("Nose", id=0), Node("LEye", id=1)])
    return mock_skeleton


@patch("pose_editor.core.person_facade.dal", autospec=True)
def test_find_next_stitch_frame(mock_dal):
    """Tests that the next keyframe is correctly identified."""
    from pose_editor.core.person_facade import RealPersonInstanceFacade

    # Arrange
    person_ref = MagicMock()
    person_ref.name = "Alice"
    facade = RealPersonInstanceFacade(person_ref)

    mock_dal.get_object_by_name.return_value = MagicMock()  # Ensure ds_obj is not None
    mock_dal.get_fcurve_on_object.return_value = MagicMock()
    mock_dal.get_fcurve_keyframes.return_value = [(1.0, 0.0), (50.0, 1.0), (100.0, 2.0)]
    mock_dal.get_scene_frame_range.return_value = (1, 250)

    # Act
    next_frame = facade.find_next_stitch_frame("cam1", 50)

    # Assert
    assert next_frame == 99  # The segment should end the frame before the next keyframe


@patch("pose_editor.core.person_facade.dal", autospec=True)
def test_find_next_stitch_frame_no_future_keys(mock_dal):
    """Tests that the scene end frame is used when no future keyframes exist."""
    from pose_editor.core.person_facade import RealPersonInstanceFacade

    # Arrange
    person_ref = MagicMock()
    person_ref.name = "Alice"
    view_name = "cam1"
    facade = RealPersonInstanceFacade(person_ref)

    mock_dal.get_object_by_name.return_value = MagicMock()
    mock_dal.get_fcurve_on_object.return_value = MagicMock()
    mock_dal.get_fcurve_keyframes.return_value = [(1.0, 0.0), (50.0, 1.0)]
    mock_dal.get_scene_frame_range.return_value = (1, 250)

    # Act
    next_frame = facade.find_next_stitch_frame("cam1", 50)

    # Assert
    assert next_frame == 250

    # Mock dal.get_or_create_object to prevent TypeError when setting parent
    mock_blender_obj_ref_with_parent = MagicMock()
    mock_blender_obj_ref_with_parent._get_obj.return_value = MagicMock()
    mock_blender_obj_ref_with_parent._get_obj().parent = MagicMock()  # Allow parent to be set
    mock_dal.get_or_create_object.return_value = mock_blender_obj_ref_with_parent

    # Mock dal.get_object_by_name to return a mock BlenderObjRef with custom properties
    mock_pv_root_obj_ref = MagicMock()
    mock_pv_root_obj_ref.name = f"PV.{person_ref.name}.{view_name}"
    mock_pv_root_obj_ref._get_obj.return_value = MagicMock()
    mock_pv_root_obj_ref._get_obj().get.side_effect = (
        lambda prop: "PersonDataView" if prop == mock_dal.POSE_EDITOR_OBJECT_TYPE else None
    )
    mock_dal.get_object_by_name.return_value = mock_pv_root_obj_ref

    mock_dal.get_or_create_object.return_value = mock_blender_obj_ref_with_parent




@patch("pose_editor.core.person_facade.dal", autospec=True)
@patch("pose_editor.blender.dal.CustomProperty", autospec=True)
@patch("pose_editor.core.person_facade.MarkerData") # Remove autospec for now, will manually mock instances
@patch("pose_editor.core.person_facade.PersonDataView", autospec=True)
@patch("pose_editor.core.person_facade.RealPersonInstanceFacade._get_dataseries_for_view")
@patch("pose_editor.core.person_facade.RealPersonInstanceFacade.find_next_stitch_frame")
def test_assign_source_track_for_segment_preserves_outside_keyframes(
    mock_find_next_stitch_frame,
    mock_get_dataseries_for_view,
    mock_person_data_view,
    mock_marker_data,
    mock_custom_proeprty,
    mock_dal,
    mock_skeleton,
):
    """Tests that assign_source_track_for_segment correctly replaces keyframes
    within a segment while preserving keyframes outside of it.
    """
    from pose_editor.core.person_facade import RealPersonInstanceFacade, ACTIVE_TRACK_INDEX

    # Arrange
    person_ref = MagicMock()
    person_ref.name = "Alice"
    view_name = "cam1"
    facade = RealPersonInstanceFacade(person_ref)

    # Mock _get_dataseries_for_view
    mock_ds_obj = MagicMock()
    mock_dal.get_object_by_name = MagicMock()
    mock_dal.get_object_by_name.return_value = mock_ds_obj
    mock_get_dataseries_for_view.return_value = mock_ds_obj

    # Mock find_next_stitch_frame
    start_frame = 20
    end_frame = 30
    mock_find_next_stitch_frame.return_value = end_frame # Use the new mock

    # Explicitly define mock actions
    mock_source_action = MagicMock()
    mock_target_action = MagicMock()

    # Create specific mock instances for source and target MarkerData
    mock_source_md_instance = MagicMock(action=mock_source_action) # Assign action here
    mock_target_md_instance = MagicMock(action=mock_target_action) # Assign action here

    # Configure MarkerData to return these specific instances
    # The first call to MarkerData will be for the target, the second for the source
    mock_marker_data.from_blender_object = MagicMock()
    mock_marker_data.from_blender_object.side_effect = [mock_target_md_instance, mock_source_md_instance]

    # Mock get_animation_data_as_numpy to return some source data
    source_data_np = np.array([[10.0, 11.0], [12.0, 13.0], [14.0, 15.0], [16.0, 17.0], [18.0, 19.0], [20.0, 21.0], [22.0, 23.0], [24.0, 25.0], [26.0, 27.0], [28.0, 29.0], [30.0, 31.0]]) # 11 frames (20 to 30 inclusive)
    mock_dal.get_animation_data_as_numpy = MagicMock()
    mock_dal.get_animation_data_as_numpy.return_value = source_data_np

    # Mock get_or_create_fcurve to return a unique mock fcurve for each call
    mock_fcurve_nose_loc_x = MagicMock()
    mock_fcurve_nose_loc_y = MagicMock()
    mock_fcurve_nose_quality = MagicMock()
    mock_fcurve_leye_loc_x = MagicMock()
    mock_fcurve_leye_loc_y = MagicMock()
    mock_fcurve_leye_quality = MagicMock()

    mock_dal.get_or_create_fcurve = MagicMock()
    mock_dal.get_or_create_fcurve.side_effect = [
        mock_fcurve_nose_loc_x,
        mock_fcurve_nose_loc_y,
        mock_fcurve_nose_quality,
        mock_fcurve_leye_loc_x,
        mock_fcurve_leye_loc_y,
        mock_fcurve_leye_quality,
    ]

    # Act
    facade.assign_source_track_for_segment(
        view_name, 1, start_frame, mock_skeleton
    )

    # Assert
    # Verify get_animation_data_as_numpy was called correctly
    mock_dal.get_animation_data_as_numpy.assert_called_once_with(
        mock_source_action,
        [
            ("Nose", "location", 0),
            ("Nose", "location", 1),
            ("Nose", '["quality"]', -1),
            ("LEye", "location", 0),
            ("LEye", "location", 1),
            ("LEye", '["quality"]', -1),
        ],
        start_frame,
        end_frame,
    )

    # Verify replace_fcurve_segment_from_numpy was called
    mock_dal.replace_fcurve_segment_from_numpy.assert_called_once_with(
        mock_target_action,
        [
            ("Nose", "location", 0),
            ("Nose", "location", 1),
            ("Nose", '["quality"]', -1),
            ("LEye", "location", 0),
            ("LEye", "location", 1),
            ("LEye", '["quality"]', -1),
        ],
        start_frame,
        end_frame,
        source_data_np,
    )

    # Verify active_track_index keyframe was set
    mock_dal.set_custom_property.assert_called_once_with(
        mock_ds_obj, ACTIVE_TRACK_INDEX, 1
    )
    mock_dal.add_keyframe.assert_called_once_with(
        mock_ds_obj, start_frame, {'["active_track_index"]': [1]}
    )

    # Verify PersonDataView reconnection
    mock_person_data_view.from_blender_object.assert_called_once()
    mock_target_md_instance.apply_to_view.assert_called_once()
