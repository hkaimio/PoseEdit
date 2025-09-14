# SPDX-FileCopyrightText: 2025 Harri Kaimio
#
# SPDX-License-Identifier: BSD-3-Clause

"""Module for handling camera calibration data."""

import json
import tomllib
from typing import Any, Dict, List, Optional

from ..blender import dal
from ..blender.dal import CustomProperty

CALIBRATION_OBJECT_NAME = "_CalibrationData"
CALIBRATION_DATA_JSON = CustomProperty[str]("calibration_data_json")


def load_calibration_from_file(filepath: str) -> None:
    """Loads calibration data from a TOML file and stores it in the scene."""
    # Find or create the calibration data object
    calib_obj_ref = dal.get_or_create_object(CALIBRATION_OBJECT_NAME, "EMPTY")

    # Read and parse the TOML file
    with open(filepath, "rb") as f:
        toml_data = tomllib.load(f)

    # Convert the data to a JSON string
    json_string = json.dumps(toml_data, indent=2)

    # Store the JSON string in a custom property
    dal.set_custom_property(calib_obj_ref, CALIBRATION_DATA_JSON, json_string)


class Calibration:
    """A facade for accessing calibration data stored in the scene."""

    def __init__(self) -> None:
        """Initializes the Calibration object by loading data from the scene."""
        self._data: Dict[str, Any] = {}
        self._load_data()

    def _load_data(self) -> None:
        """Loads the calibration data from the Blender scene."""
        calib_obj = dal.get_object_by_name(CALIBRATION_OBJECT_NAME)
        if not calib_obj:
            # No calibration data loaded yet
            return

        json_string = dal.get_custom_property(calib_obj, CALIBRATION_DATA_JSON)
        if not json_string:
            json_string = "{}"

        try:
            self._data = json.loads(json_string)
        except json.JSONDecodeError:
            # Handle corrupted or empty data
            self._data = {}

    def get_camera_names(self) -> List[str]:
        """Returns a list of all camera names from the calibration data."""
        # Filters out the 'metadata' key
        return [key for key in self._data.keys() if key != "metadata"]

    def get_camera_data(self, camera_name: str) -> Optional[Dict[str, Any]]:
        """Returns all data for a specific camera."""
        return self._data.get(camera_name)

    def get_matrix(self, camera_name: str) -> Optional[List[List[float]]]:
        """Returns the intrinsic matrix for a specific camera."""
        cam_data = self.get_camera_data(camera_name)
        return cam_data.get("matrix") if cam_data else None