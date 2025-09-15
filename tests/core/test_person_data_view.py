# SPDX-FileCopyrightText: 2025 Harri Kaimio
#
# SPDX-License-Identifier: BSD-3-Clause

from unittest.mock import MagicMock, patch

from anytree import Node
import pytest

from pose_editor.core.person_data_view import PersonDataView
from pose_editor.core.person_facade import RealPersonInstanceFacade

# Mock the dal module before importing the class to be tested
@pytest.fixture(autouse=True)
def mock_dal_module():
    with patch.dict("sys.modules", {"pose_editor.blender.dal": MagicMock()}):
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



@patch("pose_editor.core.person_data_view.dal")
@patch("pose_editor.core.person_facade.RealPersonInstanceFacade")
def test_get_person_returns_facade(mock_facade_cls, mock_dal):
    # Arrange
    mock_obj = MagicMock()
    mock_dal.get_custom_property.return_value = "person_123"
    mock_facade_instance = MagicMock()
    mock_facade_instance.person_id = "person_123"
    # Patch get_by_id to return our instance
    mock_facade_cls.get_by_id.return_value = mock_facade_instance

    pdv = PersonDataView(mock_obj)

    # Act
    result = pdv.get_person()

    # Assert
    assert result == mock_facade_instance
    mock_facade_cls.get_by_id.assert_called_once_with("person_123")

@patch("pose_editor.core.person_data_view.dal")
@patch("pose_editor.core.person_facade.RealPersonInstanceFacade")
def test_get_person_returns_none_if_not_assigned(mock_facade_cls, mock_dal):
    # Arrange
    mock_obj = MagicMock()
    mock_dal.get_custom_property.return_value = None

    pdv = PersonDataView(mock_obj)

    # Act
    result = pdv.get_person()

    # Assert
    assert result is None
    mock_facade_cls.get_all.assert_not_called()

@patch("pose_editor.core.person_data_view.dal")
@patch("pose_editor.core.person_facade.RealPersonInstanceFacade")
def test_get_person_returns_none_if_id_not_found(mock_facade_cls, mock_dal):
    # Arrange
    mock_obj = MagicMock()
    mock_dal.get_custom_property.return_value = "person_999"
    mock_facade_cls.get_by_id.return_value = None  # <-- Ensure returns None

    pdv = PersonDataView(mock_obj)

    # Act
    result = pdv.get_person()

    # Assert
    assert result is None
    mock_dal.get_custom_property.assert_called()
    mock_facade_cls.get_by_id.assert_called_once_with("person_999")
