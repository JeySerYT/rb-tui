"""Тесты поиска конфига OpenCode и каталога кеша на разных ОС."""

import os
import tempfile
import unittest
from unittest import mock

from rb_tui import paths


def write(path, text="{}"):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


class ConfigDirsTest(unittest.TestCase):
    def test_windows_uses_appdata(self):
        home = os.path.join(os.sep, "Users", "me")
        env = {
            "APPDATA": os.path.join(home, "AppData", "Roaming"),
            "ProgramData": os.path.join(os.sep, "ProgramData"),
        }
        dirs = paths.config_dirs("win32", env=env, home=home)
        self.assertEqual(dirs[0], os.path.join(env["APPDATA"], "opencode"))
        self.assertIn(os.path.join(home, ".config", "opencode"), dirs)
        self.assertEqual(dirs[-1], os.path.join(env["ProgramData"], "opencode"))

    def test_macos_uses_application_support(self):
        home = os.path.join(os.sep, "Users", "me")
        dirs = paths.config_dirs("darwin", env={}, home=home)
        self.assertEqual(
            dirs[0], os.path.join(home, "Library", "Application Support", "opencode"),
        )
        self.assertIn(os.path.join(home, ".config", "opencode"), dirs)

    def test_linux_uses_xdg(self):
        home = os.path.join(os.sep, "home", "me")
        env = {"XDG_CONFIG_HOME": os.path.join(home, ".config-custom")}
        dirs = paths.config_dirs("linux", env=env, home=home)
        self.assertEqual(dirs[0], os.path.join(env["XDG_CONFIG_HOME"], "opencode"))
        # На Windows разделитель в путях другой — сравниваем нормализованные.
        self.assertIn(
            os.path.normpath(os.path.join(os.sep, "etc", "opencode")),
            [os.path.normpath(d) for d in dirs],
        )

    def test_opencode_config_dir_wins(self):
        home = os.path.join(os.sep, "home", "me")
        env = {"OPENCODE_CONFIG_DIR": "~/custom-opencode"}
        dirs = paths.config_dirs("linux", env=env, home=home)
        self.assertEqual(dirs[0], os.path.join(home, "custom-opencode"))

    def test_no_duplicates(self):
        home = os.path.join(os.sep, "home", "me")
        dirs = paths.config_dirs("linux", env={}, home=home)
        self.assertEqual(len(dirs), len(set(dirs)))


class DiscoverTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.home = self.tmp.name
        self.dir = os.path.join(self.home, ".config", "opencode")

    def test_nothing_found_returns_default(self):
        found = paths.discover_config("linux", env={}, home=self.home)
        self.assertEqual(found, os.path.join(self.dir, "opencode.json"))

    def test_jsonc_preferred_over_json(self):
        plain = os.path.join(self.dir, "opencode.json")
        jsonc = os.path.join(self.dir, "opencode.jsonc")
        write(plain)
        write(jsonc)
        self.assertEqual(
            paths.discover_config("linux", env={}, home=self.home), jsonc,
        )

    def test_prefers_file_with_provider(self):
        jsonc = os.path.join(self.dir, "opencode.jsonc")
        plain = os.path.join(self.dir, "opencode.json")
        write(jsonc, '{"theme": "dark"}')
        write(plain, '{"providers": {"reformboss": {"models": {}}}}')
        self.assertEqual(
            paths.discover_config("linux", env={}, home=self.home), plain,
        )

    def test_explicit_rb_tui_config_wins(self):
        explicit = os.path.join(self.home, "custom.json")
        write(explicit)
        write(os.path.join(self.dir, "opencode.json"))
        found = paths.discover_config(
            "linux", env={"RB_TUI_CONFIG": explicit}, home=self.home,
        )
        self.assertEqual(found, explicit)

    def test_searched_paths_list_jsonc_and_json(self):
        listed = paths.searched_paths("linux", env={}, home=self.home)
        self.assertIn(os.path.join(self.dir, "opencode.jsonc"), listed)
        self.assertIn(os.path.join(self.dir, "opencode.json"), listed)


class CacheDirTest(unittest.TestCase):
    def test_windows_uses_localappdata(self):
        home = os.path.join(os.sep, "Users", "me")
        env = {"LOCALAPPDATA": os.path.join(home, "AppData", "Local")}
        self.assertEqual(
            paths.cache_dir("win32", env=env, home=home),
            os.path.join(env["LOCALAPPDATA"], "rb-tui"),
        )

    def test_linux_keeps_legacy_path(self):
        home = os.path.join(os.sep, "home", "me")
        self.assertEqual(
            paths.cache_dir("linux", env={}, home=home),
            os.path.join(home, ".config", "reformboss-tui"),
        )

    def test_macos_also_keeps_legacy_path(self):
        home = os.path.join(os.sep, "Users", "me")
        self.assertEqual(
            paths.cache_dir("darwin", env={}, home=home),
            os.path.join(home, ".config", "reformboss-tui"),
        )


class SetConfigPathTest(unittest.TestCase):
    def test_updates_loaded_modules(self):
        from rb_tui import config, utils

        with tempfile.TemporaryDirectory() as tmp:
            target = os.path.join(tmp, "custom.json")
            with mock.patch.object(utils, "CONFIG", "old"), \
                    mock.patch.object(config, "CONFIG", "old"):
                paths.set_config_path(target)
                self.assertEqual(utils.CONFIG, os.path.abspath(target))
                self.assertEqual(config.CONFIG, os.path.abspath(target))


if __name__ == "__main__":
    unittest.main()