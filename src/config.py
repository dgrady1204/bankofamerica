"""
src/config.py

Data directory is stored in settings.ini in the project root.
Use the Settings button in the app to change it, or edit settings.ini directly.
"""
import os
import configparser

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(SCRIPT_DIR)
SETTINGS_FILE = os.path.join(PROJECT_DIR, "settings.ini")

_DEFAULT_DATA_DIR = os.path.join(PROJECT_DIR, "data")


def _read_data_dir() -> str:
    """Read the data directory from settings.ini, falling back to project/data."""
    config = configparser.ConfigParser()
    if os.path.exists(SETTINGS_FILE):
        config.read(SETTINGS_FILE)
        path = config.get("paths", "data_directory", fallback="")
        if path and os.path.isdir(path):
            return path
    return _DEFAULT_DATA_DIR


def save_data_dir(data_dir: str) -> None:
    """Write the data directory to settings.ini."""
    config = configparser.ConfigParser()
    if os.path.exists(SETTINGS_FILE):
        config.read(SETTINGS_FILE)
    if not config.has_section("paths"):
        config.add_section("paths")
    config.set("paths", "data_directory", data_dir)
    with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
        config.write(f)


_DATA_DIR = _read_data_dir()

STATEMENT_DIRECTORY = _DATA_DIR
DATABASE_PATH = _DATA_DIR

CURRENT_SCHEMA_VERSION = 3
