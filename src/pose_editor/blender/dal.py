# SPDX-FileCopyrightText: 2025 Harri Kaimio
#
# SPDX-License-Identifier: BSD-3-Clause

import math
from typing import Generic, Optional, TypeVar

import bpy
import numpy as np


class BlenderObjRef:
    def __init__(self, id: str):
        self._id = id
        self._obj: bpy.types.Object | None = None

    @property
    def name(self) -> str:
        return self._id

    def _get_obj(self) -> bpy.types.Object:
        if self._obj is None:
            self._obj = bpy.data.objects.get(self._id)
        else:
            try:
                _ = self._obj.name  # This will raise ReferenceError if object was deleted
            except ReferenceError:
                self._obj = bpy.data.objects.get(self._id)
        return self._obj


class CollectionRef:
    def __init__(self, id: str):
        self._id = id
        self._collection: bpy.types.Collection | None = None

    def _get_collection(self) -> bpy.types.Collection:
        if self._collection is None:
            self._collection = bpy.data.collections.get(self._id)
        return self._collection


T = TypeVar("T")


class CustomProperty(Generic[T]):
    """
    A generic class to identify and describe custom properties on Blender objects,
    providing type hints for their values.
    """

    def __init__(self, prop_name: str):
        """
        Initializes a CustomProperty.

        Args:
            prop_name: The name of the custom property.
        """
        self._prop_name = prop_name


def set_custom_property(obj_ref: BlenderObjRef, prop: CustomProperty[T], value: T) -> None:
    """
    Sets a custom property on a Blender object.

    Args:
        obj_ref: The Blender object reference to set the property on.
        prop: A CustomProperty object describing the property.
        value: The value to set the property to.
    """
    obj = obj_ref._get_obj()
    if not obj:
        raise ValueError(f"Blender object with ID {obj_ref._id} not found.")
    obj[prop._prop_name] = value


def get_custom_property(obj_ref: BlenderObjRef, prop: CustomProperty[T]) -> T | None:
    """
    Gets a custom property from a Blender object.

    Args:
        obj_ref: The Blender object reference to retrieve the property from.
        prop: A CustomProperty object describing the property.

    Returns:
        The value of the custom property, or None if the property does not exist.
    """
    obj = obj_ref._get_obj()
    if not obj:
        raise ValueError(f"Blender object with ID {obj_ref._id} not found.")

    # Check if the object is still valid (not deleted)
    try:
        _ = obj.name  # This will raise ReferenceError if object was deleted
    except ReferenceError:
        return None

    return obj.get(prop._prop_name)


# Specific custom properties for DataSeries objects
SERIES_NAME = CustomProperty[str]("series_name")
SKELETON = CustomProperty[str]("skeleton")
ACTION_NAME = CustomProperty[str]("action_name")
MARKER_ROLE = CustomProperty[str]("marker_role")
BODY_PART = CustomProperty[str]("body_part")
IS_CAMERA_VIEW = CustomProperty[bool]("is_camera_view")
POSE_EDITOR_OBJECT_TYPE = CustomProperty[str]("pose_editor_object_type")
POSE_EDITOR_OBJECT_ID = CustomProperty[str]("pose_editor_object_id")
CAMERA_VIEW_ID = CustomProperty[str]("camera_view_id")
COLOR = CustomProperty[tuple[float, float, float, float]]("color")
MARKER_DATA_ID = CustomProperty[str]("marker_data_id")
CALIBRATION_CAMERA_NAME = CustomProperty[str]("calibration_camera_name")


def create_collection(name: str, parent_collection: bpy.types.Collection = None) -> bpy.types.Collection:
    """
    Creates a new collection in the scene.

    Args:
        name: The name of the new collection.
        parent_collection: The parent collection. If None, the collection is created in the scene's master collection.

    Returns:
        The new collection.
    """
    if parent_collection is None:
        parent_collection = bpy.context.scene.collection

    collection = bpy.data.collections.new(name)
    parent_collection.children.link(collection)
    return collection


def get_or_create_collection(name: str, parent_collection: bpy.types.Collection = None) -> bpy.types.Collection:
    """
    Gets a collection by name, or creates it if it doesn't exist.

    Args:
        name: The name of the collection.
        parent_collection: The parent collection. If None, the collection is created in the scene's master collection.

    Returns:
        The found or created collection.
    """
    collection = bpy.data.collections.get(name)
    if not collection:
        collection = create_collection(name, parent_collection)
    return collection


def create_empty(name: str, collection: bpy.types.Collection = None, parent_obj: BlenderObjRef = None) -> BlenderObjRef:
    """
    Creates a new empty object in the scene.

    Args:
        name: The name of the new empty.
        collection: The collection to link the empty to. If None, the empty is linked to the scene's master collection.
        parent_obj: The parent object for the new empty, wrapped in a BlenderObjRef.

    Returns:
        The new empty object wrapped in a BlenderObjRef.
    """
    empty = bpy.data.objects.new(name, None)
    if collection is None:
        collection = bpy.context.scene.collection
    collection.objects.link(empty)

    if parent_obj:
        empty.parent = parent_obj._get_obj()
        empty.matrix_parent_inverse.identity()  # Clear parent inverse to keep local transform

    return BlenderObjRef(empty.name)


def add_keyframe(obj_ref: BlenderObjRef, frame: int, values: dict[str, any]) -> None:
    """
    Adds a keyframe to a Blender object.

    Args:
        obj_ref: The Blender object reference.
        frame: The frame number to add the keyframe at.
    """
    blender_object = obj_ref._get_obj()
    if not blender_object:
        raise ValueError(f"Blender object with ID {obj_ref._id} not found.")

    for data_path, value in values.items():
        if data_path == "location":
            blender_object.location = value
        else:
            if len(value) == 1:
                value = value[0]
            blender_object[data_path] = value
        blender_object.keyframe_insert(data_path=f'["{data_path}"]', frame=frame)


def set_fcurve_from_data(obj_ref: BlenderObjRef, data_path: str, keyframes: list[tuple[int, list[float]]]) -> None:
    """
    Sets F-curves for a given data path on a Blender object from a list of keyframe data.

    Args:
        blender_object: The Blender object to set the F-curves on.
        data_path: The data path for the property (e.g., "location", "quality").
        keyframes: A list of (frame_number, [list of values]) tuples. If the property is an array, the values list must match data path array length.
    """
    if not keyframes:
        return

    blender_object = obj_ref._get_obj()
    if not blender_object:
        raise ValueError(f"Blender object with ID {obj_ref._id} not found.")

    # Ensure animation data exists
    if not blender_object.animation_data:
        blender_object.animation_data_create()

    # Ensure an action exists for the animation data
    if not blender_object.animation_data.action:
        blender_object.animation_data.action = bpy.data.actions.new(name=f"{blender_object.name}_Action")

    # Create F-curve
    fcurves = []
    if len(keyframes[0][1]) == 1:
        fcurve = blender_object.animation_data.action.fcurves.new(data_path)
        fcurve.keyframe_points.add(count=len(keyframes))
        fcurves.append(fcurve)
    else:
        for i in range(len(keyframes[0][1])):
            fcurve = blender_object.animation_data.action.fcurves.new(data_path, index=i)
            fcurve.keyframe_points.add(count=len(keyframes))
            fcurves.append(fcurve)

    # Add keyframes
    for i in range(len(keyframes)):
        frame, values = keyframes[i]
        for j in range(len(fcurves)):
            if j < len(values):
                fcurves[j].keyframe_points[i].co = (frame, values[j])
            else:
                print(f"Warning: Not enough values for F-curve index {j} at frame {frame}")

    # Update tangents
    for fcurve in fcurves:
        fcurve.update()

    # Hack to force update
    max_keyframe = keyframes[-1][0]
    print(data_path)
    blender_object.keyframe_insert(data_path, frame=max_keyframe + 1)
    for f in fcurves:
        f.keyframe_points.remove(f.keyframe_points[-1])


