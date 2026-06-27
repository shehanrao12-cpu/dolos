"""prepush — run your GitHub Actions workflow steps locally, without Docker.

Catch the dumb CI failures (typos, missing steps, failing tests/lint/build)
*before* you push, instead of waiting on the edit-commit-push-wait loop.
"""

from __future__ import annotations

__version__ = "0.1.0"
__all__ = ["__version__"]
