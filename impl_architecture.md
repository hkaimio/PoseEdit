# Implementation Architecture

This document describes the proposed Python class structure and overall architecture for the Pose Editor add-on. The design emphasizes separation of concerns, maintainability, and unit testability.

## 1. High-Level Architecture: Blender as the Source of Truth

Per our discussion, we will adopt an architecture where the Blender scene (`bpy.data`) serves as the single source of truth. This is a robust, idiomatic approach for Blender add-ons that avoids complex data synchronization issues.

The layers are now defined as follows:

-   **Blender Data (Source of Truth):** All persistent data, such as marker positions, object relationships, and project settings, resides directly in the `.blend` file on `bpy.data` objects (e.g., as custom properties on Empties).

-   **Data Access Layer (DAL):** A thin, dedicated module that is the *only* part of the add-on allowed to make direct `bpy.data` calls (e.g., `obj.get("my_prop")`, `obj.location`). This layer provides simple, abstract functions for getting and setting data. Crucially, it can be easily mocked for unit testing the layers above it.

-   **Business Logic / Facades (Model):** This layer contains the application's intelligence. The classes here (`RealPersonInstance`, `CameraView`) are lightweight, often transient wrappers that are initialized with a Blender object (like an Empty). They use the DAL to get or set data and perform operations. They contain the business logic (e.g., "how to triangulate") but do not know how the data is stored in Blender.

-   **Operators & UI (Controller & View):** This layer remains the same. Operators handle user actions, using the Facade classes to work with the data. UI Panels read data (via the Facades) to draw themselves.

```mermaid
classDiagram
    class UIPanels {
        <<View>>
    }
    class Operators {
        <<Controller>>
    }
    class BusinessLogicFacades {
        <<Facade>>
        +RealPersonInstance(bpy_object)
        +get_3d_markers()
    }
    class DataAccessLayer {
        <<DAL>>
        +get_custom_property(obj, key)
        +set_fcurve_value(obj, path, frame, value)
    }
    class BlenderData {
        <<Source of Truth>>
        bpy.data
    }

    UIPanels ..> Operators : triggers
    Operators ..> BusinessLogicFacades : uses
    Operators ..> DataAccessLayer : uses
    BusinessLogicFacades ..> DataAccessLayer : uses
    DataAccessLayer ..> BlenderData : manipulates
```

## 2. Proposed Directory Structure

The directory structure is updated to reflect this new architecture.

```
pose_editor/
|-- __init__.py           # Main add-on registration
|-- core/                 # Business Logic / Facades
|   |-- __init__.py
|   |-- project_facade.py
|   `-- person_facade.py
|-- blender/              # Blender-specific code
|   |-- __init__.py
|   |-- dal.py            # The Data Access Layer
|   |-- scene_builder.py  # For initial object creation
|   |-- operators.py      # All bpy.types.Operator classes
|   `-- properties.py       # Blender PropertyGroup definitions
`-- ui/                   # UI Panels
    |-- __init__.py
    `-- panels.py
```

## 3. Data Access Layer (DAL)
This is a new, critical layer located at `blender/dal.py`. It abstracts all `bpy` interactions into simple, testable functions.

```python
# blender/dal.py

# This module contains all direct access to bpy.data

def get_root_project_empty() -> bpy.types.Object:
    # Logic to find and return the main project empty
    pass

def get_custom_property(blender_object: bpy.types.Object, key: str, default: any) -> any:
    return blender_object.get(key, default)

def set_custom_property(blender_object: bpy.types.Object, key: str, value: any) -> None:
    blender_object[key] = value

def get_marker_world_location(marker_object: bpy.types.Object, frame: int) -> tuple[float, float, float]:
    # Logic to get f-curve value at a specific frame
    pass

# ... and so on for every other bpy.data interaction.
```

## 4. Business Logic / Facades
These classes in the `core/` directory provide the main API for the rest of the application to use. They are initialized with a Blender object but perform all their internal data access via the DAL.