def create_marker(
    parent: BlenderObjRef,
    name: str,
    color: tuple[float, float, float, float],
    collection: bpy.types.Collection = None,
    image_path: str = "C:\\Users\\HarriKaimio\\projects\\pose-editor\\assets\\marker-128x128.png",
    body_part: str | None = None,
) -> BlenderObjRef:
    """
    Creates a new empty object with an image, to be used as a marker.

    Args:
        parent: The parent BlenderObjRef for the marker.
        name: The name of the marker, which will be appended to the parent's name.
        color: A tuple (R, G, B, A) representing the emission color of the marker.
        collection: The collection to link the marker to.
        image_path: The path to the image file to use for the empty.
        body_part: The name of the body part this marker belongs to.

    Returns:
        The newly created marker object wrapped in a BlenderObjRef.
    """
    parent_obj = parent._get_obj()
    if not parent_obj:
        raise ValueError(f"Parent object with ID {parent._id} not found.")

    # Create an empty with an image
    marker_obj = bpy.data.objects.new(f"{parent_obj.name}_{name}", None)
    marker_obj.empty_display_type = "IMAGE"
    marker_obj.empty_display_size = 4

    # Load the image
    try:
        img = load_image(image_path)
        marker_obj.data = img
    except RuntimeError as e:
        print(f"Could not load marker image: {e}")

    if collection:
        collection.objects.link(marker_obj)

    # Set parent
    marker_obj.parent = parent_obj
    marker_obj.matrix_parent_inverse.identity()  # Clear parent inverse to keep local transform

    # Set name
    marker_obj.name = f"{parent_obj.name}_{name}"

    # Add "quality" custom property
    marker_obj["quality"] = 1.0

    # Store the marker role and body part as custom properties
    marker_ref = BlenderObjRef(marker_obj.name)
    set_custom_property(marker_ref, MARKER_ROLE, name)
    if body_part:
        set_custom_property(marker_ref, BODY_PART, body_part)

    # Store original color components as custom properties for drivers
    marker_obj["_original_color_r"] = color[0]
    marker_obj["_original_color_g"] = color[1]
    marker_obj["_original_color_b"] = color[2]
    marker_obj["_original_color_a"] = color[3]

    # Drive the object color with the quality
    for i in range(4):  # R, G, B, A
        driver = marker_obj.driver_add("color", i).driver
        driver.type = "SCRIPTED"
        driver.expression = f"get_quality_driven_color_component(quality, r, g, b, a, {i})"

        var_quality = driver.variables.new()
        var_quality.name = "quality"
        var_quality.type = "SINGLE_PROP"
        var_quality.targets[0].id = marker_obj
        var_quality.targets[0].data_path = '["quality"]'

        var_r = driver.variables.new()
        var_r.name = "r"
        var_r.type = "SINGLE_PROP"
        var_r.targets[0].id = marker_obj
        var_r.targets[0].data_path = '["_original_color_r"]'

        var_g = driver.variables.new()
        var_g.name = "g"
        var_g.type = "SINGLE_PROP"
        var_g.targets[0].id = marker_obj
        var_g.targets[0].data_path = '["_original_color_g"]'

        var_b = driver.variables.new()
        var_b.name = "b"
        var_b.type = "SINGLE_PROP"
        var_b.targets[0].id = marker_obj
        var_b.targets[0].data_path = '["_original_color_b"]'

        var_a = driver.variables.new()
        var_a.name = "a"
        var_a.type = "SINGLE_PROP"
        var_a.targets[0].id = marker_obj
        var_a.targets[0].data_path = '["_original_color_a"]'

    # Add driver for hide_viewport based on "quality"
    driver = marker_obj.driver_add("hide_viewport").driver
    driver.type = "SCRIPTED"
    driver.expression = "quality < 0"

    var_quality_hide = driver.variables.new()
    var_quality_hide.name = "quality"
    var_quality_hide.type = "SINGLE_PROP"
    var_quality_hide.targets[0].id = marker_obj
    var_quality_hide.targets[0].data_path = '["quality"]'

    return marker_ref


def create_camera(
    name: str, collection: bpy.types.Collection = None, parent_obj: BlenderObjRef = None
) -> BlenderObjRef:
    """
    Creates a new camera object in the scene.

    Args:
        name: The name of the new camera.
        collection: The collection to link the camera to. If None, the camera is linked to the scene's master collection.
        parent_obj: The parent object for the new camera, wrapped in a BlenderObjRef.

    Returns:
        The new camera object wrapped in a BlenderObjRef.
    """
    camera_data = bpy.data.cameras.new(name)
    camera_object = bpy.data.objects.new(name, camera_data)

    if collection is None:
        collection = bpy.context.scene.collection
    collection.objects.link(camera_object)

    if parent_obj:
        camera_object.parent = parent_obj._get_obj()
        camera_object.matrix_parent_inverse.identity()

    return BlenderObjRef(camera_object.name)


def load_movie_clip(filepath: str) -> bpy.types.MovieClip:
    """
    Loads a movie clip from a file path.

    Args:
        filepath: The path to the movie file.

    Returns:
        The loaded movie clip.
    """
    return bpy.data.movieclips.load(filepath)


def load_image(filepath: str) -> bpy.types.Image:
    """
    Loads an image from a file path.

    Args:
        filepath: The path to the image file.

    Returns:
        The loaded image.
    """
    return bpy.data.images.load(filepath, check_existing=True)


def set_camera_background(camera_obj_ref: BlenderObjRef, movie_clip: bpy.types.MovieClip) -> None:
    """
    Sets the background of a camera to a movie clip.

    Args:
        camera_obj_ref: The camera object reference.
        movie_clip: The movie clip to set as the background.
    """
    camera_obj = camera_obj_ref._get_obj()
    if not camera_obj or camera_obj.type != "CAMERA":
        raise ValueError(f"Object {camera_obj_ref.name} is not a camera.")

    camera_obj.data.show_background_images = True
    bg = camera_obj.data.background_images.new()
    bg.source = "MOVIE_CLIP"
    bg.clip = movie_clip


def set_camera_ortho(camera_obj_ref: BlenderObjRef, ortho_scale: float) -> None:
    """
    Sets a camera to orthographic projection.

    Args:
        camera_obj_ref: The camera object reference.
        ortho_scale: The orthographic scale.
    """
    camera_obj = camera_obj_ref._get_obj()
    if not camera_obj or camera_obj.type != "CAMERA":
        raise ValueError(f"Object {camera_obj_ref.name} is not a camera.")

    camera_obj.data.type = "ORTHO"
    camera_obj.data.ortho_scale = ortho_scale


