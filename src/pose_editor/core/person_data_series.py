from ..blender.dal import BlenderObjRef

class PersonDataSeries2D(object):

    _blenderObj: BlenderObjRef

    def __init__(self, blender_obj: BlenderObjRef):
        self._blenderObj = blender_obj


    