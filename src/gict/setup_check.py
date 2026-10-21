"""Checks for the system dependencies required for iPhone device access."""

import shutil
import sys
from dataclasses import dataclass
from pathlib import Path

from gict.devices.linux import IFUSE_VERSION, LinuxDeviceAdapter

OS_RELEASE_PATH = Path("/etc/os-release")

_INSTALL_COMMANDS = {
    "debian": "sudo apt install ifuse libimobiledevice-utils usbmuxd fuse3",
    "fedora": "sudo dnf install ifuse libimobiledevice-utils usbmuxd fuse",
    "arch": "sudo pacman -S ifuse libimobiledevice usbmuxd fuse3",
}

_DISTRO_LABELS = {
    "debian": "Debian / Ubuntu",
    "fedora": "Fedora",
    "arch": "Arch Linux",
}

_ID_TO_DISTRO = {
    "debian": "debian",
    "ubuntu": "debian",
    "fedora": "fedora",
    "arch": "arch",
}


@dataclass(frozen=True, slots=True)
class DependencyCheck:
    """The status of one requirement for iPhone device access."""

    name: str
    status: str  # "available" | "missing" | "incompatible" | "unknown"
    detail: str


def check_iphone_dependencies() -> list[DependencyCheck]:
    """Check every requirement for iPhone device access, individually."""
    return [
        _check_linux_platform(),
        _check_python_version(),
        _check_ifuse(),
        _check_simple_executable("idevice_id"),
        _check_simple_executable("ideviceinfo"),
        _check_simple_executable("mountpoint"),
        _check_unmount_tool(),
    ]


def _check_linux_platform() -> DependencyCheck:
    if sys.platform == "linux":
        return DependencyCheck("Linux operating system", "available", "Linux detected")
    return DependencyCheck(
        "Linux operating system",
        "incompatible",
        f"iPhone device access requires Linux; detected: {sys.platform}",
    )


def _check_python_version() -> DependencyCheck:
    version = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    return DependencyCheck("Python version", "available", f"Python {version} (>= 3.10 required)")


def _check_simple_executable(name: str) -> DependencyCheck:
    try:
        found = shutil.which(name)
    except Exception as exc:
        return DependencyCheck(name, "unknown", f"Could not determine: {exc}")
    if found is None:
        return DependencyCheck(name, "missing", f"{name} was not found on PATH")
    return DependencyCheck(name, "available", found)


def _check_unmount_tool() -> DependencyCheck:
    try:
        found = shutil.which("fusermount3") or shutil.which("fusermount")
    except Exception as exc:
        return DependencyCheck("fusermount3 or fusermount", "unknown", f"Could not determine: {exc}")
    if found is None:
        return DependencyCheck(
            "fusermount3 or fusermount",
            "missing",
            "Neither fusermount3 nor fusermount was found on PATH",
        )
    return DependencyCheck("fusermount3 or fusermount", "available", found)


def _check_ifuse() -> DependencyCheck:
    try:
        ifuse_path = shutil.which("ifuse")
    except Exception as exc:
        return DependencyCheck("ifuse", "unknown", f"Could not determine: {exc}")
    if ifuse_path is None:
        return DependencyCheck("ifuse", "missing", "ifuse was not found on PATH")

    try:
        LinuxDeviceAdapter._verify_ifuse(ifuse_path)
    except RuntimeError as exc:
        return DependencyCheck("ifuse", "incompatible", str(exc))
    except Exception as exc:
        return DependencyCheck("ifuse", "unknown", f"Could not determine: {exc}")

    return DependencyCheck(
        "ifuse", "available", f"ifuse {IFUSE_VERSION} (exact version required)"
    )


def overall_status(checks: list[DependencyCheck]) -> str:
    """Summarize a set of dependency checks as one headline status."""
    if all(check.status == "available" for check in checks):
        return "Ready for iPhone backups"
    return "Setup incomplete"


def detect_distro() -> str:
    """Identify the Linux distribution from /etc/os-release, if possible."""
    try:
        content = OS_RELEASE_PATH.read_text(encoding="utf-8")
    except OSError:
        return "unknown"

    values: dict[str, str] = {}
    for line in content.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        values[key.strip()] = value.strip().strip('"').strip("'")

    candidates = [values.get("ID", "")]
    candidates.extend(values.get("ID_LIKE", "").split())

    for candidate in candidates:
        distro = _ID_TO_DISTRO.get(candidate.lower())
        if distro is not None:
            return distro

    return "unknown"


def distro_label(distro: str) -> str:
    """A human-readable label for a detected distro identifier."""
    return _DISTRO_LABELS.get(distro, "your distribution")


def install_command_for(distro: str) -> str | None:
    """The example install command for a detected distro, if one exists."""
    return _INSTALL_COMMANDS.get(distro)


def all_install_commands() -> dict[str, str]:
    """Every known example install command, keyed by distro label."""
    return {_DISTRO_LABELS[distro]: command for distro, command in _INSTALL_COMMANDS.items()}
