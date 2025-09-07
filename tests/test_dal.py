# SPDX-FileCopyrightText: 2025 Harri Kaimio
#
# SPDX-License-Identifier: BSD-3-Clause

import pytest
from unittest.mock import MagicMock, patch

# Mock bpy module for testing outside Blender environment
bpy = MagicMock()
bpy.data = MagicMock()
bpy.context = MagicMock()
bpy.ops = MagicMock()

# Import the dal module after mocking bpy
with patch.dict('sys.modules', {'bpy': bpy}):
    from src.pose_editor.blender import dal

@pytest.fixture
def mock_bpy_data():
    """Fixture to reset bpy.data mocks for each test."""
    bpy.data.collections = MagicMock()
    bpy.data.objects = MagicMock()
    bpy.data.materials = MagicMock()
    bpy.context.scene.collection = MagicMock()
    bpy.ops.mesh.primitive_uv_sphere_add = MagicMock()
    bpy.ops.object.select_all = MagicMock()
    bpy.ops.object.parent_set = MagicMock()
    return bpy.data

@pytest.fixture
def mock_parent_obj():
    """Fixture for a mock parent Blender object."""
    parent = MagicMock()
    parent.name = "ParentObj"
    parent.objects = [] # To simulate children
    return parent

@pytest.fixture
def mock_blender_obj_ref(mock_parent_obj):
    """Fixture for a mock BlenderObjRef."""
    mock_ref = MagicMock(spec=dal.BlenderObjRef)
    mock_ref._id = mock_parent_obj.name
    mock_ref._get_obj.return_value = mock_parent_obj
    return mock_ref

class TestDal:
    def test_create_collection(self, mock_bpy_data):
        mock_collection_obj = MagicMock()
        mock_collection_obj.name = "NewCollection" # Explicitly set the name attribute
        mock_bpy_data.collections.new.return_value = mock_collection_obj
        mock_parent_collection = MagicMock()
        
        collection = dal.create_collection("TestCollection", mock_parent_collection)
        
        mock_bpy_data.collections.new.assert_called_once_with("TestCollection")
        mock_parent_collection.children.link.assert_called_once_with(collection)
        assert collection.name == "NewCollection"

    def test_create_empty(self, mock_bpy_data):
        mock_empty_obj = MagicMock()
        mock_empty_obj.name = "NewEmpty" # Explicitly set the name attribute
        mock_bpy_data.objects.new.return_value = mock_empty_obj
        mock_collection = MagicMock()
        
        empty = dal.create_empty("TestEmpty", mock_collection)
        
        mock_bpy_data.objects.new.assert_called_once_with("TestEmpty", None)
        mock_collection.objects.link.assert_called_once_with(empty)
        assert empty.name == "NewEmpty"

    # SPDX-FileCopyrightText: 2025 Harri Kaimio
#
# SPDX-License-Identifier: BSD-3-Clause

import pytest
from unittest.mock import MagicMock, patch

# Mock bpy module for testing outside Blender environment
bpy = MagicMock()
bpy.data = MagicMock()
bpy.context = MagicMock()
bpy.ops = MagicMock()

# Import the dal module after mocking bpy
with patch.dict('sys.modules', {'bpy': bpy}):
    from src.pose_editor.blender import dal

@pytest.fixture
def mock_bpy_data():
    """Fixture to reset bpy.data mocks for each test."""
    bpy.data.collections = MagicMock()
    bpy.data.objects = MagicMock()
    bpy.data.materials = MagicMock()
    bpy.context.scene.collection = MagicMock()
    bpy.ops.mesh.primitive_uv_sphere_add = MagicMock()
    bpy.ops.object.select_all = MagicMock()
    bpy.ops.object.parent_set = MagicMock()
    return bpy.data

@pytest.fixture
def mock_parent_obj():
    """Fixture for a mock parent Blender object."""
    parent = MagicMock()
    parent.name = "ParentObj"
    parent.objects = [] # To simulate children
    return parent

@pytest.fixture
def mock_blender_obj_ref(mock_parent_obj):
    """Fixture for a mock BlenderObjRef."""
    mock_ref = MagicMock(spec=dal.BlenderObjRef)
    mock_ref._id = mock_parent_obj.name
    mock_ref._get_obj.return_value = mock_parent_obj
    return mock_ref

class TestDal:
    def test_create_collection(self, mock_bpy_data):
        mock_collection_obj = MagicMock()
        mock_collection_obj.name = "NewCollection" # Explicitly set the name attribute
        mock_bpy_data.collections.new.return_value = mock_collection_obj
        mock_parent_collection = MagicMock()
        
        collection = dal.create_collection("TestCollection", mock_parent_collection)
        
        mock_bpy_data.collections.new.assert_called_once_with("TestCollection")
        mock_parent_collection.children.link.assert_called_once_with(collection)
        assert collection.name == "NewCollection"

    def test_create_empty(self, mock_bpy_data):
        mock_empty_obj = MagicMock()
        mock_empty_obj.name = "NewEmpty" # Explicitly set the name attribute
        mock_bpy_data.objects.new.return_value = mock_empty_obj
        mock_collection = MagicMock()
        
        empty = dal.create_empty("TestEmpty", mock_collection)
        
        mock_bpy_data.objects.new.assert_called_once_with("TestEmpty", None)
        mock_collection.objects.link.assert_called_once_with(empty)
        assert empty.name == "NewEmpty"

    # SPDX-FileCopyrightText: 2025 Harri Kaimio
