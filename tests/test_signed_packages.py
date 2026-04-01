from __future__ import annotations

import json
import shutil
import tempfile
import unittest
import zipfile
from pathlib import Path
from types import SimpleNamespace

from dngine.core.services import AppServices
from dngine.core.builtin_tool_commands import register_builtin_tool_commands
from dngine.core.commands import CommandRegistry
from dngine.core.plugin_manager import PluginManager
from dngine.core.plugin_packages import PluginPackageManager
from dngine.core.plugin_signing import verify_installed_signed_package, verify_signed_archive
from dngine.core.plugin_state import PluginStateManager
from tools.build_first_party_packages import build_first_party_packages


PROJECT_ROOT = Path(__file__).resolve().parents[1]
BUILTIN_ROOT = PROJECT_ROOT / "dngine" / "plugins"
SIGNERS_PATH = PROJECT_ROOT / "dngine" / "first_party_signers.json"
PRIVATE_KEY_PATH = PROJECT_ROOT / "tools" / "first_party_signing_private_key.pem"
EXPECTED_PACKAGE_IDS = {
    "data_analysis",
    "files_storage",
    "network_security",
    "office_docs",
    "web_dev",
}


class _DummyDependencyManager:
    def __init__(self, runtime_root: Path):
        self._runtime_root = Path(runtime_root)
        self.installs: list[tuple[str, bool]] = []
        self.cleared: list[str] = []

    def runtime_dir(self, plugin_id: str) -> Path:
        return self._runtime_root / plugin_id

    def summary_for_spec(self, spec):
        has_manifest = any(
            spec.file_path.with_name(f"{spec.file_path.stem}{suffix}").exists()
            for suffix in (".deps", ".deps.txt")
        )
        return SimpleNamespace(has_manifest=has_manifest)

    def install_for_spec(self, spec, _context, *, repair: bool = False):
        runtime_dir = self.runtime_dir(spec.plugin_id)
        runtime_dir.mkdir(parents=True, exist_ok=True)
        self.installs.append((spec.plugin_id, repair))
        return {
            "plugin_id": spec.plugin_id,
            "runtime_dir": str(runtime_dir),
            "repair": "yes" if repair else "no",
        }

    def clear_for_spec(self, spec) -> bool:
        runtime_dir = self.runtime_dir(spec.plugin_id)
        existed = runtime_dir.exists()
        if existed:
            shutil.rmtree(runtime_dir)
        self.cleared.append(spec.plugin_id)
        return existed


class _StubServices:
    def __init__(self, plugin_manager: PluginManager, temp_root: Path):
        self.plugin_manager = plugin_manager
        self.database_path = temp_root / "clipboard.db"
        self._output_root = temp_root / "output"

    def default_output_path(self) -> Path:
        self._output_root.mkdir(parents=True, exist_ok=True)
        return self._output_root

    def record_run(self, _plugin_id: str, _status: str, _details: str = "") -> None:
        return None


class _ServiceMethodHarness:
    def __init__(self):
        self.install_calls: list[str] = []
        self.remove_calls: list[str] = []
        self.reload_calls = 0
        self.plugin_package_manager = SimpleNamespace(
            install_catalog_package=self._install_catalog_package,
            remove_package=self._remove_package,
        )

    def _install_catalog_package(self, package_id: str):
        self.install_calls.append(package_id)
        return {"package_id": package_id, "plugin_ids": ["example"]}

    def _remove_package(self, package_id: str):
        self.remove_calls.append(package_id)
        return {"package_id": package_id, "removed": True}

    def reload_plugins(self) -> None:
        self.reload_calls += 1


