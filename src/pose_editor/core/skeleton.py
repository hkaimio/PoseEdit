import ..pose2sim.skeletons
from anytree import Node

class Skeleton(object)
    def __init__(self, skeleton_def: Node):
        self._skeleton = skeleton_def
        pass

    def get_joint_name(self, id: int) -> str:
        pass

    def get_joint_id(self, name: str) -> int | None:
        pass

    def calculate_fake_maerker_pos(self, name: str, marker_data: Dict[str, List[float]]) -> List[float] | None:
        pass

    
