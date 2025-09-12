# Blender 4.4 Animation API Changes

This document summarizes the significant changes to the animation data model and Python API introduced in Blender 4.4. The previous API is now considered legacy and will be removed in Blender 5.0.

## 1. Slotted Actions

The most significant change is the introduction of **Slotted Actions**. This fundamentally alters the structure of `Action` data-blocks.

-   **Previous Model:** An `Action` was directly tied to a single data-block type. For example, one `Action` would animate an object's transform, and a separate `Action` would be needed to animate its material properties.
-   **New Model:** A single `Action` can now store animation data for multiple different data-blocks simultaneously. It does this by containing one or more **Action Slots**.

### Data Model Hierarchy

The new hierarchy for an `Action` is as follows:

-   **`Action`**: The top-level animation data-block.
    -   **`Action.fcurves`**: A collection of all F-Curves for the entire action. This is where the animation data is stored.
    -   **`Action.slots`**: A collection of `ActionSlot` objects. These act as targets or contexts for the animation data.

An `ActionSlot` itself does not directly contain F-Curves. Instead, an F-Curve that belongs to the `Action` is associated with a specific slot via its `data_path` property. The `data_path` is formatted to reference the slot by its key in the collection (e.g., `slots["OBMarkerName"].location`).

*Note: While the API also exposes a `slot.strips` and `strip.layers` hierarchy, this is a more advanced NLA-style structure. For direct animation, creating F-Curves on the `Action` with a slotted `data_path` is the correct approach.*

## 2. Python API Changes

The Python API has been updated to reflect the new slotted action model.

### Legacy API (To be removed in Blender 5.0)

The old methods for accessing animation data are now considered legacy. Using them is discouraged.

-   `action.fcurves` (when used with non-slotted `data_path`s)
-   `action.groups`
-   `action.pose_markers`

### New API

The new API involves creating slots and then creating F-Curves on the action that target those slots.

```python
# Example of the correct API usage
import bpy

action = bpy.data.actions.new("MySlottedAction")

# 1. Create a slot for an object. 
#    The name provided ("MyObject") is used to generate the key ("OBMyObject").
slot = action.slots.new(name="MyObject", id_type='OBJECT')

# 2. Create an F-Curve on the Action itself.
#    The data_path targets the property through the slot's prefixed name.
slotted_data_path = 'slots["OBMyObject"].location'
fc_loc_x = action.fcurves.new(slotted_data_path, index=0)

# 3. Add keyframes to the F-Curve.
fc_loc_x.keyframe_points.insert(0, 42)
```

### Breaking Changes

-   **Action Assignment:** Simply assigning an `Action` to an object's `animation_data.action` is no longer sufficient. The `animation_data.action_slot` must also be set to the correct slot within the `Action`.

## 3. Implications for Pose Editor

-   All animation data creation and manipulation must use the new slotted action API.
-   We must create F-Curves on the `Action` with a `data_path` that correctly targets the desired slot.
-   Reading animation data requires finding the F-Curve with the correct slotted `data_path`.

## 4. Marker Data Design (Revised)

This section outlines the definitive design for storing and accessing marker animation data.

### Blender Data Structure

The design separates the visible marker objects (View) from the underlying data (Model).

#### View Layer: Object Hierarchy

-   **Person View Root Empty**: A main Empty object that groups the markers for a person in a specific view (e.g., `PV.Alice.cam1`).
-   **Marker Empties**: Parented to the `Person View Root`. These represent the individual markers (e.g., `"Nose"`).
    -   **Animation Data**: Each marker empty has its `animation_data` configured to link to a specific slot in a shared Action.
        -   `marker.animation_data.action`: Points to the shared `Action`.
        -   `marker.animation_data.action_slot`: Points to the specific `ActionSlot` within that Action.

#### Model Layer: Data Representation

-   **Data Series Empty**: A separate Empty object that defines a single data series (e.g., `DS.cam1_person0_raw`).
-   **Action**: A single `Action` stores all animation data for the series.
    -   **Action Name**: e.g., `AC.cam1_person0_raw`.
    -   **Action Slots**: The Action contains one `ActionSlot` for each marker. The key for the slot will be the marker name prefixed with `OB` (e.g., `action.slots["OBNose"]`).
    -   **F-Curves**: The F-Curves for all markers in the series are stored directly on the `Action`. Each F-Curve's `data_path` targets a specific slot (e.g., `slots["OBNose"].location`).

### Python Class (`MarkerData`)

The `MarkerData` facade class manages the `DataSeries` and its `Action`.

```python
# Conceptual structure for pose_editor.core.marker_data.py

class MarkerData:
    def __init__(self, series_name: str, skeleton_name: Optional[str] = None):
        # ... initialization using DAL to find/create DS Empty and Action ...
        pass

    def apply_to_view(self, view_root_object_name: str):
        # ... uses DAL to iterate children of view_root ...
        # ... for each child, calls dal.assign_action_to_object ...
        pass

    def get_animation_data(self, markers, channels, frame_range):
        # ... uses dal.get_fcurve_from_action and dal.sample_fcurve ...
        pass

    def set_animation_data(self, data, columns, start_frame):
        # ... iterates through columns ...
        # ... uses dal.get_or_create_fcurve and dal.set_fcurve_keyframes ...
        pass
```