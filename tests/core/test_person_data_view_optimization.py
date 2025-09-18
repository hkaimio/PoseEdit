# SPDX-FileCopyrightText: 2025 Harri Kaimio
#
# SPDX-License-Identifier: BSD-3-Clause

from unittest.mock import MagicMock, patch, ANY

from pose_editor.core.person_data_view import PersonDataView, SKELETON_NAME
from pose_editor.core.person_facade import POSE_EDITOR_OBJECT_TYPE, PERSON_DEFINITION_REF


@patch("pose_editor.core.person_facade.dal")
@patch("pose_editor.core.person_data_view.dal")
@patch("pose_editor.core.person_data_view.frame_handler")
@patch("pose_editor.core.person_data_view.get_skeleton")
@patch("pose_editor.core.person_data_view.PersonDataView.get_data_series")
def test_create_new_real_person_view_registers_handler_and_inits_props(
    mock_get_data_series, mock_get_skeleton, mock_frame_handler, mock_pdv_dal, mock_facade_dal
):
    """Test that creating a Real Person view registers with the frame handler
    and initializes the required animated properties.
    """
    # Arrange
    # Configure both dal mocks. They are separate objects.
    mock_pdv_dal.get_scene_frame_range.return_value = (1, 10)
    mock_facade_dal.get_scene_frame_range.return_value = (1, 10)

    mock_person_facade = MagicMock()
    mock_person_facade.obj.name = "PI.Alice"
    mock_person_facade.obj._id = "<person_id>"

    mock_camera_view = MagicMock()
    mock_camera_view.name = "View_cam1"
    mock_marker_data = MagicMock()
    mock_marker_data.obj_ref.name = "MD.Alice.cam1"
    mock_get_data_series.return_value = mock_marker_data

    # This is the object that will be created for the PersonDataView
    mock_pdv_obj = mock_pdv_dal.get_or_create_object.return_value
    mock_pdv_obj.name = "PV.Alice.cam1"

    # This is what get_by_id will find, leading to the RealPersonInstanceFacade
    mock_facade_dal.find_object_by_property.return_value = mock_person_facade.obj

    # Configure the dal mock to handle get_person() correctly
    def get_prop_side_effect(obj_ref, prop, default=None):
        # When get_person() is called on the PersonDataView instance,
        # it asks for the person ref from its own object.
        if obj_ref == mock_pdv_obj and prop == PERSON_DEFINITION_REF:
            return mock_person_facade.obj._id

        # When RealPersonInstanceFacade.from_blender_obj is called,
        # it asks for the object type from the person object.
        if obj_ref == mock_person_facade.obj and prop == POSE_EDITOR_OBJECT_TYPE:
            return "Person"

        # Any other call
        return MagicMock()

    mock_pdv_dal.get_custom_property.side_effect = get_prop_side_effect
    mock_facade_dal.get_custom_property.side_effect = get_prop_side_effect

    # Act
    pdv = PersonDataView.create_new(
        view_name="PV.Alice.cam1",
        skeleton=MagicMock(),
        color=(1, 0, 0, 1),
        camera_view=mock_camera_view,
        person=mock_person_facade,
    )

    # Assert
    # 1. Check that it registered with the frame handler
    mock_frame_handler.add_callback.assert_called_once_with(pdv._check_and_update_frame)

    # 2. Check that requested_source_id was initialized with one keyframe
    mock_pdv_dal.set_custom_property.assert_any_call(mock_marker_data.obj_ref, ANY, -1)
    mock_pdv_dal.add_keyframe.assert_any_call(mock_marker_data.obj_ref, 1, {'["requested_source_id"]': [-1]})

    # 3. Check that applied_source_id was initialized with dense keyframes
    expected_keyframes = [(i, [-1]) for i in range(1, 11)]
    mock_pdv_dal.set_fcurve_from_data.assert_called_once_with(
        mock_marker_data.obj_ref, '["applied_source_id"]', expected_keyframes
    )


@patch("pose_editor.core.person_data_view.dal")
@patch("pose_editor.core.person_data_view.frame_handler")
@patch("pose_editor.core.person_data_view.get_skeleton")
def test_create_new_raw_person_view_does_not_register_handler(
    mock_get_skeleton, mock_frame_handler, mock_dal
):
    """Test that creating a raw track view does NOT register with the frame handler."""
    # Arrange
    mock_camera_view = MagicMock()
    mock_camera_view.name = "View_cam1"

    # Act
    PersonDataView.create_new(
        view_name="PV.cam1_person0",
        skeleton=MagicMock(),
        color=(1, 0, 0, 1),
        camera_view=mock_camera_view,
        person=None,  # This is the key difference: it's a raw track
    )

    # Assert
    mock_frame_handler.add_callback.assert_not_called()