def get_or_create_object(
    name: str, obj_type: str, collection_name: str | None = None, parent: Optional["BlenderObjRef"] = None
) -> "BlenderObjRef":
    """Gets an object by name, or creates it if it doesn't exist.

    Args:
        name: The name for the object.
        obj_type: The type of object to create (e.g., 'EMPTY', 'ARMATURE').
        collection_name: The name of the collection to place the object in.
                         If the collection doesn't exist, it will be created.
        parent: An optional parent for the object.

    Returns:
        A BlenderObjRef wrapper for the found or created object.
    """
    # Note: When parenting, Blender may rename the object if a name collision
    # occurs under the new parent. We retrieve the name from the final object.
    obj = bpy.data.objects.get(name)

    if obj and parent:
        parent_obj = parent._get_obj()
        if obj.parent != parent_obj:
            obj.parent = parent_obj

    if not obj:
        if obj_type == "EMPTY":
            obj = bpy.data.objects.new(name, None)
        elif obj_type == "ARMATURE":
            armature = bpy.data.armatures.new(name)
            obj = bpy.data.objects.new(name, armature)
        else:
            raise NotImplementedError(f"Object creation for type '{obj_type}' is not implemented.")

        if collection_name:
            target_collection = bpy.data.collections.get(collection_name)
            if not target_collection:
                target_collection = bpy.data.collections.new(collection_name)
                bpy.context.scene.collection.children.link(target_collection)

            # Unlink from default scene collection if linking to a specific one
            if obj.name in bpy.context.scene.collection.objects:
                bpy.context.scene.collection.objects.unlink(obj)
            target_collection.objects.link(obj)
        else:
            # If no collection is specified, link to the scene's master collection
            bpy.context.scene.collection.objects.link(obj)

        if parent:
            parent_obj = parent._get_obj()
            if parent_obj:
                obj.parent = parent_obj

    return BlenderObjRef(obj.name)


def get_or_create_action(action_name: str) -> bpy.types.Action:
    """Gets an Action data-block by name, or creates it if it doesn't exist.

    Args:
        action_name: The name of the Action.

    Returns:
        The found or created Action data-block.
    """
    action = bpy.data.actions.get(action_name)
    if not action:
        action = bpy.data.actions.new(action_name)
    return action


def _get_prefixed_slot_name(slot_name: str) -> str:
    """Returns the name of the slot with Blender's internal prefix.

    For id_type='OBJECT', Blender prepends 'OB' to the name provided by the user
    to form the key in the `action.slots` collection.

    Args:
        slot_name: The user-facing name of the slot.

    Returns:
        The internal, prefixed name used as the key in the collection.
    """
    return f"OB{slot_name}"


def action_has_slot(action: bpy.types.Action, slot_name: str) -> bool:
    """Checks if an Action has a specific slot, checking by its prefixed name.

    Args:
        action: The Action to check.
        slot_name: The user-facing name of the slot.

    Returns:
        True if the slot exists, False otherwise.
    """
    prefixed_name = _get_prefixed_slot_name(slot_name)
    return prefixed_name in action.slots


def get_or_create_action_slot(action: bpy.types.Action, slot_name: str) -> bpy.types.ActionSlot:
    """Gets a slot from an action, or creates it if it doesn't exist.

    Handles the Blender API nuance where the key for the slot in the collection
    is automatically prefixed based on its `id_type`.

    Args:
        action: The action to get the slot from.
        slot_name: The desired user-facing name for the slot.

    Returns:
        The found or created ActionSlot.
    """
    prefixed_name = _get_prefixed_slot_name(slot_name)
    slot = action.slots.get(prefixed_name)
    if not slot:
        # Pass the UN-PREFIXED name to new(). Blender handles creating the
        # correct key (e.g., "OB" + slot_name) internally.
        slot = action.slots.new(name=slot_name, id_type="OBJECT")
    return slot


def _get_or_create_channelbag(action: bpy.types.Action, slot: bpy.types.ActionSlot) -> bpy.types.ActionChannelbag:
    """
    Gets or creates the channelbag for a specific action and slot.
    A channelbag is technically an ActionStripKeyframe.
    """
    if not action.layers:
        layer = action.layers.new("Layer")
    else:
        layer = action.layers[0]

    if not layer.strips:
        strip = layer.strips.new(type="KEYFRAME")
    else:
        strip = layer.strips[0]

    return strip.channelbag(slot, ensure=True)


def get_or_create_fcurve(action: bpy.types.Action, slot_name: str, data_path: str, index: int = -1) -> bpy.types.FCurve:
    """Gets or creates an F-Curve within the correct channelbag for a slot.

    Args:
        action: The Action data-block.
        slot_name: The user-facing name of the slot to target.
        data_path: The property to animate (e.g., "location").
        index: The array index for vector properties (e.g., 0 for X).

    Returns:
        The found or created FCurve.
    """
    slot = get_or_create_action_slot(action, slot_name)
    channelbag = _get_or_create_channelbag(action, slot)

    fcurve = channelbag.fcurves.find(data_path, index=index)
    if not fcurve:
        fcurve = channelbag.fcurves.new(data_path, index=index)
    return fcurve


def set_fcurve_keyframes(fcurve: bpy.types.FCurve, keyframes: list[tuple[float, float]]) -> None:
    """Populates an F-Curve with keyframes and sets their interpolation to LINEAR.

    Args:
        fcurve: The F-Curve to modify.
        keyframes: A list of (frame, value) tuples.
    """
    fcurve.keyframe_points.clear()
    for frame, value in keyframes:
        kp = fcurve.keyframe_points.insert(frame, value)
        kp.interpolation = "LINEAR"
    fcurve.update()


def assign_action_to_object(obj_ref: "BlenderObjRef", action: bpy.types.Action, slot_name: str) -> None:
    """Assigns a shared Action and a specific ActionSlot to an object.

    This function ensures the object's animation data is set up to be driven
    by a specific slot within a larger Action.

    Args:
        obj_ref: A reference to the object to assign the action to.
        action: The Action containing the animation data.
        slot_name: The user-facing name of the slot that should drive the object.
    """
    obj = obj_ref._get_obj()
    if not obj:
        raise ValueError(f"Blender object with ID {obj_ref._id} not found.")
    if not obj.animation_data:
        obj.animation_data_create()

    obj.animation_data.action = action

    # Ensure the slot is created before assigning
    get_or_create_action_slot(action, slot_name)
    prefixed_name = _get_prefixed_slot_name(slot_name)
    obj.animation_data.action_slot = action.slots[prefixed_name]


