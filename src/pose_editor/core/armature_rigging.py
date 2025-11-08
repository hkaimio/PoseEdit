# SPDX-FileCopyrightText: 2025 Harri Kaimio
#
# SPDX-License-Identifier: BSD-3-Clause

"""
Armature rigging system for creating tracking rigs from motion capture data.

This module implements the rigging system described in blender-armature-animation.md,
which creates tracking bones (TRK) and mechanics bones (MCH) for animating
scaled Rigify armatures with motion capture data.
"""

from ..blender import dal
from .skeleton import SkeletonBase


class TrackingBoneMapping:
    """Defines the mapping between motion capture points and Rigify bone positions."""
    
    # Maps motion capture joint names to Rigify bone positions (bone_name, head/tail)
    # Based on the specification in blender-armature-animation.md
    MOCAP_TO_RIGIFY_MAPPING = {
        # Head and spine
        "Head": ("spine.006", "tail"),
        
        # Left arm
        "LShoulder": ("upper_arm.L", "head"),
        "LElbow": ("forearm.L", "head"), 
        "LWrist": ("forearm.L", "tail"),
        
        # Right arm
        "RShoulder": ("upper_arm.R", "head"),
        "RElbow": ("forearm.R", "head"),
        "RWrist": ("forearm.R", "tail"),
        
        # Left leg
        "LHip": ("thigh.L", "head"),
        "LKnee": ("shin.L", "head"),
        "LAnkle": ("shin.L", "tail"),
        "LBigToe": ("toe.L", "tail"),
        "LSmallToe": ("toe.L", "tail"),
        "LHeel": ("heel.L", "head"),
        
        # Right leg
        "RHip": ("thigh.R", "head"),
        "RKnee": ("shin.R", "head"),
        "RAnkle": ("shin.R", "tail"),
        "RBigToe": ("toe.R", "tail"),
        "RSmallToe": ("toe.R", "tail"),
        "RHeel": ("heel.R", "head"),
    }
    
    @classmethod
    def get_tracking_bone_name(cls, mocap_joint_name: str) -> str:
        """Convert mocap joint name to TRK bone name following Rigify convention."""
        # Convert mocap names to rigify convention
        name_map = {
            "Head": "head",
            "LShoulder": "shoulder.L", 
            "LElbow": "elbow.L",
            "LWrist": "wrist.L",
            "RShoulder": "shoulder.R",
            "RElbow": "elbow.R", 
            "RWrist": "wrist.R",
            "LHip": "hip.L",
            "LKnee": "knee.L",
            "LAnkle": "ankle.L",
            "LBigToe": "big_toe.L",
            "LSmallToe": "small_toe.L",
            "LHeel": "heel.L",
            "RHip": "hip.R",
            "RKnee": "knee.R",
            "RAnkle": "ankle.R",
            "RBigToe": "big_toe.R",
            "RSmallToe": "small_toe.R",
            "RHeel": "heel.R",
        }
        
        rigify_name = name_map.get(mocap_joint_name, mocap_joint_name.lower())
        return f"TRK - {rigify_name}"


class LimbMechanism:
    """Implements the limb mechanism subroutine from blender-armature-animation.md."""
    
    def __init__(self, limb_name: str, trk1: str, trk2: str, trk3: str, limb1: str, limb2: str):
        """
        Initialize limb mechanism.
        
        Args:
            limb_name: Name of the limb (e.g., "arm.L", "leg.L")
            trk1, trk2, trk3: Names of tracking bones for the three points
            limb1, limb2: Names of the two main limb bones
        """
        self.limb_name = limb_name
        self.trk1 = trk1
        self.trk2 = trk2
        self.trk3 = trk3
        self.limb1 = limb1
        self.limb2 = limb2
    
    def create_mechanism_bones(self, armature_ref: dal.BlenderObjRef) -> list[str]:
        """Create the mechanism bones for this limb."""
        mechanism_bones = []
        
        # Create MCH - <limb_name>_dir bone
        dir_bone_name = f"MCH - {self.limb_name.replace('.', '_')}_dir"
        mechanism_bones.append(dir_bone_name)
        
        # Create MCH - <limb_name>_pole_dir bone  
        pole_dir_bone_name = f"MCH - {self.limb_name.replace('.', '_')}_pole_dir"
        mechanism_bones.append(pole_dir_bone_name)
        
        # Create MCH - pole_<limb_name> bone
        pole_bone_name = f"MCH - pole_{self.limb_name.replace('.', '_')}"
        mechanism_bones.append(pole_bone_name)
        
        return mechanism_bones


