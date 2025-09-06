# Blender Add-on: Pose-Editor Design

## 1. Overview
This document outlines the design for a Blender add-on that provides an end-to-end pipeline for editing motion capture data. The workflow starts with editing 2D pose data captured from video, progresses to 3D reconstruction, and finishes with a fully rigged and animated 3D character.

The add-on is designed to handle complex scenarios with multiple camera angles and multiple people, providing workflows to consolidate fragmented tracking data. It will heavily integrate with **Pose2Sim**, a third-party Python library, to handle 3D triangulation, data filtering, and body measurement estimation.

## 2. Core Workflows & Requirements

### 2.1. 2D Pose Editing
- **Multi-Camera/Multi-Person:** Support loading multiple camera views (video + 2D pose data) and provide a workflow for stitching fragmented person tracks into continuous "Real Person" entities.
- **Synced Video:** Display the source video as a synchronized background for direct visual reference during editing.
- **Blender-Native Editing:** All 2D marker data should be editable using standard Blender tools (3D Viewport, Graph Editor, Dope Sheet).
- **Hierarchical Tools:** Provide tools for selecting and manipulating entire limbs (e.g., "Select Children" command that also sets the pivot point).

### 2.2. 3D Motion Capture Pipeline
- **Camera Calibration:** Load and manage camera calibration data (intrinsics/extrinsics in OpenCV format) required for 3D reconstruction.
- **3D Triangulation:** Use `Pose2Sim` to triangulate the corrected 2D marker data from multiple views into a 3D pose. This process is iterative.
- **3D Data Filtering:** Integrate `Pose2Sim`'s filters (e.g., Butterworth, Kalman) to process the raw 3D marker animation curves.
- **Armature Fitting:** Provide a workflow to scale a standard armature to a person's estimated body measurements (calculated via `Pose2Sim`) and then rig it to be driven by the 3D markers using Blender's IK constraints.
- **Finalization:** Bake the IK-driven animation onto the armature and provide export options.

## 3. Detailed Pipeline Stages

### 3.1. 2D Identity Stitching
This phase builds continuous tracks for real people from fragmented raw tracking data.
- **Initial Visualization:** All raw tracks are loaded, each with its own annotated skeleton and markers.
- **"Real Person" Creation:** The user creates a "Real Person" entity, which gets a dedicated armature.
- **Stitching via Keyframed Index:** A custom property (`active_track_index`) on the Real Person's armature is keyframed over time to dynamically switch between the raw tracks used as the data source.

### 3.2. 2D Editing and Interaction
- **Manual Keyframing:** Moving a marker automatically sets its `likelihood` to 1.0.
- **Occlusions:** Users can keyframe a `visible` property to mark markers as occluded.
- **Hierarchical Posing:** A "Select Children" command selects a limb and sets the pivot to the root joint for intuitive rotation.

### 3.3. Camera Calibration Management
- **Separation of Concerns:** Calibration data is managed separately from pose data, allowing calibrations to be reused across projects and sessions.
- **Data Structure:**
    - An **Extrinsics** file defines the positions of all cameras in a session.
    - Each camera in the Extrinsics file references an **Intrinsics** file.
    - Each 2D pose data set loaded into the project is linked to a specific camera from the active Extrinsics set.
- **UI:** The add-on will provide a panel for loading and managing these calibration files.

### 3.4. 3D Triangulation
- **Engine:** Uses a function from the `Pose2Sim` library.
- **Inputs:** Two or more sets of 2D marker data (as NumPy arrays) and the corresponding camera calibration data.
- **Process:** The user selects the "Real Persons" they want to triangulate. The add-on gathers the 2D data from all available camera views for that person and passes it to `Pose2Sim`.
- **Output:** A set of 3D markers (e.g., empties) animated in Blender. We will aim to modify the process to output and store metadata as custom properties on each 3D marker:
    - `reprojection_error`: The calculated error for the triangulation at that frame.
    - `contributing_views`: A list of camera views used to calculate the marker's position at that frame.
- **Iterative Workflow:** The user can review the 3D output, go back to the 2D views to correct marker positions for frames with high reprojection error, and then re-run triangulation on a specific frame range.

### 3.5. 3D Data Filtering
- **Engine:** Uses filtering functions from `Pose2Sim` (Butterworth, median, Kalman, etc.).
- **Process:** The user selects a 3D marker set and applies one or more filters via the UI.
- **Implementation:** The filter is applied to the f-curves of the 3D markers' location channels.
- **Reversibility:** Before filtering, the original f-curves are saved to a custom property on the marker object, allowing the user to revert the filtering operation if needed.

### 3.6. Armature Fitting and Rigging
This is a two-step process to create the final animated character.
1.  **Armature Scaling:**
    *   **Measurement Estimation:** Use `Pose2Sim` to estimate body measurements from the 3D marker data.
    *   **UI:** The add-on will display these measurements and allow the user to edit them.
    *   **Saving/Loading:** Person-specific measurements can be saved and reused in other projects.
    *   **Application:** The user selects a target armature, and the add-on scales its bones to match the final measurements.
2.  **IK Rigging:**
    *   After scaling, the add-on will automatically create an IK rig. It will add IK constraints to the armature's limbs and target them to the corresponding 3D markers.
    *   It will support setting this up for a standard Blender human armature (e.g., Rigify).

### 3.7. Finalization
- **Baking:** Once the user is satisfied with the IK-driven motion, they can "bake" the animation. This removes the constraints and keys the final rotation, location, and scale directly onto the armature's deforming bones.
- **Export:** The baked armature can be exported to other software using standard Blender exporters (e.g., FBX, glTF).

## 4. Overall Key Use Case Flow
1.  **Project Setup:** Load camera views (video + 2D data) and the corresponding camera calibration files.
2.  **2D Stitching & Editing:** Create "Real Person" entities and stitch their tracks. Correct the 2D marker data in all views.
3.  **3D Triangulation:** Run triangulation on the corrected 2D data to generate animated 3D markers.
4.  **Iterative 3D/2D Refinement:** Review the 3D markers. If errors exist (e.g., high reprojection error), go back to the 2D views, fix the markers on the problematic frames, and re-triangulate.
5.  **3D Filtering:** Apply filters (e.g., Butterworth) to the 3D marker animation curves to smooth the motion.
6.  **Armature Scaling:** Generate and fine-tune body measurements and scale a target armature.
7.  **IK Rigging:** Automatically set up IK constraints to make the scaled armature follow the 3D markers.
8.  **Baking & Export:** Bake the final animation onto the armature and export it.