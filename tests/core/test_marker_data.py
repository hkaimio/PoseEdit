# SPDX-FileCopyrightText: 2025 Harri Kaimio
#
# SPDX-License-Identifier: BSD-3-Clause

import pytest
from unittest.mock import MagicMock, patch, call
import numpy as np

# Mock the entire dal module before importing MarkerData
# This is a common pattern for testing modules that depend on an unavailable library (like bpy)




@pytest.fixture
def mock_blender_obj_ref():
    """Creates a mock BlenderObjRef."""
    mock_ref = MagicMock()
    mock_ref.name = "MockBlenderObj"
    return mock_ref

@pytest.fixture
def mock_action():
    """Creates a mock Action."""
    return MagicMock()

class TestMarkerData:

    @patch('pose_editor.core.marker_data.dal')
    def test_init(self, mock_dal, mock_blender_obj_ref, mock_action):
        """Test that __init__ calls the DAL correctly to find/create objects."""
        from pose_editor.core.marker_data import MarkerData
        # Arrange
        series_name = "test_series"
        skeleton_name = "test_skeleton"
        mock_dal.get_or_create_object.return_value = mock_blender_obj_ref
        mock_dal.get_or_create_action.return_value = mock_action

        # Act
        md = MarkerData(series_name, skeleton_name)

        # Assert
        assert md.series_name == series_name
        assert md.action_name == f"AC.{series_name}"
        assert md.data_series_object_name == f"DS.{series_name}"
        assert md.skeleton_name == skeleton_name

        mock_dal.get_or_create_object.assert_called_once_with(
            name=f"DS.{series_name}",
            obj_type='EMPTY',
            collection_name='DataSeries'
        )
        mock_dal.get_or_create_action.assert_called_once_with(f"AC.{series_name}")

        # Check that custom properties were set
        expected_calls = [
            call(mock_blender_obj_ref, mock_dal.SERIES_NAME, series_name),
            call(mock_blender_obj_ref, mock_dal.SKELETON, skeleton_name),
            call(mock_blender_obj_ref, mock_dal.ACTION_NAME, f"AC.{series_name}")
        ]
        mock_dal.set_custom_property.assert_has_calls(expected_calls, any_order=True)

    @patch('pose_editor.core.marker_data.dal')
    def test_set_animation_data(self, mock_dal, mock_action):
        """Test that set_animation_data calls the DAL to create fcurves and keyframes."""
        from pose_editor.core.marker_data import MarkerData
        # Arrange
        mock_dal.get_or_create_action.return_value = mock_action
        md = MarkerData("set_data_series")

        # Mock the return value for get_or_create_fcurve
        mock_fcurve = MagicMock()
        mock_dal.get_or_create_fcurve.return_value = mock_fcurve

        # Sample data
        frames = 10
        columns = [('Nose', 'location', 0), ('Nose', 'location', 1)]
        data = np.random.rand(frames, len(columns))
        start_frame = 1

        # Act
        md.set_animation_data(data, columns, start_frame)

        # Assert
        assert mock_dal.get_or_create_fcurve.call_count == len(columns)
        assert mock_dal.set_fcurve_keyframes.call_count == len(columns)

        # Check call for the first column
        mock_dal.get_or_create_fcurve.assert_any_call(
            action=mock_action, 
            slot_name='Nose', 
            data_path='location', 
            index=0
        )
        # Check call for the second column
        mock_dal.get_or_create_fcurve.assert_any_call(
            action=mock_action, 
            slot_name='Nose', 
            data_path='location', 
            index=1
        )

        # Verify that set_fcurve_keyframes was called with the created fcurve
        # and the correctly structured keyframe data
        keyframes_col0 = list(zip(range(start_frame, start_frame + frames), data[:, 0]))
        mock_dal.set_fcurve_keyframes.assert_any_call(mock_fcurve, keyframes_col0)

    @patch('pose_editor.core.marker_data.dal')
    def test_apply_to_view(self, mock_dal, mock_action, mock_blender_obj_ref):
        """Test that apply_to_view correctly assigns the action to child objects."""
        from pose_editor.core.marker_data import MarkerData
        # Arrange
        mock_dal.get_or_create_action.return_value = mock_action
        md = MarkerData("apply_view_series")

        view_root_name = "PV.Test.cam1"
        mock_dal.get_object_by_name.return_value = mock_blender_obj_ref

        # Create mock children for the view root
        child1_ref = MagicMock()
        child1_ref._id = "Nose"
        child1_ref.name = "Nose"
        child2_ref = MagicMock()
        child2_ref._id = "LEye"
        child2_ref.name = "LEye"
        mock_dal.get_children_of_object.return_value = [child1_ref, child2_ref]

        # Simulate that the action has slots for these children
        mock_dal.action_has_slot.return_value = True

        # Act
        md.apply_to_view(view_root_name)

        # Assert
        mock_dal.get_object_by_name.assert_called_once_with(view_root_name)
        mock_dal.get_children_of_object.assert_called_once_with(mock_blender_obj_ref)
        
        # Check that assign_action_to_object was called for each child
        expected_calls = [
            call(child1_ref, mock_action, "Nose"),
            call(child2_ref, mock_action, "LEye")
        ]
        mock_dal.assign_action_to_object.assert_has_calls(expected_calls, any_order=True)