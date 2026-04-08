from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class PackageGroup:
    package_id: str
    label: str
    label_ar: str
    plugin_ids: tuple[str, ...]


@dataclass(frozen=True)
class PackageSourcePlugin:
    plugin_id: str
    entry: str
    files: tuple[str, ...]
    dependency_manifest: str = ""


@dataclass(frozen=True)
class FirstPartyPackageSource:
    package_id: str
    display_name: str
    display_name_ar: str
    signer: str
    package_version: str
    plugins: tuple[PackageSourcePlugin, ...]
    category_plugins: tuple[str, ...]


PLUGIN_LABELS: dict[str, dict[str, str]] = {
    "img_trans": {"en": "Image Transformer", "ar": "تحويل الصور"},
    "smart_bg": {"en": "SMART Background Remover", "ar": "إزالة الخلفية الذكية"},
    "smart_exif": {"en": "SMART EXIF Editor", "ar": "محرر EXIF الذكي"},
}


PACKAGE_GROUPS: tuple[PackageGroup, ...] = (
    PackageGroup(
        package_id="files_storage",
        label="Files & Storage",
        label_ar="الملفات والتخزين",
        plugin_ids=("batch_renamer", "deep_searcher", "hash_checker", "smart_org", "usage_analyzer"),
    ),
    PackageGroup(
        package_id="office_docs",
        label="Office & Docs",
        label_ar="المكتب والمستندات",
        plugin_ids=("doc_bridge", "pdf_suite", "cross_joiner", "cleaner"),
    ),
    PackageGroup(
        package_id="network_security",
        label="Network & Security",
        label_ar="الشبكات والأمان",
        plugin_ids=("net_scan", "wifi_profiles", "privacy_shred", "sys_audit"),
    ),
    PackageGroup(
        package_id="web_dev",
        label="Web Dev",
        label_ar="تطوير الويب",
        plugin_ids=("code_factory", "cred_scanner", "web_scraper"),
    ),
    PackageGroup(
        package_id="media_images",
        label="Media & Images",
        label_ar="الوسائط والصور",
        plugin_ids=("tagger", "color_picker", "img_trans", "smart_bg", "smart_exif"),
    ),
    PackageGroup(
        package_id="data_analysis",
        label="Data & Analysis",
        label_ar="البيانات والتحليل",
        plugin_ids=("chart_builder", "data_link_auditor", "deep_scan_auditor", "folder_mapper", "sequence_auditor"),
    ),
)

CORE_BUILTIN_PLUGIN_IDS = frozenset(
    {
        "hash_checker",
        "doc_bridge",
        "pdf_suite",
        "tagger",
        "privacy_shred",
        "sys_audit",
        "color_picker",
    }
)

PLUGIN_TO_GROUP = {
    plugin_id: group
    for group in PACKAGE_GROUPS
    for plugin_id in group.plugin_ids
}

OPTIONAL_FIRST_PARTY_PLUGIN_IDS = frozenset(
    plugin_id
    for plugin_id in PLUGIN_TO_GROUP
    if plugin_id not in CORE_BUILTIN_PLUGIN_IDS
)


def package_group_for_plugin(plugin_id: str) -> PackageGroup | None:
    return PLUGIN_TO_GROUP.get(str(plugin_id or "").strip())


def package_id_for_plugin(plugin_id: str) -> str | None:
    group = package_group_for_plugin(plugin_id)
    if group is None:
        return None
    return group.package_id


def is_optional_first_party_plugin(plugin_id: str) -> bool:
    return str(plugin_id or "").strip() in OPTIONAL_FIRST_PARTY_PLUGIN_IDS


def category_label_for_plugin(plugin_id: str, language: str = "en") -> str | None:
    group = package_group_for_plugin(plugin_id)
    if group is None:
        return None
    return group.label_ar if str(language or "").lower().startswith("ar") else group.label


def fallback_plugin_label(plugin_id: str, language: str = "en") -> str | None:
    bundle = PLUGIN_LABELS.get(str(plugin_id or "").strip())
    if not bundle:
        return None
    if str(language or "").lower().startswith("ar"):
        return bundle.get("ar") or bundle.get("en")
    return bundle.get("en") or bundle.get("ar")


def category_bundles_for_plugin(plugin_id: str) -> dict[str, dict[str, str]]:
    group = package_group_for_plugin(plugin_id)
    if group is None:
        return {}
    return {
        "en": {"plugin.category": group.label},
        "ar": {"plugin.category": group.label_ar},
    }


def package_source_root(project_root: Path) -> Path:
    return Path(project_root) / "fp_plugins"


def catalog_entry_from_source(source: FirstPartyPackageSource, *, download_url: str = "") -> dict[str, object]:
    group = next((item for item in PACKAGE_GROUPS if item.package_id == source.package_id), None)
    plugin_ids = [plugin.plugin_id for plugin in source.plugins]
    return {
        "package_id": source.package_id,
        "display_name": source.display_name,
        "display_name_ar": source.display_name_ar,
        "category_label": group.label if group is not None else source.display_name,
        "category_label_ar": group.label_ar if group is not None else source.display_name_ar,
        "package_version": source.package_version,
        "signer": source.signer,
        "plugin_ids": plugin_ids,
        "group_plugin_ids": list(source.category_plugins),
        "download_url": download_url,
    }


def load_package_source_manifest(path: Path) -> FirstPartyPackageSource:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    plugins: list[PackageSourcePlugin] = []
    for entry in payload.get("plugins", []):
        if not isinstance(entry, dict):
            continue
        plugin_id = str(entry.get("plugin_id", "")).strip()
        entry_path = str(entry.get("entry", "")).replace("\\", "/").strip()
        files = tuple(
            str(item).replace("\\", "/").strip()
            for item in entry.get("files", [])
            if str(item).strip()
        )
        dependency_manifest = str(entry.get("dependency_manifest", "")).replace("\\", "/").strip()
        if plugin_id and entry_path and files:
            plugins.append(
                PackageSourcePlugin(
                    plugin_id=plugin_id,
                    entry=entry_path,
                    files=files,
                    dependency_manifest=dependency_manifest,
                )
            )
    category_plugins = tuple(
        str(item).strip()
        for item in payload.get("category_plugins", [])
        if str(item).strip()
    )
    if not category_plugins:
        category_plugins = tuple(plugin.plugin_id for plugin in plugins)
    return FirstPartyPackageSource(
        package_id=str(payload.get("package_id", "")).strip(),
        display_name=str(payload.get("display_name", "")).strip(),
        display_name_ar=str(payload.get("display_name_ar", "")).strip(),
        signer=str(payload.get("signer", "")).strip(),
        package_version=str(payload.get("package_version", "")).strip(),
        plugins=tuple(plugins),
        category_plugins=category_plugins,
    )


def discover_package_source_manifests(root: Path) -> list[FirstPartyPackageSource]:
    sources: list[FirstPartyPackageSource] = []
    for manifest_path in sorted(Path(root).glob("*/package.json")):
        source = load_package_source_manifest(manifest_path)
        if source.package_id:
            sources.append(source)
    return sources
