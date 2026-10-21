"""Linux iPhone access through libimobiledevice and ifuse."""

import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Sequence

from gict.devices.base import DeviceAdapter, DeviceInfo, DeviceSession


IFUSE_VERSION = "1.2.1"
_LEGACY_MOUNT_NAMES = ("iphone", "iphone-gict")


def _run(command: Sequence[str]) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            command,
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError as exc:
        raise RuntimeError(f"Could not run {command[0]}: {exc}") from exc


class LinuxDeviceSession(DeviceSession):
    """An ifuse mount created by this adapter for one connected device."""

    def __init__(
        self,
        mount_path: Path,
        device_name: str,
        mountpoint_executable: str,
        unmount_executable: str,
    ) -> None:
        self._mount_path = mount_path
        self._media_root = mount_path / "DCIM"
        self._device_name = device_name
        self._mountpoint_executable = mountpoint_executable
        self._unmount_executable = unmount_executable
        self._closed = False

    @property
    def media_root(self) -> Path:
        return self._media_root

    def _is_mountpoint(self) -> bool:
        result = _run([
            self._mountpoint_executable,
            "-q",
            str(self._mount_path),
        ])
        return result.returncode == 0

    def close(self) -> None:
        if self._closed:
            return

        if self._is_mountpoint():
            result = _run([
                self._unmount_executable,
                "-u",
                str(self._mount_path),
            ])
            if result.returncode != 0:
                detail = (result.stderr or result.stdout).strip()
                raise RuntimeError(
                    f"Could not unmount GICT mount for {self._device_name} "
                    f"at {self._mount_path}: {detail or 'unmount failed'}"
                )
            if self._is_mountpoint():
                raise RuntimeError(
                    f"GICT mount is still active at {self._mount_path}"
                )

        self._closed = True
        try:
            self._mount_path.rmdir()
        except OSError:
            # Never remove contents that appeared in the mount directory.
            pass


