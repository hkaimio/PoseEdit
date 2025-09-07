from typing import Dict, List
from anytree import Node, findall
from ..pose2sim import skeletons

class SkeletonBase:
    """
    Represents a skeleton structure and provides methods to query joint information.

    This class wraps an `anytree.Node` object, which defines the hierarchical
    structure of a skeleton with joints identified by names and IDs.
    """

    def __init__(self, skeleton_def: Node):
        """
        Initializes the Skeleton with the root node of an anytree skeleton definition.

        Args:
            skeleton_def: The root `anytree.Node` of the skeleton definition.
        """
        self._skeleton = skeleton_def

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

    def calculate_fake_marker_pos(self, name: str, marker_data: Dict[str, List[float]]) -> List[float] | None:
        """
        Placeholder for future implementation to calculate fake marker positions.

        Args:
            name: The name of the fake marker.
            marker_data: A dictionary containing existing marker data.

        Returns:
            A list of floats representing the calculated position, or None.
        """
        pass


class COCO133Skeleton(SkeletonBase):
    """
    A specialized skeleton class for COCO_133 that calculates fake markers for Hip and Neck.
    """

    def __init__(self, skeleton_def: Node):
        super().__init__(skeleton_def)

    def calculate_fake_marker_pos(self, name: str, marker_data: Dict[str, List[float]]) -> List[float] | None:
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