def create_armature_action_from_marker_data(
    action_name: str,
    marker_action: bpy.types.Action,
    armature_obj_ref: BlenderObjRef,
    marker_role_to_bone_name: dict[str, str],
) -> bpy.types.Action:
    """Creates a new action for an armature by copying and remapping F-curves from MarkerData.

    MarkerData creates actions with per-marker slots and data_path="location".
    Armatures need ONE slot with data_path='pose.bones["BoneName"].location'.

    Args:
        action_name: Name for the new armature action.
        marker_action: The source action from MarkerData with per-marker slots.
        armature_obj_ref: The armature object reference.
        marker_role_to_bone_name: Mapping from marker roles to bone names.

    Returns:
        The new action configured for bone animation.
    """
    # Create new action
    new_action = bpy.data.actions.new(action_name)

    # Create slot for the armature (using OBJECT id_type)
    armature_slot = get_or_create_action_slot(new_action, armature_obj_ref.name)

    # Get the channelbag for the armature slot
    armature_channelbag = _get_or_create_channelbag(new_action, armature_slot)

    # Copy F-curves from each marker slot, remapping data paths
    for marker_role, bone_name in marker_role_to_bone_name.items():
        # Get the source channelbag for this marker
        try:
            marker_slot = get_or_create_action_slot(marker_action, marker_role)
            source_channelbag = _get_or_create_channelbag(marker_action, marker_slot)
        except Exception:
            # Marker might not have data yet
            continue

        # Copy location F-curves with remapped data paths
        for axis_index in range(3):
            source_fcurve = source_channelbag.fcurves.find("location", index=axis_index)
            if source_fcurve:
                # Create new F-curve with bone-specific data path
                bone_data_path = f'pose.bones["{bone_name}"].location'
                target_fcurve = armature_channelbag.fcurves.new(bone_data_path, index=axis_index)

                # Copy keyframes
                for kf in source_fcurve.keyframe_points:
                    new_kf = target_fcurve.keyframe_points.insert(kf.co[0], kf.co[1])
                    new_kf.interpolation = kf.interpolation

                target_fcurve.update()

        # Copy custom property F-curves (reprojection_error, etc.)
        for fcurve in source_channelbag.fcurves:
            if fcurve.data_path.startswith('["'):
                # Custom property F-curve
                # For bones, target pose bones: pose.bones["BoneName"]["property"]
                bone_data_path = f'pose.bones["{bone_name}"]{fcurve.data_path}'
                target_fcurve = armature_channelbag.fcurves.new(bone_data_path, index=fcurve.array_index)

                # Copy keyframes
                for kf in fcurve.keyframe_points:
                    new_kf = target_fcurve.keyframe_points.insert(kf.co[0], kf.co[1])
                    new_kf.interpolation = kf.interpolation

                target_fcurve.update()

    return new_action


def get_children_of_object(obj_ref: "BlenderObjRef", recursive: bool = False) -> list["BlenderObjRef"]:
    """Gets all direct or recursive children of a given Blender object.

    Args:
        obj_ref: A reference to the parent object.
        recursive: If True, retrieves all descendants; otherwise, only direct children.

    Returns:
        A list of BlenderObjRef wrappers for the children.
    """
    obj = obj_ref._get_obj()
    if not obj:
        raise ValueError(f"Blender object with ID {obj_ref._id} not found.")

    children = []
    if not recursive:
        children.extend([BlenderObjRef(child.name) for child in obj.children])
    else:
        queue = list(obj.children)
        while queue:
            current_obj = queue.pop(0)
            children.append(BlenderObjRef(current_obj.name))
            queue.extend(current_obj.children)
    return children


def get_object_by_name(name: str) -> Optional["BlenderObjRef"]:
    """Returns a Blender object by its name, wrapped in a BlenderObjRef.

    Args:
        name: The name of the object to find.

    Returns:
        A BlenderObjRef for the object, or None if not found.
    """
    obj = bpy.data.objects.get(name)
    if obj:
        return BlenderObjRef(obj.name)
    return None


def find_object_by_property(prop: CustomProperty[T], value: T) -> Optional["BlenderObjRef"]:
    """Finds the first object in the scene with a given custom property value.

    Args:
        prop: The CustomProperty to search for.
        value: The value the property should have.

    Returns:
        A BlenderObjRef for the found object, or None.
    """
    for obj in bpy.context.scene.objects:
        if prop._prop_name in obj and obj[prop._prop_name] == value:
            return BlenderObjRef(obj.name)
    return None


def find_all_objects_by_property(prop: CustomProperty[T], value: T) -> list[BlenderObjRef]:
    """Finds all objects in the scene with a given custom property value.

    Args:
        prop: The CustomProperty to search for.
        value: The value the property should have.

    Returns:
        A list of BlenderObjRef wrappers for the found objects.
    """
    found_objects = []
    for obj in bpy.context.scene.objects:
        if prop._prop_name in obj and obj[prop._prop_name] == value:
            found_objects.append(BlenderObjRef(obj.name))
    return found_objects


def get_fcurve_from_action(
    action: bpy.types.Action, slot_name: str, data_path: str, index: int = -1
) -> bpy.types.FCurve | None:
    """Gets an F-Curve from the correct channelbag for a slot.

    Args:
        action: The Action to search within.
        slot_name: The user-facing name of the slot the F-Curve targets.
        data_path: The property animated by the F-Curve (e.g., "location").
        index: The array index for vector properties.

    Returns:
        The found F-Curve, or None if it does not exist.
    """
    slot = get_or_create_action_slot(action, slot_name)
    channelbag = _get_or_create_channelbag(action, slot)
    return channelbag.fcurves.find(data_path, index=index)


def get_scene_frame_range() -> tuple[int, int]:
    """Returns the start and end frame of the current scene.

    Returns:
        A tuple containing the start and end frame numbers.
    """
    return bpy.context.scene.frame_start, bpy.context.scene.frame_end

def update_scene_end_frame(new_end_frame: int) -> None:
    """Updates the end frame of the current scene.

    Args:
        new_end_frame: The new end frame number to set.
    """
    _, current_end_frame = get_scene_frame_range()
    if new_end_frame > current_end_frame:
        bpy.context.scene.frame_end = new_end_frame


def add_bones_in_bulk(
    armature_obj_ref: BlenderObjRef,
    bones_to_add: list[tuple[str, tuple[float, float, float], tuple[float, float, float]]],
) -> None:
    """
    Adds multiple bones to an armature in a single Edit Mode session for efficiency.

    Args:
        armature_obj_ref: The armature object to add the bones to.
        bones_to_add: A list of tuples, where each tuple contains
                      (bone_name, head_position, tail_position).
    """
    armature_obj = armature_obj_ref._get_obj()
    if not armature_obj or armature_obj.type != "ARMATURE":
        raise ValueError(f"Object {armature_obj_ref.name} is not an armature.")

    # Ensure the armature is the active object
    bpy.context.view_layer.objects.active = armature_obj
    # Enter Edit Mode once
    bpy.ops.object.mode_set(mode="EDIT")

    try:
        edit_bones = armature_obj.data.edit_bones
        for bone_name, head, tail in bones_to_add:
            bone = edit_bones.new(bone_name)
            bone.head = head
            bone.tail = tail
    finally:
        # Always exit Edit Mode, even if an error occurs
        bpy.ops.object.mode_set(mode="OBJECT")


def add_bone(
    armature_obj_ref: BlenderObjRef, bone_name: str, head: tuple[float, float, float], tail: tuple[float, float, float]
) -> None:
    """Adds a bone to an armature.

    Args:
        armature_obj_ref: The armature object to add the bone to.
        bone_name: The name of the new bone.
        head: The head position of the bone.
        tail: The tail position of the bone.
    """
    armature_obj = armature_obj_ref._get_obj()
    if not armature_obj or armature_obj.type != "ARMATURE":
        raise ValueError(f"Object {armature_obj_ref.name} is not an armature.")

    bpy.context.view_layer.objects.active = armature_obj
    bpy.ops.object.mode_set(mode="EDIT")

    bone = armature_obj.data.edit_bones.new(bone_name)
    bone.head = head
    bone.tail = tail

    bpy.ops.object.mode_set(mode="OBJECT")