```python
# core/person_facade.py

# Note: No 'import bpy' here!
from ..blender import dal

class RealPersonInstanceFacade:
    """A lightweight wrapper around a person's master Empty object."""

    def __init__(self, person_instance_empty):
        # In production, this is a bpy.types.Object.
        # In testing, this can be a mock object or a simple dict.
        self.bl_obj = person_instance_empty

    @property
    def name(self) -> str:
        return dal.get_custom_property(self.bl_obj, 'person_definition_id', "")

    def get_3d_marker_data_as_numpy(self) -> 'numpy.ndarray':
        """Gets all 3D marker data for this person."""
        marker_objects = dal.get_children_in_collection(self.bl_obj, "3D Markers")
        # ... logic to iterate through frames and markers, using the DAL
        # to get locations for each frame, and assemble a numpy array.
        pass
```

## 5. Operators and UI
Operators now use the Facades to interact with the data, keeping the operator logic clean and focused on orchestration.

```python
# blender/operators.py

import bpy
from ..core.person_facade import RealPersonInstanceFacade
from ..blender import dal

class PE_OT_triangulate(bpy.types.Operator):
    bl_idname = "pose.triangulate"
    bl_label = "Triangulate Persons"

    def execute(self, context):
        # 1. Get selected Blender objects from the context
        selected_empties = context.selected_objects

        for empty in selected_empties:
            # 2. Create a facade for the person instance
            person_facade = RealPersonInstanceFacade(empty)

            # 3. Use the facade to perform the core logic
            # The facade itself uses the DAL internally
            numpy_data_2d = person_facade.get_all_2d_marker_data()
            
            # This function can be pure Python and easily tested
            triangulated_data = self.perform_triangulation(numpy_data_2d)

            # 4. Use the DAL to write the results back to Blender
            dal.create_or_update_3d_markers(empty, triangulated_data)

        return {'FINISHED'}

    def perform_triangulation(self, data):
        # Pure, testable logic that might call Pose2Sim
        pass
```
## 6. Initial Workflow Implementation Details
This chapter details the implementation flow for the initial setup and 2D stitching phases of the add-on, showing how the different architectural layers interact.

### 6.1. Project Initialization
-   **Use Case:** The user needs to set up the basic collection structure in a new `.blend` file to begin work.
-   **User Interaction:** The user clicks the "Create New Project" button in the Project Setup UI panel.
-   **Sequence Diagram:**
    ```mermaid
    sequenceDiagram
        actor User
        User->>UI Panel: Clicks 'Create New Project'
        UI Panel->>Operator (PE_OT_CreateProject): execute()
        Operator (PE_OT_CreateProject)->>Scene Builder: create_project_structure()
        Scene Builder->>DAL: create_collection("Camera Views")
        Scene Builder->>DAL: create_collection("Real Persons")
        Scene Builder->>DAL: create_empty("_ProjectSettings")
    ```
-   **Interfaces:**
    -   `ui.panels.PE_PT_ProjectPanel`: Draws the button.
    -   `blender.operators.PE_OT_CreateProject`: The operator that responds to the button click.
    -   `blender.scene_builder.create_project_structure()`: Contains the logic to build the initial scene hierarchy.
    -   `blender.dal`: Various functions to create collections and objects.

### 6.2. Loading a Camera View
-   **Use Case:** The user adds a camera view, loading its video and raw pose data.
-   **User Interaction:** Clicks "Add Camera View", which opens a file browser. The user selects the video file and the directory containing the corresponding pose data JSONs.
-   **Sequence Diagram:**
    ```mermaid
    sequenceDiagram
        actor User
        User->>UI Panel: Clicks 'Add Camera View'
        UI Panel->>Operator (PE_OT_AddCameraView): invoke() -> opens file browser
        Operator (PE_OT_AddCameraView)->>Scene Builder: create_camera_view(name, video, pose_dir)
        Scene Builder->>DAL: create_collection("View: <name>")
        Scene Builder->>DAL: create_camera_with_video_bg(video_path)
        Note right of Scene Builder: Load raw track data from JSONs
        Scene Builder->>Core Facade: parse_raw_tracks(pose_dir)
        Scene Builder->>Scene Builder: create_raw_track_objects(parsed_data)
        loop for each raw track
            Scene Builder->>DAL: create_armature(...)
            Scene Builder->>DAL: create_fcurves_from_data(...)
        end
    ```
