<!--
SPDX-FileCopyrightText: 2025 Harri Kaimio

SPDX-License-Identifier: BSD-3-Clause
-->

# Coding Conventions

This document outlines the coding conventions for the Pose Editor project. All contributions should adhere to these guidelines.

## 1. Code Style and Formatting
-   **PEP 8:** All Python code must be compliant with the [PEP 8](https://www.python.org/dev/peps/pep-0008/) style guide.
-   **Ruff:** The [Ruff](https://github.com/astral-sh/ruff) linter is used to enforce style and correctness. Ruff violations are considered errors and must be fixed before merging code.

## 2. Type Hinting
-   **Mandatory Typing:** All functions, methods, and variables must include type hints as specified in PEP 484 and subsequent typing PEPs.
-   **Type Checking:** The project uses a static type checker (e.g., `pyright` or `mypy`). Type checker violations are considered errors and must be resolved.

## 3. Documentation
-   **Docstrings:** All modules, classes, functions, and methods must have docstrings.
-   **Google Style:** Docstrings must follow the [Google Python Style Guide](https://google.github.io/styleguide/pyguide.html#3.8-comments-and-docstrings). This includes a one-line summary, an optional extended description, an `Args` section, and a `Returns` section.

Example:
```python
def my_function(arg1: str, arg2: int) -> bool:
    """This is a one-line summary of the function.

    This is a more detailed description of what the function does
    and how it behaves.

    Args:
        arg1: A description of the first argument.
        arg2: A description of the second argument.

    Returns:
        A boolean indicating success or failure.
    """
    # ... function body ...
    return True
```

## 4. Testing
-   **Unit Tests:** All new features, bug fixes, or changes in logic must be accompanied by unit tests.
-   **Coverage:** The goal is to maintain a minimum of 95% line coverage for the entire codebase. Pull requests that decrease coverage will not be accepted.
-   **Pytest:** Tests are written using the `pytest` framework.

## 5. REUSE Compliance
-   All files must be compliant with the [REUSE specification](https://reuse.software/).
-   This means every file must have an `SPDX-FileCopyrightText` and `SPDX-License-Identifier` header.