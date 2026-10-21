import tempfile
import unittest
from pathlib import Path

from gict.devices import DeviceAdapter, DeviceInfo, DeviceSession


class FakeSession(DeviceSession):
    def __init__(self, media_root: Path, events: list[str]) -> None:
        self._media_root = media_root
        self._events = events

    @property
    def media_root(self) -> Path:
        return self._media_root

    def close(self) -> None:
        self._events.append("closed")


class FakeAdapter(DeviceAdapter):
    def __init__(self, session: DeviceSession) -> None:
        self._session = session
        self.events: list[str] = []

    def discover(self) -> list[DeviceInfo]:
        self.events.append("discovered")
        return [DeviceInfo("test-id", "Test Phone", "test-platform")]

    def open(self, device: DeviceInfo) -> DeviceSession:
        self.events.append(f"opened:{device.identifier}")
        return self._session


class DeviceContractTests(unittest.TestCase):
    def test_adapter_discovers_device_and_opens_scoped_session(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            events: list[str] = []
            session = FakeSession(root, events)
            adapter = FakeAdapter(session)

            devices = adapter.discover()
            self.assertEqual(
                devices,
                [DeviceInfo("test-id", "Test Phone", "test-platform")],
            )

            with adapter.open(devices[0]) as access:
                self.assertEqual(access.media_root, root)

            self.assertEqual(adapter.events, ["discovered", "opened:test-id"])
            self.assertEqual(events, ["closed"])

    def test_session_closes_after_exception_without_suppressing_it(self):
        with tempfile.TemporaryDirectory() as temp:
            events: list[str] = []
            session = FakeSession(Path(temp), events)

            with self.assertRaisesRegex(RuntimeError, "backup failed"):
                with session:
                    raise RuntimeError("backup failed")

            self.assertEqual(events, ["closed"])

    def test_device_information_is_immutable(self):
        device = DeviceInfo("test-id", "Test Phone", "test-platform")

        with self.assertRaises(AttributeError):
            device.name = "Changed Name"


if __name__ == "__main__":
    unittest.main()