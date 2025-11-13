# SPDX-FileCopyrightText: 2025 Harri Kaimio
#
# SPDX-License-Identifier: BSD-3-Clause

"""Operators for exporting pose data to various formats."""

import os
from pathlib import Path

import bpy

from ..core.person_3d_view import Person3DView
from ..core.person_facade import RealPersonInstanceFacade


class PE_OT_ExportTRC(bpy.types.Operator):
    """Export triangulated 3D pose data to TRC file format"""

    bl_idname = "pose_editor.export_trc"
    bl_label = "Export Pose to TRC"
    bl_description = "Export triangulated 3D coordinates to TRC file format"
    bl_options = {'REGISTER'}

    # File browser properties
    filepath: bpy.props.StringProperty(subtype="FILE_PATH")
    filter_glob: bpy.props.StringProperty(default="*.trc", options={'HIDDEN'})

    # Frame range properties
    use_scene_range: bpy.props.BoolProperty(
        name="Use Scene Frame Range",
        description="Export the entire scene frame range",
        default=True,
    )

    frame_start: bpy.props.IntProperty(
        name="Start Frame",
        description="First frame to export",
        default=1,
        min=0,
    )

    frame_end: bpy.props.IntProperty(
        name="End Frame",
        description="Last frame to export",
        default=250,
        min=0,
    )

    def invoke(self, context, event):
        """Called when the operator is invoked"""
        # Get the selected person from the scene properties
        person_id = context.scene.pose_editor_props.selected_person
        if not person_id:
            self.report({'ERROR'}, "No person selected for export")
            return {'CANCELLED'}

        person = RealPersonInstanceFacade.get_by_id(person_id)
        if not person:
            self.report({'ERROR'}, "Selected person not found")
            return {'CANCELLED'}

        # Set default filepath based on person name and blend file
        blend_filepath = bpy.data.filepath
        if blend_filepath:
            base_dir = os.path.dirname(blend_filepath)
            base_name = os.path.splitext(os.path.basename(blend_filepath))[0]
            self.filepath = os.path.join(base_dir, f"{base_name}_{person.name}.trc")
        else:
            self.filepath = f"{person.name}_pose_export.trc"

        # Set frame range to scene range
        self.frame_start = context.scene.frame_start
        self.frame_end = context.scene.frame_end

        # Open file browser
        context.window_manager.fileselect_add(self)
        return {'RUNNING_MODAL'}

    def draw(self, context):
        """Draw the operator properties in the file browser"""
        layout = self.layout

        box = layout.box()
        box.label(text="Frame Range:", icon='TIME')
        box.prop(self, "use_scene_range")

        if not self.use_scene_range:
            row = box.row(align=True)
            row.prop(self, "frame_start")
            row.prop(self, "frame_end")

    def execute(self, context):
        """Execute the TRC export"""
        try:
            # Get the selected person
            person_id = context.scene.pose_editor_props.selected_person
            person = RealPersonInstanceFacade.get_by_id(person_id)
            if not person:
                self.report({'ERROR'}, "Selected person not found")
                return {'CANCELLED'}

            # Get the 3D view for this person
            person_3d_view = Person3DView.get_for_person(person)
            if not person_3d_view:
                self.report({'ERROR'}, f"No 3D triangulated data found for person '{person.name}'")
                return {'CANCELLED'}

            # Get frame range
            if self.use_scene_range:
                frame_start = context.scene.frame_start
                frame_end = context.scene.frame_end
            else:
                frame_start = self.frame_start
                frame_end = self.frame_end

            # Get animation data
            markers_data, columns = person_3d_view.get_animation_data_as_numpy()

            if markers_data is None or len(markers_data) == 0:
                self.report({'ERROR'}, "No animation data found for export")
                return {'CANCELLED'}

            # Filter data to the specified frame range
            scene_start = context.scene.frame_start
            start_idx = max(0, frame_start - scene_start)
            end_idx = min(len(markers_data), frame_end - scene_start + 1)

            if start_idx >= end_idx:
                self.report({'ERROR'}, "Invalid frame range")
                return {'CANCELLED'}

            markers_data = markers_data[start_idx:end_idx]

            # Extract marker names and XYZ coordinate columns
            marker_names = []
            xyz_columns = []

            current_marker = None
            current_xyz = []

            for i, (marker_name, coord_type) in enumerate(columns):
                if coord_type in ['x', 'y', 'z']:
                    if marker_name != current_marker:
                        if current_marker is not None and len(current_xyz) == 3:
                            marker_names.append(current_marker)
                            xyz_columns.extend(current_xyz)
                        current_marker = marker_name
                        current_xyz = [i]
                    else:
                        current_xyz.append(i)

            # Don't forget the last marker
            if current_marker is not None and len(current_xyz) == 3:
                marker_names.append(current_marker)
                xyz_columns.extend(current_xyz)

            if len(marker_names) == 0:
                self.report({'ERROR'}, "No valid XYZ coordinate data found")
                return {'CANCELLED'}

            # Extract only XYZ coordinates
            xyz_data = markers_data[:, xyz_columns]

            # Get FPS (accounting for FPS base)
            fps = context.scene.render.fps / context.scene.render.fps_base
            num_frames = len(markers_data)
            num_markers = len(marker_names)

            # Ensure output directory exists
            output_path = Path(self.filepath)
            output_path.parent.mkdir(parents=True, exist_ok=True)

            # Write TRC file
            with open(self.filepath, 'w') as f:
                # Header line 1
                f.write(f"PathFileType\t4\t(X/Y/Z)\t{self.filepath}\n")

                # Header line 2
                f.write("DataRate\tCameraRate\tNumFrames\tNumMarkers\tUnits\t"
                       "OrigDataRate\tOrigDataStartFrame\tOrigNumFrames\n")

                # Header line 3
                f.write(f"{fps:.1f}\t{fps:.1f}\t{num_frames}\t{num_markers}\tm\t"
                       f"{fps:.1f}\t{frame_start}\t{num_frames}\n")

                # Marker names header
                f.write("Frame#\tTime\t")
                for marker_name in marker_names:
                    f.write(f"{marker_name}\t\t\t")
                f.write("\n")

                # Coordinate labels
                f.write("\t\t")
                for n in range(1, num_markers + 1):
                    f.write(f"X{n}\tY{n}\tZ{n}\t")
                f.write("\n")

                # Write data
                for frame_idx in range(num_frames):
                    frame_num = frame_start + frame_idx
                    time = frame_idx / fps

                    f.write(f"{frame_num}\t{time:.8f}\t")

                    # Write XYZ coordinates for each marker
                    for marker_idx in range(num_markers):
                        base_col = marker_idx * 3
                        x = xyz_data[frame_idx, base_col]
                        y = xyz_data[frame_idx, base_col + 2]
                        z = -xyz_data[frame_idx, base_col + 1]

                        f.write(f"{x:.6f}\t{y:.6f}\t{z:.6f}\t")

                    f.write("\n")

            self.report(
                {'INFO'},
                f"Exported {num_frames} frames with {num_markers} markers to {self.filepath}"
            )
            return {'FINISHED'}

        except Exception as e:
            self.report({'ERROR'}, f"Export failed: {str(e)}")
            import traceback
            traceback.print_exc()
            return {'CANCELLED'}


def register():
    """Register export operators"""
    bpy.utils.register_class(PE_OT_ExportTRC)


def unregister():
    """Unregister export operators"""
    bpy.utils.unregister_class(PE_OT_ExportTRC)
