from __future__ import annotations

import os
import sys
from pathlib import Path


APP_DIR_ENV = "SPONSORSCOUT_DATA_DIR"
DB_PATH_ENV = "SPONSORSCOUT_DB_PATH"


def _get_frozen_base_dir() -> Path | None:
    """Return the directory of the frozen executable (PyInstaller)."""
    if getattr(sys, "frozen", False):
        # sys._MEIPASS is the temp dir; our exe sits one level above
        if hasattr(sys, "_MEIPASS"):
            return Path(sys._MEIPASS)
    return None


def _get_windows_appdata_dir(app_name: str) -> Path:
    """Return the *per-user* application data directory on Windows."""
    # Use GetKnownFolderPath via ctypes (modern, reliable, works on all
    # supported Windows versions).  Fails back to the environment variable.
    try:
        import ctypes
        from ctypes import wintypes

        class GUID(ctypes.Structure):
            _fields_ = [
                ("Data1", ctypes.c_ulong),
                ("Data2", ctypes.c_ushort),
                ("Data3", ctypes.c_ushort),
                ("Data4", ctypes.c_ubyte * 8),
            ]

        FOLDERID_RoamingAppData = GUID(
            0x3EB685DB, 0x65F9, 0x4CF6, (
                0xA0, 0xBA, 0x88, 0x15, 0x0, 0x8D, 0xF2, 0xB1)
        )

        ctypes.windll.shell32.SHGetKnownFolderPath(
            ctypes.byref(FOLDERID_RoamingAppData), 0, None, ctypes.byref(wintypes.LPWSTR())
        )
        # Function returns a pointer; we convert it.
        pf = ctypes.windll.shell32.SHGetKnownFolderPath
        pf.argtypes = [ctypes.POINTER(GUID), ctypes.c_uint32, ctypes.c_void_p, ctypes.POINTER(wintypes.LPWSTR)]
        pf.restype = ctypes.c_int
        path_ptr = wintypes.LPWSTR()
        result = pf(ctypes.byref(FOLDERID_RoamingAppData), 0, None, ctypes.byref(path_ptr))
        if result == 0:
            return Path(path_ptr.value) / app_name
    except Exception:
        pass
    # Fallback to environment variable or home directory
    env_path = os.environ.get("APPDATA")
    if env_path:
        return Path(env_path) / app_name
    return Path.home() / "." + app_name.lower()


def get_user_data_dir() -> Path:
    """Return the single per-user directory for all mutable app data."""
    override = os.environ.get(APP_DIR_ENV, "").strip()
    if override:
        return Path(override).expanduser()
    # On Windows, use the APPDATA standard directory
    if os.name == "nt":
        return _get_windows_appdata_dir("SponsorScout")
    return Path.home() / ".sponsorscout"


USER_DATA_DIR = get_user_data_dir()
DB_PATH = Path(os.environ.get(DB_PATH_ENV, "")).expanduser() if os.environ.get(DB_PATH_ENV) else USER_DATA_DIR / "sponsorscout.db"


def ensure_user_data_dir() -> Path:
    USER_DATA_DIR.mkdir(parents=True, exist_ok=True)
    return USER_DATA_DIR