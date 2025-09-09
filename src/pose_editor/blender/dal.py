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
    bpy.ops.mesh.primitive_uv_sphere_add(radius=0.02, enter_editmode=False, align='WORLD', location=(0, 0, 0))
    marker_obj = bpy.context.active_object

    # Set parent
    marker_obj.parent = parent_obj
    marker_obj.matrix_parent_inverse.identity() # Clear parent inverse to keep local transform

    # Set name
    marker_obj.name = f"{parent_obj.name}_{name}"

    # Add "quality" custom property
    marker_obj["quality"] = 1.0

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

def get_or_create_object(name: str, obj_type: str, collection_name: Optional[str] = None) -> "BlenderObjRef":
    """Gets an object by name, or creates it if it doesn't exist."""
    obj = bpy.data.objects.get(name)
    if not obj:
        if obj_type == 'EMPTY':
            obj = bpy.data.objects.new(name, None)
        # Add other object types as needed
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
            bpy.context.scene.collection.objects.link(obj)

    return BlenderObjRef(obj.name)

def get_or_create_action(action_name: str) -> bpy.types.Action:
    """Gets an Action by name, or creates it if it doesn't exist."""
    action = bpy.data.actions.get(action_name)
    if not action:
        action = bpy.data.actions.new(action_name)
    return action

def action_has_slot(action: bpy.types.Action, slot_name: str) -> bool:
    """Checks if an Action has a specific slot."""
    return slot_name in action.slots

def get_or_create_action_slot(action: bpy.types.Action, slot_name: str) -> bpy.types.ActionSlot:
    """Gets an ActionSlot by name from an Action, or creates it if it doesn't exist."""
    slot = action.slots.get(slot_name)
    if not slot:
        slot = action.slots.new(slot_name)
    return slot

def get_or_create_action_strip(slot: bpy.types.ActionSlot, strip_name: str) -> bpy.types.ActionStrip:
    """Gets an ActionStrip by name from an ActionSlot, or creates it if it doesn't exist."""
    strip = slot.strips.get(strip_name)
    if not strip:
        strip = slot.strips.new(strip_name, 0)
    return strip

def get_or_create_action_layer(strip: bpy.types.ActionStrip, layer_name: str) -> bpy.types.ActionLayer:
    """Gets an ActionLayer by name from an ActionStrip, or creates it if it doesn't exist."""
    layer = strip.layers.get(layer_name)
    if not layer:
        layer = strip.layers.new(layer_name)
    return layer

def get_or_create_fcurve(layer: bpy.types.ActionLayer, data_path: str, index: int = -1) -> bpy.types.FCurve:
    """Gets an FCurve from an ActionLayer, or creates it if it doesn't exist."""
    fcurve = layer.fcurves.find(data_path, index=index)
    if not fcurve:
        fcurve = layer.fcurves.new(data_path, index=index)
    return fcurve

def set_fcurve_keyframes(fcurve: bpy.types.FCurve, keyframes: List[Tuple[float, float]]) -> None:
    """Sets keyframes for an FCurve, clearing existing ones in the process."""
    fcurve.keyframe_points.clear()
    for frame, value in keyframes:
        fcurve.keyframe_points.insert(frame, value)
    fcurve.update()

def assign_action_to_object(obj_ref: "BlenderObjRef", action: bpy.types.Action, slot_name: str) -> None:
    """Assigns a shared Action and a specific ActionSlot to an object's animation_data."""
    obj = obj_ref._get_obj()
    if not obj:
        raise ValueError(f"Blender object with ID {obj_ref._id} not found.")
    if not obj.animation_data:
        obj.animation_data_create()
    obj.animation_data.action = action
    if slot_name in action.slots:
        obj.animation_data.action_slot = action.slots[slot_name]
    else:
        raise ValueError(f"Slot '{slot_name}' not found in action '{action.name}'")

def get_children_of_object(obj_ref: "BlenderObjRef") -> List["BlenderObjRef"]:
    """Returns a list of direct children objects of a given object."""
    obj = obj_ref._get_obj()
    if not obj:
        raise ValueError(f"Blender object with ID {obj_ref._id} not found.")
    return [BlenderObjRef(child.name) for child in obj.children]

def get_object_by_name(name: str) -> Optional["BlenderObjRef"]:
    """Returns a Blender object by its name, wrapped in a BlenderObjRef."""
    obj = bpy.data.objects.get(name)
    if obj:
        return BlenderObjRef(obj.name)
    return None

def get_fcurve_from_action_slot(slot: bpy.types.ActionSlot, data_path: str, index: int = -1) -> Optional[bpy.types.FCurve]:
    """Gets an FCurve from an ActionSlot's first strip and layer."""
    if not slot.strips:
        return None
    strip = slot.strips[0] # Assuming a single strip
    if not strip.layers:
        return None
    layer = strip.layers[0] # Assuming a single layer
    return layer.fcurves.find(data_path, index=index)

def get_scene_frame_range() -> Tuple[int, int]:
    """Returns the start and end frame of the current scene."""
    return bpy.context.scene.frame_start, bpy.context.scene.frame_end

def sample_fcurve(fcurve: bpy.types.FCurve, start_frame: int, end_frame: int) -> np.ndarray:
    """Samples an FCurve over a given frame range."""
    frames = np.arange(start_frame, end_frame + 1)
    values = np.array([fcurve.evaluate(f) for f in frames])
    return values
