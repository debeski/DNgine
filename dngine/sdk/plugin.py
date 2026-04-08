from __future__ import annotations

from PySide6.QtWidgets import QWidget

from dngine.core.plugin_api import QtPlugin
from dngine.sdk.commands import register_command_specs
from dngine.sdk.declarative import compile_page_dict
from dngine.sdk.i18n import apply_direction, bind_tr
from dngine.sdk.page import render_page_spec, wire_page_runtime


class StandardPlugin(QtPlugin):
    contract_status = "sdk_valid"

    def declare_page_spec(self, services):
        raise NotImplementedError

    def declare_command_specs(self, services):
        return ()

    def create_widget(self, services) -> QWidget:
        page_spec = self.declare_page_spec(services)
        page = render_page_spec(services, self.plugin_id, page_spec)
        wire_page_runtime(self, page, services, page_spec)
        self.configure_page(page, services)
        return page

    def configure_page(self, page, services) -> None:
        apply_direction(page, services)

    def register_commands(self, registry, services) -> None:
        register_command_specs(registry, services, self.plugin_id, list(self.declare_command_specs(services) or ()))


class DeclarativePlugin(StandardPlugin):
    page: dict[str, object] | None = None

    def declare_page(self, services) -> dict[str, object]:
        if self.page is None:
            raise NotImplementedError("DeclarativePlugin requires page or declare_page().")
        return dict(self.page)

    def declare_page_spec(self, services):
        tr = bind_tr(services, self.plugin_id)
        return compile_page_dict(
            page=self.declare_page(services),
            title=tr("title", self.name),
            description=tr("description", self.description),
        )


class TaskPlugin(StandardPlugin):
    pass


class BatchFilePlugin(TaskPlugin):
    pass


class TableToolPlugin(TaskPlugin):
    pass


class HeadlessOnlyPlugin(StandardPlugin):
    def declare_page_spec(self, services):
        tr = bind_tr(services, self.plugin_id)
        from dngine.sdk.specs import PageSpec, ResultSpec, SectionSpec

        return PageSpec(
            archetype="utility",
            title=tr("title", self.name),
            description=tr("description", self.description or "This plugin exposes command-only functionality."),
            sections=(
                SectionSpec(
                    section_id="headless.summary",
                    kind="summary_output_pane",
                    description=tr("headless.info", "This plugin is intended for workflows and CLI use."),
                    stretch=1,
                ),
            ),
            result_spec=ResultSpec(
                summary_placeholder=tr("headless.summary", "Headless command surface ready."),
                output_placeholder=tr("headless.output", "Command results appear through workflows and CLI."),
            ),
        )


class AdvancedPagePlugin(StandardPlugin):
    contract_status = "advanced_contract"

    def declare_page_spec(self, services):
        raise NotImplementedError("AdvancedPagePlugin uses build_advanced_widget().")

    def build_advanced_widget(self, services) -> QWidget:
        raise NotImplementedError

    def create_widget(self, services) -> QWidget:
        widget = self.build_advanced_widget(services)
        apply_direction(widget, services)
        return widget
