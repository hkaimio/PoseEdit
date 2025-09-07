# SPDX-FileCopyrightText: 2025 Harri Kaimio
#
# SPDX-License-Identifier: BSD-3-Clause

import pytest
import bpy

from pose_editor.blender import dal

@pytest.fixture(autouse=True)
def clean_blender_scene():
    """Cleans the Blender scene before each test."""
    # Ensure the scene is clean before each test
    #bpy.ops.wm.read_factory_settings(use_empty=True)
    #bpy.ops.wm.read_userpref()
    # Remove all objects from the scene
    bpy.context.preferences.filepaths.use_scripts_auto_execute = True
    bpy.ops.object.select_all(action='SELECT')
    bpy.ops.object.delete()
    yield
    # Clean up after test
    bpy.ops.object.select_all(action='SELECT')
    bpy.ops.object.delete()

@pytest.fixture
def blender_parent_obj():
    """Fixture for a real Blender parent object."""
    bpy.ops.object.empty_add(type='PLAIN_AXES', align='WORLD', location=(0, 0, 0))
    parent = bpy.context.active_object
    parent.name = "ParentObj"
    return parent

@pytest.fixture
def blender_obj_ref(blender_parent_obj):
    """Fixture for a real BlenderObjRef."""
    return dal.BlenderObjRef(blender_parent_obj.name)

class TestDalBlender:
    def test_create_collection(self):
        collection_name = "TestCollection"
        collection = dal.create_collection(collection_name)
        
        assert collection.name == collection_name
        assert collection_name in bpy.data.collections
        assert collection_name in bpy.context.scene.collection.children

        # Clean up
        bpy.data.collections.remove(collection)

    def test_create_empty(self):
        empty_name = "TestEmpty"
        empty = dal.create_empty(empty_name)
        
        assert empty.name == empty_name
        assert empty_name in bpy.data.objects
        assert empty_name in bpy.context.scene.collection.objects

        # Clean up
        bpy.data.objects.remove(empty)

    def test_create_marker_success(self, blender_obj_ref, blender_parent_obj):
        marker_name = "TestMarker"
        marker_color = (1.0, 0.0, 0.0, 1.0) # Red

        result_ref = dal.create_marker(blender_obj_ref, marker_name, marker_color)

        # Assertions for basic marker properties
        marker_obj = result_ref._get_obj()
        assert marker_obj is not None
        assert marker_obj.parent == blender_parent_obj
        assert marker_obj.name == f"{blender_parent_obj.name}_{marker_name}"
        assert marker_obj.type == 'MESH'
        assert marker_obj.data.materials[0].name == f"MarkerMaterial_{blender_parent_obj.name}_{marker_name}"
        
        # Assertions for custom properties
        assert "quality" in marker_obj
        assert marker_obj["quality"] == 1.0
        assert marker_obj["_original_color_r"] == marker_color[0]
        assert marker_obj["_original_color_g"] == marker_color[1]
        assert marker_obj["_original_color_b"] == marker_color[2]
        assert marker_obj["_original_color_a"] == marker_color[3]

        # Assertions for material and drivers
        material = marker_obj.data.materials[0]
        assert material.use_nodes is True
        bsdf = material.node_tree.nodes.get('Emission')
        assert bsdf is not None

        # Check Base Color drivers
        for i in range(4):
            data_path = f'nodes["Principled BSDF"].inputs["Base Color"].default_value'
            driver = material.node_tree.animation_data.drivers.find(data_path, index=i)
            assert driver is not None
            assert driver.type == 'SCRIPTED'
            expected_expression = f'drivers.get_quality_driven_color_component(quality, _original_color_r, _original_color_g, _original_color_b, _original_color_a, {i})'
            assert driver.expression == expected_expression
            # Check driver variables
            assert len(driver.variables) == 5
            for var_name in ['quality', '_original_color_r', '_original_color_g', '_original_color_b', '_original_color_a']:
                var = driver.variables.get(var_name)
                assert var is not None
                assert var.type == 'SINGLE_PROP'
                assert var.targets[0].id == marker_obj
                assert var.targets[0].data_path == f'["{var_name}"]'

        # Check Emission Color drivers
        for i in range(4):
            data_path = f'nodes["Principled BSDF"].inputs["Emission Color"].default_value'
            driver = material.node_tree.animation_data.drivers.find(data_path, index=i)
            assert driver is not None
            assert driver.type == 'SCRIPTED'
            expected_expression = f'drivers.get_quality_driven_color_component(quality, _original_color_r, _original_color_g, _original_color_b, _original_color_a, {i})'
            assert driver.expression == expected_expression
            # Check driver variables
            assert len(driver.variables) == 5
            for var_name in ['quality', '_original_color_r', '_original_color_g', '_original_color_b', '_original_color_a']:
                var = driver.variables.get(var_name)
                assert var is not None
                assert var.type == 'SINGLE_PROP'
                assert var.targets[0].id == marker_obj
                assert var.targets[0].data_path == f'["{var_name}"]'

        # Check Emission Strength
        assert bsdf.inputs['Emission Strength'].default_value == 1.0

        # Clean up
        bpy.data.objects.remove(marker_obj, do_unlink=True)

    def test_create_marker_parent_not_found(self):
        # Create a BlenderObjRef for a non-existent object
        non_existent_parent_ref = dal.BlenderObjRef("NonExistentParent")

        marker_name = "TestMarker"
        marker_color = (1.0, 0.0, 0.0, 1.0)

        with pytest.raises(ValueError, match=f"Parent object with ID {non_existent_parent_ref._id} not found."):
            dal.create_marker(non_existent_parent_ref, marker_name, marker_color)

        # Ensure no objects were created
        assert "TestMarker" not in bpy.data.objects
