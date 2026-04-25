from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

try:
    import winreg  # type: ignore
except Exception:  # pragma: no cover - non-Windows platforms
    winreg = None

# Default fallback; can be overridden by env or explicit preferred path
LOGS_BASE = Path(r"G:\Hearthstone\Logs")


# Try to locate the Hearthstone installation directory (where Hearthstone.exe lives).
#     Order:
#     1) HEARTHSTONE_INSTALL environment variable
#     2) Windows registry uninstall entries by winreg
#     3) Common install locations on available drives (Program Files variants)
#     4) Fallback rglob search for Hearthstone.exe under Program Files roots
def find_hearthstone_install() -> Optional[Path]:
    env_path = os.environ.get("HEARTHSTONE_INSTALL")
    if env_path:
        candidate = Path(env_path)
        if (candidate / "Hearthstone.exe").exists():
            return candidate

    # Registry probe on Windows
    if winreg:
        hives = [winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER]
        uninstall_roots = [
            r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall",
            r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall",
        ]
        for hive in hives:
            for root_path in uninstall_roots:
                try:
                    root = winreg.OpenKey(hive, root_path)
                except OSError:
                    continue
                try:
                    idx = 0
                    while True:
                        try:
                            subkey_name = winreg.EnumKey(root, idx)
                        except OSError:
                            break
                        idx += 1
                        try:
                            subkey = winreg.OpenKey(root, f"{root_path}\\{subkey_name}")
                            display_name, _ = winreg.QueryValueEx(subkey, "DisplayName")
                        except OSError:
                            continue
                        if "hearthstone" not in str(display_name).lower():
                            continue
                        for value_name in ("InstallLocation", "DisplayIcon"):
                            try:
                                value, _ = winreg.QueryValueEx(subkey, value_name)
                            except OSError:
                                continue
                            candidate = Path(str(value).strip('"'))
                            if (
                                candidate.is_file()
                                and candidate.name.lower() == "hearthstone.exe"
                            ):
                                return candidate.parent
                            if (
                                candidate.is_dir()
                                and (candidate / "Hearthstone.exe").exists()
                            ):
                                return candidate
                finally:
                    winreg.CloseKey(root)

    # Prefer the drive of the current user home, but also try common secondary drives
    drives = []
    home_drive = Path.home().drive or "C:"
    drives.append(home_drive)
    for letter in "CDEFGHIJKLMNOPQRSTUVWXYZ":
        d = f"{letter}:\\" # u włoda nie działało bez \\
        if d not in drives and Path(d + "\\").exists():
            drives.append(d)

    common_dirs = []
    for drive in drives:
        common_dirs.extend(
            [
                Path(drive) / "Program Files (x86)" / "Hearthstone",
                Path(drive) / "Program Files" / "Hearthstone",
                Path(drive) / "/Program Files (x86)" / "Hearthstone",
                Path(drive) / "/Program Files" / "Hearthstone",
                Path(drive) / "Hearthstone",
            ]
        )

    for candidate in common_dirs:
        if (candidate / "Hearthstone.exe").exists():
            return candidate

    # Last resort: search for the executable under Program Files roots (can be slow, but bounded)
    for drive in drives:
        for root in [
            Path(drive) / "Program Files (x86)",
            Path(drive) / "Program Files",
            Path(drive) / "/Program Files (x86)",
            Path(drive) / "/Program Files",
            Path(drive),
        ]:
            if not root.exists():
                continue
            try:
                match = next(root.rglob("Hearthstone.exe"))
                return match.parent
            except StopIteration:
                continue
            except OSError:
                continue

    return None


# Determine the Logs directory to use.
#     Order:
#     1) Explicit preferred path (if provided)
#     2) LOGS_BASE default (if it exists)
#     3) HEARTHSTONE_INSTALL (via find_hearthstone_install) -> Logs subfolder
def resolve_logs_base(preferred: Optional[Path] = None) -> Optional[Path]:
    if preferred:
        logs = Path(preferred)
        return logs if logs.exists() else None

    if LOGS_BASE.exists():
        return LOGS_BASE

    install = find_hearthstone_install()
    if install:
        logs = install / "Logs"
        if logs.exists():
            return logs

    return None


def get_latest_log_folder(base_path: Path) -> Optional[Path]:
    subs = [
        d
        for d in base_path.iterdir()
        if d.is_dir() and d.name.startswith("Hearthstone_")
    ]
    return max(subs, key=lambda d: d.stat().st_mtime) if subs else None


# Main function to resolve the zone.log
def resolve_log_dir(preferred_path: Optional[Path] = None) -> Optional[Path]:
    logs_base = resolve_logs_base(preferred_path)
    if not logs_base:
        return None

    latest = get_latest_log_folder(logs_base)
    if not latest:
        return None

    return latest


def resolve_player_log(preferred_path: Optional[Path] = None) -> Optional[Path]:
    if preferred_path:
        candidate = Path(preferred_path)
        return candidate if candidate.exists() else None

    env_path = os.environ.get("HEARTHSTONE_PLAYER_LOG")
    if env_path:
        candidate = Path(env_path)
        if candidate.exists():
            return candidate

    local_appdata = os.environ.get("LOCALAPPDATA")
    if local_appdata:
        local_low = Path(local_appdata).parent / "LocalLow"
    else:
        local_low = Path.home() / "AppData" / "LocalLow"

    candidate = (
        local_low
        / "Blizzard Entertainment"
        / "Hearthstone"
        / "Player.log"
    )
    if candidate.exists():
        return candidate

    return None
