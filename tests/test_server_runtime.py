import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.services import local_config, server_runtime, steam_locator


class ServerRuntimeTests(unittest.TestCase):
    def test_linux_is_the_default_and_windows_is_explicit(self) -> None:
        self.assertEqual(server_runtime.normalize(None), "linux")
        self.assertEqual(server_runtime.normalize("linux"), "linux")
        self.assertEqual(server_runtime.normalize("windows"), "windows")
        self.assertTrue(server_runtime.is_windows({"runtime": "windows"}))
        self.assertFalse(server_runtime.is_windows({"runtime": "linux"}))

    def test_runtime_selects_matching_executable_and_mods_folder(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "PalServer.exe").touch()
            self.assertEqual(steam_locator.find_server_executable(root, "windows"), root / "PalServer.exe")
            self.assertEqual(local_config.default_mods_path(str(root), "windows"), str(root / "Pal" / "Binaries" / "Win64" / "Mods"))
            self.assertEqual(local_config.default_mods_path(str(root), "linux"), str(root / "Pal" / "Binaries" / "Linux" / "Mods"))

    @patch("app.services.server_runtime.shutil.which", return_value=None)
    def test_windows_runtime_requires_wine_on_non_windows(self, _which) -> None:
        with patch("app.services.server_runtime.sys.platform", "linux"):
            self.assertFalse(server_runtime.host_can_run("windows"))


if __name__ == "__main__":
    unittest.main()
