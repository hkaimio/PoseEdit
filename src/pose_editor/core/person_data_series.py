from typing import Dict
from ..blender.dal import BlenderObjRef

class RawPersonData(object):

    _blenderObj: BlenderObjRef

    def __init__(self, blender_obj: BlenderObjRef):
        self._blenderObj = blender_obj
        self._markers: Dict[str, BlenderObjRef] = {}
        self._skeleton: anytree | None = None


