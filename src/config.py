"""
src/config.py

Paths are resolved automatically based on which user profile exists on the machine.
Set the BOA_DATA_DIR environment variable to override both paths.
"""
import os


def _resolve_data_dir() -> str:
    """Determine the data directory based on environment or machine context."""
    # 1. Environment variable override (highest priority)
    env_dir = os.environ.get("BOA_DATA_DIR")
    if env_dir:
        return env_dir

    # 2. Auto-detect based on which user directory exists
    candidates = [
        # Work
        r"C:\Users\dgrady\eclipse-workspace\Home Python\Documents\Bank of America",
        # Home
        r"C:\Users\dgrad\Documents\Python\Documents\Bank of America",
    ]
    for path in candidates:
        if os.path.isdir(path):
            return path

    # 3. Fallback: use a 'data' folder next to the src directory
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir, "data")


_DATA_DIR = _resolve_data_dir()

STATEMENT_DIRECTORY = _DATA_DIR
DATABASE_PATH = _DATA_DIR

CURRENT_SCHEMA_VERSION = 3
