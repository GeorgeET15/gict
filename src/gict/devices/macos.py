"""Experimental macOS iPhone access through ifuse and macFUSE."""

import os
import shutil
from pathlib import Path

from gict.devices.base import DeviceInfo
from gict.devices.linux import LinuxDeviceAdapter, LinuxDeviceSession


class MacOSDeviceSession(LinuxDeviceSession):
    """An ifuse mount created by GICT and tracked with macOS mount APIs."""

    def _is_mountpoint(self) -> bool:
        return os.path.ismount(self._mount_path)


class MacOSDeviceAdapter(LinuxDeviceAdapter):
    """Use upstream ifuse/macFUSE support to access iPhone media on macOS."""

    platform = "macos"

    def _executables(self) -> dict[str, str]:
        executables = {
            "ifuse": self._require_executable("ifuse"),
            "idevice_id": self._require_executable("idevice_id"),
            "ideviceinfo": self._require_executable("ideviceinfo"),
        }
        unmount = shutil.which("fusermount") or shutil.which("fusermount3")
        if unmount is None:
            raise RuntimeError(
                "Missing macOS ifuse dependency: fusermount or fusermount3"
            )
        executables["unmount"] = unmount
        executables["mountpoint"] = ""

        LinuxDeviceAdapter._verify_ifuse(executables["ifuse"])
        return executables

    @staticmethod
    def _is_mountpoint(executable: str, path: Path) -> bool:
        return os.path.ismount(path)

    def _create_session(
        self,
        mount_path: Path,
        device_name: str,
        executables: dict[str, str],
    ) -> MacOSDeviceSession:
        return MacOSDeviceSession(
            mount_path=mount_path,
            device_name=device_name,
            mountpoint_executable="",
            unmount_executable=executables["unmount"],
        )