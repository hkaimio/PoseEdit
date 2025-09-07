# SPDX-FileCopyrightText: 2025 Harri Kaimio
#
# SPDX-License-Identifier: BSD-3-Clause

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

def create_empty(name: str, collection: bpy.types.Collection = None) -> bpy.types.Object:
    """
    Creates a new empty object in the scene.

    Args:
        name: The name of the new empty.
        collection: The collection to link the empty to. If None, the empty is linked to the scene's master collection.

    Returns:
        The new empty object.
    """
    empty = bpy.data.objects.new(name, None)
    if collection is None:
        collection = bpy.context.scene.collection
    collection.objects.link(empty)
    return empty

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

    return BlenderObjRef(marker_obj.name)