#
# SPDX-License-Identifier: BSD-3-Clause

import pytest
from unittest.mock import MagicMock, patch

# Mock bpy module for testing outside Blender environment
bpy = MagicMock()
bpy.data = MagicMock()
bpy.context = MagicMock()
bpy.ops = MagicMock()

# Import the dal module after mocking bpy
with patch.dict('sys.modules', {'bpy': bpy}):
    from src.pose_editor.blender import dal

@pytest.fixture
def mock_bpy_data():
    """Fixture to reset bpy.data mocks for each test."""
    bpy.data.collections = MagicMock()
    bpy.data.objects = MagicMock()
    bpy.data.materials = MagicMock()
    bpy.context.scene.collection = MagicMock()
    bpy.ops.mesh.primitive_uv_sphere_add = MagicMock()
    bpy.ops.object.select_all = MagicMock()
    bpy.ops.object.parent_set = MagicMock()
    return bpy.data

@pytest.fixture
def mock_parent_obj():
    """Fixture for a mock parent Blender object."""
    parent = MagicMock()
    parent.name = "ParentObj"
    parent.objects = [] # To simulate children
    return parent

@pytest.fixture
def mock_blender_obj_ref(mock_parent_obj):
    """Fixture for a mock BlenderObjRef."""
    mock_ref = MagicMock(spec=dal.BlenderObjRef)
    mock_ref._id = mock_parent_obj.name
    mock_ref._get_obj.return_value = mock_parent_obj
    return mock_ref

