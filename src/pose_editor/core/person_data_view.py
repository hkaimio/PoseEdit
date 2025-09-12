# SPDX-FileCopyrightText: 2025 Harri Kaimio
#
# SPDX-License-Identifier: BSD-3-Clause

from typing import List, Optional

from .marker_data import MarkerData
from .skeleton import SkeletonBase
from ..blender import dal
from anytree import Node, RenderTree


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
        self.view_name = view_root_obj_ref.name

        # Read properties from the Blender object
        self.skeleton = dal.get_custom_property(self.view_root_object, dal.SKELETON)
        self.color = dal.get_custom_property(self.view_root_object, dal.COLOR)
        self.camera_view_id = dal.get_custom_property(self.view_root_object, dal.CAMERA_VIEW_ID)

        # Populate marker objects and find armature from existing Blender objects
        self._marker_objects_by_role = {}
        self._populate_marker_objects_by_role()
        armature_name = f"{self.view_name}_Armature"
        self._armature_object = dal.get_object_by_name(armature_name)
        if not self._armature_object:
            print(f"Warning: Armature {armature_name} not found for existing PersonDataView {self.view_name}")

    def __init__(self, view_root_obj_ref: dal.BlenderObjRef):
        """Initializes the PersonDataView as a wrapper around an existing Blender object.

        Args:
            view_root_obj_ref: A BlenderObjRef pointing to the root Empty of the
                               existing PersonDataView (e.g., PV.Alice.cam1).
        """
        self._init_from_blender_ref(view_root_obj_ref)

    @classmethod
    def create_new(
        cls,
        view_name: str,
        skeleton: SkeletonBase,
        color: tuple[float, float, float, float],
        camera_view_obj_ref: dal.BlenderObjRef,
        collection: "bpy.types.Collection" = None,
    ) -> "PersonDataView":
        """Creates a new PersonDataView, including its Blender objects.

        Args:
            view_name: A unique name for this person view (e.g., "PV.Alice.cam1").
            skeleton: The skeleton definition to use for creating marker objects.
            color: The color for the markers (RGBA tuple).
            camera_view_obj_ref: The BlenderObjRef of the CameraView this PersonDataView belongs to.
            collection: The collection to link the root Empty to.

        Returns:
            A new PersonDataView instance.
        """
        # Create the root Empty for this view
        view_root_object = dal.get_or_create_object(
            name=view_name, obj_type="EMPTY", collection_name="PersonViews", parent=camera_view_obj_ref
        )

        # Set custom properties
        dal.set_custom_property(view_root_object, dal.POSE_EDITOR_OBJECT_TYPE, "PersonDataView")
        dal.set_custom_property(view_root_object, dal.SKELETON, skeleton._skeleton.name)
        dal.set_custom_property(view_root_object, dal.COLOR, color)
        dal.set_custom_property(view_root_object, dal.CAMERA_VIEW_ID, camera_view_obj_ref.name)

        # Create a temporary instance to call internal creation methods
        temp_instance = cls.__new__(cls)  # Bypass __init__ for now
        temp_instance.view_root_object = view_root_object
        temp_instance.view_name = view_name
        temp_instance.skeleton = skeleton
        temp_instance.color = color
        temp_instance.camera_view_id = camera_view_obj_ref.name
        temp_instance._marker_objects_by_role = {}

        # Create marker objects based on the skeleton definition
        print("Creating marker objects...")
        temp_instance._create_marker_objects(collection)
        # Populate the dictionary after creating markers
        print("Populating marker objects by role...")
        temp_instance._populate_marker_objects_by_role()

        # Create armature and bones
        print("Creating armature...")
        temp_instance._create_armature()

        # Now, call the actual __init__ to properly initialize the instance
        instance = cls(view_root_object)
        return instance

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

        # Check if it's a valid PersonDataView root object
        obj_type = dal.get_custom_property(view_root_obj_ref, dal.POSE_EDITOR_OBJECT_TYPE)
        if obj_type != "PersonDataView":
            print(f"Object {view_root_obj_ref.name} is not a PersonDataView root.")
            return None

        # Instantiate PersonDataView by calling its __init__ with the existing ref
        instance = cls(view_root_obj_ref)
        return instance

    @classmethod
    def from_existing_blender_object(
        cls, view_root_obj_ref: dal.BlenderObjRef, skeleton: SkeletonBase
    ) -> "PersonDataView":
        """Builds a PersonDataView instance from existing Blender objects.

        This factory method assumes the Blender objects (root Empty, markers, armature)
        already exist in the scene and initializes the Python wrapper around them.
        It does NOT create any new Blender objects.

        Args:
            view_root_obj_ref: A BlenderObjRef pointing to the root Empty of the
                               existing PersonDataView (e.g., PV.Alice.cam1).
            skeleton: The skeleton definition associated with this view.

        Returns:
            A PersonDataView instance initialized from the existing Blender data.
        """
        view_name = view_root_obj_ref.name
        # We need to retrieve the color from the existing objects if possible,
        # but for now, we'll use a default or assume it's set elsewhere.
        # For simplicity, let's assume the color is not critical for reconstruction
        # or can be derived from the first marker's original color properties.
        # For now, we'll use a default color.
        # A more robust solution would store the color on the view_root_object.
        color = (1.0, 1.0, 1.0, 1.0)  # Default color for reconstruction

        # Instantiate PersonDataView, telling it NOT to create Blender objects
        instance = cls(view_name, skeleton, color, create_blender_objects=False)

        # The __init__ with create_blender_objects=False already handles
        # populating _marker_objects_by_role and finding the armature.
        return instance

    def _create_marker_objects(self, collection: "bpy.types.Collection"):
        """Creates a marker object for each joint in the skeleton."""
        if self.skeleton is None or self.skeleton._skeleton is None:
            return

        from anytree import PreOrderIter

        for node in PreOrderIter(self.skeleton._skeleton):
            if not (hasattr(node, "id") and node.id is not None):
                continue

            marker_name = node.name
            dal.create_marker(parent=self.view_root_object, name=marker_name, color=self.color, collection=collection)

    def _create_armature(self):
        """Creates an armature with bones connecting the markers."""
        armature_name = f"{self.view_name}_Armature"
        self._armature_object = dal.get_or_create_object(
            name=armature_name, obj_type="ARMATURE", collection_name="PersonViews", parent=self.view_root_object
        )
        self._armature_object._get_obj().color = self.color

        dal.set_armature_display_stick(self._armature_object)

        bones_to_add = []
        for node in self.skeleton._skeleton.descendants:
            if (
                node.parent
                and hasattr(node, "id")
                and node.id is not None
                and hasattr(node.parent, "id")
                and node.parent.id is not None
            ):
                parent_marker_role = node.parent.name
                child_marker_role = node.name

                parent_marker = self._marker_objects_by_role.get(parent_marker_role)
                child_marker = self._marker_objects_by_role.get(child_marker_role)

                if parent_marker and child_marker:
                    bone_name = f"{parent_marker_role}-{child_marker_role}"
                    # Placeholder head/tail, will be positioned by constraints
                    bones_to_add.append((bone_name, (0, 0, 0), (0, 1, 0)))

        # Create all bones in one go
        if bones_to_add:
            dal.add_bones_in_bulk(self._armature_object, bones_to_add)

        # Now, add constraints and drivers in a separate loop
        for node in self.skeleton._skeleton.descendants:
            if (
                node.parent
                and hasattr(node, "id")
                and node.id is not None
                and hasattr(node.parent, "id")
                and node.parent.id is not None
            ):
                parent_marker_role = node.parent.name
                child_marker_role = node.name

                parent_marker = self._marker_objects_by_role.get(parent_marker_role)
                child_marker = self._marker_objects_by_role.get(child_marker_role)

                if parent_marker and child_marker:
                    bone_name = f"{parent_marker_role}-{child_marker_role}"

                    dal.add_bone_constraint(self._armature_object, bone_name, "COPY_LOCATION", parent_marker)
                    dal.add_bone_constraint(self._armature_object, bone_name, "STRETCH_TO", child_marker)

                    # Add driver to hide bone
                    expression = "var1 or var2"
                    variables = [
                        ("var1", "SINGLE_PROP", parent_marker.name, "hide_viewport"),
                        ("var2", "SINGLE_PROP", child_marker.name, "hide_viewport"),
                    ]
                    dal.add_bone_driver(self._armature_object, bone_name, "hide", expression, variables)

    def _populate_marker_objects_by_role(self):
        """Populates the _marker_objects_by_role dictionary by reading custom properties."""
        self._marker_objects_by_role = {}
        for marker_obj_ref in dal.get_children_of_object(self.view_root_object):
            marker_role = dal.get_custom_property(marker_obj_ref, dal.MARKER_ROLE)
            if marker_role:
                self._marker_objects_by_role[marker_role] = marker_obj_ref

    def connect_to_series(self, marker_data: MarkerData):
        """Connects this view to a MarkerData series.

        This applies the animation data from the series to the marker objects
        in this view.

        Args:
            marker_data: The MarkerData series to connect to.
        """
        marker_data.apply_to_view(self)

    def get_marker_objects(self) -> dict[str, dal.BlenderObjRef]:
        """Returns a dictionary of marker objects in this view, keyed by their role."""
        return self._marker_objects_by_role
