"""Operator to apply rigging to scaled armature after triangulation."""

import bpy
from bpy.props import BoolProperty, StringProperty
from bpy.types import Operator

from ..blender import dal
from ..core.armature_rigging import ArmatureRiggingSystem


class POSE_EDITOR_OT_apply_rigging(Operator):
    """Apply rigging to scaled armature for motion capture tracking."""
    
    bl_idname = "pose_editor.apply_rigging"
    bl_label = "Apply Motion Capture Rigging"
    bl_description = "Add tracking bones and IK rigging to scaled armature"
    bl_options = {'REGISTER', 'UNDO'}
    
    # Properties
    armature_name: StringProperty(
        name="Armature Name",
        description="Name of the armature to rig",
        default=""
    )
    
    create_tracking_bones: BoolProperty(
        name="Create Tracking Bones",
        description="Create tracking bones for motion capture data",
        default=True
    )
    
    create_ik_chains: BoolProperty(
        name="Create IK Chains",
        description="Create IK chains for limbs",
        default=True
    )
    
    setup_pelvis_torso: BoolProperty(
        name="Setup Pelvis/Torso",
        description="Setup pelvis and torso mechanics",
        default=True
    )
    
    @classmethod
    def poll(cls, context):
        """Check if operator can be executed."""
        return (
            context.active_object and 
            context.active_object.type == 'ARMATURE' and
            context.mode == 'OBJECT'
        )
    
    def execute(self, context):
        """Execute the rigging operation."""
        try:
            # Get armature object
            if self.armature_name:
                armature_obj = bpy.data.objects.get(self.armature_name)
            else:
                armature_obj = context.active_object
                
            if not armature_obj or armature_obj.type != 'ARMATURE':
                self.report({'ERROR'}, "No valid armature found")
                return {'CANCELLED'}
            
            # Validate armature has Rigify structure
            armature = armature_obj.data
            if not self._validate_rigify_armature(armature):
                self.report({'ERROR'}, "Armature is not a valid Rigify skeleton")
                return {'CANCELLED'}
            
            # Initialize rigging system
            rigging_system = ArmatureRiggingSystem(armature)
            
            # Apply rigging based on options
            if self.create_tracking_bones:
                self.report({'INFO'}, "Creating tracking bones...")
                rigging_system.apply_tracking_bones()
            
            if self.create_ik_chains:
                self.report({'INFO'}, "Setting up IK chains...")
                rigging_system.apply_limb_mechanisms()
            
            if self.setup_pelvis_torso:
                self.report({'INFO'}, "Setting up pelvis and torso...")
                rigging_system.apply_pelvis_mechanism()
            
            # Update view layer
            dal.update_view_layer()
            
            self.report({'INFO'}, f"Rigging applied to armature '{armature_obj.name}'")
            return {'FINISHED'}
            
        except Exception as e:
            self.report({'ERROR'}, f"Failed to apply rigging: {str(e)}")
            return {'CANCELLED'}
    
    def _validate_rigify_armature(self, armature) -> bool:
        """Validate that armature has basic Rigify structure."""
        required_bones = ["spine", "spine.001"]
        
        for bone_name in required_bones:
            if bone_name not in armature.bones:
                print(f"Missing required bone: {bone_name}")
                return False
        
        return True
    
    def invoke(self, context, event):
        """Invoke operator with dialog."""
        if context.active_object and context.active_object.type == 'ARMATURE':
            self.armature_name = context.active_object.name
        
        return context.window_manager.invoke_props_dialog(self)
    
    def draw(self, context):
        """Draw operator properties panel."""
        layout = self.layout
        
        # Armature selection
        layout.prop_search(self, "armature_name", bpy.data, "objects")
        
        layout.separator()
        
        # Rigging options
        col = layout.column()
        col.prop(self, "create_tracking_bones")
        col.prop(self, "create_ik_chains")
        col.prop(self, "setup_pelvis_torso")


def register():
    """Register operator."""
    bpy.utils.register_class(POSE_EDITOR_OT_apply_rigging)


def unregister():
    """Unregister operator."""
    bpy.utils.unregister_class(POSE_EDITOR_OT_apply_rigging)


if __name__ == "__main__":
    register()