class SignedPackageTests(unittest.TestCase):
    def _build_packages(self, temp_root: Path) -> tuple[dict[str, object], Path]:
        output_dir = temp_root / "dist" / "first_party_packages"
        catalog_path = temp_root / "dngine" / "first_party_catalog.json"
        catalog_path.parent.mkdir(parents=True, exist_ok=True)
        result = build_first_party_packages(
            output_dir=output_dir,
            catalog_path=catalog_path,
            private_key_path=PRIVATE_KEY_PATH,
        )
        return result, catalog_path

    def _make_environment(self, temp_root: Path):
        signed_root = temp_root / "signed_plugins"
        custom_root = temp_root / "custom_plugins"
        catalog_root = temp_root / "catalog_state"
        cache_root = temp_root / "package_cache"
        state_manager = PluginStateManager(temp_root / "plugin_state.json")
        plugin_manager = PluginManager(
            BUILTIN_ROOT,
            signed_root,
            custom_root,
            state_manager,
            builtin_manifest_path=PROJECT_ROOT / "dngine" / "builtin_plugin_manifest.json",
            enforce_builtin_manifest=False,
            signed_signers_path=SIGNERS_PATH,
        )
        dependency_manager = _DummyDependencyManager(temp_root / "plugin_deps")
        package_manager = PluginPackageManager(
            plugin_manager,
            custom_root,
            signed_root,
            catalog_root,
            cache_root,
            state_manager,
            dependency_manager,
            temp_root / "dngine" / "first_party_catalog.json",
            SIGNERS_PATH,
        )
        return plugin_manager, package_manager, dependency_manager

    def test_build_outputs_signed_archives_and_catalog(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            result, catalog_path = self._build_packages(temp_root)
            archives = {Path(path).name for path in result["archives"]}
            self.assertEqual(result["count"], len(EXPECTED_PACKAGE_IDS))
            self.assertEqual(
                archives,
                {f"{package_id}-0.9.0.zip" for package_id in EXPECTED_PACKAGE_IDS},
            )
            catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
            package_ids = {entry["package_id"] for entry in catalog["packages"]}
            self.assertEqual(package_ids, EXPECTED_PACKAGE_IDS)
            self.assertNotIn("media_images", package_ids)

    def test_plugin_categories_follow_package_groups(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            plugin_manager, _, _ = self._make_environment(Path(temp_dir))
            specs = {spec.plugin_id: spec for spec in plugin_manager.discover_plugins(include_disabled=True)}
            self.assertEqual(specs["hash_checker"].localized_category("en"), "Files & Storage")
            self.assertEqual(specs["pdf_suite"].localized_category("en"), "Office & Docs")
            self.assertEqual(specs["sys_audit"].localized_category("en"), "Network & Security")
            self.assertEqual(specs["color_picker"].localized_category("en"), "Media & Images")

    def test_optional_tool_commands_only_register_when_plugin_is_installed(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            plugin_manager, package_manager, _ = self._make_environment(Path(temp_dir))
            services = _StubServices(plugin_manager, Path(temp_dir))
            registry = CommandRegistry()
            register_builtin_tool_commands(registry, services)
            command_ids = {spec.command_id for spec in registry.list_commands()}
            self.assertIn("tool.pdf_suite.merge", command_ids)
            self.assertNotIn("tool.chart_builder.run", command_ids)

            result, _ = self._build_packages(Path(temp_dir))
            chart_archive = next(
                Path(path)
                for path in result["archives"]
                if Path(path).name.startswith("data_analysis-")
            )
            package_manager.install_signed_package_archive(chart_archive)

            registry = CommandRegistry()
            register_builtin_tool_commands(registry, services)
            command_ids = {spec.command_id for spec in registry.list_commands()}
            self.assertIn("tool.chart_builder.run", command_ids)
            self.assertIn("tool.deep_scan_auditor.folder", command_ids)

    def test_install_and_remove_signed_package_archive(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            result, _ = self._build_packages(temp_root)
            plugin_manager, package_manager, dependency_manager = self._make_environment(temp_root)
            archive_path = next(
                Path(path)
                for path in result["archives"]
                if Path(path).name.startswith("web_dev-")
            )

            install_result = package_manager.install_signed_package_archive(archive_path)
            self.assertEqual(install_result["package_id"], "web_dev")
            self.assertEqual(set(install_result["plugin_ids"]), {"code_factory", "cred_scanner", "web_scraper"})
            self.assertEqual(
                {entry["plugin_id"] for entry in install_result["dependency_results"]},
                {"web_scraper"},
            )
            self.assertIn(("web_scraper", False), dependency_manager.installs)

            specs = {
                spec.plugin_id: spec
                for spec in plugin_manager.discover_plugins(include_disabled=True)
                if spec.source_type == "signed"
            }
            self.assertEqual(specs["web_scraper"].package_name, "web_dev")
            self.assertEqual(specs["web_scraper"].signature_status, "verified")
            self.assertEqual(specs["web_scraper"].signer, "dngine-first-party-dev")
            self.assertEqual(specs["web_scraper"].localized_category("en"), "Web Dev")

            verification = verify_installed_signed_package(
                Path(install_result["install_path"]),
                SIGNERS_PATH,
            )
            self.assertEqual(verification.package_id, "web_dev")

            removal = package_manager.remove_package("web_dev")
            self.assertTrue(removal["removed"])
            self.assertEqual(set(removal["plugin_ids"]), {"code_factory", "cred_scanner", "web_scraper"})
            remaining = {
                spec.plugin_id
                for spec in plugin_manager.discover_plugins(include_disabled=True)
                if spec.source_type == "signed"
            }
            self.assertNotIn("web_scraper", remaining)

    def test_catalog_refresh_install_and_updates(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            result, source_catalog = self._build_packages(temp_root)
            _, package_manager, _ = self._make_environment(temp_root)

            refresh = package_manager.refresh_catalog(str(source_catalog))
            self.assertEqual(refresh["count"], len(EXPECTED_PACKAGE_IDS))
            catalog_rows = {entry["package_id"]: entry for entry in package_manager.list_catalog_packages()}
            self.assertIn("web_dev", catalog_rows)
            self.assertFalse(catalog_rows["web_dev"]["installed"])

            install_result = package_manager.install_catalog_package("web_dev")
            self.assertEqual(install_result["package_id"], "web_dev")

            catalog_payload = json.loads(source_catalog.read_text(encoding="utf-8"))
            for entry in catalog_payload["packages"]:
                if entry["package_id"] == "web_dev":
                    entry["package_version"] = "0.9.1"
            source_catalog.write_text(json.dumps(catalog_payload, indent=2) + "\n", encoding="utf-8")

            package_manager.refresh_catalog(str(source_catalog))
            updates = {entry["package_id"]: entry for entry in package_manager.available_updates()}
            self.assertIn("web_dev", updates)
            self.assertEqual(updates["web_dev"]["package_version"], "0.9.1")

            archive_path = next(
                Path(path)
                for path in result["archives"]
                if Path(path).name.startswith("web_dev-")
            )
            self.assertEqual(verify_signed_archive(archive_path, SIGNERS_PATH).package_id, "web_dev")

    def test_tampered_signed_archive_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            result, _ = self._build_packages(temp_root)
            archive_path = next(Path(path) for path in result["archives"] if Path(path).name.startswith("web_dev-"))
            tampered_path = temp_root / "web_dev-tampered.zip"

            with tempfile.TemporaryDirectory() as extract_dir:
                extract_root = Path(extract_dir)
                with zipfile.ZipFile(archive_path, "r") as archive:
                    archive.extractall(extract_root)
                plugin_file = extract_root / "plugins" / "web_scraper.py"
                plugin_file.write_text(plugin_file.read_text(encoding="utf-8") + "\n# tampered\n", encoding="utf-8")
                with zipfile.ZipFile(tampered_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
                    for file_path in sorted(extract_root.rglob("*")):
                        if file_path.is_file():
                            archive.write(file_path, file_path.relative_to(extract_root).as_posix())

            with self.assertRaises(ValueError):
                verify_signed_archive(tampered_path, SIGNERS_PATH)

    def test_services_install_helper_does_not_reload_ui(self) -> None:
        harness = _ServiceMethodHarness()
        payload = AppServices._install_catalog_package(harness, "web_dev")
        self.assertEqual(payload["package_id"], "web_dev")
        self.assertEqual(harness.install_calls, ["web_dev"])
        self.assertEqual(harness.reload_calls, 0)

    def test_services_remove_helper_does_not_reload_ui(self) -> None:
        harness = _ServiceMethodHarness()
        payload = AppServices._remove_signed_package(harness, "web_dev")
        self.assertTrue(payload["removed"])
        self.assertEqual(harness.remove_calls, ["web_dev"])
        self.assertEqual(harness.reload_calls, 0)


if __name__ == "__main__":
    unittest.main()
