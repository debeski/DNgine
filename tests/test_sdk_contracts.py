from __future__ import annotations

import hashlib
import os
import tempfile
import unittest
from unittest import mock
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PIL import Image
from PySide6.QtWidgets import QApplication, QFormLayout, QLabel, QLineEdit, QVBoxLayout, QWidget

from dngine.core.commands import CommandRegistry
from dngine.core.plugin_manager import _parse_plugin_specs
from dngine.plugins.core_tools.color_picker import ColorPickerPlugin
from dngine.plugins.core_tools.document_bridge import DocumentBridgePlugin
from dngine.plugins.core_tools.hash_checker import HashCheckerPlugin
from dngine.plugins.core_tools.image_tagger import ImageTaggerPlugin
from dngine.plugins.core_tools.pdf_suite import PDFSuitePlugin
from dngine.plugins.core_tools.privacy_shredder import PrivacyShredderPlugin
from dngine.plugins.core_tools.system_audit import SystemAuditPlugin
from dngine.plugins.system.about_info import AboutInfoPlugin
from dngine.plugins.system.dev_lab import DevLabPlugin
from fp_plugins.office_docs.plugins.cross_joiner import CrossJoinerPlugin
from fp_plugins.office_docs.plugins.data_cleaner import DataCleanerPlugin
from fp_plugins.media_images.plugins.smart_background_remover import SmartBackgroundRemoverPlugin
from fp_plugins.media_images.plugins.image_transformer import ImageTransformerPlugin
from fp_plugins.media_images.plugins.smart_exif_editor import SmartExifEditorPlugin
from dngine.sdk import (
    ActionSpec,
    AdvancedPagePlugin,
    ChoiceOption,
    CommandSpec,
    DeclarativePlugin,
    FieldSpec,
    PageSpec,
    ResultSpec,
    SectionSpec,
    StandardPlugin,
    _pt,
    apply_direction,
)


class _DummyI18n:
    def __init__(self, *, language: str = "en"):
        self._language = language
        self.language_changed = _DummySignal()

    def current_language(self) -> str:
        return self._language

    def is_rtl(self) -> bool:
        return self._language == "ar"

    def layout_direction(self):
        return Qt.LayoutDirection.RightToLeft if self.is_rtl() else Qt.LayoutDirection.LeftToRight


class _DummyThemeManager:
    def __init__(self):
        self.theme_changed = _DummySignal()

    class _Palette:
        card_bg = "#222222"
        text_primary = "#ffffff"
        text_muted = "#aaaaaa"
        border = "#444444"
        accent = "#4f8cff"
        mode = "dark"

    def current_palette(self):
        return self._Palette()


class _DummySignal:
    def connect(self, _callback) -> None:
        return None


class _DummyTaskContext:
    def __init__(self):
        self.logs: list[tuple[str, str]] = []
        self.progress_values: list[float] = []

    def log(self, message: str, level: str = "INFO") -> None:
        self.logs.append((level, str(message)))

    def progress(self, value: float) -> None:
        self.progress_values.append(float(value))


class _DummyUIInspector:
    def __init__(self):
        self.snapshot_changed = _DummySignal()
        self.inspect_mode_changed = _DummySignal()
        self.text_unlock_changed = _DummySignal()
        self._inspect_mode = False
        self._text_unlock = False
        self._snapshot: dict[str, object] = {}

    def inspect_mode(self) -> bool:
        return self._inspect_mode

    def set_inspect_mode(self, enabled: bool) -> bool:
        self._inspect_mode = bool(enabled)
        return self._inspect_mode

    def toggle_inspect_mode(self) -> bool:
        self._inspect_mode = not self._inspect_mode
        return self._inspect_mode

    def text_unlock_enabled(self) -> bool:
        return self._text_unlock

    def set_text_unlock_enabled(self, enabled: bool) -> bool:
        self._text_unlock = bool(enabled)
        return self._text_unlock

    def last_snapshot(self) -> dict[str, object]:
        return dict(self._snapshot)


