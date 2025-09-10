# SPDX-FileCopyrightText: 2025 Harri Kaimio
#
# SPDX-License-Identifier: BSD-3-Clause

from typing import Generic, List, TypeVar, Optional, Tuple, Any
import numpy as np
import bpy
from . import drivers # Import the new drivers module

class BlenderObjRef:
    def __init__(self, id:str):
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
    def __init__(self, id:str):
        self._id = id
        self._collection: bpy.types.Collection | None = None

    def _get_collection(self) -> bpy.types.Collection:
        if self._collection is None:
            self._collection = bpy.data.collections.get(self._id)
        return self._collection

T = TypeVar('T')
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

# Specific custom properties for CameraView objects
CAMERA_X_FACTOR = CustomProperty[float]("camera_x_factor")
CAMERA_Y_FACTOR = CustomProperty[float]("camera_y_factor")
CAMERA_X_OFFSET = CustomProperty[float]("camera_x_offset")
CAMERA_Y_OFFSET = CustomProperty[float]("camera_y_offset")

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
            if(j < len(values)):
                fcurves[j].keyframe_points[i].co = (frame, values[j])
            else:
                print(f"Warning: Not enough values for F-curve index {j} at frame {frame}")

    # Update tangents
    for fcurve in fcurves:
        fcurve.update()

    # Hack to force update
    max_keyframe = keyframes[-1][0]
    print(data_path)
    blender_object.keyframe_insert(data_path, frame=max_keyframe+1)
    for f in fcurves:
        f.keyframe_points.remove(f.keyframe_points[-1])


