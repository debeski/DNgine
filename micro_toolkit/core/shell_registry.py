from __future__ import annotations


DASHBOARD_PLUGIN_ID = "welcome_overview"
SYSTEM_TOOLBAR_PLUGIN_IDS = (DASHBOARD_PLUGIN_ID, "clip_manager", "workflow_studio", "about_center", "settings_center")
NON_SIDEBAR_PLUGIN_IDS = frozenset(SYSTEM_TOOLBAR_PLUGIN_IDS)
UNSCROLLED_PLUGIN_IDS = frozenset()
