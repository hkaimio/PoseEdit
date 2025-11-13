"""Operators for scaling rigs and exporting to OpenSim."""

import bpy

from ..core.person_facade import RealPersonInstanceFacade
from ..core.scale_model import create_and_scale_armature


class PE_OT_ScaleRigFromPerson(bpy.types.Operator):
    """Scale a Blender rig to match motion capture data from selected person."""

    bl_idname = "pose_editor.scale_rig_from_person"
    bl_label = "Scale Rig from Person"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        """Execute the scaling operation."""
        scene = context.scene

        # Get selected person
        if not hasattr(scene, 'pose_editor_props') or not scene.pose_editor_props.selected_person:
            self.report({'ERROR'}, "No person selected")
            return {'CANCELLED'}

        person_id = scene.pose_editor_props.selected_person

        # Find the person
        persons = RealPersonInstanceFacade.get_all()
        person = None
        for p in persons:
            if p.obj._id == person_id:
                person = p
                break

        if not person:
            self.report({'ERROR'}, f"Person with ID {person_id} not found")
            return {'CANCELLED'}

        # Get 3D view
        from ..core.person_3d_view import Person3DView
        view_3d = Person3DView.get_for_person(person)
        if not view_3d:
            self.report({'ERROR'}, "Person has no 3D triangulated data")
            return {'CANCELLED'}

        # Get animation data
        try:
            markers, columns = view_3d.get_animation_data_as_numpy()
        except Exception as e:
            self.report({'ERROR'}, f"Failed to get animation data: {str(e)}")
            return {'CANCELLED'}

        # Build column map
        col_map = {}
        for column, col_desc in enumerate(columns):
            marker = col_desc[0]
            meas = col_desc[1]
            col_map[(marker, meas)] = column

        # Create scaled armature
        try:
            rig_name = f"Scaled_{person.name}"
            create_and_scale_armature(markers, col_map, rig_name)
            self.report({'INFO'}, f"Created scaled rig: {rig_name}")
            return {'FINISHED'}
        except Exception as e:
            self.report({'ERROR'}, f"Failed to create scaled rig: {str(e)}")
            return {'CANCELLED'}


class PE_OT_ExportRigToOpenSim(bpy.types.Operator):
    """Export a Blender armature rig to OpenSim .osim format."""

    bl_idname = "pose_editor.export_rig_to_opensim"
    bl_label = "Export to OpenSim"
    bl_options = {'REGISTER'}

    # File browser properties
    filepath: bpy.props.StringProperty(subtype="FILE_PATH")
    filter_glob: bpy.props.StringProperty(default="*.osim", options={'HIDDEN'})

    # Export options
    opensim_collection_name: bpy.props.StringProperty(
        name="Bone Collection",
        description="Name of bone collection containing bones to export",
        default="opensim"
    )

    marker_collection_name: bpy.props.StringProperty(
        name="Marker Collection",
        description="Name of bone collection containing markers",
        default="Markers"
    )

    model_name: bpy.props.StringProperty(
        name="Model Name",
        description="Name for the OpenSim model",
        default="ExportedModel"
    )

    def invoke(self, context, event):
        """Open file browser."""
        # Set default filename based on active armature
        if context.active_object and context.active_object.type == 'ARMATURE':
            armature_name = context.active_object.name
            self.filepath = f"{armature_name}.osim"
            self.model_name = armature_name
        else:
            self.filepath = "exported_model.osim"

        context.window_manager.fileselect_add(self)
        return {'RUNNING_MODAL'}

    def draw(self, context):
        """Draw export options in file browser."""
        layout = self.layout

        layout.prop(self, "model_name")
        layout.prop(self, "opensim_collection_name")
        layout.prop(self, "marker_collection_name")

    def execute(self, context):
        """Execute the export operation."""
        # Ensure we have an active armature
        if not context.active_object or context.active_object.type != 'ARMATURE':
            self.report({'ERROR'}, "No armature selected. Please select an armature to export.")
            return {'CANCELLED'}

        armature_name = context.active_object.name
        output_file = self.filepath

        # Import the export function from core module
        try:
            from ..core.opensim_export import export_armature_to_opensim
        except ImportError as e:
            self.report({'ERROR'}, f"OpenSim export module not found: {str(e)}")
            return {'CANCELLED'}

        # Export
        try:
            export_armature_to_opensim(
                armature_name,
                output_file,
                opensim_collection_name=self.opensim_collection_name,
                model_name=self.model_name,
                marker_collection_name=self.marker_collection_name
            )
            self.report({'INFO'}, f"Exported OpenSim model to: {output_file}")
            return {'FINISHED'}
        except Exception as e:
            self.report({'ERROR'}, f"Export failed: {str(e)}")
            return {'CANCELLED'}
