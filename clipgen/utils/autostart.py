"""Windows autostart management via registry."""

import sys
import winreg
import logging

logger = logging.getLogger('ClipGen')

REGISTRY_PATH = r"Software\Microsoft\Windows\CurrentVersion\Run"
APP_NAME = "ClipGen"


def is_autostart_enabled() -> bool:
    """Check if app is in Windows autostart registry."""
    try:
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            REGISTRY_PATH,
            0,
            winreg.KEY_READ
        )
        try:
            winreg.QueryValueEx(key, APP_NAME)
            return True
        except FileNotFoundError:
            return False
        finally:
            winreg.CloseKey(key)
    except Exception as e:
        print(f"Autostart check error: {e}")
        return False


def set_autostart(enabled: bool) -> bool:
    """Add or remove app from Windows autostart.

    Returns True if operation was successful.
    """
    if not getattr(sys, 'frozen', False):
        print("Autostart is disabled in development mode (.py)")
        return False

    exe_path = sys.executable

    try:
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            REGISTRY_PATH,
            0,
            winreg.KEY_WRITE
        )

        if enabled:
            winreg.SetValueEx(key, APP_NAME, 0, winreg.REG_SZ, f'"{exe_path}"')
            logger.info("Added to Windows startup")
        else:
            try:
                winreg.DeleteValue(key, APP_NAME)
                logger.info("Removed from Windows startup")
            except FileNotFoundError:
                pass

        winreg.CloseKey(key)
        return True

    except Exception as e:
        logger.error(f"Failed to change autostart: {e}")
        return False
