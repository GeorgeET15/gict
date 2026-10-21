"""Platform-neutral interfaces for discovering and accessing devices."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from types import TracebackType
from typing import Sequence


@dataclass(frozen=True, slots=True)
class DeviceInfo:
    """Stable identifying information reported for a discovered device."""

    identifier: str
    name: str
    platform: str


class DeviceSession(ABC):
    """Temporary access to a device media root.

    Implementations must release only resources they created in ``close``;
    they must never unmount or otherwise alter pre-existing filesystems.
    """

    @property
    @abstractmethod
    def media_root(self) -> Path:
        """Return the accessible root containing media to back up."""

    @abstractmethod
    def close(self) -> None:
        """Release resources acquired by this session."""

    def __enter__(self) -> "DeviceSession":
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()


class DeviceAdapter(ABC):
    """Discover devices and create scoped access sessions for them."""

    @abstractmethod
    def discover(self) -> Sequence[DeviceInfo]:
        """Return connected devices without mounting or modifying filesystems."""

    @abstractmethod
    def open(self, device: DeviceInfo) -> DeviceSession:
        """Establish access to a device, scoped to the returned session."""