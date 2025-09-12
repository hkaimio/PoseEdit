# SPDX-FileCopyrightText: 2025 Harri Kaimio
#
# SPDX-License-Identifier: BSD-3-Clause

import pytest
from unittest.mock import MagicMock, patch, call

# By patching the dal module where it is imported, we can control its behavior
# for all classes that use it, like RealPersonInstanceFacade and MarkerData.

@pytest.fixture
def mock_skeleton():
    """Creates a mock SkeletonBase object with a simple hierarchy."""
    from anytree import Node
    mock_skeleton = MagicMock()
    from anytree import Node
    mock_skeleton = MagicMock()
    mock_skeleton._skeleton = Node("COCO-133", id=-1, children=[
        Node("Nose", id=0),
        Node("LEye", id=1)
    ])
    return mock_skeleton
    return mock_skeleton

@patch('pose_editor.core.person_facade.dal', autospec=True)
def test_find_next_stitch_frame(mock_dal):
    """Tests that the next keyframe is correctly identified."""
    from pose_editor.core.person_facade import RealPersonInstanceFacade

    # Arrange
    person_ref = MagicMock()
    person_ref.name = "Alice"
    facade = RealPersonInstanceFacade(person_ref)

    mock_dal.get_object_by_name.return_value = MagicMock() # Ensure ds_obj is not None
    mock_dal.get_fcurve_on_object.return_value = MagicMock()
    mock_dal.get_fcurve_keyframes.return_value = [(1.0, 0.0), (50.0, 1.0), (100.0, 2.0)]
    mock_dal.get_scene_frame_range.return_value = (1, 250)

    # Act
    next_frame = facade.find_next_stitch_frame("cam1", 50)

    # Assert
    assert next_frame == 99 # The segment should end the frame before the next keyframe

@patch('pose_editor.core.person_facade.dal', autospec=True)
def test_find_next_stitch_frame_no_future_keys(mock_dal):
    """Tests that the scene end frame is used when no future keyframes exist."""
    from pose_editor.core.person_facade import RealPersonInstanceFacade

    # Arrange
    person_ref = MagicMock()
    person_ref.name = "Alice"
    facade = RealPersonInstanceFacade(person_ref)

    mock_dal.get_object_by_name.return_value = MagicMock()
    mock_dal.get_fcurve_on_object.return_value = MagicMock()
    mock_dal.get_fcurve_keyframes.return_value = [(1.0, 0.0), (50.0, 1.0)]
    mock_dal.get_scene_frame_range.return_value = (1, 250)

    # Act
    next_frame = facade.find_next_stitch_frame("cam1", 50)

    # Assert
    assert next_frame == 250

# Patch dal in both modules that use it to ensure they both get the same mock
@patch('pose_editor.core.marker_data.dal', new_callable=MagicMock)
@patch('pose_editor.core.person_facade.dal', new_callable=MagicMock)
def test_assign_source_track_for_segment(mock_dal, mock_marker_dal, mock_skeleton):
    """Tests the main orchestration logic of the stitching process."""
    # Ensure both patches use the same mock object
    mock_dal.get_or_create_action = mock_marker_dal.get_or_create_action

    from pose_editor.core.person_facade import RealPersonInstanceFacade

    # Arrange
    person_ref = MagicMock()
    person_ref.name = "Alice"
    facade = RealPersonInstanceFacade(person_ref)
    
    start_frame = 50
    source_track_index = 3
    view_name = "cam1"

    # Mock the return values of helper methods and DAL calls
    facade.find_next_stitch_frame = MagicMock(return_value=99)
    
    mock_numpy_data = MagicMock()
    mock_dal.get_animation_data_as_numpy.return_value = mock_numpy_data

    # Have get_or_create_action return a mock with a name for clarity in debugging
    mock_action = MagicMock()
    mock_dal.get_or_create_action.return_value = mock_action

    # Act
    facade.assign_source_track_for_segment(view_name, source_track_index, start_frame, mock_skeleton)

    # Assert
    # 1. Check that we determined the end frame
    facade.find_next_stitch_frame.assert_called_once_with(view_name, start_frame)

    # 2. Check that MarkerData tried to create the correct actions
    mock_dal.get_or_create_action.assert_has_calls([
        call('AC.Alice.cam1'),
        call('AC.cam1_person3')
    ])

    # 3. Check that we got the source data from the correct action
    mock_dal.get_animation_data_as_numpy.assert_called_once()
    call_args = mock_dal.get_animation_data_as_numpy.call_args[0]
    assert call_args[0] == mock_action # Check it's the action returned by the mock dal
    assert len(call_args[1]) == 6 # 2 joints * 3 channels (X, Y, Quality)
    assert call_args[2] == start_frame
    assert call_args[3] == 99

    # 4. Check that we wrote the data to the target action
    mock_dal.set_fcurves_from_numpy.assert_called_once_with(
        mock_action, 
        call_args[1], # Should be the same columns
        start_frame, 
        mock_numpy_data
    )

    # 5. Check that we set the keyframe for the index property
    mock_dal.add_keyframe.assert_called_once()
    keyframe_args, _ = mock_dal.add_keyframe.call_args
    assert keyframe_args[1] == start_frame
    assert '["active_track_index"]' in keyframe_args[2]
    assert keyframe_args[2]['["active_track_index"]'][0] == source_track_index