class LinuxDeviceAdapter(DeviceAdapter):
    """Access iPhone DCIM directories through a GICT-owned ifuse mount."""

    platform = "linux"

    def __init__(self, mount_root: Path | None = None) -> None:
        self._mount_root = (
            Path(mount_root) if mount_root is not None else Path.home() / "mnt"
        )

    @staticmethod
    def _require_executable(name: str) -> str:
        executable = shutil.which(name)
        if executable is None:
            raise RuntimeError(f"Missing required Linux dependency: {name}")
        return executable

    def _executables(self) -> dict[str, str]:
        executables = {
            "ifuse": self._require_executable("ifuse"),
            "idevice_id": self._require_executable("idevice_id"),
            "ideviceinfo": self._require_executable("ideviceinfo"),
            "mountpoint": self._require_executable("mountpoint"),
        }
        unmount = shutil.which("fusermount3") or shutil.which("fusermount")
        if unmount is None:
            raise RuntimeError(
                "Missing required Linux dependency: fusermount3 or fusermount"
            )
        executables["unmount"] = unmount

        LinuxDeviceAdapter._verify_ifuse(executables["ifuse"])
        return executables

    @staticmethod
    def _verify_ifuse(executable: str) -> None:
        result = _run([executable, "--version"])
        version_text = f"{result.stdout}\n{result.stderr}".strip()
        if (
            result.returncode != 0
            or re.search(r"(?<!\d)1\.2\.1(?!\d)", version_text) is None
        ):
            raise RuntimeError(
                f"GICT currently requires ifuse {IFUSE_VERSION}; "
                f"found {version_text or 'no version output'}"
            )

    @staticmethod
    def _device_name(executable: str, identifier: str) -> str:
        result = _run([
            executable,
            "-u",
            identifier,
            "-k",
            "DeviceName",
        ])
        name = result.stdout.strip()
        if result.returncode != 0 or not name:
            detail = (result.stderr or result.stdout).strip()
            raise RuntimeError(
                f"Could not read the name for iPhone {identifier}: "
                f"{detail or 'no device name returned'}"
            )
        return name

    def discover(self) -> list[DeviceInfo]:
        executables = self._executables()
        result = _run([executables["idevice_id"], "-l"])
        if result.returncode != 0:
            detail = (result.stderr or result.stdout).strip()
            raise RuntimeError(
                f"Could not discover connected iPhones: "
                f"{detail or 'idevice_id failed'}"
            )

        devices = []
        for identifier in result.stdout.splitlines():
            identifier = identifier.strip()
            if identifier:
                devices.append(DeviceInfo(
                    identifier=identifier,
                    name=self._device_name(
                        executables["ideviceinfo"], identifier
                    ),
                    platform=self.platform,
                ))
        return devices

    @staticmethod
    def _is_mountpoint(executable: str, path: Path) -> bool:
        result = _run([executable, "-q", str(path)])
        return result.returncode == 0

    def _check_existing_mounts(self, mountpoint_executable: str) -> None:
        known_names = set(_LEGACY_MOUNT_NAMES)
        try:
            candidates = list(self._mount_root.iterdir())
        except FileNotFoundError:
            return

        for candidate in candidates:
            name = candidate.name
            is_known_path = (
                name in known_names
                or name.startswith("iphone-gict-")
                or name == "gict-iphone"
                or name.startswith("gict-iphone-")
            )
            if is_known_path and self._is_mountpoint(
                mountpoint_executable,
                candidate,
            ):
                raise RuntimeError(
                    f"An existing mount was found at {candidate}; "
                    "GICT will not reuse or unmount it."
                )

    def _create_mount_path(self) -> Path:
        suffix = 0
        while True:
            name = "gict-iphone" if suffix == 0 else f"gict-iphone-{suffix}"
            candidate = self._mount_root / name
            try:
                candidate.mkdir()
                return candidate
            except FileExistsError:
                suffix += 1

    def _create_session(
        self,
        mount_path: Path,
        device_name: str,
        executables: dict[str, str],
    ) -> LinuxDeviceSession:
        return LinuxDeviceSession(
            mount_path=mount_path,
            device_name=device_name,
            mountpoint_executable=executables["mountpoint"],
            unmount_executable=executables["unmount"],
        )

    def _cleanup_created_mount(
        self,
        mount_path: Path,
        device_name: str,
        executables: dict[str, str],
    ) -> None:
        self._create_session(mount_path, device_name, executables).close()

    def open(self, device: DeviceInfo) -> DeviceSession:
        if device.platform != self.platform:
            raise ValueError(
                f"{type(self).__name__} can only open Linux devices"
            )

        executables = self._executables()
        self._mount_root.mkdir(parents=True, exist_ok=True)
        self._check_existing_mounts(executables["mountpoint"])
        mount_path = self._create_mount_path()

        try:
            result = _run([
                executables["ifuse"],
                str(mount_path),
                "-o",
                "ro",
                "--udid",
                device.identifier,
            ])
            if result.returncode != 0:
                detail = (result.stderr or result.stdout).strip()
                raise RuntimeError(
                    f"Could not mount iPhone {device.name} at {mount_path}: "
                    f"{detail or 'ifuse failed'}"
                )
            if not self._is_mountpoint(executables["mountpoint"], mount_path):
                raise RuntimeError(
                    f"ifuse reported success but did not mount {mount_path}"
                )
        except BaseException as mount_error:
            try:
                self._cleanup_created_mount(mount_path, device.name, executables)
            except Exception as cleanup_error:
                raise RuntimeError(
                    f"Mount setup failed for {device.name}; cleanup failed: "
                    f"{cleanup_error}"
                ) from cleanup_error
            raise mount_error

        session = self._create_session(mount_path, device.name, executables)
        try:
            if not session.media_root.is_dir():
                raise RuntimeError(
                    f"The iPhone media directory is not accessible: "
                    f"{session.media_root}"
                )
        except BaseException:
            session.close()
            raise
        return session