def create_marker(parent: BlenderObjRef, name: str, color: tuple[float, float, float, float]) -> BlenderObjRef:
    """
    Creates a small UV sphere as a child of the given object, sets its name,
    and assigns an emission material with the specified color.

    Args:
        parent: The parent BlenderObjRef for the marker.
        name: The name of the marker, which will be appended to the parent's name.
        color: A tuple (R, G, B, A) representing the emission color of the marker.

    Returns:
        The newly created marker object wrapped in a BlenderObjRef.
    """
    parent_obj = parent._get_obj()
    if not parent_obj:
        raise ValueError(f"Parent object with ID {parent._id} not found.")

    # Ensure the active object is not the parent to avoid issues with primitive_uv_sphere_add
    # This is a common pattern when using bpy.ops to ensure the operator acts as expected.
    if bpy.context.active_object and bpy.context.active_object == parent_obj:
        bpy.ops.object.select_all(action='DESELECT')

    # Create a UV sphere
    bpy.ops.mesh.primitive_uv_sphere_add(radius=2, enter_editmode=False, align='WORLD', location=(0, 0, 0))
    marker_obj = bpy.context.active_object

    # Set parent
    marker_obj.parent = parent_obj
    marker_obj.matrix_parent_inverse.identity() # Clear parent inverse to keep local transform

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

    # Create and assign material
    mat_name = f"MarkerMaterial_{parent_obj.name}_{name}"
    material = bpy.data.materials.new(name=mat_name)
    material.use_nodes = True
    # Clear existing nodes
    material.node_tree.nodes.clear()

    # Create nodes
    value_node = material.node_tree.nodes.new(type='ShaderNodeValue')
    color_ramp_node = material.node_tree.nodes.new(type='ShaderNodeValToRGB')
    emission_node = material.node_tree.nodes.new(type='ShaderNodeEmission')
    material_output_node = material.node_tree.nodes.new(type='ShaderNodeOutputMaterial')

    # Position nodes (optional, for better readability in Blender's shader editor)
    value_node.location = (-800, 0)
    color_ramp_node.location = (-400, 0)
    emission_node.location = (0, 0)
    material_output_node.location = (400, 0)

    # Set up driver for Value node
    driver = value_node.outputs[0].driver_add('default_value').driver # 'value' input
    #driver.type = 'SCRIPTED'
    driver.expression = 'quality' # Use the 'quality' custom property directly

    # Add variable to the driver
    var_quality = driver.variables.new()
    var_quality.name = 'quality'
    var_quality.type = 'SINGLE_PROP'
    var_quality.targets[0].id = marker_obj
    var_quality.targets[0].data_path = '["quality"]'

    # Configure ColorRamp stops
    # Clear default stops
    while len(color_ramp_node.color_ramp.elements) > 1:
        color_ramp_node.color_ramp.elements.remove(color_ramp_node.color_ramp.elements[0])

    # Add new stops
    # Stop 1: at 0.0, color #390007FF (dark red)
    element = color_ramp_node.color_ramp.elements[0]
    element.position = 0.0
    element.color = (0.2235, 0.0, 0.0275, 1.0) # #390007FF in RGBA (0-1 range)

    # Stop 2: at 0.3, same color #390007FF
    element = color_ramp_node.color_ramp.elements.new(0.3)
    element.color = (0.2235, 0.0, 0.0275, 1.0)

    # Stop 3: at 0.301, color #7f7f7fff (grey)
    element = color_ramp_node.color_ramp.elements.new(0.301)
    element.color = (0.498, 0.498, 0.498, 1.0) # #7f7f7fff in RGBA (0-1 range)

    # Stop 4: at 1.0, the target color (from function argument)
    element = color_ramp_node.color_ramp.elements.new(1.0)
    element.color = color # Use the 'color' argument directly

    # Link nodes
    links = material.node_tree.links
    links.new(value_node.outputs[0], color_ramp_node.inputs[0]) # Value to ColorRamp Fac
    links.new(color_ramp_node.outputs[0], emission_node.inputs[0]) # ColorRamp Color to Emission Color
    links.new(emission_node.outputs[0], material_output_node.inputs[0]) # Emission to Material Output Surface

    # Set Emission Strength
    emission_node.inputs['Strength'].default_value = 1.0

    if marker_obj.data.materials:
        marker_obj.data.materials[0] = material
    else:
        marker_obj.data.materials.append(material)

    # Add driver for hide_viewport based on "quality"
    driver = marker_obj.driver_add('hide_viewport').driver
    driver.type = 'SCRIPTED'
    driver.expression = 'quality < 0'

    var_quality_hide = driver.variables.new()
    var_quality_hide.name = 'quality'
    var_quality_hide.type = 'SINGLE_PROP'
    var_quality_hide.targets[0].id = marker_obj
    var_quality_hide.targets[0].data_path = '["quality"]'

    return BlenderObjRef(marker_obj.name)