def add_bone_constraint(
    armature_obj_ref: BlenderObjRef,
    bone_name: str,
    constraint_type: str,
    target_obj_ref: BlenderObjRef,
    subtarget_name: str = None,
) -> None:
    """Adds a constraint to a bone.

    Args:
        armature_obj_ref: The armature object.
        bone_name: The name of the bone to add the constraint to.
        constraint_type: The type of constraint to add (e.g., 'COPY_LOCATION', 'STRETCH_TO').
        target_obj_ref: The target object for the constraint.
        subtarget_name: The name of the subtarget (e.g., for STRETCH_TO).
    """
    armature_obj = armature_obj_ref._get_obj()
    if not armature_obj or armature_obj.type != "ARMATURE":
        raise ValueError(f"Object {armature_obj_ref.name} is not an armature.")

    bone = armature_obj.pose.bones.get(bone_name)
    if not bone:
        raise ValueError(f"Bone {bone_name} not found in armature {armature_obj.name}.")

    constraint = bone.constraints.new(type=constraint_type)
    constraint.target = target_obj_ref._get_obj()
    if subtarget_name:
        constraint.subtarget = subtarget_name
    if constraint_type == "STRETCH_TO":
        constraint.rest_length = 1.0


def set_armature_display_stick(armature_obj_ref: BlenderObjRef) -> None:
    """Sets the armature display to 'STICK'.

    Args:
        armature_obj_ref: The armature object.
    """
    armature_obj = armature_obj_ref._get_obj()
    if not armature_obj or armature_obj.type != "ARMATURE":
        raise ValueError(f"Object {armature_obj_ref.name} is not an armature.")

    armature_obj.data.display_type = "STICK"


def add_bone_driver(
    armature_obj_ref: BlenderObjRef,
    bone_name: str,
    data_path: str,
    expression: str,
    variables: list[tuple[str, str, str, str]],
) -> None:
    """Adds a driver to a bone property.

    Args:
        armature_obj_ref: The armature object.
        bone_name: The name of the bone.
        data_path: The property to drive (e.g., 'location[0]', 'hide').
        expression: The driver expression.
        variables: A list of tuples, where each tuple defines a driver variable:
                   (var_name, var_type, target_id, data_path)
    """
    armature_obj = armature_obj_ref._get_obj()
    if not armature_obj or armature_obj.type != "ARMATURE":
        raise ValueError(f"Object {armature_obj_ref.name} is not an armature.")

    # Use pose bones instead of data bones for drivers
    pose_bone = armature_obj.pose.bones.get(bone_name)
    if not pose_bone:
        raise ValueError(f"Bone {bone_name} not found in armature {armature_obj.name}.")

    # For array properties like location[0], split into property and index
    if "[" in data_path and "]" in data_path:
        prop_name = data_path.split("[")[0]
        array_index = int(data_path.split("[")[1].rstrip("]"))
        driver = pose_bone.driver_add(prop_name, array_index).driver
    else:
        driver = pose_bone.driver_add(data_path).driver

    driver.type = "SCRIPTED"
    driver.expression = expression

    for var_name, var_type, target_id, target_data_path in variables:
        var = driver.variables.new()
        var.name = var_name
        var.type = var_type
        var.targets[0].id = bpy.data.objects.get(target_id)
        var.targets[0].data_path = target_data_path


def sample_fcurve(fcurve: bpy.types.FCurve, start_frame: int, end_frame: int) -> np.ndarray:
    """Samples an F-Curve's values over a given frame range.

    Args:
        fcurve: The F-Curve to sample.
        start_frame: The first frame to sample (inclusive).
        end_frame: The last frame to sample (inclusive).

    Returns:
        A NumPy array of the evaluated F-Curve values for each frame.
    """
    frames = np.arange(start_frame, end_frame + 1)
    values = np.array([fcurve.evaluate(f) for f in frames])
    return values


def get_fcurve_on_object(obj_ref: BlenderObjRef, data_path: str, index: int = -1) -> bpy.types.FCurve | None:
    """Gets a specific F-Curve from an object's default action.

    Args:
        obj_ref: The object to get the F-Curve from.
        data_path: The data path of the property (e.g., '["my_prop"]').
        index: The array index for vector properties.

    Returns:
        The found F-Curve, or None.
    """
    obj = obj_ref._get_obj()
    if not obj or not obj.animation_data:
        return None

    action = obj.animation_data.action
    slot = obj.animation_data.action_slot

    if not action or not slot:
        return None

    channelbag = _get_or_create_channelbag(action, slot)

    return channelbag.fcurves.find(data_path, index=index)


def get_fcurve_keyframes(fcurve: bpy.types.FCurve) -> list[tuple[float, float]]:
    """Extracts all keyframe points from an F-Curve.

    Args:
        fcurve: The F-Curve to read from.

    Returns:
        A list of (frame, value) tuples.
    """
    if not fcurve:
        return []
    return [(kp.co[0], kp.co[1]) for kp in fcurve.keyframe_points]


def get_fcurve_keyframes_in_range(
    fcurve: bpy.types.FCurve, start_frame: int, end_frame: int
) -> list[tuple[float, float]]:
    """Extracts keyframe points from an F-Curve within a given frame range.

    Args:
        fcurve: The F-Curve to read from.
        start_frame: The starting frame of the range (inclusive).
        end_frame: The ending frame of the range (inclusive).

    Returns:
        A list of (frame, value) tuples within the specified range.
    """
    if not fcurve:
        return []

    return [(kp.co[0], kp.co[1]) for kp in fcurve.keyframe_points if start_frame <= kp.co[0] <= end_frame]


def replace_fcurve_keyframes_in_range(
    fcurve: bpy.types.FCurve, start_frame: int, end_frame: int, new_keyframes: list[tuple[float, float]], interpolation: str = "LINEAR"
):
    """Replaces keyframes in a given range with a new set of keyframes.

    This function first removes all keyframes within the specified range and then
    inserts the new ones.

    Args:
        fcurve: The F-Curve to modify.
        start_frame: The starting frame of the range to clear (inclusive).
        end_frame: The ending frame of the range to clear (inclusive).
        new_keyframes: A list of (frame, value) tuples to insert.
    """
    # Remove existing keyframes in the specified range
    # Iterate backwards when removing items from a list
    for kp in reversed(fcurve.keyframe_points):
        if start_frame <= kp.co[0] <= end_frame:
            fcurve.keyframe_points.remove(kp)

    # Add the new keyframes
    for frame, value in new_keyframes:
        kp = fcurve.keyframe_points.insert(frame, value)
        kp.interpolation = interpolation

    fcurve.update()