-   **Interfaces:**
    -   `blender.operators.PE_OT_AddCameraView`: Has an `invoke` method for the file browser and an `execute` method to trigger the process.
    -   `blender.scene_builder.create_camera_view()`: Orchestrates the creation of all necessary objects for a view.
    -   `core.project_facade.parse_raw_tracks()`: A pure Python function to read and parse the JSON data files into a simple data structure.
    -   `blender.dal`: Functions for creating cameras, collections, armatures, and populating their f-curves from data.

### 6.3. Creating a Real Person Instance
-   **Use Case:** The user adds a person to the project, either by creating a new reusable definition or by selecting an existing one from the library.
-   **User Interaction:** Clicks "Add Person Instance". A popup dialog appears, allowing the user to select from a dropdown of existing `PersonDefinition`s or enter a new name to create a new one.
-   **Sequence Diagram:**
    ```mermaid
    sequenceDiagram
        actor User
        User->>UI Panel: Clicks 'Add Person Instance'
        UI Panel->>Operator (PE_OT_AddPersonInstance): invoke() -> opens popup
        Operator (PE_OT_AddPersonInstance)->>Core Library: person_library.load_from_disk()
        Note right of Operator (PE_OT_AddPersonInstance): Operator populates UI with person names
        User->>Operator (PE_OT_AddPersonInstance): Selects person (e.g. 'Alice')
        Operator (PE_OT_AddPersonInstance)->>Scene Builder: create_person_instance('Alice')
        Scene Builder->>DAL: create_empty("Alice")
        Scene Builder->>DAL: set_custom_property(empty, "person_definition_id", "Alice")
    ```
-   **Interfaces:**
    -   `blender.operators.PE_OT_AddPersonInstance`: Manages the popup dialog and selection.
    -   `core.person.PersonLibrary`: Methods to load, find, and create `PersonDefinition`s.
    -   `blender.scene_builder.create_person_instance()`: Creates the Blender objects for the new instance.

### 6.4. Stitching a Timeline
-   **Use Case:** The user specifies that for a given `RealPersonInstance`, the data source should switch from one `RawTrack` to another at the current frame. The `RealPersonInstance`'s 2D armature must update its pose in real-time as the timeline is scrubbed.
-   **Mechanism:** This is achieved non-destructively using Blender drivers. When a `RealPersonInstance` 2D armature is created, drivers are added to the transform channels of each marker. These drivers read the `active_track_index` custom property at the current frame and pull the animation data from the corresponding `RawTrack` marker. The "stitching" operation is therefore just the simple act of inserting a keyframe on the index property.
-   **User Interaction:** The user selects a `RealPersonInstance`, a `CameraView`, and a `RawTrack` from UI lists. They move the timeline to the desired frame and click "Switch Source".
-   **Sequence Diagram (for the "Switch Source" operation):**
    ```mermaid
    sequenceDiagram
        actor User
        User->>UI Panel: Clicks 'Switch Source'
        UI Panel->>Operator (PE_OT_SwitchSource): execute()
        Note right of Operator (PE_OT_SwitchSource): Gets selected objects and current frame from context.
        Operator (PE_OT_SwitchSource)->>Facade (RealPersonInstance): get_2d_armature_for_view(view_name)
        Facade (RealPersonInstance)->>DAL: find_object_in_collection(...)
        Operator (PE_OT_SwitchSource)->>DAL: set_keyframe(armature, '["active_track_index"]', frame, new_track_index)
        Note left of DAL: The driver on the armature's markers now automatically pulls data from the new source track.
    ```
-   **Interfaces:**
    -   `blender.scene_builder.create_person_2d_armature()`: This function is now also responsible for setting up the drivers on each marker bone.
    -   `blender.dal.add_driver(object, property, expression)`: A function to create a scripted driver with a given Python expression.
    -   `blender.operators.PE_OT_SwitchSource`: Reads context and sets a single keyframe on the `active_track_index` property.
