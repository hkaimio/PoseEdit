
from anytree import Node, findall
from ..pose2sim.skeletons import COCO_133, get_skeleton_definition
from dataclasses import dataclass
@dataclass 
class BodyPartDef:
    name: str
    parent_node_name: str
    include_parent: bool

class SkeletonBase:
    """
    Represents a skeleton structure and provides methods to query joint information.

    This class wraps an `anytree.Node` object, which defines the hierarchical
    structure of a skeleton with joints identified by names and IDs.
    """

    _body_part_map : dict[str, str] = {}

    def __init__(self, skeleton_def: Node, name: str = "UnnamedSkeleton", body_parts: list[BodyPartDef] = []):
        """
        Initializes the Skeleton with the root node of an anytree skeleton definition.

        Args:
            skeleton_def: The root `anytree.Node` of the skeleton definition.
        """
        self._skeleton = skeleton_def
        self._name = name
        self._body_parts = body_parts
        self._update_body_part_map_children(self._skeleton, "Unknown", body_parts)

    @property
    def name(self) -> str:
        """Returns the name of the skeleton."""
        return self._name

    def get_joint_name(self, joint_id: int) -> str | None:
        """
        Finds the name of a joint given its ID.

        Args:
            joint_id: The ID of the joint to find.

        Returns:
            The name of the joint if found, otherwise None.
        """
        if joint_id is None:
            return None

        nodes = findall(self._skeleton, lambda node: node.id == joint_id)
        if len(nodes) == 1:
            return nodes[0].name
        return None

    def get_joint_id(self, joint_name: str) -> int | None:
        """
        Finds the ID of a joint given its name.

        Args:
            joint_name: The name of the joint to find.

        Returns:
            The ID of the joint if found, otherwise None.
        """
        if joint_name is None:
            return None

        nodes = findall(self._skeleton, lambda node: node.name == joint_name)
        if len(nodes) == 1:
            return nodes[0].id
        return None

    def body_part(self, joint_name: str) -> str:
        """
        Determines the body part associated with a given joint name.

        Args:
            joint_name: The name of the joint to find.

        Returns:
            The name of the body part if found, otherwise None.
        """
        return self._body_part_map.get(joint_name, "Unknown")
    
    def body_parts(self) -> list[str]:
        """
        Returns a list of all defined body parts in the skeleton.

        Returns:
            A list of body part names.
        """
        return [bp.name for bp in self._body_parts]
    



    def calculate_fake_marker_pos(self, name: str, marker_data: dict[str, list[float]]) -> list[float] | None:
        """
        Placeholder for future implementation to calculate fake marker positions.

        Args:
            name: The name of the fake marker.
            marker_data: A dictionary containing existing marker data.

        Returns:
            A list of floats representing the calculated position, or None.
        """
        pass


    def _update_body_part_map_children(self, parent_node: Node, body_part_name: str, body_parts: list[BodyPartDef] = []):
        """
        Updates the internal mapping of joint names to body parts based on the defined body parts.
        """
        node_def = next((bp for bp in body_parts if bp.parent_node_name == parent_node.name), None)
        current_node_part = body_part_name
        if node_def:
            if node_def.include_parent:
                current_node_part = node_def.name
            body_part_name = node_def.name
        self._body_part_map[parent_node.name] = current_node_part

        for child in parent_node.children:
            self._update_body_part_map_children(child, body_part_name, body_parts)


_coco_133_body_parts =  [
        BodyPartDef("Torso", "Hip", True),
        BodyPartDef("Left leg", "LHip", False),
        BodyPartDef("Right leg", "RHip", False),
        BodyPartDef("Left arm", "LShoulder", False),
        BodyPartDef("Right arm", "RShoulder", False),
        BodyPartDef("Head", "Head", False),
        BodyPartDef("Left hand", "LPalm", True),
        BodyPartDef("Right hand", "RPalm", True),
        BodyPartDef("Left foot", "LAnkle", False),
        BodyPartDef("Right foot", "RAnkle", False),
    ]

class COCO133Skeleton(SkeletonBase):
    """
    A specialized skeleton class for COCO_133 that calculates fake markers for Hip and Neck.
    """


    def __init__(self):
        super().__init__(COCO_133, "COCO_133", _coco_133_body_parts)

    def calculate_fake_marker_pos(self, name: str, marker_data: dict[str, list[float]]) -> list[float] | None:
        """
        Calculates fake marker positions for 'Hip' and 'Neck' based on other joint data.

        Args:
            name: The name of the fake marker to calculate ('Hip' or 'Neck').
            marker_data: A dictionary containing existing marker data.
                         Expected format: {'joint_name': [x, y, z, ...]} or {'joint_name': [x, y, likelihood, ...]}

        Returns:
            A list of floats representing the calculated position, or None if input data is insufficient.
        """
        if name == "Hip":
            rhip_data = marker_data.get("RHip")
            lhip_data = marker_data.get("LHip")
            if rhip_data and lhip_data and len(rhip_data) == len(lhip_data):
                # Calculate midpoint for 2D or 3D coordinates
                midpoint = [(rhip_data[i] + lhip_data[i]) / 2 for i in range(len(rhip_data))]
                return midpoint
        elif name == "Neck":
            rshoulder_data = marker_data.get("RShoulder")
            lshoulder_data = marker_data.get("LShoulder")
            if rshoulder_data and lshoulder_data and len(rshoulder_data) == len(lshoulder_data):
                # Calculate midpoint for 2D or 3D coordinates
                midpoint = [(rshoulder_data[i] + lshoulder_data[i]) / 2 for i in range(len(rshoulder_data))]
                return midpoint

        return super().calculate_fake_marker_pos(name, marker_data)

def get_skeleton(skeleton_name: str) -> SkeletonBase:
    """
    Factory function to return a SkeletonBase (or subclass) for the given skeleton name.

    Args:
        skeleton_name (str): The name of the skeleton definition (e.g. "COCO_133", "HALPE_26").

    Returns:
        SkeletonBase: An instance of SkeletonBase or a subclass (e.g. COCO133Skeleton).

    Raises:
        ValueError: If no skeleton definition with the given name exists.
    """
    if skeleton_name == "COCO_133":
        return COCO133Skeleton()
    try:
        skeleton_def = get_skeleton_definition(skeleton_name)
        return SkeletonBase(skeleton_def, skeleton_name)
    except ValueError:
        raise ValueError(f"No skeleton definition found for '{skeleton_name}'")