def get_animation_data_as_numpy(
    action: bpy.types.Action, columns: list[tuple[str, str, int]], start_frame: int, end_frame: int
) -> np.ndarray:
    """Reads animation data from a slotted Action into a NumPy array.

    This is the counterpart to `set_fcurves_from_numpy`.

    Args:
        action: The Action to read data from.
        columns: A list of (slot_name, data_path, index) tuples describing what to read.
        start_frame: The first frame of the range to read (inclusive).
        end_frame: The last frame of the range to read (inclusive).

    Returns:
        A 2D NumPy array of shape (frames, columns) with the animation data.
    """
    if not action or not columns:
        return np.array([])

    num_frames = end_frame - start_frame + 1
    num_columns = len(columns)
    data = np.full((num_frames, num_columns), np.nan)

    for col_idx, (slot_name, data_path, index) in enumerate(columns):
        fcurve = get_fcurve_from_action(action, slot_name, data_path, index if index is not None else -1)
        if fcurve:
            for frame_offset in range(num_frames):
                frame = start_frame + frame_offset
                data[frame_offset, col_idx] = fcurve.evaluate(float(frame))

    return data


def replace_fcurve_segment_from_numpy(
    action: bpy.types.Action,
    columns: list[tuple[str, str, int]],
    start_frame: int,
    end_frame: int,
    data: np.ndarray,
    interpolation: str = "LINEAR"
) -> None:
    """Replaces a segment of multiple F-Curves in an Action from a NumPy array.

    This function iterates through each F-Curve defined by 'columns', removes
    existing keyframes within the [start_frame, end_frame] range, and then
    inserts new keyframes from the provided NumPy array 'data'.

    Args:
        action: The Action to modify.
        columns: A list of tuples, where each tuple defines an F-Curve and
                 corresponds to a column in the data array. The tuple format is
                 (slot_name, data_path, index).
        start_frame: The starting frame number for the segment to replace.
        end_frame: The ending frame number for the segment to replace.
        data: A 2D NumPy array of shape (frames, columns) containing the
              animation data for the segment. The frames in this array are
              relative to 'start_frame'.
    """
    if not action or not columns or data.size == 0:
        return

    num_frames_in_data = data.shape[0]

    for col_idx, (slot_name, data_path, index) in enumerate(columns):
        fcurve = get_or_create_fcurve(action, slot_name, data_path, index if index is not None else -1)

        new_keyframes_for_fcurve = []
        for frame_offset in range(num_frames_in_data):
            current_frame = start_frame + frame_offset
            # Ensure we don't go beyond the specified end_frame for replacement
            if current_frame > end_frame:
                break
            value = data[frame_offset, col_idx]
            if not np.isnan(value):
                new_keyframes_for_fcurve.append((float(current_frame), value))

        replace_fcurve_keyframes_in_range(fcurve, start_frame, end_frame, new_keyframes_for_fcurve, interpolation)

    # Update all F-Curves.
    for chb in action.layers[0].strips[0].channelbags:
        for fcurve in chb.fcurves:
            fcurve.update()


def set_fcurves_from_numpy(
    action: bpy.types.Action, columns: list[tuple[str, str, int]], start_frame: int, data: np.ndarray, interpolation: str = "LINEAR"
) -> None:
    """Populates multiple F-Curves in an Action from a single NumPy array.

    This function is optimized to write data in batches. It first creates all
    necessary F-Curves, then pre-allocates the keyframe points for each curve,
    and finally iterates through the NumPy data to set the coordinates for each
    keyframe. This is significantly faster than inserting keyframes one by one.

    Args:
        action: The Action to add the F-Curves to.
        columns: A list of tuples, where each tuple defines an F-Curve and
                 corresponds to a column in the data array. The tuple format is
                 (slot_name, data_path, index).
        start_frame: The starting frame number for the animation data.
        data: A 2D NumPy array of shape (frames, columns) containing the
              animation data. A `np.nan` value will result in no keyframe
              being created for that frame.
    """
    if not action or not columns or data.size == 0:
        return

    num_frames = data.shape[0]

    # 1. Get or create all F-Curves first and clear existing data.
    fcurves = []
    for slot_name, data_path, index in columns:
        fcurve = get_or_create_fcurve(action, slot_name, data_path, index if index is not None else -1)
        fcurve.keyframe_points.clear()
        fcurves.append(fcurve)

    # 2. Pre-calculate the number of valid keyframes for each F-Curve.
    valid_keyframe_counts = [np.count_nonzero(~np.isnan(data[:, i])) for i in range(data.shape[1])]

    # 3. Add the required number of keyframe points to each F-Curve in a batch.
    for i, fcurve in enumerate(fcurves):
        if valid_keyframe_counts[i] > 0:
            fcurve.keyframe_points.add(count=valid_keyframe_counts[i])

    # 4. Iterate through the data and set the keyframes.
    keyframe_indices = [0] * len(fcurves)
    for frame_offset in range(num_frames):
        current_frame = start_frame + frame_offset
        for col_idx, fcurve in enumerate(fcurves):
            value = data[frame_offset, col_idx]
            if not np.isnan(value):
                kp_idx = keyframe_indices[col_idx]
                kp = fcurve.keyframe_points[kp_idx]
                kp.co = (float(current_frame), value)
                kp.interpolation = interpolation
                keyframe_indices[col_idx] += 1

    # 5. Update all F-Curves.
    for fcurve in fcurves:
        fcurve.update()

def shift_action(action: bpy.types.Action, frame_delta: int) -> None:
    """Shifts all keyframes in an Action by a given frame delta.

    Args:
        action: The Action to modify.
        frame_delta: The amount to shift keyframes by (can be positive or negative).
    """
    if not action:
        return

    for channelbag in action.layers[0].strips[0].channelbags:
        for fcurve in channelbag.fcurves:
            for kp in fcurve.keyframe_points:
                kp.co[0] += frame_delta
            fcurve.update()


# Rigging-specific DAL functions

def create_bone_collection(armature_obj_ref: BlenderObjRef, collection_name: str) -> None:
    """Creates a bone collection in an armature.

    Args:
        armature_obj_ref: The armature object.
        collection_name: Name of the bone collection to create.
    """
    armature_obj = armature_obj_ref._get_obj()
    if not armature_obj or armature_obj.type != "ARMATURE":
        raise ValueError(f"Object {armature_obj_ref.name} is not an armature.")

    # Check if collection already exists
    if collection_name in armature_obj.data.collections:
        return

    # Create new bone collection
    bone_collection = armature_obj.data.collections.new(collection_name)
    return bone_collection


def move_bone_to_collection(armature_obj_ref: BlenderObjRef, bone_name: str, collection_name: str) -> None:
    """Moves a bone to a specific bone collection.

    Args:
        armature_obj_ref: The armature object.
        bone_name: Name of the bone to move.
        collection_name: Name of the target bone collection.
    """
    armature_obj = armature_obj_ref._get_obj()
    if not armature_obj or armature_obj.type != "ARMATURE":
        raise ValueError(f"Object {armature_obj_ref.name} is not an armature.")

    bone = armature_obj.data.bones.get(bone_name)
    if not bone:
        raise ValueError(f"Bone {bone_name} not found in armature {armature_obj.name}.")

    collection = armature_obj.data.collections.get(collection_name)
    if not collection:
        raise ValueError(f"Bone collection {collection_name} not found in armature {armature_obj.name}.")

    # Remove from current collections
    for coll in bone.collections:
        coll.unassign(bone)

    # Add to target collection
    collection.assign(bone)


