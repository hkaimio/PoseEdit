# SPDX-FileCopyrightText: 2025 Harri Kaimio
#
# SPDX-License-Identifier: BSD-3-Clause

"""Module for creating and managing the 3D visual representation of a person."""

from typing import TYPE_CHECKING, Optional

import numpy as np
from anytree import PreOrderIter

from ..blender import dal, dal3d
from .calibration import Calibration
from .marker_data import MarkerData
from .skeleton import SkeletonBase, get_skeleton

if TYPE_CHECKING:
    from .person_facade import RealPersonInstanceFacade

_all_3d_views_cache: dict[str, "Person3DView"] = {}

class Person3DView:
    """A facade for a person's 3D data view.

    Manages a 'Person 3D View' root Empty and its hierarchy of marker objects
    (Spheres for real markers, Empties for virtual ones) and a connecting armature.
    """

    def __init__(self, view_root_obj_ref: dal.BlenderObjRef):
        """Initializes the Person3DView as a wrapper around an existing Blender object."""
        self._init_from_blender_ref(view_root_obj_ref)

    def _init_from_blender_ref(self, view_root_obj_ref: dal.BlenderObjRef):
        """Initializes the instance from an existing Blender object reference."""
        self.view_root_object = view_root_obj_ref
        self.skeleton: Optional[SkeletonBase] = None
        self.color: Optional[tuple[float, float, float, float]] = None
        self._marker_objects_by_role: dict[str, dal.BlenderObjRef] = {}

        skeleton_name = dal.get_custom_property(view_root_obj_ref, dal.SKELETON)
        if skeleton_name:
            self.skeleton = get_skeleton(skeleton_name)
        self.color = dal.get_custom_property(view_root_obj_ref, dal.COLOR)
        self._populate_marker_objects_by_role()
        _all_3d_views_cache[view_root_obj_ref._id] = self

    def _populate_marker_objects_by_role(self):
        """Populates the marker dictionary by finding child objects with a MARKER_ROLE."""
        self._marker_objects_by_role = {}
        children = dal.get_children_of_object(self.view_root_object, recursive=True)
        for child_ref in children:
            role = dal.get_custom_property(child_ref, dal.MARKER_ROLE)
            if role:
                self._marker_objects_by_role[role] = child_ref

    @classmethod
    def from_blender_object(cls, view_root_obj_ref: dal.BlenderObjRef) -> Optional["Person3DView"]:
        """Builds a Person3DView from an existing Blender object."""
        if not view_root_obj_ref or not view_root_obj_ref._get_obj():
            return None
        
        if view_root_obj_ref._id in _all_3d_views_cache:
            return _all_3d_views_cache[view_root_obj_ref._id]
        
        obj_type = dal.get_custom_property(view_root_obj_ref, dal.POSE_EDITOR_OBJECT_TYPE)
        if obj_type != "Person3DView":
            return None
        instance = cls(view_root_obj_ref)
        return instance

    @classmethod
    def get_for_person(cls, person: "RealPersonInstanceFacade") -> Optional["Person3DView"]:
        """Finds the Person3DView for a given RealPersonInstanceFacade."""
        from .person_facade import PERSON_DEFINITION_REF

        all_3d_views = dal.find_all_objects_by_property(dal.POSE_EDITOR_OBJECT_TYPE, "Person3DView")
        for view_ref in all_3d_views:
            person_id = dal.get_custom_property(view_ref, PERSON_DEFINITION_REF)
            if person_id == person.obj._id:
                return cls.from_blender_object(view_ref)
        return None

    def get_person(self) -> Optional["RealPersonInstanceFacade"]:
        """Returns the RealPersonInstanceFacade associated with this view."""
        from .person_facade import PERSON_DEFINITION_REF, RealPersonInstanceFacade

        person_id = dal.get_custom_property(self.view_root_object, PERSON_DEFINITION_REF)
        if not person_id:
            return None
        person_obj_ref = dal.get_object_by_name(person_id)
        if not person_obj_ref:
            return None
        return RealPersonInstanceFacade.from_blender_obj(person_obj_ref)

    @classmethod
    def create_new(
        cls,
        view_name: str,
        skeleton: SkeletonBase,
        color: tuple[float, float, float, float],
        parent_ref: dal.BlenderObjRef,
        person: Optional["RealPersonInstanceFacade"] = None,
    ) -> "Person3DView":
        """Creates a new Person3DView, including its Blender objects."""
        from .person_facade import PERSON_DEFINITION_REF

        # Create collection hierarchy
        person_views_col = dal.get_or_create_collection("PersonViews")
        triangulated_col = dal.get_or_create_collection("Triangulated", parent_collection=person_views_col)
        p3d_col = dal.get_or_create_collection(view_name, parent_collection=triangulated_col)

        body_part_collections = {}
        for part_name in skeleton.body_parts():
            body_part_collections[part_name] = dal.get_or_create_collection(part_name, parent_collection=p3d_col)

        # The main P3D object goes into the triangulated_col
        view_root_object = dal.get_or_create_object(
            name=view_name,
            obj_type="EMPTY",
            collection_name=triangulated_col.name,
            parent=parent_ref,
        )

        dal.set_custom_property(view_root_object, dal.POSE_EDITOR_OBJECT_TYPE, "Person3DView")
        dal.set_custom_property(view_root_object, dal.SKELETON, skeleton.name)
        dal.set_custom_property(view_root_object, dal.COLOR, color)
        dal.set_custom_property(view_root_object, PERSON_DEFINITION_REF, person.obj._id if person and person.obj else "")

        instance = cls(view_root_object)
        instance.skeleton = skeleton
        instance.color = color
        instance._marker_objects_by_role = {}

        instance._create_marker_objects(body_part_collections)
        instance._create_armature()
        instance._create_drivers()

        return instance

    def get_marker_objects(self) -> dict[str, dal.BlenderObjRef]:
        """Returns a dictionary of marker objects in this view, keyed by their role."""
        return self._marker_objects_by_role

    def connect_to_series(self, marker_data: MarkerData):
        """Connects the marker objects in this view to a MarkerData action.

        Args:
            marker_data: The MarkerData instance containing the animation action.
        """
        if not marker_data or not marker_data.action:
            print(f"Warning: Cannot connect Person3DView to an invalid MarkerData series.")
            return

        # Store the ID of the MarkerData this view is connected to
        dal.set_custom_property(self.view_root_object, dal.MARKER_DATA_ID, marker_data._obj._id)

        # Assign the action to each marker object, targeting the correct slot
        for role, marker_obj_ref in self._marker_objects_by_role.items():
            dal.assign_action_to_object(marker_obj_ref, marker_data.action, slot_name=role)

        print(f"Connected 3D view '{self.view_root_object.name}' to action '{marker_data.action.name}'.")

    def get_animation_data_as_numpy(self) -> tuple[np.ndarray, list[tuple[str, str]]]:
        """
        Retrieves the triangulated 3D animation data as a NumPy array.

        Returns:
            A tuple containing:
            - A 2D NumPy array of shape (frames, columns) with the animation data.
            - A list of (marker_name, data_description) tuples for each column.
        """
        # 1. Get MarkerData and Action
        marker_data_id = dal.get_custom_property(self.view_root_object, dal.MARKER_DATA_ID)
        if not marker_data_id:
            return np.array([]), []

        marker_data_obj_ref = dal.get_object_by_name(marker_data_id)
        if not marker_data_obj_ref:
            return np.array([]), []

        marker_data = MarkerData.from_blender_object(marker_data_obj_ref)
        if not marker_data or not marker_data.action:
            return np.array([]), []

        action = marker_data.action

        # 2. Get frame range
        start_frame, end_frame = dal.get_scene_frame_range()
        num_frames = end_frame - start_frame + 1

        # 3. Get camera names
        calibration = Calibration()
        camera_names = calibration.get_camera_names() if calibration._data else []

        column_info = []
        all_columns_data = []

        # 4. Iterate through markers in skeleton order
        for node in PreOrderIter(self.skeleton._skeleton):
            marker_name = node.name

            # Check if it's a real marker that has data
            if marker_name not in self._marker_objects_by_role:
                continue

            # -- Location and Interpolated --
            location_fcurves = [
                dal.get_fcurve_from_action(action, marker_name, "location", i) for i in range(3)
            ]

            # Location data
            for i, axis in enumerate(["x", "y", "z"]):
                column_info.append((marker_name, axis))
                if location_fcurves[i]:
                    all_columns_data.append(dal.sample_fcurve(location_fcurves[i], start_frame, end_frame))
                else:
                    all_columns_data.append(np.full(num_frames, np.nan))

            # Interpolated data
            column_info.append((marker_name, "interpolated"))
            keyframed_frames = set()
            for fcurve in location_fcurves:
                if fcurve:
                    keyframes = dal.get_fcurve_keyframes(fcurve)
                    keyframed_frames.update([int(frame) for frame, _ in keyframes])

            interpolated_col = np.zeros(num_frames, dtype=bool)
            for frame_idx in range(num_frames):
                if (start_frame + frame_idx) in keyframed_frames:
                    interpolated_col[frame_idx] = True
            all_columns_data.append(interpolated_col)

            # -- Custom Properties --
            properties_to_fetch = [
                ("reprojection_error", '["reprojection_error"]', -1),
                ("contributing_cameras_count", '["contributing_cam_count"]', -1),
            ]
            for cam_name in camera_names:
                properties_to_fetch.append((f"contrib_{cam_name}", f'["contrib_{cam_name}"]', -1))

            for prop_name, data_path, index in properties_to_fetch:
                column_info.append((marker_name, prop_name))
                fcurve = dal.get_fcurve_from_action(action, marker_name, data_path, index)
                if fcurve:
                    all_columns_data.append(dal.sample_fcurve(fcurve, start_frame, end_frame))
                else:
                    all_columns_data.append(np.full(num_frames, np.nan))

        # 5. Combine into a single array
        if not all_columns_data:
            return np.array([]), []

        final_data = np.column_stack(all_columns_data)

        return final_data, column_info

    def _create_marker_objects(self, body_part_collections: dict[str, "bpy.types.Collection"]):
        """Creates a marker object for each joint in the skeleton."""
        calibration = Calibration()
        all_camera_names = calibration.get_camera_names() if calibration._data else []

        for node in PreOrderIter(self.skeleton._skeleton):
            marker_name = node.name
            body_part = self.skeleton.body_part(marker_name)
            marker_collection = body_part_collections.get(body_part)

            marker_ref = None
            if hasattr(node, "id") and node.id is not None:
                marker_ref = dal3d.create_sphere_marker(
                    parent=self.view_root_object,
                    name=marker_name,
                    color=self.color,
                    collection=marker_collection,
                )
            else:
                marker_ref = dal.create_empty(
                    name=f"{self.view_root_object.name}_{marker_name}",
                    collection=marker_collection,
                    parent_obj=self.view_root_object,
                )

            # Initialize all custom properties that will be driven by F-Curves
            dal.set_custom_property(marker_ref, dal.MARKER_ROLE, marker_name)
            dal.set_custom_property(marker_ref, dal.BODY_PART, body_part)
            marker_obj = marker_ref._get_obj()
            marker_obj["reprojection_error"] = 0.0
            marker_obj["contributing_cam_count"] = 0
            for cam_name in all_camera_names:
                marker_obj[f"contrib_{cam_name}"] = False

            self._marker_objects_by_role[marker_name] = marker_ref

    def _create_armature(self):
        """Creates an armature with bones connecting the markers."""
        armature_name = f"{self.view_root_object.name}_Armature"
        armature_object = dal.get_or_create_object(
            name=armature_name, obj_type="ARMATURE", collection_name="PersonViews", parent=self.view_root_object
        )
        armature_object._get_obj().color = self.color
        dal.set_armature_display_stick(armature_object)

        bones_to_add = []
        for node in PreOrderIter(self.skeleton._skeleton):
            if node.parent:
                parent_marker_role = node.parent.name
                child_marker_role = node.name

                if parent_marker_role in self._marker_objects_by_role and child_marker_role in self._marker_objects_by_role:
                    bone_name = f"{parent_marker_role}-{child_marker_role}"
                    bones_to_add.append((bone_name, (0, 0, 0), (0, 1, 0)))

        if bones_to_add:
            dal.add_bones_in_bulk(armature_object, bones_to_add)

        for node in PreOrderIter(self.skeleton._skeleton):
            if node.parent:
                parent_marker_role = node.parent.name
                child_marker_role = node.name

                parent_marker = self._marker_objects_by_role.get(parent_marker_role)
                child_marker = self._marker_objects_by_role.get(child_marker_role)

                if parent_marker and child_marker:
                    bone_name = f"{parent_marker_role}-{child_marker_role}"
                    dal.add_bone_constraint(armature_object, bone_name, "COPY_LOCATION", parent_marker)
                    dal.add_bone_constraint(armature_object, bone_name, "STRETCH_TO", child_marker)

    def _create_drivers(self):
        """Creates drivers for the virtual markers based on hardcoded rules."""
        virtual_definitions = {
            "Hip": ("LHip", "RHip"),
            "Neck": ("LShoulder", "RShoulder"),
            "Head":("LEar", "REar")
        }

        for virtual_name, (source1_name, source2_name) in virtual_definitions.items():
            virtual_marker = self._marker_objects_by_role.get(virtual_name)
            source1 = self._marker_objects_by_role.get(source1_name)
            source2 = self._marker_objects_by_role.get(source2_name)

            if not (virtual_marker and source1 and source2):
                continue

            dal3d.add_midpoint_driver(
                target_obj_ref=virtual_marker, source_a_ref=source1, source_b_ref=source2
            )
