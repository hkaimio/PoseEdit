# SPDX-FileCopyrightText: 2025 Harri Kaimio
#
# SPDX-License-Identifier: BSD-3-Clause

"""Module for creating and managing the 3D visual representation of a person."""

from typing import TYPE_CHECKING, Optional

import numpy as np
from anytree import PreOrderIter

from ..blender import dal
from .calibration import Calibration
from .marker_data import MarkerData
from .skeleton import SkeletonBase, get_skeleton

if TYPE_CHECKING:
    from .person_facade import RealPersonInstanceFacade

_all_3d_views_cache: dict[str, "Person3DView"] = {}

class Person3DView:
    """A facade for a person's 3D data view.

    Manages a 'Person 3D View' root Empty and an armature with marker bones
    (organized into body part bone collections) and connecting bones with constraints.
    """

    def __init__(self, view_root_obj_ref: dal.BlenderObjRef):
        """Initializes the Person3DView as a wrapper around an existing Blender object."""
        self._init_from_blender_ref(view_root_obj_ref)

    def _init_from_blender_ref(self, view_root_obj_ref: dal.BlenderObjRef):
        """Initializes the instance from an existing Blender object reference."""
        self.view_root_object = view_root_obj_ref
        self.skeleton: SkeletonBase | None = None
        self.color: tuple[float, float, float, float] | None = None
        self.armature_ref: dal.BlenderObjRef | None = None
        self._marker_bones_by_role: dict[str, str] = {}  # role -> bone_name

        skeleton_name = dal.get_custom_property(view_root_obj_ref, dal.SKELETON)
        if skeleton_name:
            self.skeleton = get_skeleton(skeleton_name)
        self.color = dal.get_custom_property(view_root_obj_ref, dal.COLOR)
        self._find_armature_and_populate_marker_bones()
        _all_3d_views_cache[view_root_obj_ref._id] = self

    def _find_armature_and_populate_marker_bones(self):
        """Finds the armature and populates the marker bones dictionary."""
        self._marker_bones_by_role = {}
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

    @classmethod
    def from_blender_object(cls, view_root_obj_ref: dal.BlenderObjRef) -> Optional["Person3DView"]:
        """Builds a Person3DView from an existing Blender object."""
        if not view_root_obj_ref:
            return None

        obj = view_root_obj_ref._get_obj()
        if not obj:
            return None

        # Check if object is still valid (not deleted)
        try:
            _ = obj.name
        except ReferenceError:
            # Object was deleted, remove from cache if present
            if view_root_obj_ref._id in _all_3d_views_cache:
                del _all_3d_views_cache[view_root_obj_ref._id]
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
        person_id = person.obj._id if person and person.obj else ""
        dal.set_custom_property(view_root_object, PERSON_DEFINITION_REF, person_id)

        instance = cls(view_root_object)
        instance.skeleton = skeleton
        instance.color = color
        instance._marker_bones_by_role = {}

        instance._create_armature_with_bones(body_part_collections)
        instance._create_drivers()

        return instance

    def get_marker_bones(self) -> dict[str, str]:
        """Returns a dictionary of marker bone names in this view, keyed by their role."""
        return self._marker_bones_by_role

    def connect_to_series(self, marker_data: MarkerData):
        """Connects the marker bones in this view to a MarkerData action.

        Args:
            marker_data: The MarkerData instance containing the animation action.
        """
        if not marker_data or not marker_data.action:
            print("Warning: Cannot connect Person3DView to an invalid MarkerData series.")
            return

        if not self.armature_ref:
            print("Warning: Person3DView has no armature.")
            return

        # Store the ID of the MarkerData this view is connected to
        dal.set_custom_property(self.view_root_object, dal.MARKER_DATA_ID, marker_data._obj._id)

        # Create a new action for the armature with bone-specific F-curves
        # MarkerData has per-marker slots with data_path="location"
        # Bones need ONE armature slot with data_path='pose.bones["BoneName"].location'
        armature_action_name = f"{self.view_root_object.name}_Animation"
        armature_action = dal.create_armature_action_from_marker_data(
            armature_action_name,
            marker_data.action,
            self.armature_ref,
            self._marker_bones_by_role
        )

        # Assign the new action to the armature
        dal.assign_action_to_object(self.armature_ref, armature_action, slot_name=self.armature_ref.name)

        print(f"Connected 3D view '{self.view_root_object.name}' to action '{armature_action.name}'.")

    def get_animation_data_as_numpy(self) -> tuple[np.ndarray, list[tuple[str, str]]]:
        """
        Retrieves the triangulated 3D animation data as a NumPy array.

        Returns:
            A tuple containing:
            - A 2D NumPy array of shape (frames, columns) with the animation data.
            - A list of (marker_name, data_description) tuples for each column.
        """
        if not self.armature_ref:
            return np.array([]), []

        # Get the armature's action (created by connect_to_series)
        armature_obj = self.armature_ref._get_obj()
        if not armature_obj or not armature_obj.animation_data or not armature_obj.animation_data.action:
            return np.array([]), []

        action = armature_obj.animation_data.action

        # Get frame range
        start_frame, end_frame = dal.get_scene_frame_range()
        num_frames = end_frame - start_frame + 1

        # Get camera names
        calibration = Calibration()
        camera_names = calibration.get_camera_names() if calibration._data else []

        column_info = []
        all_columns_data = []

        # Get the armature's slot and channelbag
        armature_slot = armature_obj.animation_data.action_slot
        if not armature_slot or not action.layers:
            return np.array([]), []

        layer = action.layers[0]
        if not layer.strips:
            return np.array([]), []

        channelbag = layer.strips[0].channelbag(armature_slot)

        # Iterate through markers in skeleton order
        for node in PreOrderIter(self.skeleton._skeleton):
            marker_name = node.name

            # Check if it's a marker that has a bone
            if marker_name not in self._marker_bones_by_role:
                continue

            bone_name = self._marker_bones_by_role[marker_name]

            # -- Location and Interpolated --
            location_fcurves = []
            for i in range(3):
                data_path = f'pose.bones["{bone_name}"].location'
                fcurve = channelbag.fcurves.find(data_path, index=i)
                location_fcurves.append(fcurve)

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

            for prop_name, prop_suffix, index in properties_to_fetch:
                column_info.append((marker_name, prop_name))
                data_path = f'pose.bones["{bone_name}"]{prop_suffix}'
                fcurve = channelbag.fcurves.find(data_path, index=index)
                if fcurve:
                    all_columns_data.append(dal.sample_fcurve(fcurve, start_frame, end_frame))
                else:
                    all_columns_data.append(np.full(num_frames, np.nan))

        # Combine into a single array
        if not all_columns_data:
            return np.array([]), []

        final_data = np.column_stack(all_columns_data)

        return final_data, column_info

    def _create_armature_with_bones(self, body_part_collections: dict[str, "dal.CollectionRef"]):
        """Creates an armature with marker bones and connecting bones."""
        import os

        armature_name = f"{self.view_root_object.name}_Armature"
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

        # Create bone collections for body parts
        for body_part_name in self.skeleton.body_parts():
            dal.create_bone_collection(armature_object, body_part_name)

        # Prepare all bones to add (markers + connecting bones)
        bones_to_add = []
        calibration = Calibration()
        all_camera_names = calibration.get_camera_names() if calibration._data else []

        # Add marker bones
        for node in PreOrderIter(self.skeleton._skeleton):
            marker_name = node.name
            # Create a small bone at the origin, will be positioned by animation
            bones_to_add.append((marker_name, (0, 0, 0), (0, 0.01, 0)))
            self._marker_bones_by_role[marker_name] = marker_name

        # Add connecting bones
        for node in PreOrderIter(self.skeleton._skeleton):
            if node.parent:
                parent_marker_role = node.parent.name
                child_marker_role = node.name
                bone_name = f"{parent_marker_role}-{child_marker_role}"
                bones_to_add.append((bone_name, (0, 0, 0), (0, 1, 0)))

        # Create all bones in one edit mode session
        dal.add_bones_in_bulk(armature_object, bones_to_add)

        # Set custom properties on marker bones and assign to collections
        for node in PreOrderIter(self.skeleton._skeleton):
            marker_name = node.name
            body_part = self.skeleton.body_part(marker_name)

            # Set custom properties
            dal.set_bone_custom_property(armature_object, marker_name, dal.MARKER_ROLE, marker_name)
            dal.set_bone_custom_property(armature_object, marker_name, dal.BODY_PART, body_part)

            # Initialize custom properties that will be driven by F-Curves
            armature_obj = armature_object._get_obj()
            bone = armature_obj.pose.bones.get(marker_name)
            if bone:
                bone["reprojection_error"] = 0.0
                bone["contributing_cam_count"] = 0
                for cam_name in all_camera_names:
                    bone[f"contrib_{cam_name}"] = False

            # Move to body part collection
            dal.move_bone_to_collection(armature_object, marker_name, body_part)

            # Set custom shape for marker bone
            if sphere_widget:
                dal.set_bone_custom_shape(
                    armature_object, marker_name, sphere_widget, scale=0.02, wireframe=True, wire_width=3.0
                )

        # Add constraints to connecting bones and assign to body part collections
        for node in PreOrderIter(self.skeleton._skeleton):
            if node.parent:
                parent_marker_role = node.parent.name
                child_marker_role = node.name

                parent_marker_bone = self._marker_bones_by_role.get(parent_marker_role)
                child_marker_bone = self._marker_bones_by_role.get(child_marker_role)

                if parent_marker_bone and child_marker_bone:
                    bone_name = f"{parent_marker_role}-{child_marker_role}"
                    # Add constraints - target is the armature itself, subtarget is the bone
                    dal.add_bone_constraint(
                        armature_object, bone_name, "COPY_LOCATION", armature_object, parent_marker_bone
                    )
                    dal.add_bone_constraint(
                        armature_object, bone_name, "STRETCH_TO", armature_object, child_marker_bone
                    )

                    # Move to body part collection
                    body_part = self.skeleton.body_part(child_marker_role)
                    dal.move_bone_to_collection(armature_object, bone_name, body_part)

                    # Set custom shape for connecting bone
                    if line_widget:
                        dal.set_bone_custom_shape(
                            armature_object, bone_name, line_widget, scale=1.0, wireframe=True, wire_width=3.0
                        )

    def _create_drivers(self):
        """Creates drivers for the virtual marker bones based on hardcoded rules."""
        if not self.armature_ref:
            return

        virtual_definitions = {
            "Hip": ("LHip", "RHip"),
            "Neck": ("LShoulder", "RShoulder"),
            "Head": ("LEar", "REar"),
        }

        for virtual_name, (source1_name, source2_name) in virtual_definitions.items():
            virtual_marker_bone = self._marker_bones_by_role.get(virtual_name)
            source1_bone = self._marker_bones_by_role.get(source1_name)
            source2_bone = self._marker_bones_by_role.get(source2_name)

            if not (virtual_marker_bone and source1_bone and source2_bone):
                continue

            # Add midpoint driver for location (x, y, z)
            for axis_index in range(3):
                expression = "(source_a + source_b) / 2"
                variables = [
                    (
                        "source_a",
                        "SINGLE_PROP",
                        self.armature_ref._id,
                        f'pose.bones["{source1_bone}"].location[{axis_index}]',
                    ),
                    (
                        "source_b",
                        "SINGLE_PROP",
                        self.armature_ref._id,
                        f'pose.bones["{source2_bone}"].location[{axis_index}]',
                    ),
                ]
                dal.add_bone_driver(
                    self.armature_ref, virtual_marker_bone, f"location[{axis_index}]", expression, variables
                )
