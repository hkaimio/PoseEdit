# SPDX-FileCopyrightText: 2025 Harri Kaimio
#
# SPDX-License-Identifier: BSD-3-Clause

from typing import Generic, List, TypeVar, Optional, Tuple, Any
import numpy as np
import bpy
from . import drivers  # Import the new drivers module


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
    return obj.get(prop._prop_name)


# Specific custom properties for DataSeries objects
SERIES_NAME = CustomProperty[str]("series_name")
SKELETON = CustomProperty[str]("skeleton")
ACTION_NAME = CustomProperty[str]("action_name")
MARKER_ROLE = CustomProperty[str]("marker_role")


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
        blender_object.keyframe_insert(data_path=data_path, frame=frame)


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
    image_path: str = "C:\\Users\\HarriKaimio\\projects\\pose-editor\\assets\\marker-128x128.png",
) -> BlenderObjRef:
    """
    Creates a new empty object with an image, to be used as a marker.

    Args:
        parent: The parent BlenderObjRef for the marker.
        name: The name of the marker, which will be appended to the parent's name.
        color: A tuple (R, G, B, A) representing the emission color of the marker.
        image_path: The path to the image file to use for the empty.

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

    bpy.context.collection.objects.link(marker_obj)

    # Set parent
    marker_obj.parent = parent_obj
    marker_obj.matrix_parent_inverse.identity()  # Clear parent inverse to keep local transform

    # Set name
    marker_obj.name = f"{parent_obj.name}_{name}"

    # Add "quality" custom property
    marker_obj["quality"] = 1.0

    # Store the marker role as a custom property
    set_custom_property(BlenderObjRef(marker_obj.name), MARKER_ROLE, name)

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

    return BlenderObjRef(marker_obj.name)


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
    name: str, obj_type: str, collection_name: Optional[str] = None, parent: Optional["BlenderObjRef"] = None
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


def set_fcurve_keyframes(fcurve: bpy.types.FCurve, keyframes: List[Tuple[float, float]]) -> None:
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


def get_children_of_object(obj_ref: "BlenderObjRef") -> List["BlenderObjRef"]:
    """Returns a list of direct children objects of a given object.

    Args:
        obj_ref: A reference to the parent object.

    Returns:
        A list of BlenderObjRef wrappers for the children.
    """
    obj = obj_ref._get_obj()
    if not obj:
        raise ValueError(f"Blender object with ID {obj_ref._id} not found.")
    return [BlenderObjRef(child.name) for child in obj.children]


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


def get_fcurve_from_action(
    action: bpy.types.Action, slot_name: str, data_path: str, index: int = -1
) -> Optional[bpy.types.FCurve]:
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


def get_scene_frame_range() -> Tuple[int, int]:
    """Returns the start and end frame of the current scene.

    Returns:
        A tuple containing the start and end frame numbers.
    """
    return bpy.context.scene.frame_start, bpy.context.scene.frame_end


def add_bones_in_bulk(
    armature_obj_ref: BlenderObjRef,
    bones_to_add: List[Tuple[str, Tuple[float, float, float], Tuple[float, float, float]]],
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
    armature_obj_ref: BlenderObjRef, bone_name: str, head: Tuple[float, float, float], tail: Tuple[float, float, float]
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
        data_path: The property to drive (e.g., 'hide').
        expression: The driver expression.
        variables: A list of tuples, where each tuple defines a driver variable:
                   (var_name, var_type, target_id, data_path)
    """
    armature_obj = armature_obj_ref._get_obj()
    if not armature_obj or armature_obj.type != "ARMATURE":
        raise ValueError(f"Object {armature_obj_ref.name} is not an armature.")

    bone = armature_obj.data.bones.get(bone_name)
    if not bone:
        raise ValueError(f"Bone {bone_name} not found in armature {armature_obj.name}.")

    driver = bone.driver_add(data_path).driver
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


def get_fcurve_on_object(obj_ref: BlenderObjRef, data_path: str, index: int = -1) -> Optional[bpy.types.FCurve]:
    """Gets a specific F-Curve from an object's default action.

    Args:
        obj_ref: The object to get the F-Curve from.
        data_path: The data path of the property (e.g., '["my_prop"]').
        index: The array index for vector properties.

    Returns:
        The found F-Curve, or None.
    """
    obj = obj_ref._get_obj()
    if not obj or not obj.animation_data or not obj.animation_data.action:
        return None
    
    return obj.animation_data.action.fcurves.find(data_path, index=index)


def get_fcurve_keyframes(fcurve: bpy.types.FCurve) -> List[Tuple[float, float]]:
    """Extracts all keyframe points from an F-Curve.

    Args:
        fcurve: The F-Curve to read from.

    Returns:
        A list of (frame, value) tuples.
    """
    if not fcurve:
        return []
    return [(kp.co[0], kp.co[1]) for kp in fcurve.keyframe_points]


def set_fcurves_from_numpy(
    action: bpy.types.Action, columns: List[Tuple[str, str, int]], start_frame: int, data: np.ndarray
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
                kp.interpolation = "LINEAR"
                keyframe_indices[col_idx] += 1

    # 5. Update all F-Curves.
    for fcurve in fcurves:
        fcurve.update()
