# SPDX-FileCopyrightText: 2025 Harri Kaimio
#
# SPDX-License-Identifier: BSD-3-Clause

from . import dal


def create_project_structure():
    """
    Creates the basic collection structure for a new project.
    """
    dal.create_collection("Camera Views")
    dal.create_collection("Real Persons")
    dal.create_empty("_ProjectSettings")