def get_or_create_object(
    name: str, 
    obj_type: str, 
    collection_name: Optional[str] = None,
    parent: Optional["BlenderObjRef"] = None
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
        if obj_type == 'EMPTY':
            obj = bpy.data.objects.new(name, None)
        elif obj_type == 'ARMATURE':
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
        slot = action.slots.new(name=slot_name, id_type='OBJECT')
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
        strip = layer.strips.new(type='KEYFRAME')
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
        kp.interpolation = 'LINEAR'
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

def get_fcurve_from_action(action: bpy.types.Action, slot_name: str, data_path: str, index: int = -1) -> Optional[bpy.types.FCurve]:
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

def add_bone(armature_obj_ref: BlenderObjRef, bone_name: str, head: Tuple[float, float, float], tail: Tuple[float, float, float]) -> None:
    """Adds a bone to an armature.

    Args:
        armature_obj_ref: The armature object to add the bone to.
        bone_name: The name of the new bone.
        head: The head position of the bone.
        tail: The tail position of the bone.
    """
    armature_obj = armature_obj_ref._get_obj()
    if not armature_obj or armature_obj.type != 'ARMATURE':
        raise ValueError(f"Object {armature_obj_ref.name} is not an armature.")

    bpy.context.view_layer.objects.active = armature_obj
    bpy.ops.object.mode_set(mode='EDIT')

    bone = armature_obj.data.edit_bones.new(bone_name)
    bone.head = head
    bone.tail = tail

    bpy.ops.object.mode_set(mode='OBJECT')

def add_bone_constraint(armature_obj_ref: BlenderObjRef, bone_name: str, constraint_type: str, target_obj_ref: BlenderObjRef, subtarget_name: str = None) -> None:
    """Adds a constraint to a bone.

    Args:
        armature_obj_ref: The armature object.
        bone_name: The name of the bone to add the constraint to.
        constraint_type: The type of constraint to add (e.g., 'COPY_LOCATION', 'STRETCH_TO').
        target_obj_ref: The target object for the constraint.
        subtarget_name: The name of the subtarget (e.g., for STRETCH_TO).
    """
    armature_obj = armature_obj_ref._get_obj()
    if not armature_obj or armature_obj.type != 'ARMATURE':
        raise ValueError(f"Object {armature_obj_ref.name} is not an armature.")

    bone = armature_obj.pose.bones.get(bone_name)
    if not bone:
        raise ValueError(f"Bone {bone_name} not found in armature {armature_obj.name}.")

    constraint = bone.constraints.new(type=constraint_type)
    constraint.target = target_obj_ref._get_obj()
    if subtarget_name:
        constraint.subtarget = subtarget_name

def set_armature_display_stick(armature_obj_ref: BlenderObjRef) -> None:
    """Sets the armature display to 'STICK'.

    Args:
        armature_obj_ref: The armature object.
    """
    armature_obj = armature_obj_ref._get_obj()
    if not armature_obj or armature_obj.type != 'ARMATURE':
        raise ValueError(f"Object {armature_obj_ref.name} is not an armature.")

    armature_obj.data.display_type = 'STICK'

def create_bone_group(armature_obj_ref: BlenderObjRef, group_name: str, color: tuple[float, float, float, float]) -> None:
    """Creates a bone group with a specific color.

    Args:
        armature_obj_ref: The armature object.
        group_name: The name of the bone group.
        color: The color for the bone group.
    """
    armature_obj = armature_obj_ref._get_obj()
    if not armature_obj or armature_obj.type != 'ARMATURE':
        raise ValueError(f"Object {armature_obj_ref.name} is not an armature.")

    bone_group = armature_obj.pose.bone_groups.new(name=group_name)
    bone_group.color_set = 'CUSTOM'
    bone_group.colors.normal = color[:3]
    bone_group.colors.select = (0.0, 1.0, 0.0) # Green for selected
    bone_group.colors.active = (1.0, 1.0, 0.0) # Yellow for active

def assign_bone_to_group(armature_obj_ref: BlenderObjRef, bone_name: str, group_name: str) -> None:
    """Assigns a bone to a bone group.

    Args:
        armature_obj_ref: The armature object.
        bone_name: The name of the bone.
        group_name: The name of the bone group.
    """
    armature_obj = armature_obj_ref._get_obj()
    if not armature_obj or armature_obj.type != 'ARMATURE':
        raise ValueError(f"Object {armature_obj_ref.name} is not an armature.")

    bone = armature_obj.pose.bones.get(bone_name)
    if not bone:
        raise ValueError(f"Bone {bone_name} not found in armature {armature_obj.name}.")

    bone_group = armature_obj.pose.bone_groups.get(group_name)
    if not bone_group:
        raise ValueError(f"Bone group {group_name} not found in armature {armature_obj.name}.")

    bone.bone_group = bone_group

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

def set_fcurves_from_numpy(
    action: bpy.types.Action, 
    columns: List[Tuple[str, str, int]], 
    start_frame: int, 
    data: np.ndarray
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
                kp.interpolation = 'LINEAR'
                keyframe_indices[col_idx] += 1

    # 5. Update all F-Curves.
    for fcurve in fcurves:
        fcurve.update()