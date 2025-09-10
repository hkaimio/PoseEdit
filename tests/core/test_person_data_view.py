# SPDX-FileCopyrightText: 2025 Harri Kaimio
#
# SPDX-License-Identifier: BSD-3-Clause

import pytest
from unittest.mock import MagicMock, patch, call
from anytree import Node

# Mock the dal module before importing the class to be tested
@pytest.fixture(autouse=True)
def mock_dal_module():
    with patch.dict('sys.modules', {'pose_editor.blender.dal': MagicMock()}):
        yield

@pytest.fixture
def mock_skeleton():
    """Creates a mock SkeletonBase object with a simple hierarchy."""
    root = Node("RootNode", id=-1)
    nose = Node("Nose", parent=root, id=0)
    leye = Node("LEye", parent=root, id=1)
    mock = MagicMock()
    mock._skeleton = root
    return mock

@pytest.fixture
def mock_marker_data():
    """Creates a mock MarkerData object."""
    return MagicMock()

@pytest.fixture
def mock_blender_obj_ref():
    """Creates a mock Blender object reference."""
    mock_ref = MagicMock()
    mock_ref.name = "MockBlenderObj"
    return mock_ref

class TestPersonDataView:

    @patch('pose_editor.core.person_data_view.dal')
    def test_init_creates_objects_and_armature(self, mock_dal, mock_skeleton, mock_blender_obj_ref):
        """Test that __init__ creates the root empty, markers, and armature."""
        from pose_editor.core.person_data_view import PersonDataView

        # Arrange
        view_name = "PV.Test.cam1"
        marker_color = (0.1, 0.2, 0.3, 1.0)
        mock_dal.get_or_create_object.return_value = mock_blender_obj_ref

        mock_root_marker_ref = MagicMock()
        mock_root_marker_ref.name = "RootNode_marker_obj"
        mock_nose_marker_ref = MagicMock()
        mock_nose_marker_ref.name = "Nose_marker_obj"
        mock_leye_marker_ref = MagicMock()
        mock_leye_marker_ref.name = "LEye_marker_obj"
        mock_dal.get_children_of_object.return_value = [mock_root_marker_ref, mock_nose_marker_ref, mock_leye_marker_ref]

        def get_prop_se(obj_ref, prop):
            if obj_ref.name == "RootNode_marker_obj":
                return "RootNode"
            if obj_ref.name == "Nose_marker_obj":
                return "Nose"
            return "LEye"
        mock_dal.get_custom_property.side_effect = get_prop_se

        # Act
        view = PersonDataView(view_name, mock_skeleton, color=marker_color)

        # Assert
        # Check root object creation
        mock_dal.get_or_create_object.assert_any_call(
            name=view_name,
            obj_type='EMPTY',
            collection_name='PersonViews'
        )

        # Check marker creation
        assert mock_dal.create_marker.call_count == 3

        # Check armature creation
        armature_name = f"{view_name}_Armature"
        mock_dal.get_or_create_object.assert_any_call(
            name=armature_name,
            obj_type='ARMATURE',
            collection_name='PersonViews',
            parent=mock_blender_obj_ref
        )
        mock_dal.set_armature_display_stick.assert_called_once()

        # Check bone and constraint creation
        assert mock_dal.add_bone.call_count == 2
        assert mock_dal.add_bone_constraint.call_count == 4 # 2 bones * 2 constraints
        assert mock_dal.add_bone_constraint.call_count == 4 # 2 bones * 2 constraints

    @patch('pose_editor.core.person_data_view.dal')
    def test_connect_to_series(self, mock_dal, mock_skeleton, mock_marker_data):
        """Test that connect_to_series calls apply_to_view on the marker data object."""
        from pose_editor.core.person_data_view import PersonDataView

        # Arrange
        view_name = "PV.Test.cam1"
        marker_color = (0.1, 0.2, 0.3, 1.0)
        mock_dal.get_or_create_object.return_value = MagicMock()

        mock_nose_marker_ref = MagicMock()
        mock_nose_marker_ref.name = "Nose_marker_obj"
        mock_leye_marker_ref = MagicMock()
        mock_leye_marker_ref.name = "LEye_marker_obj"
        mock_dal.get_children_of_object.return_value = [mock_nose_marker_ref, mock_leye_marker_ref]
        mock_dal.get_custom_property.side_effect = lambda obj_ref, prop: "Nose" if obj_ref.name == "Nose_marker_obj" else "LEye"

        view = PersonDataView(view_name, mock_skeleton, color=marker_color)

        # Act
        view.connect_to_series(mock_marker_data)

        # Assert
        mock_marker_data.apply_to_view.assert_called_once_with(view)

    @patch('pose_editor.core.person_data_view.dal')
    def test_get_marker_objects(self, mock_dal, mock_skeleton, mock_blender_obj_ref):
        """Test that get_marker_objects returns the internally stored dictionary."""
        from pose_editor.core.person_data_view import PersonDataView

        # Arrange
        view_name = "PV.Test.cam1"
        marker_color = (0.1, 0.2, 0.3, 1.0)
        mock_dal.get_or_create_object.return_value = mock_blender_obj_ref

        mock_nose_marker_ref = MagicMock()
        mock_nose_marker_ref.name = "Nose_marker_obj"
        mock_leye_marker_ref = MagicMock()
        mock_leye_marker_ref.name = "LEye_marker_obj"
        mock_dal.get_children_of_object.return_value = [mock_nose_marker_ref, mock_leye_marker_ref]
        mock_dal.get_custom_property.side_effect = lambda obj_ref, prop: "Nose" if obj_ref.name == "Nose_marker_obj" else "LEye"

        view = PersonDataView(view_name, mock_skeleton, color=marker_color)

        # Act
        marker_objects_dict = view.get_marker_objects()

        # Assert
        assert marker_objects_dict == {
            "Nose": mock_nose_marker_ref,
            "LEye": mock_leye_marker_ref
        }
        mock_dal.get_children_of_object.assert_called_once()

