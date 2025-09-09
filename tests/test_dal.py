# SPDX-FileCopyrightText: 2025 Harri Kaimio
#
# SPDX-License-Identifier: BSD-3-Clause

import pytest
import bpy

from pose_editor.blender import dal

@pytest.fixture(autouse=True)
def clean_blender_scene():
    """Cleans the Blender scene before each test."""
    bpy.context.preferences.filepaths.use_scripts_auto_execute = True
    # Clean up actions
    for action in bpy.data.actions:
        bpy.data.actions.remove(action)
    # Clean up objects
    if bpy.data.objects:
        bpy.ops.object.select_all(action='SELECT')
        bpy.ops.object.delete()
    # Clean up collections
    for collection in bpy.data.collections:
        # Don't remove the scene collection
        if collection.name not in (bpy.context.scene.collection.name, "Scene Collection"):
            bpy.data.collections.remove(collection)
    yield
    # Final cleanup after test
    for action in bpy.data.actions:
        bpy.data.actions.remove(action)
    if bpy.data.objects:
        bpy.ops.object.select_all(action='SELECT')
        bpy.ops.object.delete()
    for collection in bpy.data.collections:
        if collection.name not in (bpy.context.scene.collection.name, "Scene Collection"):
            bpy.data.collections.remove(collection)

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

    def test_create_empty(self):
        empty_name = "TestEmpty"
        empty_ref = dal.create_empty(empty_name)
        
        assert empty_ref._get_obj().name == empty_name
        assert empty_name in bpy.data.objects
        assert empty_name in bpy.context.scene.collection.objects

    def test_create_marker_success(self, blender_obj_ref, blender_parent_obj):
        marker_name = "TestMarker"
        marker_color = (1.0, 0.0, 0.0, 1.0) # Red

        result_ref = dal.create_marker(blender_obj_ref, marker_name, marker_color)

        marker_obj = result_ref._get_obj()
        assert marker_obj is not None
        assert marker_obj.parent == blender_parent_obj
        assert marker_obj.name == f"{blender_parent_obj.name}_{marker_name}"
        assert marker_obj.type == 'MESH'
        assert marker_obj.data.materials[0].name == f"MarkerMaterial_{blender_parent_obj.name}_{marker_name}"
        
    def test_set_and_get_custom_property_string(self, blender_obj_ref):
        prop = dal.CustomProperty[str]("my_string_prop")
        value = "hello world"
        dal.set_custom_property(blender_obj_ref, prop, value)
        retrieved_value = dal.get_custom_property(blender_obj_ref, prop)
        assert retrieved_value == value
        assert isinstance(retrieved_value, str)

    # --- New/Refactored Tests for Slotted Actions ---

    def test_get_or_create_action(self):
        action_name = "TestAction"
        assert bpy.data.actions.get(action_name) is None
        
        action1 = dal.get_or_create_action(action_name)
        assert action1 is not None
        assert action1.name == action_name
        assert action_name in bpy.data.actions

        action2 = dal.get_or_create_action(action_name)
        assert action2 == action1

    def test_get_or_create_action_slot(self):
        action = dal.get_or_create_action("SlotTestAction")
        slot_name = "TestSlot"
        prefixed_name = dal._get_prefixed_slot_name(slot_name)

        assert prefixed_name not in action.slots

        slot1 = dal.get_or_create_action_slot(action, slot_name)
        assert slot1 is not None
        assert prefixed_name in action.slots
        assert action.slots.get(prefixed_name) == slot1

        slot2 = dal.get_or_create_action_slot(action, slot_name)
        assert slot2 == slot1

    def test_action_has_slot(self):
        action = dal.get_or_create_action("HasSlotAction")
        slot_name = "MySlot"

        assert not dal.action_has_slot(action, slot_name)
        dal.get_or_create_action_slot(action, slot_name)
        assert dal.action_has_slot(action, slot_name)

    def test_get_or_create_fcurve(self):
        action = dal.get_or_create_action("FCurveAction")
        slot_name = "TestSlot"
        data_path = "location"

        fcurve = dal.get_or_create_fcurve(action, slot_name, data_path, index=0)
        assert fcurve is not None
        
        prefixed_slot_name = dal._get_prefixed_slot_name(slot_name)
        expected_data_path = f'slots["{prefixed_slot_name}"].{data_path}'
        assert fcurve.data_path == expected_data_path
        assert fcurve.array_index == 0

        # Check it was added to the action
        assert action.fcurves.find(fcurve.data_path, index=fcurve.array_index) is not None

        fcurve2 = dal.get_or_create_fcurve(action, slot_name, data_path, index=0)
        assert fcurve2 == fcurve

    def test_set_fcurve_keyframes(self):
        action = dal.get_or_create_action("KeyframeAction")
        slot_name = "TestSlot"
        fcurve = dal.get_or_create_fcurve(action, slot_name, "location", index=1)

        keyframes = [(1.0, 10.0), (10.0, 20.0), (20.0, 5.0)]
        dal.set_fcurve_keyframes(fcurve, keyframes)

        assert len(fcurve.keyframe_points) == len(keyframes)
        for i, (frame, value) in enumerate(keyframes):
            kp = fcurve.keyframe_points[i]
            assert kp.co.x == pytest.approx(frame)
            assert kp.co.y == pytest.approx(value)

    def test_assign_action_to_object(self, blender_obj_ref):
        obj = blender_obj_ref._get_obj()
        action = dal.get_or_create_action("AssignAction")
        slot_name = "MyObjectSlot"

        dal.assign_action_to_object(blender_obj_ref, action, slot_name)

        assert obj.animation_data is not None
        assert obj.animation_data.action == action
        assert obj.animation_data.action_slot is not None
        
        prefixed_name = dal._get_prefixed_slot_name(slot_name)
        assert obj.animation_data.action_slot == action.slots[prefixed_name]

    def test_get_fcurve_from_action(self):
        action = dal.get_or_create_action("GetFCurveAction")
        slot_name = "TestSlot"
        fcurve = dal.get_or_create_fcurve(action, slot_name, "location", index=2)

        retrieved_fcurve = dal.get_fcurve_from_action(action, slot_name, "location", index=2)
        assert retrieved_fcurve == fcurve

        assert dal.get_fcurve_from_action(action, slot_name, "location", index=0) is None

    def test_sample_fcurve(self):
        import numpy as np
        action = dal.get_or_create_action("SampleAction")
        slot_name = "TestSlot"
        fcurve = dal.get_or_create_fcurve(action, slot_name, "location", index=0)
        
        keyframes = [(0, 0), (10, 10)]
        dal.set_fcurve_keyframes(fcurve, keyframes)

        start_frame, end_frame = 0, 10
        sampled_data = dal.sample_fcurve(fcurve, start_frame, end_frame)
        
        assert isinstance(sampled_data, np.ndarray)
        assert len(sampled_data) == 11
        expected = np.arange(0.0, 11.0)
        assert np.allclose(sampled_data, expected)
