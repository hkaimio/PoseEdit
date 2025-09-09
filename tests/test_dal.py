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
        empty_ref = dal.create_empty(empty_name)
        
        assert empty_ref._get_obj().name == empty_name
        assert empty_name in bpy.data.objects
        assert empty_name in bpy.context.scene.collection.objects

        # Clean up
        bpy.data.objects.remove(empty_ref._get_obj())

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

        # Assertions for material and nodes
        material = marker_obj.data.materials[0]
        assert material.use_nodes is True

        nodes = material.node_tree.nodes
        value_node = nodes.get('Value')
        color_ramp_node = nodes.get('Color Ramp') # ShaderNodeValToRGB is displayed as ColorRamp
        emission_node = nodes.get('Emission')
        material_output_node = nodes.get('Material Output')

        assert value_node is not None
        assert color_ramp_node is not None
        assert emission_node is not None
        assert material_output_node is not None

        # Check Value node driver
        driver = value_node.outputs[0].driver_add('default_value').driver
        assert driver is not None
        assert driver.type == 'SCRIPTED'
        # assert driver.expression == 'quality'
        assert len(driver.variables) == 1
        var_quality = driver.variables.get('quality')
        assert var_quality is not None
        assert var_quality.type == 'SINGLE_PROP'
        assert var_quality.targets[0].id == marker_obj
        assert var_quality.targets[0].data_path == '["quality"]'

        # Check ColorRamp stops
        color_ramp_elements = color_ramp_node.color_ramp.elements
        assert len(color_ramp_elements) == 4

        # Stop 1
        assert color_ramp_elements[0].position == pytest.approx(0.0)
        assert list(color_ramp_elements[0].color) == pytest.approx((0.2235, 0.0, 0.0275, 1.0))
        # Stop 2
        assert color_ramp_elements[1].position == pytest.approx(0.3)
        assert list(color_ramp_elements[1].color) == pytest.approx((0.2235, 0.0, 0.0275, 1.0))
        # Stop 3
        assert color_ramp_elements[2].position == pytest.approx(0.301)
        assert list(color_ramp_elements[2].color) == pytest.approx((0.498, 0.498, 0.498, 1.0))
        # Stop 4
        assert color_ramp_elements[3].position == pytest.approx(1.0)
        assert list(color_ramp_elements[3].color) == pytest.approx(marker_color)

        # # Check links
        # TODO: This needs to be clarified
        # links = material.node_tree.links
        # # Value to ColorRamp Fac
        # assert links.find(value_node.outputs[0], color_ramp_node.inputs[0]) is not None
        # # ColorRamp Color to Emission Color
        # assert links.find(color_ramp_node.outputs[0], emission_node.inputs[0]) is not None
        # # Emission to Material Output Surface
        # assert links.find(emission_node.outputs[0], material_output_node.inputs[0]) is not None

        # Check Emission Strength
        assert emission_node.inputs['Strength'].default_value == pytest.approx(1.0)

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

    def test_set_fcurve_from_data(self, blender_obj_ref):
        # Get the actual Blender object from the ref
        blender_object = blender_obj_ref._get_obj()
        assert blender_object is not None, "Blender object should exist for testing"

        data_path = "location"
        keyframes = [(1, [10.0]), (10, [20.0]), (20, [5.0])]

        # Call the function under test
        dal.set_fcurve_from_data(blender_obj_ref, data_path, keyframes)

        # Assertions
        assert blender_object.animation_data is not None
        assert blender_object.animation_data.action is not None

        fcurve = blender_object.animation_data.action.fcurves.find(data_path)
        assert fcurve is not None

        assert len(fcurve.keyframe_points) == len(keyframes)

        for i, (frame, value) in enumerate(keyframes):
            keyframe_point = fcurve.keyframe_points[i]
            assert keyframe_point.co.x == pytest.approx(frame)
            assert keyframe_point.co.y == pytest.approx(value[0])

    def test_set_and_get_custom_property_int(self, blender_obj_ref):
        prop = dal.CustomProperty[int]("my_int_prop")
        value = 123
        dal.set_custom_property(blender_obj_ref, prop, value)
        retrieved_value = dal.get_custom_property(blender_obj_ref, prop)
        assert retrieved_value == value
        assert isinstance(retrieved_value, int)

    def test_set_and_get_custom_property_float(self, blender_obj_ref):
        prop = dal.CustomProperty[float]("my_float_prop")
        value = 123.45
        dal.set_custom_property(blender_obj_ref, prop, value)
        retrieved_value = dal.get_custom_property(blender_obj_ref, prop)
        assert retrieved_value == pytest.approx(value)
        assert isinstance(retrieved_value, float)

    def test_set_and_get_custom_property_string(self, blender_obj_ref):
        prop = dal.CustomProperty[str]("my_string_prop")
        value = "hello world"
        dal.set_custom_property(blender_obj_ref, prop, value)
        retrieved_value = dal.get_custom_property(blender_obj_ref, prop)
        assert retrieved_value == value
        assert isinstance(retrieved_value, str)

    def test_set_and_get_custom_property_bool(self, blender_obj_ref):
        prop = dal.CustomProperty[bool]("my_bool_prop")
        value = True
        dal.set_custom_property(blender_obj_ref, prop, value)
        retrieved_value = dal.get_custom_property(blender_obj_ref, prop)
        assert retrieved_value == value
        assert isinstance(retrieved_value, bool)

    def test_get_custom_property_non_existent(self, blender_obj_ref):
        prop = dal.CustomProperty[str]("non_existent_prop")
        retrieved_value = dal.get_custom_property(blender_obj_ref, prop)
        assert retrieved_value is None

    def test_get_custom_property_with_default_value(self, blender_obj_ref):
        # This test is not directly applicable with the current get_custom_property signature
        # as it doesn't take a default value. Blender's .get() method does.
        # If a default value parameter is added to dal.get_custom_property, this test would be relevant.
        pass

    def test_get_or_create_action(self):
        action_name = "TestAction"
        # Ensure action doesn't exist
        assert bpy.data.actions.get(action_name) is None
        
        # Create action
        action1 = dal.get_or_create_action(action_name)
        assert action1 is not None
        assert action1.name == action_name
        assert action_name in bpy.data.actions

        # Get existing action
        action2 = dal.get_or_create_action(action_name)
        assert action2 == action1

        # Clean up
        bpy.data.actions.remove(action1)

    def test_action_slot_functions(self):
        action = dal.get_or_create_action("SlotTest_Action")
        slot_name = "TestSlot"

        # action_has_slot
        assert not dal.action_has_slot(action, slot_name)
        
        # get_or_create_action_slot
        slot1 = dal.get_or_create_action_slot(action, slot_name)
        assert slot1 is not None
        assert slot1.name == slot_name
        assert dal.action_has_slot(action, slot_name)

        # Get existing slot
        slot2 = dal.get_or_create_action_slot(action, slot_name)
        assert slot1 == slot2

        # Clean up
        bpy.data.actions.remove(action)

    def test_action_strip_layer_fcurve_creation(self):
        action = dal.get_or_create_action("HierarchyTest_Action")
        slot = dal.get_or_create_action_slot(action, "TestSlot")
        strip_name = "TestStrip"
        layer_name = "TestLayer"
        data_path = "location"
        
        # get_or_create_action_strip
        strip = dal.get_or_create_action_strip(slot, strip_name)
        assert strip is not None
        assert strip.name == strip_name

        # get_or_create_action_layer
        layer = dal.get_or_create_action_layer(strip, layer_name)
        assert layer is not None
        assert layer.name == layer_name

        # get_or_create_fcurve
        fcurve = dal.get_or_create_fcurve(layer, data_path, index=0)
        assert fcurve is not None
        assert fcurve.data_path == data_path
        assert fcurve.array_index == 0

        # get existing fcurve
        fcurve2 = dal.get_or_create_fcurve(layer, data_path, index=0)
        assert fcurve == fcurve2

        # Clean up
        bpy.data.actions.remove(action)

    def test_set_fcurve_keyframes(self):
        action = dal.get_or_create_action("KeyframeTest_Action")
        slot = dal.get_or_create_action_slot(action, "TestSlot")
        strip = dal.get_or_create_action_strip(slot, "TestStrip")
        layer = dal.get_or_create_action_layer(strip, "TestLayer")
        fcurve = dal.get_or_create_fcurve(layer, "location", index=0)

        keyframes = [(1.0, 10.0), (10.0, 20.0), (20.0, 5.0)]
        dal.set_fcurve_keyframes(fcurve, keyframes)

        assert len(fcurve.keyframe_points) == len(keyframes)
        for i, (frame, value) in enumerate(keyframes):
            kp = fcurve.keyframe_points[i]
            assert kp.co.x == pytest.approx(frame)
            assert kp.co.y == pytest.approx(value)

        # Clean up
        bpy.data.actions.remove(action)

    def test_assign_action_to_object(self, blender_obj_ref):
        obj = blender_obj_ref._get_obj()
        action = dal.get_or_create_action("AssignActionTest")
        slot_name = "TestSlot"
        dal.get_or_create_action_slot(action, slot_name)

        dal.assign_action_to_object(blender_obj_ref, action, slot_name)

        assert obj.animation_data is not None
        assert obj.animation_data.action == action
        assert obj.animation_data.action_slot is not None
        assert obj.animation_data.action_slot.name == slot_name

        # Clean up
        bpy.data.actions.remove(action)

    def test_get_children_of_object(self, blender_parent_obj):
        parent_ref = dal.BlenderObjRef(blender_parent_obj.name)
        
        # Create children
        child1 = dal.create_empty("Child1", parent_obj=parent_ref)
        child2 = dal.create_empty("Child2", parent_obj=parent_ref)

        children_refs = dal.get_children_of_object(parent_ref)
        
        assert len(children_refs) == 2
        child_names = [ref._id for ref in children_refs]
        assert child1._id in child_names
        assert child2._id in child_names

    def test_get_object_by_name(self):
        obj_name = "FindMe"
        dal.create_empty(obj_name)

        obj_ref = dal.get_object_by_name(obj_name)
        assert obj_ref is not None
        assert obj_ref._id == obj_name
        assert obj_ref._get_obj() is not None

        non_existent_ref = dal.get_object_by_name("DoesNotExist")
        assert non_existent_ref is None

    def test_get_fcurve_from_action_slot(self):
        action = dal.get_or_create_action("GetFCurveTest")
        slot = dal.get_or_create_action_slot(action, "TestSlot")
        strip = dal.get_or_create_action_strip(slot, "TestStrip")
        layer = dal.get_or_create_action_layer(strip, "TestLayer")
        fcurve = dal.get_or_create_fcurve(layer, "location", index=1)

        retrieved_fcurve = dal.get_fcurve_from_action_slot(slot, "location", index=1)
        assert retrieved_fcurve == fcurve

        # Test non-existent
        assert dal.get_fcurve_from_action_slot(slot, "location", index=2) is None

        # Clean up
        bpy.data.actions.remove(action)

    def test_get_scene_frame_range(self):
        bpy.context.scene.frame_start = 10
        bpy.context.scene.frame_end = 150
        start, end = dal.get_scene_frame_range()
        assert start == 10
        assert end == 150

    def test_sample_fcurve(self):
        # This requires numpy
        import numpy as np

        action = dal.get_or_create_action("SampleTest")
        slot = dal.get_or_create_action_slot(action, "TestSlot")
        strip = dal.get_or_create_action_strip(slot, "TestStrip")
        layer = dal.get_or_create_action_layer(strip, "TestLayer")
        fcurve = dal.get_or_create_fcurve(layer, "location", index=0)
        
        keyframes = [(0, 0), (10, 10)]
        dal.set_fcurve_keyframes(fcurve, keyframes)

        start_frame, end_frame = 0, 10
        sampled_data = dal.sample_fcurve(fcurve, start_frame, end_frame)
        
        assert isinstance(sampled_data, np.ndarray)
        assert len(sampled_data) == 11
        expected = np.arange(0.0, 11.0)
        assert np.allclose(sampled_data, expected)

        # Clean up
        bpy.data.actions.remove(action)

    def test_get_or_create_object(self):
        obj_name = "TestGOC"
        collection_name = "TestGOC_Collection"

        # Create new object and collection
        obj_ref = dal.get_or_create_object(obj_name, 'EMPTY', collection_name)
        assert obj_ref._id == obj_name
        obj = obj_ref._get_obj()
        assert obj is not None
        assert obj.name == obj_name
        assert collection_name in bpy.data.collections
        assert obj.name in bpy.data.collections[collection_name].objects

        # Get existing object
        obj_ref2 = dal.get_or_create_object(obj_name, 'EMPTY', collection_name)
        assert obj_ref2._id == obj_ref._id