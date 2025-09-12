# SPDX-FileCopyrightText: 2025 Harri Kaimio
#
# SPDX-License-Identifier: BSD-3-Clause

import pytest
import bpy
import numpy as np

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
        bpy.ops.object.select_all(action="SELECT")
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
        bpy.ops.object.select_all(action="SELECT")
        bpy.ops.object.delete()
    for collection in bpy.data.collections:
        if collection.name not in (bpy.context.scene.collection.name, "Scene Collection"):
            bpy.data.collections.remove(collection)


@pytest.fixture
def blender_parent_obj():
    """Fixture for a real Blender parent object."""
    bpy.ops.object.empty_add(type="PLAIN_AXES", align="WORLD", location=(0, 0, 0))
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

    def test_create_marker_success(self, blender_obj_ref, blender_parent_obj, tmp_path):
        # Create a dummy image file for the test
        assets_dir = tmp_path / "assets"
        assets_dir.mkdir()
        test_image_path = assets_dir / "test_marker.png"

        # Create a minimal 1x1 black PNG
        png_data = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
        test_image_path.write_bytes(png_data)

        marker_name = "TestMarker"
        marker_color = (1.0, 0.0, 0.0, 1.0)  # Red

        result_ref = dal.create_marker(blender_obj_ref, marker_name, marker_color, image_path=str(test_image_path))

        marker_obj = result_ref._get_obj()
        assert marker_obj is not None
        assert marker_obj.parent == blender_parent_obj
        assert marker_obj.name == f"{blender_parent_obj.name}_{marker_name}"
        assert marker_obj.type == "EMPTY"
        assert marker_obj.empty_display_type == "IMAGE"
        assert marker_obj.data is not None
        assert marker_obj.data.name == "test_marker.png"
        # Assert that the MARKER_ROLE custom property is set
        assert dal.get_custom_property(result_ref, dal.MARKER_ROLE) == marker_name

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

        # Verify the data_path is simple, not the complex slotted path
        assert fcurve.data_path == data_path
        assert fcurve.array_index == 0

        # Check that the fcurve was created in the correct channelbag
        slot = dal.get_or_create_action_slot(action, slot_name)
        channelbag = dal._get_or_create_channelbag(action, slot)
        assert channelbag.fcurves.find(data_path, index=0) is not None

        fcurve2 = dal.get_or_create_fcurve(action, slot_name, data_path, index=0)
        assert fcurve2 == fcurve

    def test_set_fcurve_keyframes(self):
        action = dal.get_or_create_action("KeyframeAction")
        fcurve = dal.get_or_create_fcurve(action, "TestSlot", "location", index=1)

        keyframes = [(1.0, 10.0), (10.0, 20.0), (20.0, 5.0)]
        dal.set_fcurve_keyframes(fcurve, keyframes)

        assert len(fcurve.keyframe_points) == len(keyframes)
        for i, (frame, value) in enumerate(keyframes):
            kp = fcurve.keyframe_points[i]
            assert kp.co.x == pytest.approx(frame)
            assert kp.co.y == pytest.approx(value)
            assert kp.interpolation == "LINEAR"

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
        # Create the fcurve first
        fcurve = dal.get_or_create_fcurve(action, slot_name, "location", index=2)

        # Now try to retrieve it
        retrieved_fcurve = dal.get_fcurve_from_action(action, slot_name, "location", index=2)
        assert retrieved_fcurve == fcurve

        # Test for non-existent fcurve
        assert dal.get_fcurve_from_action(action, slot_name, "location", index=0) is None

    def test_get_or_create_object_with_parent(self, blender_parent_obj):
        """Tests creating an object with a specified parent."""
        child_name = "ChildObject"
        parent_ref = dal.BlenderObjRef(blender_parent_obj.name)

        child_ref = dal.get_or_create_object(child_name, "EMPTY", parent=parent_ref)
        child_obj = child_ref._get_obj()

        assert child_obj is not None
        assert child_obj.parent == blender_parent_obj

    def test_sample_fcurve(self):
        action = dal.get_or_create_action("SampleAction")
        fcurve = dal.get_or_create_fcurve(action, "TestSlot", "location", index=0)

        keyframes = [(0, 0), (10, 10)]
        dal.set_fcurve_keyframes(fcurve, keyframes)

        start_frame, end_frame = 0, 10
        sampled_data = dal.sample_fcurve(fcurve, start_frame, end_frame)

        assert isinstance(sampled_data, np.ndarray)
        assert len(sampled_data) == 11
        expected = np.arange(0.0, 11.0)
        assert np.allclose(sampled_data, expected)

    def test_set_fcurves_from_numpy(self):
        """Tests the optimized batch function for setting f-curves from numpy data."""
        action = dal.get_or_create_action("NumpyBatchAction")
        start_frame = 10

        # Define the columns and the numpy data array, now including Z coordinate
        columns = [
            ("Slot1", "location", 0),  # X
            ("Slot1", "location", 1),  # Y
            ("Slot1", "location", 2),  # Z
            ("Slot2", '["quality"]', -1),  # Custom property
        ]
        data = np.array(
            [
                [1.0, 2.0, 0.0, 0.9],  # Frame 10
                [1.1, 2.2, 0.0, 0.8],  # Frame 11
                [np.nan, 2.4, 0.0, 0.7],  # Frame 12 (X is nan)
                [1.3, np.nan, np.nan, np.nan],  # Frame 13 (Y, Z and quality are nan)
                [1.4, 2.8, 0.0, 0.5],  # Frame 14
            ]
        )

        # Call the function to test
        dal.set_fcurves_from_numpy(action, columns, start_frame, data)

        # --- Verification ---

        # 1. Verify Slot1, location.x
        fcurve_x = dal.get_fcurve_from_action(action, "Slot1", "location", 0)
        assert fcurve_x is not None
        assert len(fcurve_x.keyframe_points) == 4  # One frame was nan
        assert fcurve_x.keyframe_points[0].co.y == pytest.approx(1.0)

        # 2. Verify Slot1, location.y
        fcurve_y = dal.get_fcurve_from_action(action, "Slot1", "location", 1)
        assert fcurve_y is not None
        assert len(fcurve_y.keyframe_points) == 4  # One frame was nan
        assert fcurve_y.keyframe_points[0].co.y == pytest.approx(2.0)

        # 3. Verify Slot1, location.z
        fcurve_z = dal.get_fcurve_from_action(action, "Slot1", "location", 2)
        assert fcurve_z is not None
        assert len(fcurve_z.keyframe_points) == 4  # One frame was nan
        assert fcurve_z.keyframe_points[0].co.y == pytest.approx(0.0)
        # All z values should be 0
        for kp in fcurve_z.keyframe_points:
            assert kp.co.y == pytest.approx(0.0)

        # 4. Verify Slot2, quality
        fcurve_q = dal.get_fcurve_from_action(action, "Slot2", '["quality"]', -1)
        assert fcurve_q is not None
        assert len(fcurve_q.keyframe_points) == 4  # One frame was nan
        assert fcurve_q.keyframe_points[0].co.y == pytest.approx(0.9)

        # 5. Check interpolation mode on one keyframe
        assert fcurve_x.keyframe_points[0].interpolation == "LINEAR"
