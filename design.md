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

## Identity Stitching Workflow
This phase allows the user to build continuous tracks for real people from fragmented raw tracking data.

1.  **Initial Visualization:**
    *   Upon loading a camera view, all raw tracks from the pose data are loaded and visualized simultaneously. Each raw track will have its own skeleton and markers.
    *   To distinguish them, each raw track's visualization will be contained within a bounding box, and an annotation with the track ID (e.g., "track_a") will be displayed.

2.  **"Real Person" Creation:**
    *   The user creates a "Real Person" entity via the add-on UI.
    *   They assign it a unique name (e.g., "Alice") and a distinct base color for its visualization.
    *   This action creates a new, separate armature for the Real Person.

3.  **Stitching Process:**
    *   The user selects the first raw track that corresponds to the Real Person.
    *   They scrub through the timeline to a frame where the identity changes (e.g., the person is now tracked by a different raw ID).
    *   At this frame, the user selects the new raw track in the UI and clicks a "Switch Source" button.

4.  **Implementation via Keyframed Index:**
    *   The armature of the "Real Person" will hold the logic for data sourcing.
    *   It will have two custom properties:
        1.  `raw_track_names`: A string property holding a comma-separated list of all available raw track IDs (e.g., "track_a,track_b,track_c").
        2.  `active_track_index`: An integer property.
    *   When the user performs a "Switch Source" action at a given frame, the add-on inserts a keyframe on the `active_track_index` property, setting its value to the index of the new source track in the `raw_track_names` list.
    *   An operator or driver will be responsible for copying the animation data (marker locations, likelihoods) from the active raw track to the "Real Person's" markers. This data copy is effective from the keyframe onward, until a new keyframe on `active_track_index` is encountered.

## Key Use Case Flow
1.  **Installation and Setup:** The user installs and enables the add-on.

2.  **Project and Camera Setup:**
    *   The user adds one or more camera views, specifying a video file and pose data directory for each.
    *   The add-on creates Blender cameras and sets up the synchronized video backgrounds.

3.  **Identity Stitching (Per Camera View):**
    *   The user selects a camera view. All raw tracks are displayed with annotations.
    *   The user creates a "Real Person" (e.g., "Alice"), which gets its own armature.
    *   The user scrubs the timeline. At frames where the person's track ID changes, they use the UI to keyframe the `active_track_index` property on Alice's armature, pointing it to the correct raw track for that time segment.
    *   The system automatically updates Alice's animation data based on these keyframed index changes.

4.  **Editing and Interaction:**
    *   Once stitching is complete, the user can hide the raw track visualizations.
    *   The user can switch between camera views to see the stitched result from different angles.
    *   The user selects a marker on a "Real Person's" skeleton and moves it to correct its position. The change is keyframed on the Real Person's marker.

5.  **Exporting Data:**
    *   The user selects a "Real Person" and exports their continuous, corrected animation data to a NumPy file.

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
2.  For each view, the user performs identity stitching using the keyframed index method to map raw tracks to final, "Real Person" armatures.
3.  The animation data for the Real Person is dynamically sourced from the underlying raw tracks based on the `active_track_index` property.
4.  After stitching, the user can directly edit the markers on the Real Person's armature.
5.  User exports the final, edited data.

## Extensibility
- Support for 3D pose data by extending `PoseData2D` to `PoseData3D`.
- Visualization options (sphere size, armature style) can be parameterized.

## References
- Marker data format: See `2d-markers.py`
- Skeleton structure: See `skeletons.py`