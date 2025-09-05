# Blender Add-on: Pose Data Editor Design

## Overview
This add-on provides tools for editing pose data captured from video, visualized and animated in Blender. It is designed to handle complex scenarios with multiple camera angles and multiple people, providing a workflow to consolidate fragmented tracking data into coherent character poses before editing.

The core class, `PoseData2D`, encapsulates the final, stitched pose data for a single person in a single camera view and manages the associated Blender objects.

## Requirements
- **Video Background:** The video from which pose data was extracted can be loaded and displayed as a synchronized background for the markers and skeleton, providing direct visual reference for editing.
- **Multi-Camera Support:** The add-on must support loading data from multiple camera angles into a single Blender scene. Each angle has its own video and pose data. The user must be able to switch between these camera views.
- **Multi-Person Identity Stitching:** Provide a pre-editing workflow to resolve tracking inconsistencies. Users can define a "real person" and construct a continuous animation track for them by stitching together various fragmented tracks from the source pose data. For example, a single real person might be composed of `track_A` (frames 1-50) and `track_C` (frames 51-100).
- **Data Loading:** Pose data is loaded from a directory of JSON files. The loader also receives a skeleton definition. Markers are named according to the skeleton.
- **Visualization:** Each marker is visualized as a small sphere. The skeleton is realized as a Blender armature whose bones connect the markers.
- **Color-Coded Feedback:** Sphere and bone colors dynamically indicate data quality. The base color is used for high-likelihood data, with different colors (e.g., gray, red) for low-likelihood or missing data.
- **Keyframe Animation:** All pose data is stored as keyframes on the sphere objects (location, and custom properties for likelihood and visibility).
- **Editing:** Users can manually adjust marker positions by moving the spheres in the 3D view, with changes automatically saved to the corresponding keyframe.
- **Data Export:** The edited animation data for a person can be exported to a numpy array.

## Multi-Person & Multi-Camera Management
A new management layer will handle the initial data loading and organization:
1.  **Project Setup:** The user defines a new project and imports one or more camera views.
2.  **Camera View:** Each camera view consists of a video file and a corresponding pose data directory.
3.  **Track Stitching UI:** For each camera view, a dedicated UI will be presented to the user:
    *   It lists all raw tracks detected in the pose data files (e.g., `person_1`, `person_2`, `person_3`).
    *   The user can create "Final Person" profiles (e.g., "Alice", "Bob").
    *   The user can then assign raw tracks and frame ranges to each Final Person. For example:
        *   `Alice` = `person_1` (1-100) + `person_3` (101-200)
        *   `Bob` = `person_2` (1-200)
4.  **Scene Generation:** Once the user confirms the stitching, the add-on generates the Blender objects. For each "Final Person" in each camera view, it creates a `PoseData2D` instance.

## Key Use Case Flow
1.  **Installation and Setup:** The user installs and enables the add-on. A "Pose Data Editor" panel appears in the 3D View.

2.  **Project and Camera Setup:**
    *   The user creates a new project.
    *   The user adds one or more camera views. For each view, they specify the video file and the pose data directory.
    *   The add-on creates a Blender camera for each view and sets up the video as a synchronized background.

3.  **Identity Stitching (Per Camera View):**
    *   The user selects a camera view to work on.
    *   In the add-on panel, a UI appears for stitching tracks. The user defines final persons and assigns the raw, fragmented tracks from the pose data to them.

4.  **Loading Data into Scene:**
    *   After stitching, the user clicks a "Load to Scene" button.
    *   The add-on creates `PoseData2D` objects for each defined person. This generates the spheres and armatures in the scene, parented under objects corresponding to their camera view.

5.  **Editing and Interaction:**
    *   The user can switch the active camera in Blender to change views.
    *   The user selects a marker and moves it to correct its position. The change is keyframed.
    *   The user can inspect and modify custom properties like `likelihood` in the properties panel.

6.  **Exporting Data:**
    *   The user selects a person and clicks "Export to NumPy" to save the corrected animation data to a file.

## Class Design: PoseData2D
Represents a single, continuous pose for one person.

### Constructor
- Parameters:
	- `parent_object`: Blender object (geometry parent).
	- `base_color`: tuple (RGBA).
	- `skeleton`: Skeleton structure.
	- `stitched_pose_data`: The consolidated pose data for a single person, passed in after the identity stitching phase.

### Methods
- `load_pose_data()`: Now takes the `stitched_pose_data` and creates the spheres, armature, and keyframes.
- (Other methods like `update_marker_colors`, `select_children`, `get_animation_array` remain largely the same).

## Data Flow
1.  User sets up camera views (video + pose data directory).
2.  For each view, the user performs identity stitching, mapping raw tracks to final persons.
3.  The application creates `PoseData2D` instances, passing the stitched data for each person.
4.  The `PoseData2D` object creates and manages the Blender visualization (spheres, armature).
5.  Keyframes and custom properties are set.
6.  Armature constraints link bones to the marker spheres.
7.  User edits the data, and can then export the result as a numpy array.

## Extensibility
- Support for 3D pose data by extending `PoseData2D` to `PoseData3D`.
- Visualization options (sphere size, armature style) can be parameterized.

## References
- Marker data format: See `2d-markers.py`
- Skeleton structure: See `skeletons.py`