class TestDal:
    def test_create_collection(self, mock_bpy_data):
        mock_collection_obj = MagicMock()
        mock_collection_obj.name = "NewCollection" # Explicitly set the name attribute
        mock_bpy_data.collections.new.return_value = mock_collection_obj
        mock_parent_collection = MagicMock()
        
        collection = dal.create_collection("TestCollection", mock_parent_collection)
        
        mock_bpy_data.collections.new.assert_called_once_with("TestCollection")
        mock_parent_collection.children.link.assert_called_once_with(collection)
        assert collection.name == "NewCollection"

    def test_create_empty(self, mock_bpy_data):
        mock_empty_obj = MagicMock()
        mock_empty_obj.name = "NewEmpty" # Explicitly set the name attribute
        mock_bpy_data.objects.new.return_value = mock_empty_obj
        mock_collection = MagicMock()
        
        empty = dal.create_empty("TestEmpty", mock_collection)
        
        mock_bpy_data.objects.new.assert_called_once_with("TestEmpty", None)
        mock_collection.objects.link.assert_called_once_with(empty)
        assert empty.name == "NewEmpty"

    def test_create_marker_success(self, mock_bpy_data, mock_blender_obj_ref, mock_parent_obj):
        # Mock the marker object that bpy.context.active_object will return
        mock_marker_obj = MagicMock()
        mock_marker_obj.name = "NewMarker"
        mock_marker_obj.data.materials = []
        mock_marker_obj.__setitem__ = MagicMock() # Mock setting custom properties
        mock_marker_obj.__getitem__ = MagicMock(return_value=1.0) # Mock getting custom properties
        bpy.context.active_object = mock_marker_obj

        # Mock material creation
        mock_material = MagicMock()
        mock_bsdf_node = MagicMock()
        mock_material.node_tree.nodes.get.return_value = mock_bsdf_node
        mock_bpy_data.materials.new.return_value = mock_material

        # Mock driver_add and its return values
        mock_drivers = []
        for _ in range(8): # 4 for Base Color, 4 for Emission
            mock_driver = MagicMock()
            mock_driver.variables.new.return_value = MagicMock(targets=[MagicMock()]) # Mock driver variables
            mock_drivers.append(mock_driver)

        # Configure driver_add to return these mock drivers sequentially
        mock_bsdf_node.inputs = {
            'Base Color': MagicMock(driver_add=MagicMock(side_effect=[MagicMock(driver=d) for d in mock_drivers[:4]])),
            'Emission': MagicMock(driver_add=MagicMock(side_effect=[MagicMock(driver=d) for d in mock_drivers[4:]])),
            'Emission Strength': MagicMock() # Add this line
        }

        marker_name = "TestMarker"
        marker_color = (1.0, 0.0, 0.0, 1.0) # Red

        # Call the function
        result_ref = dal.create_marker(mock_blender_obj_ref, marker_name, marker_color)

        # Assertions for basic marker properties
        mock_blender_obj_ref._get_obj.assert_called_once() # Ensure parent object is retrieved
        bpy.ops.mesh.primitive_uv_sphere_add.assert_called_once_with(radius=0.02, enter_editmode=False, align='WORLD', location=(0, 0, 0))
        assert mock_marker_obj.parent == mock_parent_obj
        assert mock_marker_obj.name == f"{mock_parent_obj.name}_{marker_name}"
        mock_bpy_data.materials.new.assert_called_once_with(name=f"MarkerMaterial_{mock_parent_obj.name}_{marker_name}")
        assert mock_material.use_nodes is True
        assert mock_material.node_tree.nodes.get.called_with('Principled BSDF')
        assert mock_marker_obj.data.materials[0] == mock_material
        assert isinstance(result_ref, dal.BlenderObjRef)
        assert result_ref._id == mock_marker_obj.name

        # Assertions for custom properties
        mock_marker_obj.__setitem__.assert_any_call("quality", 1.0)
        mock_marker_obj.__setitem__.assert_any_call("_original_color_r", marker_color[0])
        mock_marker_obj.__setitem__.assert_any_call("_original_color_g", marker_color[1])
        mock_marker_obj.__setitem__.assert_any_call("_original_color_b", marker_color[2])
        mock_marker_obj.__setitem__.assert_any_call("_original_color_a", marker_color[3])

        # Assertions for driver setup
        expected_expressions = []
        for i in range(4):
            expected_expressions.append(f'drivers.get_quality_driven_color_component(quality, _original_color_r, _original_color_g, _original_color_b, _original_color_a, {i})')

        # Check Base Color drivers
        assert mock_bsdf_node.inputs['Base Color'].driver_add.call_count == 4
        for i in range(4):
            call_args = mock_bsdf_node.inputs['Base Color'].driver_add.call_args_list[i]
            assert call_args.args == ('default_value', i)
            
            # Get the specific mock driver for this call
            current_mock_driver = mock_drivers[i]
            assert current_mock_driver.type == 'SCRIPTED'
            assert current_mock_driver.expression == expected_expressions[i]
            # Check driver variables (simplified, just checking creation)
            assert current_mock_driver.variables.new.call_count == 5 # 5 variables per channel

        # Check Emission drivers
        assert mock_bsdf_node.inputs['Emission'].driver_add.call_count == 4
        for i in range(4):
            call_args = mock_bsdf_node.inputs['Emission'].driver_add.call_args_list[i]
            assert call_args.args == ('default_value', i)
            
            # Get the specific mock driver for this call (offset by 4 for Emission drivers)
            current_mock_driver = mock_drivers[i + 4]
            assert current_mock_driver.type == 'SCRIPTED'
            assert current_mock_driver.expression == expected_expressions[i]
            # Check driver variables (simplified, just checking creation)
            assert current_mock_driver.variables.new.call_count == 5 # 5 variables per channel


    def test_create_marker_parent_not_found(self, mock_bpy_data):
        mock_blender_obj_ref = MagicMock(spec=dal.BlenderObjRef)
        mock_blender_obj_ref._id = "NonExistentParent"
        mock_blender_obj_ref._get_obj.return_value = None # Simulate parent not found

        marker_name = "TestMarker"
        marker_color = (1.0, 0.0, 0.0, 1.0)

        with pytest.raises(ValueError, match=f"Parent object with ID {mock_blender_obj_ref._id} not found."):
            dal.create_marker(mock_blender_obj_ref, marker_name, marker_color)

        mock_blender_obj_ref._get_obj.assert_called_once()
        # Ensure no Blender ops are called if parent is not found
        bpy.ops.mesh.primitive_uv_sphere_add.assert_not_called()


    def test_create_marker_parent_not_found(self, mock_bpy_data):
        mock_blender_obj_ref = MagicMock(spec=dal.BlenderObjRef)
        mock_blender_obj_ref._id = "NonExistentParent"
        mock_blender_obj_ref._get_obj.return_value = None # Simulate parent not found

        marker_name = "TestMarker"
        marker_color = (1.0, 0.0, 0.0, 1.0)

        with pytest.raises(ValueError, match=f"Parent object with ID {mock_blender_obj_ref._id} not found."):
            dal.create_marker(mock_blender_obj_ref, marker_name, marker_color)

        mock_blender_obj_ref._get_obj.assert_called_once()
        # Ensure no Blender ops are called if parent is not found
        bpy.ops.mesh.primitive_uv_sphere_add.assert_not_called()


    def test_create_marker_parent_not_found(self, mock_bpy_data):
        mock_blender_obj_ref = MagicMock(spec=dal.BlenderObjRef)
        mock_blender_obj_ref._id = "NonExistentParent"
        mock_blender_obj_ref._get_obj.return_value = None # Simulate parent not found

        marker_name = "TestMarker"
        marker_color = (1.0, 0.0, 0.0, 1.0)

        with pytest.raises(ValueError, match=f"Parent object with ID {mock_blender_obj_ref._id} not found."):
            dal.create_marker(mock_blender_obj_ref, marker_name, marker_color)

        mock_blender_obj_ref._get_obj.assert_called_once()
        # Ensure no Blender ops are called if parent is not found
        bpy.ops.mesh.primitive_uv_sphere_add.assert_not_called()