class _DummyServices:
    def __init__(self, *, language: str = "en"):
        self.i18n = _DummyI18n(language=language)
        self.theme_manager = _DummyThemeManager()
        self.ui_inspector = _DummyUIInspector()
        self.logged: list[tuple[str, str]] = []
        self.runs: list[tuple[str, str, str]] = []
        self._default_output_dir = Path(tempfile.mkdtemp(prefix="dngine-sdk-contracts-"))
        self.data_root = self._default_output_dir / "data"
        self.data_root.mkdir(parents=True, exist_ok=True)
        self._developer_mode_enabled = True

    def plugin_text(self, _plugin_id: str, _key: str, default: str | None = None, **kwargs) -> str:
        text = default or ""
        return text.format(**kwargs) if kwargs else text

    def log(self, message: str, level: str = "INFO") -> None:
        self.logged.append((level, str(message)))

    def record_run(self, plugin_id: str, status: str, details: str = "") -> None:
        self.runs.append((plugin_id, status, details))

    def default_output_path(self) -> Path:
        return self._default_output_dir

    def developer_mode_enabled(self) -> bool:
        return bool(self._developer_mode_enabled)

    def run_task(
        self,
        task_fn,
        *,
        on_result=None,
        on_error=None,
        on_finished=None,
        on_progress=None,
        status_text: str | None = None,
    ):
        context = _DummyTaskContext()
        try:
            result = task_fn(context)
            if callable(on_result):
                on_result(result)
        except Exception as exc:
            if callable(on_error):
                on_error({"message": str(exc)})
        finally:
            if callable(on_progress):
                for value in context.progress_values:
                    on_progress(value)
            if callable(on_finished):
                on_finished()
        return context


def _write_exif_test_jpeg(path: Path, *, description: str, artist: str = "", copyright: str = "") -> None:
    image = Image.new("RGB", (48, 48), (235, 235, 235))
    exif = Image.Exif()
    exif[270] = description
    exif[315] = artist
    exif[33432] = copyright
    exif[306] = "2024:01:01 10:00:00"
    image.save(path, exif=exif)


class _SDKExamplePlugin(StandardPlugin):
    plugin_id = "sdk_example"
    name = "SDK Example"
    description = "SDK example plugin."
    category = "General"

    def declare_page_spec(self, services):
        return PageSpec(
            archetype="simple_form",
            title="SDK Example",
            description="Strict SDK page.",
            sections=(
                SectionSpec(
                    section_id="settings",
                    kind="settings_card",
                    fields=(
                        FieldSpec("name", "text", "Name", placeholder="Enter a name"),
                        FieldSpec(
                            "mode",
                            "choice",
                            "Mode",
                            default="fast",
                            options=(ChoiceOption("fast", "Fast"), ChoiceOption("safe", "Safe")),
                        ),
                    ),
                ),
                SectionSpec(
                    section_id="actions",
                    kind="actions_row",
                    actions=(ActionSpec("run", "Run"),),
                ),
                SectionSpec(
                    section_id="summary",
                    kind="summary_output_pane",
                    description="Ready",
                    stretch=1,
                ),
            ),
            result_spec=ResultSpec(
                summary_placeholder="Ready",
                output_placeholder="Output appears here.",
            ),
        )

    def declare_command_specs(self, services):
        return (
            CommandSpec(
                command_id="tool.sdk_example.run",
                title="Run SDK Example",
                description="Run the SDK example command.",
                worker=lambda context, value="ok": {"value": value, "ok": True},
                aliases=("tool.sdk_example.alias",),
            ),
        )


class SDKContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._app = QApplication.instance() or QApplication([])

    def test_parse_plugin_specs_classifies_sdk_and_legacy_contracts(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            plugin_file = root / "sample_plugin.py"
            plugin_file.write_text(
                "\n".join(
                    [
                        "from dngine.core.plugin_api import QtPlugin",
                        "from dngine.sdk import DeclarativePlugin, StandardPlugin, AdvancedPagePlugin",
                        "",
                        "class LegacyTool(QtPlugin):",
                        "    plugin_id = 'legacy_tool'",
                        "    name = 'Legacy Tool'",
                        "",
                        "class SDKTool(StandardPlugin):",
                        "    plugin_id = 'sdk_tool'",
                        "    name = 'SDK Tool'",
                        "    def declare_page_spec(self, services):",
                        "        return None",
                        "",
                        "class ControllerStyledSDK(StandardPlugin):",
                        "    plugin_id = 'controller_sdk'",
                        "    name = 'Controller SDK'",
                        "    def declare_page_spec(self, services):",
                        "        return None",
                        "    def create_widget(self, services):",
                        "        return None",
                        "",
                        "class DictTool(DeclarativePlugin):",
                        "    plugin_id = 'dict_tool'",
                        "    name = 'Dict Tool'",
                        "    page = {}",
                        "",
                        "class FancyAdvanced(AdvancedPagePlugin):",
                        "    plugin_id = 'advanced_tool'",
                        "    name = 'Advanced Tool'",
                        "    def build_advanced_widget(self, services):",
                        "        return None",
                        "",
                        "class BrokenSDK(StandardPlugin):",
                        "    plugin_id = 'broken_sdk'",
                        "    name = 'Broken SDK'",
                    ]
                ),
                encoding="utf-8",
            )

            specs = {spec.plugin_id: spec for spec in _parse_plugin_specs(plugin_file, root, source_type="imported")}

            self.assertEqual(specs["legacy_tool"].contract_status, "legacy_contract")
            self.assertEqual(specs["sdk_tool"].contract_status, "sdk_valid")
            self.assertEqual(specs["controller_sdk"].contract_status, "sdk_invalid")
            self.assertEqual(specs["dict_tool"].contract_status, "sdk_valid")
            self.assertEqual(specs["advanced_tool"].contract_status, "advanced_contract")
            self.assertEqual(specs["broken_sdk"].contract_status, "sdk_invalid")

    def test_system_page_plugins_classify_as_advanced_contracts(self) -> None:
        repo_root = Path(__file__).resolve().parents[1]
        plugin_files = {
            "dash_hub": repo_root / "dngine/plugins/system/dash_hub.py",
            "clip_snip": repo_root / "dngine/plugins/system/clip_snip.py",
            "command_center": repo_root / "dngine/plugins/system/command_center.py",
            "plugin_manager": repo_root / "dngine/plugins/system/plugin_manager.py",
            "workflow_studio": repo_root / "dngine/plugins/system/workflow_studio.py",
        }

        for plugin_id, file_path in plugin_files.items():
            with self.subTest(plugin_id=plugin_id):
                specs = {
                    spec.plugin_id: spec
                    for spec in _parse_plugin_specs(file_path, repo_root, source_type="builtin")
                }
                self.assertEqual(specs[plugin_id].contract_status, "advanced_contract")

    def test_about_info_classifies_as_sdk_valid_system_page(self) -> None:
        repo_root = Path(__file__).resolve().parents[1]
        file_path = repo_root / "dngine/plugins/system/about_info.py"

        specs = {
            spec.plugin_id: spec
            for spec in _parse_plugin_specs(file_path, repo_root, source_type="builtin")
        }

        self.assertEqual(specs["about_info"].contract_status, "sdk_valid")

    def test_dev_lab_classifies_as_sdk_valid_system_page(self) -> None:
        repo_root = Path(__file__).resolve().parents[1]
        file_path = repo_root / "dngine/plugins/system/dev_lab.py"

        specs = {
            spec.plugin_id: spec
            for spec in _parse_plugin_specs(file_path, repo_root, source_type="builtin")
        }

        self.assertEqual(specs["dev_lab"].contract_status, "sdk_valid")

    def test_standard_plugin_renders_declared_page(self) -> None:
        plugin = _SDKExamplePlugin()
        services = _DummyServices()
        page = plugin.create_widget(services)

        self.assertEqual(page.generated_widgets["page.title"].text(), "SDK Example")
        self.assertIn("name", page.generated_widgets)
        self.assertIn("mode", page.generated_widgets)
        self.assertIn("run", page.generated_actions)
        self.assertIn("summary.output", page.generated_widgets)

    def test_standard_plugin_registers_declared_commands(self) -> None:
        plugin = _SDKExamplePlugin()
        services = _DummyServices()
        registry = CommandRegistry()

        plugin.register_commands(registry, services)
        command_ids = {spec.command_id for spec in registry.list_commands()}

        self.assertIn("tool.sdk_example.run", command_ids)
        self.assertIn("tool.sdk_example.alias", command_ids)
        result = registry.execute("tool.sdk_example.run", value="done")
        self.assertEqual(result["value"], "done")
        self.assertEqual(services.runs[-1][0], "sdk_example")

    def test_document_bridge_declares_sdk_commands_and_runtime_page(self) -> None:
        plugin = DocumentBridgePlugin()
        services = _DummyServices()
        registry = CommandRegistry()

        self.assertIsInstance(plugin, DeclarativePlugin)

        plugin.register_commands(registry, services)
        command_ids = {spec.command_id for spec in registry.list_commands()}
        self.assertIn("tool.doc_bridge.md_to_docx", command_ids)
        self.assertIn("tool.doc_bridge.docx_to_md", command_ids)

        page = plugin.create_widget(services)
        self.assertFalse(hasattr(page, "_controller"))
        self.assertIsNotNone(getattr(page, "_sdk_runtime", None))

        mode = page.generated_widgets["mode"]
        source_path = page.generated_widgets["source_path"]
        output_path = page.generated_widgets["output_path"]
        layout_mode = page.generated_widgets["layout_mode"]
        font_name = page.generated_widgets["font_name"]
        extract_images = page.generated_widgets["extract_images"]
        open_result = page.generated_actions["open_result"]

        self.assertIn("markdown", source_path.placeholderText().lower())
        self.assertIn("docx", output_path.placeholderText().lower())
        self.assertEqual(getattr(source_path, "_mode", ""), "file")
        self.assertEqual(getattr(output_path, "_mode", ""), "file")
        self.assertFalse(layout_mode.isHidden())
        self.assertFalse(font_name.isHidden())
        self.assertTrue(extract_images.isHidden())
        self.assertFalse(open_result.isEnabled())

        mode.setCurrentIndex(mode.findData("docx_to_md"))

        self.assertIn("docx", source_path.placeholderText().lower())
        self.assertIn("markdown", output_path.placeholderText().lower())
        self.assertTrue(layout_mode.isHidden())
        self.assertTrue(font_name.isHidden())
        self.assertFalse(extract_images.isHidden())

        page._sdk_runtime.set_value("latest_output_path", "/tmp/result.md")
        self.assertTrue(open_result.isEnabled())

        with mock.patch("dngine.plugins.core_tools.document_bridge.open_file_or_folder", return_value=True) as opener:
            open_result.click()
        opener.assert_called_once_with("/tmp/result.md")

    def test_hash_checker_declares_sdk_command_and_runtime_page(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            target = Path(temp_dir) / "sample.txt"
            payload = b"hash-checker"
            target.write_bytes(payload)
            expected_md5 = hashlib.md5(payload).hexdigest()

            plugin = HashCheckerPlugin()
            services = _DummyServices()
            registry = CommandRegistry()

            plugin.register_commands(registry, services)
            command_ids = {spec.command_id for spec in registry.list_commands()}
            self.assertIn("tool.hash_checker.calculate", command_ids)

            command_result = registry.execute(
                "tool.hash_checker.calculate",
                file_path=str(target),
                expected_hash=expected_md5,
            )
            self.assertEqual(command_result["md5"], expected_md5)
            self.assertTrue(command_result["verification_match"])
            self.assertEqual(command_result["verification_algorithm"], "md5")

            page = plugin.create_widget(services)
            self.assertFalse(hasattr(page, "_controller"))
            self.assertIsNotNone(getattr(page, "_sdk_runtime", None))

            source_path = page.generated_widgets["source_path"]
            expected_hash_input = page.generated_widgets["expected_hash"]
            run_button = page.generated_actions["run"]
            verify_button = page.generated_actions["verify"]
            copy_md5 = page.generated_actions["copy_md5"]
            copy_sha256 = page.generated_actions["copy_sha256"]
            output = page.generated_widgets["result.output"]
            summary = page.generated_widgets["result.summary"]

            self.assertFalse(run_button.isEnabled())
            self.assertFalse(verify_button.isEnabled())
            self.assertFalse(copy_md5.isEnabled())
            self.assertFalse(copy_sha256.isEnabled())

            source_path.setText(str(target))

            self.assertTrue(run_button.isEnabled())
            self.assertTrue(verify_button.isEnabled())

            run_button.click()

            self.assertTrue(copy_md5.isEnabled())
            self.assertTrue(copy_sha256.isEnabled())
            self.assertIn(expected_md5, output.toPlainText())
            self.assertIn(target.name, summary.text())

            expected_hash_input.setText(expected_md5)
            verify_button.click()

            self.assertIn("match confirmed", summary.text().lower())
            self.assertIn("match confirmed", output.toPlainText().lower())

    def test_color_picker_uses_sdk_runtime_without_controller_class(self) -> None:
        plugin = ColorPickerPlugin()
        services = _DummyServices()
        page = plugin.create_widget(services)

        self.assertFalse(hasattr(page, "_controller"))
        self.assertIsNotNone(getattr(page, "_sdk_runtime", None))

        preview = page.generated_widgets["preview"]
        hex_value = page.generated_widgets["hex_value"]
        rgb_value = page.generated_widgets["rgb_value"]
        hsl_value = page.generated_widgets["hsl_value"]
        status_text = page.generated_widgets["status_text"]

        self.assertIsNotNone(preview.pixmap())
        self.assertEqual(hex_value.text(), "#D85A8F")
        self.assertIn("rgb(", rgb_value.text().lower())
        self.assertIn("hsl(", hsl_value.text().lower())
        self.assertIn("ready", status_text.toPlainText().lower())

        with mock.patch("dngine.plugins.core_tools.color_picker.start_screen_picker") as mock_start:
            class DummySession:
                pass
            dummy_session = DummySession()
            callback_holder = []
            
            def side_effect(parent, on_picked, on_canceled):
                callback_holder.append(on_picked)
                return dummy_session
                
            mock_start.side_effect = side_effect
            
            pick_button = page.generated_actions["pick_color"]
            pick_button.click()
            
            # Simulate async selection
            callback_holder[0]({"hex": "#123456", "rgb": "rgb(18, 52, 86)", "hsl": "hsl(210, 65%, 20%)", "isValid": True})

        self.assertEqual(hex_value.text(), "#123456")
        self.assertIn("captured", status_text.toPlainText().lower())

    def test_pdf_suite_declares_sdk_command_and_runtime_page(self) -> None:
        plugin = PDFSuitePlugin()
        services = _DummyServices()
        registry = CommandRegistry()

        self.assertIsInstance(plugin, DeclarativePlugin)

        plugin.register_commands(registry, services)
        command_ids = {spec.command_id for spec in registry.list_commands()}
        self.assertIn("tool.pdf_suite.merge", command_ids)

        page = plugin.create_widget(services)
        self.assertFalse(hasattr(page, "_controller"))
        self.assertIsNotNone(getattr(page, "_sdk_runtime", None))
        self.assertTrue(callable(getattr(page, "add_file_paths", None)))

        run_button = page.generated_actions["run"]
        open_output = page.generated_actions["open_output"]
        output_dir = page.generated_widgets["output_dir"]
        file_list = page.generated_widgets["files"]

        self.assertFalse(run_button.isEnabled())
        self.assertFalse(open_output.isEnabled())
        self.assertEqual(output_dir.text(), str(services.default_output_path()))

        page.add_file_paths(["/tmp/one.pdf", "/tmp/two.pdf"])

        self.assertEqual(file_list.count(), 2)
        self.assertTrue(run_button.isEnabled())
        self.assertEqual(getattr(output_dir, "_mode", ""), "directory")

        page._sdk_runtime.set_value("latest_output_path", "/tmp/output.pdf")
        self.assertTrue(open_output.isEnabled())

        with mock.patch("dngine.plugins.core_tools.pdf_suite.open_file_or_folder") as open_url:
            open_output.click()
        open_url.assert_called_once()

    def test_privacy_shredder_declares_sdk_command_and_runtime_page(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            command_file = root / "legacy-secret.txt"
            command_file.write_text("delete me", encoding="utf-8")

            plugin = PrivacyShredderPlugin()
            services = _DummyServices()
            registry = CommandRegistry()

            plugin.register_commands(registry, services)
            command_ids = {spec.command_id for spec in registry.list_commands()}
            self.assertIn("tool.privacy_shred.run", command_ids)
            self.assertIn("tool.shredder.run", command_ids)

            command_result = registry.execute(
                "tool.shredder.run",
                path=str(command_file),
                passes=1,
            )
            self.assertEqual(command_result["deleted_count"], 1)
            self.assertFalse(command_file.exists())

            queued_file = root / "queued-secret.txt"
            queued_file.write_text("queued", encoding="utf-8")
            queued_dir = root / "queued-folder"
            queued_dir.mkdir()
            (queued_dir / "nested.txt").write_text("nested", encoding="utf-8")

            page = plugin.create_widget(services)
            self.assertFalse(hasattr(page, "_controller"))
            self.assertIsNotNone(getattr(page, "_sdk_runtime", None))
            self.assertTrue(callable(getattr(page, "add_file_paths", None)))

            targets = page.generated_widgets["targets"]
            run_button = page.generated_actions["run"]
            clear_button = page.generated_actions["targets.__clear"]
            summary = page.generated_widgets["result.summary"]
            output = page.generated_widgets["result.output"]

            self.assertFalse(run_button.isEnabled())

            page.add_file_paths([str(queued_file), str(queued_dir)], "targets")

            self.assertEqual(targets.count(), 2)
            self.assertTrue(run_button.isEnabled())
            self.assertTrue(clear_button.isEnabled())

            with mock.patch(
                "dngine.plugins.core_tools.privacy_shredder.confirm_action",
                return_value=True,
            ):
                run_button.click()

            self.assertFalse(queued_file.exists())
            self.assertFalse(queued_dir.exists())
            self.assertEqual(targets.count(), 0)
            self.assertIn("deleted 2", summary.text().lower())
            self.assertIn("deleted: 2", output.toPlainText().lower())

    def test_system_audit_uses_declarative_contract(self) -> None:
        plugin = SystemAuditPlugin()
        services = _DummyServices()
        registry = CommandRegistry()

        self.assertIsInstance(plugin, DeclarativePlugin)

        plugin.register_commands(registry, services)
        command_ids = {spec.command_id for spec in registry.list_commands()}
        self.assertIn("tool.sys_audit.run", command_ids)

        result = registry.execute("tool.sys_audit.run")
        self.assertIn("hostname", result)
        self.assertIn("python_version", result)

        page = plugin.create_widget(services)
        self.assertFalse(hasattr(page, "_controller"))
        self.assertIsNotNone(getattr(page, "_sdk_runtime", None))
        
        runtime = page._sdk_runtime
        
        refresh_action = page.generated_actions.get("refresh")
        self.assertIsNotNone(refresh_action)
        self.assertEqual(refresh_action.text(), "Refresh overview")
        
        details_table = runtime.widget("details_table")
        profile_card = runtime.widget("profile_card")
        self.assertEqual(details_table.columnCount(), 2)

        from PySide6.QtCore import QEventLoop, QTimer

        loop = QEventLoop()
        QTimer.singleShot(250, loop.quit)
        loop.exec()

        self.assertGreater(details_table.rowCount(), 0)
        self.assertIn("Host", profile_card.body_label.text())
        self.assertFalse(any(status == "ERROR" for plugin_id, status, _details in services.runs if plugin_id == "sys_audit"))
        
        for timer in runtime._timers.values():
            timer.stop()

    def test_about_info_uses_sdk_runtime_without_controller_class(self) -> None:
        plugin = AboutInfoPlugin()
        services = _DummyServices()
        page = plugin.create_widget(services)

        self.assertFalse(hasattr(page, "_controller"))
        self.assertIsNotNone(getattr(page, "_sdk_runtime", None))
        self.assertEqual(page.generated_widgets["page.title"].text(), "About Info")

        libraries = page.generated_widgets["libraries"]
        support_card = page.generated_widgets["support_card"]
        identity_card = page.generated_widgets["identity_card"]

        self.assertGreater(libraries.rowCount(), 0)
        self.assertEqual(libraries.columnCount(), 2)
        self.assertIn("github.com/debeski/micro-Toolkit", support_card.body_label.text())
        self.assertIn("DeBeski (micro)", identity_card.body_label.text())
        self.assertNotIn("qt-material", {libraries.item(row, 0).text() for row in range(libraries.rowCount())})

    def test_dev_lab_uses_declarative_runtime_without_controller_class(self) -> None:
        plugin = DevLabPlugin()
        services = _DummyServices()
        services.ui_inspector._snapshot = {
            "class_name": "QPushButton",
            "object_name": "inspectButton",
            "window_title": "Main Window",
            "geometry": "10, 20, 120 x 40",
            "parent_chain": ["QMainWindow#root", "QWidget#central"],
            "child_count": 0,
            "visible": True,
            "enabled": True,
        }
        page = plugin.create_widget(services)

        self.assertFalse(hasattr(page, "_controller"))
        self.assertIsNotNone(getattr(page, "_sdk_runtime", None))

        runtime = page._sdk_runtime
        inspect_start = page.generated_actions["inspect_start"]
        copy_snapshot = page.generated_actions["copy_snapshot"]
        status_card = page.generated_widgets["status_card"]
        selection_card = page.generated_widgets["selection_card"]
        parent_chain = page.generated_widgets["parent_chain_panel"]
        details_panel = page.generated_widgets["details_panel"]

        from PySide6.QtCore import QEventLoop, QTimer

        loop = QEventLoop()
        QTimer.singleShot(300, loop.quit)
        loop.exec()

        self.assertTrue(inspect_start.isEnabled())
        self.assertTrue(copy_snapshot.isEnabled())
        self.assertIn("Developer Mode", status_card.body_label.text())
        self.assertIn("QPushButton", selection_card.body_label.text())
        self.assertIn("QMainWindow#root", parent_chain.toPlainText())
        self.assertIn('"class_name": "QPushButton"', details_panel.toPlainText())

        with mock.patch("dngine.plugins.system.dev_lab.copy_to_clipboard") as copy_mock:
            copy_snapshot.click()
        copy_mock.assert_called_once()

        for timer in runtime._timers.values():
            timer.stop()

    def test_data_cleaner_declares_sdk_command_and_runtime_page(self) -> None:
        import pandas as pd

        with tempfile.TemporaryDirectory() as temp_dir:
            source = Path(temp_dir) / "dirty.xlsx"
            pd.DataFrame(
                {
                    "name": ["  Alice  ", None, "Bob"],
                    "value": [1, None, 2],
                }
            ).to_excel(source, index=False)

            plugin = DataCleanerPlugin()
            services = _DummyServices()
            registry = CommandRegistry()

            plugin.register_commands(registry, services)
            command_ids = {spec.command_id for spec in registry.list_commands()}
            self.assertIn("tool.cleaner.run", command_ids)

            command_result = registry.execute(
                "tool.cleaner.run",
                file_path=str(source),
                trim=True,
                drop_empty=True,
                fill_nulls=True,
            )
            self.assertTrue(Path(command_result["output_path"]).exists())
            self.assertEqual(command_result["file_name"], "dirty.xlsx")

            page = plugin.create_widget(services)
            self.assertFalse(hasattr(page, "_controller"))
            self.assertIsNotNone(getattr(page, "_sdk_runtime", None))

            file_path = page.generated_widgets["file_path"]
            run_button = page.generated_actions["run"]
            open_result = page.generated_actions["open_result"]
            output = page.generated_widgets["result.output"]
            summary = page.generated_widgets["result.summary"]

            self.assertFalse(open_result.isEnabled())
            file_path.setText(str(source))
            run_button.click()

            self.assertTrue(open_result.isEnabled())
            self.assertIn("dirty.xlsx", summary.text())
            self.assertIn(str(services.default_output_path()), output.toPlainText())

    def test_cross_joiner_declares_sdk_command_and_runtime_page(self) -> None:
        import pandas as pd

        with tempfile.TemporaryDirectory() as temp_dir:
            file_a = Path(temp_dir) / "dataset_a.xlsx"
            file_b = Path(temp_dir) / "dataset_b.xlsx"
            pd.DataFrame(
                {
                    "key_a": [1, 2],
                    "name": ["alpha", "beta"],
                }
            ).to_excel(file_a, index=False)
            pd.DataFrame(
                {
                    "key_b": [2, 3],
                    "name": ["beta", "gamma"],
                }
            ).to_excel(file_b, index=False)

            plugin = CrossJoinerPlugin()
            services = _DummyServices()
            registry = CommandRegistry()

            plugin.register_commands(registry, services)
            command_ids = {spec.command_id for spec in registry.list_commands()}
            self.assertIn("tool.cross_joiner.run", command_ids)

            command_result = registry.execute(
                "tool.cross_joiner.run",
                file_a=str(file_a),
                col_a="key_a",
                file_b=str(file_b),
                col_b="key_b",
            )
            output_labels = {label for label, _path, _rows in command_result["outputs"]}
            output_paths = [Path(path) for _label, path, _rows in command_result["outputs"]]
            self.assertEqual(output_labels, {"matches", "only_a", "only_b"})
            self.assertTrue(all(path.exists() for path in output_paths))

            page = plugin.create_widget(services)
            self.assertFalse(hasattr(page, "_controller"))
            self.assertIsNotNone(getattr(page, "_sdk_runtime", None))

            page.generated_widgets["file_a"].setText(str(file_a))
            page.generated_widgets["col_a"].setText("key_a")
            page.generated_widgets["file_b"].setText(str(file_b))
            page.generated_widgets["col_b"].setText("key_b")

            run_button = page.generated_actions["run"]
            open_matches = page.generated_actions["open_matches"]
            open_only_a = page.generated_actions["open_only_a"]
            open_only_b = page.generated_actions["open_only_b"]
            output = page.generated_widgets["result.output"]
            summary = page.generated_widgets["result.summary"]

            self.assertFalse(open_matches.isEnabled())
            self.assertFalse(open_only_a.isEnabled())
            self.assertFalse(open_only_b.isEnabled())

            run_button.click()

            self.assertTrue(open_matches.isEnabled())
            self.assertTrue(open_only_a.isEnabled())
            self.assertTrue(open_only_b.isEnabled())
            self.assertIn("Generated 3 result file(s).", summary.text())
            self.assertIn("dataset_a.xlsx", output.toPlainText())
            self.assertIn("matches: 1 rows", output.toPlainText())
            self.assertIn(str(services.default_output_path()), output.toPlainText())

    def test_sdk_translation_helper_applies_direction(self) -> None:
        plugin = _SDKExamplePlugin()
        services = _DummyServices(language="ar")
        page = plugin.create_widget(services)

        self.assertEqual(page.layoutDirection(), Qt.LayoutDirection.RightToLeft)
        self.assertEqual(_pt(lambda key, default=None, **kwargs: default or key, "sdk.key", "Value"), "Value")
        self.assertEqual(apply_direction(page, services), Qt.LayoutDirection.RightToLeft)

    def test_sdk_translation_helper_updates_nested_form_direction_immediately(self) -> None:
        services = _DummyServices(language="ar")
        page = QWidget()
        outer = QVBoxLayout(page)
        card = QWidget(page)
        card.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
        form = QFormLayout(card)
        label = QLabel("Name", card)
        field = QLineEdit(card)
        form.addRow(label, field)
        outer.addWidget(card)

        page.resize(420, 160)
        page.show()
        self._app.processEvents()

        self.assertEqual(card.layoutDirection(), Qt.LayoutDirection.LeftToRight)

        apply_direction(page, services)
        self._app.processEvents()

        self.assertEqual(card.layoutDirection(), Qt.LayoutDirection.RightToLeft)
        self.assertGreater(label.geometry().x(), field.geometry().x())

    def test_image_tagger_uses_sdk_runtime_without_controller_class(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            image_path = Path(temp_dir) / "sample.png"
            Image.new("RGB", (96, 96), (220, 220, 220)).save(image_path)

            plugin = ImageTaggerPlugin()
            services = _DummyServices()
            page = plugin.create_widget(services)

            self.assertFalse(hasattr(page, "_controller"))
            self.assertIsNotNone(getattr(page, "_sdk_runtime", None))
            self.assertIn("files.__add", page.generated_actions)
            self.assertIn("files.__clear", page.generated_actions)

            name_input = page.generated_widgets["name"]
            date_mode = page.generated_widgets["date_mode"]
            custom_date = page.generated_widgets["custom_date"]
            file_list = page.generated_widgets["files"]
            preview = page.generated_widgets["preview"]

            file_list.files_dropped.emit([str(image_path)])
            self.assertEqual(file_list.count(), 1)
            self.assertEqual(file_list.currentRow(), 0)

            name_input.setText("Demo")
            self.assertIsNotNone(preview.pixmap())

            date_mode.setCurrentIndex(date_mode.findData("custom"))
            self.assertFalse(custom_date.isHidden())
            custom_date.setText("2026-04-06")
            self.assertIsNotNone(preview.pixmap())

    def test_image_transformer_uses_sdk_runtime_without_controller_class(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            image_path = Path(temp_dir) / "sample.png"
            Image.new("RGB", (120, 60), (90, 140, 220)).save(image_path)

            plugin = ImageTransformerPlugin()
            services = _DummyServices()
            page = plugin.create_widget(services)

            self.assertFalse(hasattr(page, "_controller"))
            self.assertIsNotNone(getattr(page, "_sdk_runtime", None))
            self.assertTrue(callable(getattr(page, "add_file_paths", None)))

            rotate_enabled = page.generated_widgets["rotate_enabled"]
            rotate_mode = page.generated_widgets["rotate_mode"]
            resize_enabled = page.generated_widgets["resize_enabled"]
            resize_width = page.generated_widgets["resize_width"]
            resize_height = page.generated_widgets["resize_height"]
            preview = page.generated_widgets["preview"]

            self.assertFalse(rotate_mode.isEnabled())
            rotate_enabled.setChecked(True)
            self.assertTrue(rotate_mode.isEnabled())

            page.add_file_paths([str(image_path)])
            self.assertIsNotNone(preview.pixmap())

            resize_enabled.setChecked(True)
            self.assertEqual(resize_width.text(), "60")
            self.assertEqual(resize_height.text(), "120")

            resize_width.setText("240")
            self.assertEqual(resize_height.text(), "480")

    def test_smart_exif_uses_sdk_table_details_runtime_without_controller_class(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            image_path = Path(temp_dir) / "sample.jpg"
            _write_exif_test_jpeg(
                image_path,
                description="before",
                artist="before-artist",
                copyright="before-copyright",
            )

            plugin = SmartExifEditorPlugin()
            services = _DummyServices()
            page = plugin.create_widget(services)

            self.assertFalse(hasattr(page, "_controller"))
            self.assertIsNotNone(getattr(page, "_sdk_runtime", None))
            self.assertTrue(callable(getattr(page, "add_file_paths", None)))
            self.assertIn("files_panel.splitter", page.generated_widgets)

            run_button = page.generated_actions["run"]
            undo_button = page.generated_actions["undo_run"]
            metadata_table = page.generated_widgets["metadata_table"]
            metadata_details = page.generated_widgets["metadata_details"]
            description_input = page.generated_widgets["description"]
            clear_artist = page.generated_widgets["clear_artist"]
            write_mode = page.generated_widgets["write_mode"]

            self.assertFalse(run_button.isEnabled())
            self.assertFalse(undo_button.isEnabled())

            page.add_file_paths([str(image_path)])

            self.assertTrue(run_button.isEnabled())
            self.assertEqual(metadata_table.rowCount(), 5)
            self.assertEqual(metadata_table.item(0, 1).text(), "before")
            self.assertIn(str(image_path), metadata_details.toPlainText())
            self.assertEqual(description_input.placeholderText(), "before")

            description_input.setText("after")
            clear_artist.setChecked(True)
            write_mode.setCurrentIndex(write_mode.findData("in_place"))

            self.assertEqual(metadata_table.item(0, 2).text(), "after")
            self.assertEqual(metadata_table.item(1, 2).text(), "(clear)")
            self.assertIn("Edit in place", metadata_details.toPlainText())

    def test_smart_background_remover_uses_sdk_runtime_without_controller_class(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            image_path = Path(temp_dir) / "sample.png"
            Image.new("RGB", (160, 120), (255, 255, 255)).save(image_path)

            plugin = SmartBackgroundRemoverPlugin()
            services = _DummyServices()
            page = plugin.create_widget(services)

            self.assertFalse(hasattr(page, "_controller"))
            self.assertIsNotNone(getattr(page, "_sdk_runtime", None))
            self.assertTrue(callable(getattr(page, "add_file_paths", None)))
            self.assertTrue(callable(getattr(page, "refresh_preview", None)))

            run_button = page.generated_actions["run"]
            custom_color = page.generated_widgets["custom_color"]
            background_mode = page.generated_widgets["background_mode"]
            preview = page.generated_widgets["preview"]

            self.assertFalse(run_button.isEnabled())
            self.assertTrue(custom_color.isHidden())

            page.add_file_paths([str(image_path)])
            page.refresh_preview(True)

            self.assertTrue(run_button.isEnabled())
            self.assertIsNotNone(preview.pixmap())

            background_mode.setCurrentIndex(background_mode.findData("custom"))
            self.assertFalse(custom_color.isHidden())
            custom_color.setText("#00ff00")
            self.assertIsNotNone(preview.pixmap())


if __name__ == "__main__":
    unittest.main()