class TestPersonDataView:
    @patch("pose_editor.core.person_data_view.dal")
    def test_init_creates_objects_and_armature(self, mock_dal, mock_skeleton, mock_blender_obj_ref):
        """Test that __init__ creates the root empty, markers, and armature."""
        from pose_editor.core.person_data_view import PersonDataView

        # Arrange
        view_name = "PV.Test.cam1"
        marker_color = (0.1, 0.2, 0.3, 1.0)

        mock_collection = MagicMock()
        mock_collection.name = "PersonViews"
        mock_dal.get_or_create_collection.return_value = mock_collection

        mock_dal.get_or_create_object.return_value = mock_blender_obj_ref

        mock_root_marker_ref = MagicMock()
        mock_root_marker_ref.name = "RootNode_marker_obj"
        mock_nose_marker_ref = MagicMock()
        mock_nose_marker_ref.name = "Nose_marker_obj"
        mock_leye_marker_ref = MagicMock()
        mock_leye_marker_ref.name = "LEye_marker_obj"
        mock_dal.get_children_of_object.return_value = [
            mock_root_marker_ref,
            mock_nose_marker_ref,
            mock_leye_marker_ref,
        ]

        def get_prop_se(obj_ref, prop):
            if obj_ref.name == "RootNode_marker_obj":
                return "RootNode"
            if obj_ref.name == "Nose_marker_obj":
                return "Nose"
            return "LEye"

        mock_dal.get_custom_property.side_effect = get_prop_se

        # Act
        mock_camera_view_obj_ref = MagicMock()
        mock_camera_view = MagicMock()
        mock_camera_view._obj = mock_camera_view_obj_ref
        mock_camera_view.get_transform_scale.return_value = (1.0, 1.0, 1.0)
        mock_camera_view.get_transform_location.return_value = (0.0, 0.0, 0.0)

        view = PersonDataView.create_new(
            view_name=view_name,
            skeleton=mock_skeleton,
            color=marker_color,
            camera_view=mock_camera_view,
            collection=mock_collection,  # Test the default collection logic
        )

        # Assert
        # Check that the collection was retrieved
        # mock_dal.get_or_create_collection.assert_called_once_with("PersonViews")

        # Check root object creation
        mock_dal.get_or_create_object.assert_any_call(
            name=view_name,
            obj_type="EMPTY",
            collection_name=mock_collection.name,
            parent=mock_camera_view._obj,
        )

        # Check marker creation
        assert mock_dal.create_marker.call_count == 3
        # Check that markers are created in the correct collection
        mock_dal.create_marker.assert_any_call(
            parent=mock_blender_obj_ref, name="Nose", color=marker_color, collection=mock_collection
        )

        # Check armature creation
        armature_name = f"{view_name}_Armature"
        mock_dal.get_or_create_object.assert_any_call(
            name=armature_name,
            obj_type="ARMATURE",
            collection_name="PersonViews",
            parent=mock_blender_obj_ref,
        )

    @patch("pose_editor.core.person_data_view.dal")
    def test_create_new_applies_transform(self, mock_dal, mock_skeleton):
        """Test that create_new applies the transform from the CameraView."""
        from pose_editor.core.person_data_view import PersonDataView

        # Arrange
        view_name = "PV.Test.cam1"
        marker_color = (0.1, 0.2, 0.3, 1.0)

        mock_camera_view_obj_ref = MagicMock()
        mock_camera_view = MagicMock()
        mock_camera_view._obj = mock_camera_view_obj_ref

        expected_scale = (0.5, -0.5, 0.5)
        expected_location = (-100, 100, 0)
        mock_camera_view.get_transform_scale.return_value = expected_scale
        mock_camera_view.get_transform_location.return_value = expected_location

        mock_view_root_object = MagicMock()
        mock_dal.get_or_create_object.return_value = mock_view_root_object

        # Act
        PersonDataView.create_new(
            view_name=view_name,
            skeleton=mock_skeleton,
            color=marker_color,
            camera_view=mock_camera_view,
            collection=None,
        )

        # Assert
        mock_camera_view.get_transform_scale.assert_called_once()
        mock_camera_view.get_transform_location.assert_called_once()

        # Check that the scale and location were set on the mock object
        # that dal.get_or_create_object returns.
        created_obj_mock = mock_dal.get_or_create_object.return_value
        assert created_obj_mock._get_obj().scale == expected_scale
        assert created_obj_mock._get_obj().location == expected_location

    @patch("pose_editor.core.person_data_view.dal")
    def test_create_armature_method(self, mock_dal, mock_skeleton, mock_blender_obj_ref):
        """Test that _create_armature method correctly creates armature, bones, and constraints."""
        from pose_editor.core.person_data_view import PersonDataView

        # Arrange
        view_name = "PV.Test.cam1"
        marker_color = (0.1, 0.2, 0.3, 1.0)

        # Create a real PersonDataView instance, but bypass its __init__
        # to control its internal state for this specific test.
        person_data_view_instance = PersonDataView.__new__(PersonDataView)
        person_data_view_instance.view_name = view_name
        person_data_view_instance.skeleton = mock_skeleton
        person_data_view_instance.color = marker_color
        person_data_view_instance.view_root_object = mock_blender_obj_ref  # Mock the root object

        # Mock marker objects by role for _populate_marker_objects_by_role
        mock_root_marker_ref = MagicMock()
        mock_root_marker_ref.name = "RootNode_marker_obj"
        mock_nose_marker_ref = MagicMock()
        mock_nose_marker_ref.name = "Nose_marker_obj"
        mock_leye_marker_ref = MagicMock()
        mock_leye_marker_ref.name = "LEye_marker_obj"

        person_data_view_instance._marker_objects_by_role = {
            "RootNode": mock_root_marker_ref,
            "Nose": mock_nose_marker_ref,
            "LEye": mock_leye_marker_ref,
        }

        # Mock dal.get_or_create_object for armature creation
        mock_armature_obj_ref = MagicMock()
        mock_armature_obj_ref._get_obj.return_value = MagicMock()
        mock_dal.get_or_create_object.return_value = mock_armature_obj_ref

        # Act
        person_data_view_instance._create_armature()

        # Assert
        # Check armature creation
        armature_name = f"{view_name}_Armature"
        mock_dal.get_or_create_object.assert_called_once_with(
            name=armature_name, obj_type="ARMATURE", collection_name="PersonViews", parent=mock_blender_obj_ref
        )
        mock_armature_obj_ref._get_obj.assert_called_once()
        mock_armature_obj_ref._get_obj().color = marker_color

        # Check set_armature_display_stick
        mock_dal.set_armature_display_stick.assert_called_once_with(mock_armature_obj_ref)

        # Check bone and constraint creation
        mock_dal.add_bones_in_bulk.assert_called_once()
        # Check that the number of bones to add is correct (RootNode-Nose, RootNode-LEye)
        assert len(mock_dal.add_bones_in_bulk.call_args[0][1]) == 2
        assert mock_dal.add_bone_constraint.call_count == 4  # 2 bones * 2 constraints
        assert mock_dal.add_bone_driver.call_count == 2  # 2 bones * 1 driver

    @patch("pose_editor.core.person_data_view.dal")
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
        mock_dal.get_custom_property.side_effect = (
            lambda obj_ref, prop: "Nose" if obj_ref.name == "Nose_marker_obj" else "LEye"
        )

        mock_view_root_obj_ref = MagicMock()  # Mock the root object
        mock_view_root_obj_ref.name = view_name  # Ensure it has a name
        mock_dal.get_custom_property.side_effect = (
            lambda obj, prop: {
                mock_view_root_obj_ref: {
                    mock_dal.POSE_EDITOR_OBJECT_TYPE: "PersonDataView",
                    mock_dal.SKELETON: "COCO_133",
                    mock_dal.COLOR: marker_color,
                    mock_dal.CAMERA_VIEW_ID: "cam1",  # Example camera view ID
                }
            }.get(obj, {}).get(prop)
        )  # Mock custom properties for from_blender_object

        view = PersonDataView.from_blender_object(mock_view_root_obj_ref)

        # Act
        view.connect_to_series(mock_marker_data)

        # Assert
        mock_marker_data.apply_to_view.assert_called_once_with(view)

    @patch("pose_editor.core.person_data_view.dal")
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

        mock_view_root_obj_ref = MagicMock()  # Mock the root object
        mock_view_root_obj_ref.name = view_name  # Ensure it has a name

        def combined_get_custom_property_side_effect(obj, prop):
            if obj == mock_view_root_obj_ref:
                # Logic for PersonDataView root properties
                return {
                    mock_dal.POSE_EDITOR_OBJECT_TYPE: "PersonDataView",
                    mock_dal.SKELETON: mock_skeleton.name,
                    mock_dal.COLOR: marker_color,
                    mock_dal.CAMERA_VIEW_ID: "cam1",
                }.get(prop)
            elif prop == mock_dal.MARKER_ROLE:
                # Logic for marker roles
                if obj == mock_nose_marker_ref:
                    return "Nose"
                elif obj == mock_leye_marker_ref:
                    return "LEye"
            return None  # Default for other cases

        mock_dal.get_custom_property.side_effect = combined_get_custom_property_side_effect

        view = PersonDataView.from_blender_object(mock_view_root_obj_ref)

        # Act
        marker_objects_dict = view.get_marker_objects()

        # Assert
        assert marker_objects_dict == {"Nose": mock_nose_marker_ref, "LEye": mock_leye_marker_ref}
        mock_dal.get_children_of_object.assert_called_once()