class ArmatureRiggingSystem:
    """Main rigging system for creating tracking rigs on scaled armatures."""
    
    def __init__(self, armature_ref: dal.BlenderObjRef, skeleton: SkeletonBase):
        """
        Initialize the rigging system.
        
        Args:
            armature_ref: Reference to the scaled Rigify armature
            skeleton: Skeleton definition for motion capture data
        """
        self.armature_ref = armature_ref
        self.skeleton = skeleton
        self.tracking_bone_mapping = TrackingBoneMapping()
    
    def create_tracking_bones(self, marker_objects: dict[str, dal.BlenderObjRef]) -> list[str]:
        """
        Create tracking bones (TRK) for all motion capture points.
        
        Args:
            marker_objects: Dictionary mapping joint names to marker objects
            
        Returns:
            List of created tracking bone names
        """
        tracking_bones = []
        
        for joint_name, marker_ref in marker_objects.items():
            if joint_name in self.tracking_bone_mapping.MOCAP_TO_RIGIFY_MAPPING:
                trk_bone_name = self.tracking_bone_mapping.get_tracking_bone_name(joint_name)
                rigify_bone, position = self.tracking_bone_mapping.MOCAP_TO_RIGIFY_MAPPING[joint_name]
                
                # Get position from the corresponding Rigify bone
                bone_position = self._get_rigify_bone_position(rigify_bone, position)
                
                if bone_position:
                    # Create TRK bone at the rigify bone position
                    dal.add_bone(self.armature_ref, trk_bone_name, bone_position, bone_position)
                    
                    # Add copy location constraint to follow the marker
                    dal.add_bone_constraint(
                        self.armature_ref, 
                        trk_bone_name, 
                        "COPY_LOCATION", 
                        marker_ref
                    )
                    
                    tracking_bones.append(trk_bone_name)
        
        return tracking_bones
    
    def create_limb_mechanisms(self, tracking_bones: list[str]) -> list[str]:
        """
        Create limb mechanisms for arms and legs.
        
        Args:
            tracking_bones: List of created tracking bone names
            
        Returns:
            List of created mechanism bone names
        """
        mechanism_bones = []
        
        # Define limb mechanisms based on the documentation
        limb_definitions = [
            LimbMechanism("arm.L", "TRK - shoulder.L", "TRK - elbow.L", "TRK - wrist.L", 
                         "upper_arm.L", "forearm.L"),
            LimbMechanism("arm.R", "TRK - shoulder.R", "TRK - elbow.R", "TRK - wrist.R",
                         "upper_arm.R", "forearm.R"),
            LimbMechanism("leg.L", "TRK - hip.L", "TRK - knee.L", "TRK - ankle.L",
                         "thigh.L", "shin.L"),
            LimbMechanism("leg.R", "TRK - hip.R", "TRK - knee.R", "TRK - ankle.R",
                         "thigh.R", "shin.R"),
        ]
        
        for limb_mech in limb_definitions:
            # Check if all required tracking bones exist
            required_bones = [limb_mech.trk1, limb_mech.trk2, limb_mech.trk3]
            if all(bone in tracking_bones for bone in required_bones):
                mech_bones = limb_mech.create_mechanism_bones(self.armature_ref)
                mechanism_bones.extend(mech_bones)
                
                # Create the mechanism setup (constraints will be added later)
                self._setup_limb_mechanism(limb_mech)
        
        return mechanism_bones
    
    def create_pelvis_torso_setup(self, tracking_bones: list[str]) -> list[str]:
        """
        Create pelvis and torso mechanics bones.
        
        Args:
            tracking_bones: List of available tracking bones
            
        Returns:
            List of created mechanism bone names
        """
        mechanism_bones = []
        
        # Check if required tracking bones exist
        if "TRK - hip.L" in tracking_bones and "TRK - hip.R" in tracking_bones:
            # Create MCH - pelvis_dir
            pelvis_dir_bone = "MCH - pelvis_dir"
            mechanism_bones.append(pelvis_dir_bone)
            
            # Create MCH - pelvis_spine_root
            pelvis_spine_root_bone = "MCH - pelvis_spine_root"
            mechanism_bones.append(pelvis_spine_root_bone)
            
            # Setup constraints for pelvis mechanism
            self._setup_pelvis_mechanism()
        
        if "TRK - head" in tracking_bones:
            # Setup head IK mechanism
            self._setup_head_mechanism()
        
        return mechanism_bones
    
    def apply_full_rigging(self, marker_objects: dict[str, dal.BlenderObjRef]) -> dict[str, list[str]]:
        """
        Apply the complete rigging system to the armature.
        
        Args:
            marker_objects: Dictionary mapping joint names to marker objects
            
        Returns:
            Dictionary with lists of created bones by type
        """
        result = {
            "tracking_bones": [],
            "mechanism_bones": [],
            "collections": []
        }
        
        # Create bone collections
        self._create_bone_collections()
        result["collections"] = ["TRK", "MCH", "DEF"]
        
        # Create tracking bones
        tracking_bones = self.create_tracking_bones(marker_objects)
        result["tracking_bones"] = tracking_bones
        
        # Move tracking bones to TRK collection
        self._move_bones_to_collection(tracking_bones, "TRK")
        
        # Create limb mechanisms
        limb_bones = self.create_limb_mechanisms(tracking_bones)
        result["mechanism_bones"].extend(limb_bones)
        
        # Create pelvis/torso setup
        torso_bones = self.create_pelvis_torso_setup(tracking_bones)
        result["mechanism_bones"].extend(torso_bones)
        
        # Move mechanism bones to MCH collection
        self._move_bones_to_collection(result["mechanism_bones"], "MCH")
        
        # Set bone properties
        self._set_bone_properties(result["mechanism_bones"])
        
        return result
    
    def _get_rigify_bone_position(self, bone_name: str, position: str) -> tuple[float, float, float] | None:
        """Get the head or tail position of a Rigify bone."""
        try:
            return dal.get_bone_position(self.armature_ref, bone_name, position)
        except ValueError:
            # Bone not found, return None
            return None
    
    def _create_bone_collections(self):
        """Create bone collections for organization."""
        collections = ["TRK", "MCH", "DEF"]
        for collection_name in collections:
            dal.create_bone_collection(self.armature_ref, collection_name)
    
    def _move_bones_to_collection(self, bones: list[str], collection_name: str):
        """Move bones to a specific collection."""
        for bone_name in bones:
            try:
                dal.move_bone_to_collection(self.armature_ref, bone_name, collection_name)
            except ValueError as e:
                print(f"Warning: Could not move bone {bone_name} to collection {collection_name}: {e}")
    
    def _set_bone_properties(self, mechanism_bones: list[str]):
        """Set properties for mechanism bones (non-deforming, etc.)."""
        for bone_name in mechanism_bones:
            try:
                # Make mechanism bones non-deforming
                dal.set_bone_deform(self.armature_ref, bone_name, False)
                # Set stick display for mechanism bones
                if "dir" in bone_name.lower():
                    dal.set_bone_display_type(self.armature_ref, bone_name, "STICK")
            except ValueError as e:
                print(f"Warning: Could not set properties for bone {bone_name}: {e}")
    
    def _setup_limb_mechanism(self, limb_mech: LimbMechanism):
        """Setup constraints and properties for a limb mechanism."""
        try:
            # Create IK target bone if it doesn't exist
            ik_target_name = f"IK-{limb_mech.chain[-1]}"
            target_bone = dal.create_bone(self.armature, ik_target_name)
            
            # Position IK target at end of chain
            end_bone_pos = self._get_rigify_bone_position(limb_mech.chain[-1])
            if end_bone_pos:
                dal.set_bone_position(target_bone, end_bone_pos)
                dal.set_bone_length(target_bone, 0.1)  # Small display bone
                dal.set_bone_deform(target_bone, False)
                dal.set_bone_display_type(target_bone, 'SPHERE')
                
                # Move to MCH collection
                dal.move_bone_to_collection(self.armature, ik_target_name, "MCH")
            
            # Create pole target if specified
            if limb_mech.pole_target:
                pole_bone = dal.create_bone(self.armature, limb_mech.pole_target)
                
                # Position pole target offset from middle joint
                if len(limb_mech.chain) >= 3:
                    middle_pos = self._get_rigify_bone_position(limb_mech.chain[1])
                    if middle_pos:
                        # Calculate offset based on limb type
                        offset_distance = 1.0
                        if 'arm' in limb_mech.chain[0].lower():
                            # For arms, pole points backward
                            offset = (0.0, -offset_distance, 0.0)
                        else:
                            # For legs, pole points forward
                            offset = (0.0, offset_distance, 0.0)
                        
                        pole_pos = (
                            middle_pos[0] + offset[0],
                            middle_pos[1] + offset[1],
                            middle_pos[2] + offset[2]
                        )
                        
                        dal.set_bone_position(pole_bone, pole_pos)
                        dal.set_bone_length(pole_bone, 0.1)
                        dal.set_bone_deform(pole_bone, False)
                        dal.set_bone_display_type(pole_bone, 'SPHERE')
                        
                        # Move to MCH collection
                        dal.move_bone_to_collection(self.armature, limb_mech.pole_target, "MCH")
            
            # Set up IK constraint on end bone of chain
            end_bone = limb_mech.chain[-1]
            
            # Add IK constraint
            constraint_options = {
                'target': self.armature,
                'subtarget': ik_target_name,
                'chain_count': len(limb_mech.chain)
            }
            
            if limb_mech.pole_target:
                constraint_options['pole_target'] = self.armature
                constraint_options['pole_subtarget'] = limb_mech.pole_target
            
            dal.add_bone_constraint_with_options(
                self.armature, end_bone, 'IK', **constraint_options
            )
            
            # Set IK properties on chain bones
            for bone_name in limb_mech.chain[:-1]:  # All but last bone
                try:
                    dal.set_bone_ik_properties(self.armature, bone_name,
                                             ik_stiffness_x=0.5, ik_stiffness_y=0.5, ik_stiffness_z=0.5)
                except Exception as e:
                    print(f"Warning: Could not set IK properties for bone {bone_name}: {e}")
                    
        except Exception as e:
            print(f"Error setting up limb mechanism for {limb_mech.chain}: {e}")
    
    def _setup_pelvis_mechanism(self):
        """Setup pelvis and spine mechanism."""
        try:
            # Create pelvis master control
            pelvis_master = "MCH-pelvis.master"
            pelvis_bone = dal.create_bone(self.armature, pelvis_master)
            
            # Position at pelvis location
            pelvis_pos = self._get_rigify_bone_position("pelvis")
            if pelvis_pos:
                dal.set_bone_position(pelvis_bone, pelvis_pos)
                dal.set_bone_length(pelvis_bone, 0.2)
                dal.set_bone_deform(pelvis_bone, False)
                dal.set_bone_display_type(pelvis_bone, 'CUBE')
                
                # Move to MCH collection
                dal.move_bone_to_collection(self.armature, pelvis_master, "MCH")
            
            # Create torso controls
            torso_bones = ["spine", "spine.001", "spine.002", "spine.003"]
            for i, bone_name in enumerate(torso_bones):
                if self._get_rigify_bone_position(bone_name):
                    # Create FK control for each spine segment
                    fk_control = f"MCH-spine.fk.{i:03d}"
                    fk_bone = dal.create_bone(self.armature, fk_control)
                    
                    spine_pos = self._get_rigify_bone_position(bone_name)
                    if spine_pos:
                        dal.set_bone_position(fk_bone, spine_pos)
                        dal.set_bone_length(fk_bone, 0.15)
                        dal.set_bone_deform(fk_bone, False)
                        dal.set_bone_display_type(fk_bone, 'OCTAHEDRAL')
                        
                        # Move to MCH collection
                        dal.move_bone_to_collection(self.armature, fk_control, "MCH")
                        
                        # Parent to previous spine control or pelvis master
                        if i == 0:
                            dal.parent_bone_to_bone(self.armature, fk_control, pelvis_master)
                        else:
                            prev_control = f"MCH-spine.fk.{i-1:03d}"
                            dal.parent_bone_to_bone(self.armature, fk_control, prev_control)
            
            # Create shoulder controls
            shoulder_bones = ["shoulder.L", "shoulder.R"]
            for shoulder in shoulder_bones:
                if self._get_rigify_bone_position(shoulder):
                    shoulder_control = f"MCH-{shoulder}"
                    shoulder_bone = dal.create_bone(self.armature, shoulder_control)
                    
                    shoulder_pos = self._get_rigify_bone_position(shoulder)
                    if shoulder_pos:
                        dal.set_bone_position(shoulder_bone, shoulder_pos)
                        dal.set_bone_length(shoulder_bone, 0.1)
                        dal.set_bone_deform(shoulder_bone, False)
                        dal.set_bone_display_type(shoulder_bone, 'SPHERE')
                        
                        # Move to MCH collection
                        dal.move_bone_to_collection(self.armature, shoulder_control, "MCH")
                        
                        # Parent to top spine control
                        dal.parent_bone_to_bone(self.armature, shoulder_control, "MCH-spine.fk.003")
                        
        except Exception as e:
            print(f"Error setting up pelvis mechanism: {e}")
    
    def _setup_head_mechanism(self):
        """Setup head IK mechanism."""
        # This will be implemented when DAL functions are extended
        pass