def set_bone_deform(armature_obj_ref: BlenderObjRef, bone_name: str, use_deform: bool) -> None:
    """Sets whether a bone is used for deformation.

    Args:
        armature_obj_ref: The armature object.
        bone_name: Name of the bone.
        use_deform: Whether the bone should be used for deformation.
    """
    armature_obj = armature_obj_ref._get_obj()
    if not armature_obj or armature_obj.type != "ARMATURE":
        raise ValueError(f"Object {armature_obj_ref.name} is not an armature.")

    bone = armature_obj.data.bones.get(bone_name)
    if not bone:
        raise ValueError(f"Bone {bone_name} not found in armature {armature_obj.name}.")

    bone.use_deform = use_deform


def set_bone_display_type(armature_obj_ref: BlenderObjRef, bone_name: str, display_type: str) -> None:
    """Sets the display type for a bone.

    Args:
        armature_obj_ref: The armature object.
        bone_name: Name of the bone.
        display_type: Display type ('WIRE', 'STICK', 'BBONE', 'ENVELOPE', 'OCTAHEDRAL').
    """
    armature_obj = armature_obj_ref._get_obj()
    if not armature_obj or armature_obj.type != "ARMATURE":
        raise ValueError(f"Object {armature_obj_ref.name} is not an armature.")

    bone = armature_obj.data.bones.get(bone_name)
    if not bone:
        raise ValueError(f"Bone {bone_name} not found in armature {armature_obj.name}.")

    # Set display type on the bone's custom object or use global setting
    bone.display_type = display_type


def parent_bone_to_bone(armature_obj_ref: BlenderObjRef, child_bone: str, parent_bone: str,
                       use_connect: bool = False) -> None:
    """Parents one bone to another.

    Args:
        armature_obj_ref: The armature object.
        child_bone: Name of the child bone.
        parent_bone: Name of the parent bone.
        use_connect: Whether to connect the bones.
    """
    armature_obj = armature_obj_ref._get_obj()
    if not armature_obj or armature_obj.type != "ARMATURE":
        raise ValueError(f"Object {armature_obj_ref.name} is not an armature.")

    # Need to be in edit mode to modify bone hierarchy
    bpy.context.view_layer.objects.active = armature_obj
    bpy.ops.object.mode_set(mode="EDIT")

    child_edit_bone = armature_obj.data.edit_bones.get(child_bone)
    parent_edit_bone = armature_obj.data.edit_bones.get(parent_bone)

    if not child_edit_bone:
        bpy.ops.object.mode_set(mode="OBJECT")
        raise ValueError(f"Child bone {child_bone} not found in armature {armature_obj.name}.")

    if not parent_edit_bone:
        bpy.ops.object.mode_set(mode="OBJECT")
        raise ValueError(f"Parent bone {parent_bone} not found in armature {armature_obj.name}.")

    child_edit_bone.parent = parent_edit_bone
    child_edit_bone.use_connect = use_connect

    bpy.ops.object.mode_set(mode="OBJECT")


def get_bone_position(armature_obj_ref: BlenderObjRef, bone_name: str, position: str) -> tuple[float, float, float]:
    """Gets the head or tail position of a bone.

    Args:
        armature_obj_ref: The armature object.
        bone_name: Name of the bone.
        position: Either 'head' or 'tail'.

    Returns:
        Tuple of (x, y, z) coordinates.
    """
    armature_obj = armature_obj_ref._get_obj()
    if not armature_obj or armature_obj.type != "ARMATURE":
        raise ValueError(f"Object {armature_obj_ref.name} is not an armature.")

    bone = armature_obj.data.bones.get(bone_name)
    if not bone:
        raise ValueError(f"Bone {bone_name} not found in armature {armature_obj.name}.")

    if position == "head":
        return tuple(bone.head_local)
    elif position == "tail":
        return tuple(bone.tail_local)
    else:
        raise ValueError(f"Position must be 'head' or 'tail', got '{position}'.")


def set_bone_length(armature_obj_ref: BlenderObjRef, bone_name: str, length: float) -> None:
    """Sets the length of a bone.

    Args:
        armature_obj_ref: The armature object.
        bone_name: Name of the bone.
        length: New length for the bone.
    """
    armature_obj = armature_obj_ref._get_obj()
    if not armature_obj or armature_obj.type != "ARMATURE":
        raise ValueError(f"Object {armature_obj_ref.name} is not an armature.")

    # Need to be in edit mode to modify bone length
    bpy.context.view_layer.objects.active = armature_obj
    bpy.ops.object.mode_set(mode="EDIT")

    edit_bone = armature_obj.data.edit_bones.get(bone_name)
    if not edit_bone:
        bpy.ops.object.mode_set(mode="OBJECT")
        raise ValueError(f"Bone {bone_name} not found in armature {armature_obj.name}.")

    # Calculate direction vector and set new tail position
    direction = (edit_bone.tail - edit_bone.head).normalized()
    edit_bone.tail = edit_bone.head + direction * length

    bpy.ops.object.mode_set(mode="OBJECT")


def add_bone_constraint_with_options(armature_obj_ref: BlenderObjRef, bone_name: str,
                                    constraint_type: str, target_obj_ref: BlenderObjRef = None,
                                    subtarget_name: str = None, **options) -> None:
    """Adds a constraint to a bone with additional options.

    Args:
        armature_obj_ref: The armature object.
        bone_name: The name of the bone to add the constraint to.
        constraint_type: The type of constraint to add.
        target_obj_ref: The target object for the constraint (optional).
        subtarget_name: The name of the subtarget (optional).
        **options: Additional constraint options as keyword arguments.
    """
    armature_obj = armature_obj_ref._get_obj()
    if not armature_obj or armature_obj.type != "ARMATURE":
        raise ValueError(f"Object {armature_obj_ref.name} is not an armature.")

    bone = armature_obj.pose.bones.get(bone_name)
    if not bone:
        raise ValueError(f"Bone {bone_name} not found in armature {armature_obj.name}.")

    constraint = bone.constraints.new(type=constraint_type)

    if target_obj_ref:
        constraint.target = target_obj_ref._get_obj()

    if subtarget_name:
        constraint.subtarget = subtarget_name

    # Apply additional options
    for option_name, option_value in options.items():
        if hasattr(constraint, option_name):
            setattr(constraint, option_name, option_value)
        else:
            print(f"Warning: Constraint {constraint_type} does not have option '{option_name}'")


