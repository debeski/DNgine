from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from dngine.core.command_runtime import HeadlessTaskContext, describe_command_result


@dataclass(frozen=True)
class CommandSpec:
    command_id: str
    title: str
    description: str
    worker: Callable
    input_adapter: Callable[[dict[str, object]], dict[str, object]] | None = None
    result_adapter: Callable[[object], object] | None = None
    aliases: tuple[str, ...] = ()
    workflow_exposed: bool = True


def register_command_specs(registry, services, plugin_id: str, specs: list[CommandSpec] | tuple[CommandSpec, ...]) -> None:
    for spec in specs:
        def _handler(_spec=spec, **kwargs):
            payload = dict(kwargs)
            if _spec.input_adapter is not None:
                payload = dict(_spec.input_adapter(payload))
            context = HeadlessTaskContext(services, command_id=_spec.command_id)
            try:
                result = _spec.worker(context, **payload)
            except Exception as exc:
                services.record_run(plugin_id, "ERROR", str(exc)[:500])
                raise
            if _spec.result_adapter is not None:
                result = _spec.result_adapter(result)
            services.record_run(plugin_id, "SUCCESS", describe_command_result(result))
            return result

        registry.register(spec.command_id, spec.title, spec.description, _handler)
        for alias in spec.aliases:
            registry.register(alias, spec.title, spec.description, _handler)
