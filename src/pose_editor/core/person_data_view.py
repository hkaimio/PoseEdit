# SPDX-FileCopyrightText: 2025 Harri Kaimio
#
# SPDX-License-Identifier: BSD-3-Clause

from typing import Optional, TYPE_CHECKING

import numpy as np

from ..blender import dal
from .frame_handler import frame_handler

if TYPE_CHECKING:
    from .camera_view import CameraView
from .marker_data import MarkerData, REQUESTED_SOURCE_ID, APPLIED_SOURCE_ID
from .skeleton import SkeletonBase, get_skeleton
from .person_facade import RealPersonInstanceFacade, PERSON_DEFINITION_REF
from ..blender.dal import CAMERA_VIEW_ID

SKELETON_NAME = dal.CustomProperty[str]("skeleton_name")

_all_person_data_views_cache: dict[str, "PersonDataView"] = {}

class PersonDataView:
    """A facade for a person's 2D data view (View layer).

    Manages a 'Person View' root Empty and its hierarchy of marker Empties,
    which visually represent the animation data from a MarkerData series.

    Blender Representation:
    -   **Root Object**: A main Empty object (e.g., `PV.cam1_person0_raw`) in the
        `PersonViews` collection. This object acts as the parent for all visual
        components of this person-view.
    -   **Marker Objects**: For each joint in the skeleton, a child Empty is
        created. These are the objects that are ultimately animated.
    -   **Armature Object**: A child Armature object is created with bones
        connecting the marker objects. The bones use `COPY_LOCATION` and
        `STRETCH_TO` constraints to follow the markers.

    Custom Properties on Root Object (`view_root_object`):
    -   `pose_editor_object_type` (str): Identifies this object as a "PersonDataView".
    -   `skeleton` (str): The name of the skeleton definition used (e.g., "COCO_133").
    -   `color` (tuple[float, float, float, float]): The RGBA color of the markers.
    -   `camera_view_id` (str): The name of the CameraView this PersonDataView belongs to.
    """

    def __init__(self, view_root_obj_ref: dal.BlenderObjRef):
        """Initializes the PersonDataView as a wrapper around an existing Blender object.

        Do not call this constructor directly; use the factory methods create_new()
        or from_blender_object() instead.

        Args:
            view_root_obj_ref: A BlenderObjRef pointing to the root Empty of the
                               existing PersonDataView (e.g., PV.Alice.cam1).
        """
        self._obj = view_root_obj_ref
        self.skeleton: Optional[SkeletonBase] = None
        self._init_from_blender_ref(view_root_obj_ref)

        # If this is a "Real Person" view, register for frame changes.
        if self.get_person() is not None:
            frame_handler.add_callback(self._check_and_update_frame)

    def __del__(self):
        """Destructor to unregister the callback when the object is garbage collected."""
        if hasattr(self, "_check_and_update_frame") and self.get_person() is not None:
            frame_handler.remove_callback(self._check_and_update_frame)

    def _init_from_blender_ref(self, view_root_obj_ref: dal.BlenderObjRef):
        """Initializes the PersonDataView from an existing Blender object.

        This method assumes the Blender objects (root Empty, markers, armature)
        already exist in the scene and initializes the Python wrapper around them.
        It does NOT create any new Blender objects.

        Args:
            view_root_obj_ref: A BlenderObjRef pointing to the root Empty of the
                               existing PersonDataView (e.g., PV.Alice.cam1).
        """
        self.view_root_object = view_root_obj_ref

        # Populate marker bones and find armature from existing Blender objects
        self._marker_bones_by_role: dict[str, str] = {}
        self._find_armature_and_populate_marker_bones()

        skeleton_name = dal.get_custom_property(view_root_obj_ref, SKELETON_NAME)
        if skeleton_name:
            self.skeleton = get_skeleton(skeleton_name)

    @classmethod
    def create_new(
        cls,
        view_name: str,
        skeleton,
        color,
        camera_view,
        collection=None, # This will be ignored and re-calculated
        person: Optional[RealPersonInstanceFacade] = None,
        marker_data: Optional[MarkerData] = None,
    ) -> "PersonDataView":
        """
        Creates a new PersonDataView object in Blender.

        Args:
            view_name: Name for the view.
            skeleton: Skeleton object.
            color: Color tuple.
            camera_view: CameraView object.
            collection: (Ignored) The collection to add to.
            person: Optional RealPersonInstanceFacade to associate.
            marker_data: Optional MarkerData to connect to.

        Returns:
            PersonDataView: The newly created instance.
        """
        from .camera_view import CameraView

        # Create the collection hierarchy
        person_views_col = dal.get_or_create_collection("PersonViews")

        # Handle optional camera_view
        if camera_view and camera_view._obj:
            camera_col = dal.get_or_create_collection(f"CameraView_{camera_view._obj.name}", parent_collection=person_views_col)
            parent_obj = camera_view._obj
        else:
            camera_col = person_views_col
            parent_obj = None

        pv_col = dal.get_or_create_collection(view_name, parent_collection=camera_col)

        # Create body part sub-collections
        body_part_collections = {}
        for part_name in skeleton.body_parts():
            body_part_collections[part_name] = dal.get_or_create_collection(f"{part_name}_{view_name}", parent_collection=pv_col)

        # The main PV object goes into the camera-level collection
        obj = dal.get_or_create_object(
            name=view_name, obj_type="EMPTY", collection_name=camera_col.name, parent=parent_obj
        )
        # Set custom properties
        dal.set_custom_property(obj, dal.SERIES_NAME, view_name)
        dal.set_custom_property(obj, SKELETON_NAME, skeleton.name)
        dal.set_custom_property(obj, dal.COLOR, color)
        dal.set_custom_property(obj, CAMERA_VIEW_ID, camera_view._obj.name if camera_view and camera_view._obj else "")
        dal.set_custom_property(obj, PERSON_DEFINITION_REF, person.obj._id if person and person.obj else "")
        dal.set_custom_property(obj, dal.POSE_EDITOR_OBJECT_TYPE, "PersonDataView")
        instance = cls(obj)

        # Set skeleton and view_root_object before creating armature
        instance.view_root_object = obj
        instance.skeleton = skeleton
        instance._marker_bones_by_role = {}
        
        # Create armature with both marker and connecting bones
        instance._create_armature_with_bones(body_part_collections)
        
        # Now initialize from Blender to find and populate the armature reference
        instance._init_from_blender_ref(obj)

        # Set location and scale from camera view if available
        if camera_view:
            obj._get_obj().location = camera_view.translation
            obj._get_obj().scale = camera_view.scale

        if marker_data:
            instance.connect_to_series(marker_data)

        return instance

    def get_camera_view(self) -> Optional["CameraView"]:
        """
        Returns the CameraView object associated with this PersonDataView, or None if not assigned.
        """
        camera_view_id = dal.get_custom_property(self._obj, CAMERA_VIEW_ID)
        if not camera_view_id:
            return None
        from .camera_view import CameraView

        return CameraView.get_by_id(camera_view_id)

    @property
    def camera_view_id(self) -> Optional[str]:
        """
        Returns the ID of the CameraView this PersonDataView belongs to, or None if not assigned.
        """
        return dal.get_custom_property(self._obj, CAMERA_VIEW_ID)

    def get_person(self) -> Optional[RealPersonInstanceFacade]:
        """Returns the RealPersonInstanceFacade associated with this view."""
        from .person_facade import RealPersonInstanceFacade, PERSON_DEFINITION_REF

        person_id = dal.get_custom_property(self._obj, PERSON_DEFINITION_REF)
        if not person_id:
            return None
        return RealPersonInstanceFacade.get_by_id(person_id)

    @property
    def view_name(self) -> str:
        """Returns the name of this PersonDataView."""
        return dal.get_custom_property  (self._obj, dal.SERIES_NAME) or ""

    @property
    def color(self) -> tuple[float, float, float, float]:
        """Returns the RGBA color of this PersonDataView."""
        return dal.get_custom_property(self._obj, dal.COLOR) or (1.0, 1.0, 1.0, 1.0)

    def camera_view(self) -> Optional["CameraView"]:
        """Returns the CameraView this PersonDataView belongs to."""
        camera_view_id = dal.get_custom_property(self._obj, CAMERA_VIEW_ID)
        if not camera_view_id:
            return None
        from .camera_view import CameraView

        return CameraView.get_by_id(camera_view_id)

    @classmethod
    def get_by_id(cls, object_id: str) -> Optional["PersonDataView"]:
        """Finds a PersonDataView by its unique object ID.

        Args:
            object_id: The unique ID of the PersonDataView root object.

        Returns:
            A PersonDataView instance if found, otherwise None.
        """
        obj_ref = dal.find_object_by_property(dal.POSE_EDITOR_OBJECT_ID, object_id)
        if not obj_ref:
            return None
        return cls.from_blender_object(obj_ref)

    @classmethod
    def from_blender_object(cls, view_root_obj_ref: dal.BlenderObjRef) -> Optional["PersonDataView"]:
        """Builds a PersonDataView instance from an existing Blender object.

        This factory method assumes the Blender objects (root Empty, markers, armature)
        already exist in the scene and initializes the Python wrapper around them.
        It does NOT create any new Blender objects.

        Args:
            view_root_obj_ref: A BlenderObjRef pointing to the root Empty of the
                               existing PersonDataView (e.g., PV.Alice.cam1).

        Returns:
            A PersonDataView instance initialized from the existing Blender data,
            or None if the object is not found or is not a valid PersonDataView root.
        """
        if not view_root_obj_ref or not view_root_obj_ref._get_obj():
            return None

        if view_root_obj_ref._id in _all_person_data_views_cache:
            return _all_person_data_views_cache[view_root_obj_ref._id]

        obj_type = dal.get_custom_property(view_root_obj_ref, dal.POSE_EDITOR_OBJECT_TYPE)
        if obj_type != "PersonDataView":
            return None

        instance = cls(view_root_obj_ref)
        instance._init_from_blender_ref(view_root_obj_ref)
        _all_person_data_views_cache[view_root_obj_ref._id] = instance
        return instance

    @classmethod
    def get_all(cls) -> list["PersonDataView"]:
        """Returns all PersonDataView objects in the Blender file."""
        objs = dal.find_all_objects_by_property(dal.POSE_EDITOR_OBJECT_TYPE, "PersonDataView")
        ret = []
        for o in objs:
            if o is None:
                continue
            pdv = cls.from_blender_object(o)
            if pdv is not None:
                ret.append(pdv)
        return ret

    @classmethod
    def get_all_for_camera_view(cls, camera_view: "CameraView") -> list["PersonDataView"]:
        """Returns all PersonDataViews that belong to the given camera view."""
        if camera_view._obj is None:
            return []
        camera_view_id = camera_view._obj._id
        objs = cls.get_all()
        ret = []
        for o in objs:
            if o is None:
                continue
            pdv = cls.from_blender_object(dal.BlenderObjRef(o.view_name))
            if pdv is not None and pdv.camera_view_id == camera_view_id:
                ret.append(pdv)
        return ret

    def _create_armature_with_bones(self, body_part_collections: dict[str, "dal.CollectionRef"]):
        """Creates an armature with marker bones and connecting bones."""
        import os
        from anytree import PreOrderIter

        armature_name = f"{self.view_name}_Armature"
        armature_object = dal.get_or_create_object(
            name=armature_name,
            obj_type="ARMATURE",
            collection_name="PersonViews",
            parent=self.view_root_object,
        )
        armature_object._get_obj().color = self.color
        dal.set_armature_display_stick(armature_object)
        self.armature_ref = armature_object

        # Load custom shape widgets
        extension_dir = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
        widgets_path = os.path.join(extension_dir, "assets", "widgets.blend")
        sphere_widget = dal.load_widget_from_blend(widgets_path, "WGT-sphere")
        line_widget = dal.load_widget_from_blend(widgets_path, "WGT-line")

        # Create bone collections
        dal.create_bone_collection(armature_object, "Markers")
        for body_part_name in self.skeleton.body_parts():
            dal.create_bone_collection(armature_object, body_part_name)

        # Prepare all bones (markers + connecting)
        bones_to_add = []

        # Add marker bones
        for node in PreOrderIter(self.skeleton._skeleton):
            if not (hasattr(node, "id") and node.id is not None):
                continue
            marker_name = node.name
            bones_to_add.append((marker_name, (0, 0, 0), (0, 0.01, 0)))
            self._marker_bones_by_role[marker_name] = marker_name

        # Add connecting bones
        for node in self.skeleton._skeleton.descendants:
            if node.parent and hasattr(node, "id") and node.id is not None:
                parent_marker_role = node.parent.name
                child_marker_role = node.name
                bone_name = f"{parent_marker_role}-{child_marker_role}"
                bones_to_add.append((bone_name, (0, 0, 0), (0, 1, 0)))

        # Create all bones in one edit mode session
        dal.add_bones_in_bulk(armature_object, bones_to_add)

        # Set custom properties and collections for marker bones
        for node in PreOrderIter(self.skeleton._skeleton):
            if not (hasattr(node, "id") and node.id is not None):
                continue
            marker_name = node.name
            body_part = self.skeleton.body_part(marker_name)

            # Set custom properties on bone
            dal.set_bone_custom_property(armature_object, marker_name, dal.MARKER_ROLE, marker_name)
            dal.set_bone_custom_property(armature_object, marker_name, dal.BODY_PART, body_part)

            # Initialize quality custom property (will be animated by F-curves)
            armature_obj = armature_object._get_obj()
            pose_bone = armature_obj.pose.bones.get(marker_name)
            if pose_bone:
                pose_bone["quality"] = 0.0

            # Move to Markers collection
            dal.move_bone_to_collection(armature_object, marker_name, "Markers")

            # Set custom shape
            if sphere_widget:
                dal.set_bone_custom_shape(
                    armature_object, marker_name, sphere_widget,
                    scale=0.02, wireframe=True, wire_width=3.0
                )

        # Add constraints to connecting bones
        for node in self.skeleton._skeleton.descendants:
            if not (node.parent and hasattr(node, "id") and node.id is not None):
                continue

            parent_marker_role = node.parent.name
            child_marker_role = node.name
            parent_marker_bone = self._marker_bones_by_role.get(parent_marker_role)
            child_marker_bone = self._marker_bones_by_role.get(child_marker_role)

            if parent_marker_bone and child_marker_bone:
                bone_name = f"{parent_marker_role}-{child_marker_role}"

                # Add constraints (target is armature, subtarget is bone name)
                dal.add_bone_constraint(
                    armature_object, bone_name, "COPY_LOCATION",
                    armature_object, parent_marker_bone
                )
                dal.add_bone_constraint(
                    armature_object, bone_name, "STRETCH_TO",
                    armature_object, child_marker_bone
                )

                # Note: Hide drivers are not implemented as the 'hide' property
                # on pose bones doesn't support drivers in the same way as other properties.
                # Visibility can be controlled manually or through bone collections.

                # Move to body part collection
                body_part = self.skeleton.body_part(child_marker_role)
                dal.move_bone_to_collection(armature_object, bone_name, body_part)

                # Set custom shape
                if line_widget:
                    dal.set_bone_custom_shape(
                        armature_object, bone_name, line_widget,
                        scale=1.0, wireframe=True, wire_width=3.0
                    )

    def _find_armature_and_populate_marker_bones(self):
        """Finds the armature and populates the marker bones dictionary."""
        self._marker_bones_by_role = {}
        self.armature_ref: dal.BlenderObjRef | None = None

        # Find armature child
        children = dal.get_children_of_object(self.view_root_object, recursive=False)
        for child_ref in children:
            child_obj = child_ref._get_obj()
            if child_obj and child_obj.type == "ARMATURE":
                self.armature_ref = child_ref
                # Get all bones with MARKER_ROLE custom property
                armature_obj = child_obj
                for bone in armature_obj.data.bones:
                    role = bone.get(dal.MARKER_ROLE._prop_name)
                    if role:
                        self._marker_bones_by_role[role] = bone.name
                break

        if not self.armature_ref:
            # Legacy: Try finding armature by name
            armature_name = f"{self.view_name}_Armature"
            self.armature_ref = dal.get_object_by_name(armature_name)
            if not self.armature_ref:
                print(f"Warning: Armature {armature_name} not found for PersonDataView {self.view_name}")

    def connect_to_series(self, marker_data: MarkerData):
        """Connects this view to a MarkerData series.

        This creates an armature action from the marker data by copying and remapping
        F-curves from per-marker slots to the armature's single slot.

        Args:
            marker_data: The MarkerData series to connect to.
        """
        if not self.armature_ref:
            print(f"Warning: Cannot connect {self.view_name} - no armature found.")
            return

        # Create armature action from marker data
        action_name = f"{self.view_name}_Action"
        new_action = dal.create_armature_action_from_marker_data(
            action_name=action_name,
            marker_action=marker_data.action,
            armature_obj_ref=self.armature_ref,
            marker_role_to_bone_name=self._marker_bones_by_role
        )

        # Assign the action to the armature
        dal.assign_action_to_object(self.armature_ref, new_action, self.armature_ref.name)

        # Store reference to marker data
        dal.set_custom_property(
            self.view_root_object,
            dal.MARKER_DATA_ID,
            marker_data.data_series_object_name
        )

    def get_data_series(self) -> Optional["MarkerData"]:
        """Returns the MarkerData series connected to this view."""
        marker_data_id = dal.get_custom_property(self.view_root_object, dal.MARKER_DATA_ID)
        if not marker_data_id:
            return None
        md_obj = dal.get_object_by_name(marker_data_id)
        if not md_obj:
            return None
        return MarkerData.from_blender_object(md_obj)

    def get_marker_objects(self) -> dict[str, dal.BlenderObjRef]:
        """Returns a dictionary of marker objects in this view, keyed by their role.

        LEGACY METHOD: This method is kept for backward compatibility.
        For bone-based views, this will return an empty dict.
        Use get_marker_bones() for the new bone-based architecture.
        """
        # Return marker objects if they exist (legacy object-based views)
        if hasattr(self, '_marker_objects_by_role'):
            return self._marker_objects_by_role
        return {}

    def get_marker_bones(self) -> dict[str, str]:
        """Returns a dictionary of marker bone names in this view, keyed by their role.

        NEW METHOD: Use this for bone-based PersonDataView architecture.
        Returns bone names (str) instead of BlenderObjRef.
        """
        return self._marker_bones_by_role

    def shift(self, delta_frames: int):
        """Shifts all marker data by the given number of frames.

        Args:
            delta_frames: The number of frames to shift. Positive values shift
                          forward in time, negative values shift backward.
        """
        if delta_frames == 0:
            return

        marker_data = self.get_data_series()
        if not marker_data:
            print(f"PersonDataView {self.view_name} is not connected to any MarkerData series.")
            return
        marker_data.shift(delta_frames)

    def _check_and_update_frame(self, scene, depsgraph=None):
        """Callback for the frame change handler.

        Checks and updates the current frame, and pre-emptively updates the
        next and previous frames to improve responsiveness during scrubbing.
        """
        current_frame = scene.frame_current
        self.update_frame_if_needed(current_frame - 1)
        self.update_frame_if_needed(current_frame)
        self.update_frame_if_needed(current_frame + 1)

    def set_requested_source_id(self, track_id: int, frame: int):
        """Sets a keyframe on the requested_source_id property.

        Args:
            track_id: The ID of the raw track to request.
            frame: The frame at which to set the request.
        """
        marker_data = self.get_data_series()
        if not marker_data:
            print(f"Warning: Cannot set requested source ID for {self.view_name} as it has no MarkerData.")
            return

        md_obj = marker_data._obj
        req_fcurve = dal.get_fcurve_on_object(md_obj, '["requested_source_id"]')
        if req_fcurve:
            dal.replace_fcurve_keyframes_in_range(req_fcurve, frame, frame+1, [(frame, track_id)], "CONSTANT")

        dal.set_custom_property(md_obj, REQUESTED_SOURCE_ID, track_id)
        dal.add_keyframe(md_obj, frame, {"requested_source_id": [track_id]})

    def update_frame_if_needed(self, frame: int):
        """Checks if the applied source matches the requested source for a given
        frame and performs a single-frame data copy if they differ.
        """
        # Guard clause: If this isn't a real person view, do nothing.
        if self.get_person() is None:
            return

        marker_data = self.get_data_series()
        if not marker_data or not self.skeleton:
            return

        md_obj = marker_data._obj
        scene_start, scene_end = dal.get_scene_frame_range()
        if not (scene_start <= frame <= scene_end):
            return

        # 1. Evaluate Properties
        req_fcurve = dal.get_fcurve_on_object(md_obj, '["requested_source_id"]')
        app_fcurve = dal.get_fcurve_on_object(md_obj, '["applied_source_id"]')

        requested_id = int(req_fcurve.evaluate(frame)) if req_fcurve else -1
        applied_id = int(app_fcurve.evaluate(frame)) if app_fcurve else -1

        # 2. Compare
        if requested_id == applied_id:
            return

        # 3. Perform Single-Frame Copy
        # Find the source PersonDataView (raw track)
        source_pdv = None
        if requested_id >= 0:
            cam_view = self.get_camera_view()
            if cam_view:
                raw_views = cam_view.get_raw_person_views()
                if requested_id < len(raw_views):
                    source_pdv = raw_views[requested_id]

        # Get the columns to copy from the skeleton
        columns_to_process: list[tuple[str, str, int]] = []
        from anytree import PreOrderIter
        for joint_node in PreOrderIter(self.skeleton._skeleton):
            if not (hasattr(joint_node, "id") and joint_node.id is not None):
                continue
            joint_name = joint_node.name
            columns_to_process.append((joint_name, "location", 0))  # X
            columns_to_process.append((joint_name, "location", 1))  # Y
            columns_to_process.append((joint_name, '["quality"]', -1))  # Quality

        # Get the data to write (either from source or NaNs)
        if requested_id == -2 or source_pdv is None: # -2 is "None"
            num_columns = len(columns_to_process)
            data_to_write = np.full((1, num_columns), np.nan)
            # Set quality to 0 for "None" source
            for i, col_def in enumerate(columns_to_process):
                if col_def[1] == '["quality"]':
                    data_to_write[:, i] = 0
        else:
            source_md = source_pdv.get_data_series()
            if not source_md or not source_md.action:
                return # Should not happen if everything is set up correctly
            data_to_write = dal.get_animation_data_as_numpy(
                source_md.action,
                columns_to_process,
                frame,
                frame,
            )

        # Write the single frame of data
        if marker_data.action:
            dal.replace_fcurve_segment_from_numpy(
                marker_data.action, columns_to_process, frame, frame, data_to_write
            )

        # 4. Update Applied ID
        if app_fcurve:
            app_fcurve.keyframe_points.insert(frame, requested_id)
        # dal.add_keyframe(md_obj, frame, {'["applied_source_id"]': [requested_id]})