def set_bone_ik_properties(armature_obj_ref: BlenderObjRef, bone_name: str,
                          lock_ik_x: bool = None, lock_ik_y: bool = None, lock_ik_z: bool = None,
                          limit_x_min: float = None, limit_x_max: float = None,
                          limit_y_min: float = None, limit_y_max: float = None,
                          limit_z_min: float = None, limit_z_max: float = None,
                          use_ik_limit_x: bool = None, use_ik_limit_y: bool = None,
                          use_ik_limit_z: bool = None) -> None:
    """Sets IK properties for a bone.

    Args:
        armature_obj_ref: The armature object.
        bone_name: Name of the bone.
        lock_ik_x, lock_ik_y, lock_ik_z: Whether to lock IK on each axis.
        limit_x_min, limit_x_max, etc.: IK rotation limits in radians.
        use_ik_limit_x, use_ik_limit_y, use_ik_limit_z: Whether to use limits on each axis.
    """
    armature_obj = armature_obj_ref._get_obj()
    if not armature_obj or armature_obj.type != "ARMATURE":
        raise ValueError(f"Object {armature_obj_ref.name} is not an armature.")

    bone = armature_obj.pose.bones.get(bone_name)
    if not bone:
        raise ValueError(f"Bone {bone_name} not found in armature {armature_obj.name}.")

    # Set lock properties
    if lock_ik_x is not None:
        bone.lock_ik_x = lock_ik_x
    if lock_ik_y is not None:
        bone.lock_ik_y = lock_ik_y
    if lock_ik_z is not None:
        bone.lock_ik_z = lock_ik_z

    # Set limit properties
    if use_ik_limit_x is not None:
        bone.use_ik_limit_x = use_ik_limit_x
    if use_ik_limit_y is not None:
        bone.use_ik_limit_y = use_ik_limit_y
    if use_ik_limit_z is not None:
        bone.use_ik_limit_z = use_ik_limit_z

    # Set limit values (convert degrees to radians)
    if limit_x_min is not None:
        bone.ik_min_x = math.radians(limit_x_min)
    if limit_x_max is not None:
        bone.ik_max_x = math.radians(limit_x_max)
    if limit_y_min is not None:
        bone.ik_min_y = math.radians(limit_y_min)
    if limit_y_max is not None:
        bone.ik_max_y = math.radians(limit_y_max)
    if limit_z_min is not None:
        bone.ik_min_z = math.radians(limit_z_min)
    if limit_z_max is not None:
        bone.ik_max_z = math.radians(limit_z_max)


def set_bone_custom_property(
    armature_obj_ref: BlenderObjRef, bone_name: str, prop: CustomProperty[T], value: T
) -> None:
    """Sets a custom property on a bone.

    Args:
        armature_obj_ref: The armature object.
        bone_name: The name of the bone.
        prop: A CustomProperty object describing the property.
        value: The value to set the property to.
    """
    armature_obj = armature_obj_ref._get_obj()
    if not armature_obj or armature_obj.type != "ARMATURE":
        raise ValueError(f"Object {armature_obj_ref.name} is not an armature.")

    bone = armature_obj.data.bones.get(bone_name)
    if not bone:
        raise ValueError(f"Bone {bone_name} not found in armature {armature_obj.name}.")

    bone[prop._prop_name] = value


def get_bone_custom_property(
    armature_obj_ref: BlenderObjRef, bone_name: str, prop: CustomProperty[T]
) -> T | None:
    """Gets a custom property from a bone.

    Args:
        armature_obj_ref: The armature object.
        bone_name: The name of the bone.
        prop: A CustomProperty object describing the property.

    Returns:
        The value of the custom property, or None if the property does not exist.
    """
    armature_obj = armature_obj_ref._get_obj()
    if not armature_obj or armature_obj.type != "ARMATURE":
        raise ValueError(f"Object {armature_obj_ref.name} is not an armature.")

    bone = armature_obj.data.bones.get(bone_name)
    if not bone:
        raise ValueError(f"Bone {bone_name} not found in armature {armature_obj.name}.")

    return bone.get(prop._prop_name)


def assign_action_to_bone(
    armature_obj_ref: BlenderObjRef, bone_name: str, action: bpy.types.Action, slot_name: str
) -> None:
    """Assigns a shared Action and a specific ActionSlot to a bone.

    This function ensures the bone's animation data is set up to be driven
    by a specific slot within a larger Action.

    Args:
        armature_obj_ref: The armature object containing the bone.
        bone_name: The name of the bone to assign the action to.
        action: The Action containing the animation data.
        slot_name: The user-facing name of the slot that should drive the bone.
    """
    armature_obj = armature_obj_ref._get_obj()
    if not armature_obj or armature_obj.type != "ARMATURE":
        raise ValueError(f"Object {armature_obj_ref.name} is not an armature.")

    pose_bone = armature_obj.pose.bones.get(bone_name)
    if not pose_bone:
        raise ValueError(f"Bone {bone_name} not found in armature {armature_obj.name}.")

    # Create animation data if it doesn't exist
    if not pose_bone.id_data.animation_data:
        pose_bone.id_data.animation_data_create()

    pose_bone.id_data.animation_data.action = action

    # Ensure the slot is created before assigning
    get_or_create_action_slot(action, slot_name)
    prefixed_name = _get_prefixed_slot_name(slot_name)
    pose_bone.id_data.animation_data.action_slot = action.slots[prefixed_name]


def load_widget_from_blend(widget_blend_path: str, widget_name: str) -> bpy.types.Object | None:
    """Loads a widget mesh object from a .blend file.

    Args:
        widget_blend_path: Absolute path to the widgets.blend file.
        widget_name: Name of the widget object to load (e.g., 'WGT-sphere').

    Returns:
        The loaded widget object, or None if not found.
    """
    import os
    if not os.path.exists(widget_blend_path):
        print(f"Warning: Widget file not found: {widget_blend_path}")
        return None

    # Check if widget already exists in current file
    if widget_name in bpy.data.objects:
        return bpy.data.objects[widget_name]

    # Append the widget from the .blend file
    with bpy.data.libraries.load(widget_blend_path, link=False) as (data_from, data_to):
        if widget_name in data_from.objects:
            data_to.objects = [widget_name]
        else:
            print(f"Warning: Widget '{widget_name}' not found in {widget_blend_path}")
            return None

    if data_to.objects:
        widget_obj = data_to.objects[0]
        # Link to a collection (required before we can hide it)
        # Use a dedicated "Widgets" collection to keep them organized
        widgets_collection = bpy.data.collections.get("Widgets")
        if not widgets_collection:
            widgets_collection = bpy.data.collections.new("Widgets")
            bpy.context.scene.collection.children.link(widgets_collection)

        if widget_obj.name not in widgets_collection.objects:
            widgets_collection.objects.link(widget_obj)

        # Hide the widget object from viewport and render
        widget_obj.hide_set(True)
        widget_obj.hide_render = True
        return widget_obj

    return None


def set_bone_custom_shape(
    armature_obj_ref: BlenderObjRef,
    bone_name: str,
    custom_shape_obj: bpy.types.Object,
    scale: float = 1.0,
    wireframe: bool = False,
    wire_width: float = 1.0,
) -> None:
    """Sets a custom shape for a pose bone.

    Args:
        armature_obj_ref: The armature object.
        bone_name: The name of the bone.
        custom_shape_obj: The mesh object to use as custom shape.
        scale: Scale factor for the custom shape.
        wireframe: Whether to display as wireframe.
        wire_width: Line width for wireframe display (only applies if wireframe=True).
    """
    armature_obj = armature_obj_ref._get_obj()
    if not armature_obj or armature_obj.type != "ARMATURE":
        raise ValueError(f"Object {armature_obj_ref.name} is not an armature.")

    pose_bone = armature_obj.pose.bones.get(bone_name)
    if not pose_bone:
        raise ValueError(f"Bone {bone_name} not found in armature {armature_obj.name}.")

    pose_bone.custom_shape = custom_shape_obj
    pose_bone.use_custom_shape_bone_size = False
    pose_bone.custom_shape_scale_xyz = (scale, scale, scale)

    if wireframe:
        pose_bone.custom_shape_wire_width = wire_width
