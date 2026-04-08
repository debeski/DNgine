from __future__ import annotations

import importlib
import json
from pathlib import Path

from PySide6.QtGui import QGuiApplication

from dngine.core.clipboard_store import ClipboardStore
from dngine.core.command_runtime import HeadlessTaskContext, describe_command_result


def register_builtin_tool_commands(registry, services) -> None:
    available_specs = {
        spec.plugin_id: spec
        for spec in services.plugin_manager.discover_plugins(include_disabled=True)
    }
    available_plugin_ids = set(available_specs)

    def register_task_command(
        command_id: str,
        title: str,
        description: str,
        plugin_id: str,
        module_path: str,
        function_name: str,
        *,
        argument_adapter=None,
        result_adapter=None,
    ) -> None:
        if plugin_id not in available_plugin_ids:
            return

        def handler(**kwargs):
            module = importlib.import_module(module_path)
            task_fn = getattr(module, function_name)
            payload = dict(kwargs)
            if argument_adapter is not None:
                payload = argument_adapter(services, payload)
            context = HeadlessTaskContext(services, command_id=command_id)
            try:
                result = task_fn(context, **payload)
            except Exception as exc:
                services.record_run(plugin_id, "ERROR", str(exc)[:500])
                raise
            if result_adapter is not None:
                result = result_adapter(result)
            services.record_run(plugin_id, "SUCCESS", describe_command_result(result))
            return result

        registry.register(command_id, title, description, handler)

    output_dir_str = lambda svc: str(svc.default_output_path())
    output_dir_path = lambda svc: svc.default_output_path()

    def chart_builder_payload(_svc, payload):
        config = dict(payload.get("config", {}))
        if "group_cols" in payload and "group_columns" not in config:
            config["group_columns"] = payload.get("group_cols", "")
            config.setdefault("operation", "summarize")
        if "aggregate" in payload and "aggregate" not in config:
            config["aggregate"] = payload.get("aggregate", "count")
        if "chart_type" in payload and "chart_type" not in config:
            config["chart_type"] = payload.get("chart_type", "none")
        primary_file = payload.get("primary_file") or payload.get("file_path")
        return {
            "primary_file": primary_file,
            "config": config,
        }

    register_task_command(
        "tool.chart_builder.run",
        "Run Chart Builder",
        "Shape workbook data, build charts, and return a result table.",
        "chart_builder",
        "fp_plugins.data_analysis.plugins.chart_builder",
        "run_chart_builder_task",
        argument_adapter=chart_builder_payload,
    )
    register_task_command(
        "tool.quick_analytics.run",
        "Run Quick Analytics",
        "Backward-compatible alias for Chart Builder.",
        "chart_builder",
        "fp_plugins.data_analysis.plugins.chart_builder",
        "run_chart_builder_task",
        argument_adapter=chart_builder_payload,
    )
    register_task_command(
        "tool.cred_scanner.scan",
        "Run Code Exploit Scanner",
        "Scan a folder for exposed secrets, risky files, and exploit indicators.",
        "cred_scanner",
        "fp_plugins.web_dev.plugins.credential_scanner",
        "run_credential_scan",
    )
    register_task_command(
        "tool.net_scan.run",
        "Run Network Scan",
        "Scan a host across the requested TCP ports.",
        "net_scan",
        "fp_plugins.network_security.plugins.network_scanner",
        "run_network_scan",
        argument_adapter=lambda svc, payload: {
            **payload,
            "timeout_seconds": float(payload.get("timeout_seconds", 0.3)),
            "output_dir": Path(payload["output_dir"]) if payload.get("output_dir") else output_dir_path(svc),
        },
    )
    register_task_command(
        "tool.shredder.run",
        "Shred File",
        "Securely overwrite and delete a file.",
        "privacy_shred",
        "dngine.plugins.core_tools.privacy_shredder",
        "secure_shred_task",
        argument_adapter=lambda svc, payload: {
            **payload,
            "passes": int(payload.get("passes", 3)),
        },
    )
    register_task_command(
        "tool.folder_mapper.run",
        "Run Folder Mapper",
        "Map file metadata from a folder tree into an Excel workbook.",
        "folder_mapper",
        "fp_plugins.data_analysis.plugins.folder_mapper",
        "map_folder_contents_task",
        argument_adapter=lambda svc, payload: {
            **payload,
            "output_dir": payload.get("output_dir", output_dir_str(svc)),
        },
    )
    register_task_command(
        "tool.data_link_auditor.run",
        "Run Data-Link Auditor",
        "Audit workbook-linked filenames against one or more source folders.",
        "data_link_auditor",
        "fp_plugins.data_analysis.plugins.data_link_auditor",
        "audit_data_links_task",
        argument_adapter=lambda svc, payload: {
            **payload,
            "source_folders": list(payload.get("source_folders", [])),
            "column_names": list(payload.get("column_names", [])),
            "dest_folder": payload.get("dest_folder"),
            "split_folders": bool(payload.get("split_folders", False)),
            "output_dir": payload.get("output_dir", output_dir_str(svc)),
        },
    )
    register_task_command(
        "tool.sequence_auditor.run",
        "Run Sequence Auditor",
        "Audit a folder listing or workbook column for sequence gaps.",
        "sequence_auditor",
        "fp_plugins.data_analysis.plugins.sequence_auditor",
        "sequence_auditor_task",
        argument_adapter=lambda svc, payload: {
            **payload,
            "output_dir": payload.get("output_dir", output_dir_str(svc)),
        },
    )
    register_task_command(
        "tool.deep_scan_auditor.excel",
        "Run Deep-Scan Auditor (Excel)",
        "Audit workbook rows for duplicate combinations.",
        "deep_scan_auditor",
        "fp_plugins.data_analysis.plugins.deep_scan_auditor",
        "audit_excel_duplicates_task",
        argument_adapter=lambda svc, payload: {
            **payload,
            "output_dir": payload.get("output_dir", output_dir_str(svc)),
        },
    )
    register_task_command(
        "tool.deep_scan_auditor.folder",
        "Run Deep-Scan Auditor (Folder)",
        "Audit folder trees for duplicate files.",
        "deep_scan_auditor",
        "fp_plugins.data_analysis.plugins.deep_scan_auditor",
        "audit_folder_duplicates_task",
        argument_adapter=lambda svc, payload: {
            **payload,
            "criteria": list(payload.get("criteria", [])),
            "output_dir": payload.get("output_dir", output_dir_str(svc)),
        },
    )
    register_task_command(
        "tool.batch_renamer.run",
        "Batch Rename Files",
        "Rename files in bulk using text or regex replacement.",
        "batch_renamer",
        "fp_plugins.files_storage.plugins.batch_renamer",
        "batch_rename_task",
        argument_adapter=lambda svc, payload: {
            **payload,
            "replace_str": payload.get("replace_str", ""),
            "use_regex": bool(payload.get("use_regex", False)),
        },
    )
    register_task_command(
        "tool.smart_org.organize",
        "Organize Files",
        "Organize root-level files by extension or date.",
        "smart_org",
        "fp_plugins.files_storage.plugins.smart_organizer",
        "organize_files_task",
    )
    register_task_command(
        "tool.smart_org.undo",
        "Undo Organization",
        "Undo the last saved smart organization run.",
        "smart_org",
        "fp_plugins.files_storage.plugins.smart_organizer",
        "undo_organization_task",
    )
    register_task_command(
        "tool.deep_searcher.run",
        "Run Deep Search",
        "Search file contents under a folder tree.",
        "deep_searcher",
        "fp_plugins.files_storage.plugins.deep_searcher",
        "run_deep_search_task",
        argument_adapter=lambda svc, payload: {
            **payload,
            "use_regex": bool(payload.get("use_regex", False)),
        },
    )
    register_task_command(
        "tool.usage_analyzer.run",
        "Analyze Usage",
        "Summarize top-level file and folder sizes.",
        "usage_analyzer",
        "fp_plugins.files_storage.plugins.usage_analyzer",
        "analyze_usage_task",
    )

    for spec in available_specs.values():
        if spec.contract_status not in {"sdk_valid", "advanced_contract"}:
            continue
        try:
            plugin = services.plugin_manager.load_plugin(spec.plugin_id)
            plugin.register_commands(registry, services)
        except Exception:
            continue

    def clipboard_list(search: str = "", content_type: str = "ALL", label: str = "", limit: int = 50):
        store = ClipboardStore(services.database_path)
        return store.list_entries(
            search=search,
            content_type=content_type or "ALL",
            label=label,
        )[: max(1, int(limit))]

    def clipboard_copy(entry_id: int | None = None, search: str = ""):
        store = ClipboardStore(services.database_path)
        entries = store.list_entries(search=search)
        target = None
        if entry_id is not None:
            for entry in entries:
                if entry.entry_id == int(entry_id):
                    target = entry
                    break
        elif entries:
            target = entries[0]
        if target is None:
            raise ValueError("No clipboard entry matched the requested selection.")
        clipboard = QGuiApplication.clipboard() if QGuiApplication.instance() is not None else None
        copied = False
        if clipboard is not None:
            clipboard.setText(target.content)
            copied = True
        services.record_run("clip_snip", "SUCCESS", f"Clipboard entry {target.entry_id} copied")
        return {
            "entry_id": target.entry_id,
            "content_type": target.content_type,
            "label": target.label,
            "content": target.content,
            "copied_to_system_clipboard": copied,
        }

    def clipboard_clear():
        store = ClipboardStore(services.database_path)
        count = len(store.list_entries())
        store.clear_entries()
        services.record_run("clip_snip", "SUCCESS", f"Cleared {count} clipboard entrie(s)")
        return {"cleared": count}

    registry.register(
        "tool.clipboard.list",
        "List Clipboard Entries",
        "Return recent clipboard history entries from the persistent store.",
        clipboard_list,
    )
    registry.register(
        "tool.clipboard.copy",
        "Copy Clipboard Entry",
        "Copy a clipboard entry by id, or the newest match when no id is provided.",
        clipboard_copy,
    )
    registry.register(
        "tool.clipboard.clear",
        "Clear Clipboard History",
        "Delete all stored clipboard history entries.",
        clipboard_clear,
    )
