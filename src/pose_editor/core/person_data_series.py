
from anytree import Node

from ..blender.dal import BlenderObjRef


class RawPersonData:
    _blenderObj: BlenderObjRef

    def __init__(self, blender_obj: BlenderObjRef):
        self._blenderObj = blender_obj
        self._markers: dict[str, BlenderObjRef] = {}
        self._skeleton: Node | None = None
