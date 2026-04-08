from __future__ import annotations

import platform
from datetime import datetime
from pathlib import Path

import psutil

from dngine.sdk import CommandSpec, DeclarativePlugin, bind_tr, safe_tr
from dngine.sdk.components import Action, InfoCard, MetricDonut, Row, Table, Text, TimerTask


def _fmt_optional(value: object, suffix: str) -> str:
    if value is None or value == "":
        return "--"
    return f"{value} {suffix}"


def _tr_bool(tr, value: bool) -> str:
    return tr("status.plugged", "plugged in") if value else tr("status.battery", "battery")


def collect_system_audit_payload(*, translate=None) -> dict[str, object]:
    root_disk_path = Path.home().anchor or "/"
    boot_time = datetime.fromtimestamp(psutil.boot_time())
    memory = psutil.virtual_memory()
    disk = psutil.disk_usage(root_disk_path)

    cpu_freq = psutil.cpu_freq()
    net_io = psutil.net_io_counters()
    battery = psutil.sensors_battery() if hasattr(psutil, "sensors_battery") else None
    return {
        "system": f"{platform.system()} {platform.release()}",
        "hostname": platform.node(),
        "architecture": platform.machine(),
        "processor": platform.processor() or platform.machine() or safe_tr(translate, "status.unknown", "Unknown"),
        "physical_cpus": psutil.cpu_count(logical=False) or 0,
        "logical_cpus": psutil.cpu_count(logical=True) or 0,
        "cpu_frequency_mhz": round(cpu_freq.current, 0) if cpu_freq is not None else None,
        "memory_total_gb": round(memory.total / (1024**3), 2),
        "memory_available_gb": round(memory.available / (1024**3), 2),
        "disk_total_gb": round(disk.total / (1024**3), 2),
        "disk_free_gb": round(disk.free / (1024**3), 2),
        "disk_used_pct": float(disk.percent),
        "python_version": platform.python_version(),
        "booted_at": boot_time.strftime("%Y-%m-%d %H:%M"),
        "uptime_hours": round((datetime.now() - boot_time).total_seconds() / 3600, 1),
        "network_sent_gb": round(net_io.bytes_sent / (1024**3), 2),
        "network_recv_gb": round(net_io.bytes_recv / (1024**3), 2),
        "battery_pct": None if battery is None else float(battery.percent),
        "battery_plugged": None if battery is None else bool(battery.power_plugged),
    }


def gather_system_audit(context, *, translate=None) -> dict[str, object]:
    translate = translate or getattr(context, "translate", None)
    context.log(safe_tr(translate, "log.start", "Collecting system overview details..."))
    context.progress(0.12)
    context.progress(0.42)
    payload = collect_system_audit_payload(translate=translate)
    context.progress(1.0)
    context.log(safe_tr(translate, "log.done", "System overview audit complete."))
    return payload


def _poll_live_metrics(runtime) -> None:
    tr = bind_tr(runtime.services, "sys_audit")
    palette = runtime.services.theme_manager.current_palette()
    
    cpu_pct = psutil.cpu_percent(interval=None)
    memory = psutil.virtual_memory()
    disk = psutil.disk_usage(Path.home().anchor or "/")

    runtime.set_field_value("cpu_donut", {
        "percent": cpu_pct,
        "caption": tr("cpu.caption", "{count} threads active", count=psutil.cpu_count(logical=True) or 0),
        "accent": palette.accent,
        "remainder": palette.border,
    })
    
    runtime.set_field_value("mem_donut", {
        "percent": memory.percent,
        "caption": tr("memory.caption", "{count} GB available", count=f"{memory.available / (1024**3):.1f}"),
        "accent": "#d66b57" if palette.mode == "dark" else "#b63f26",
        "remainder": palette.border,
    })
    
    runtime.set_field_value("disk_donut", {
        "percent": disk.percent,
        "caption": tr("disk.caption", "{count} GB free", count=f"{disk.free / (1024**3):.1f}"),
        "accent": "#7fbc41" if palette.mode == "dark" else "#2f7d4d",
        "remainder": palette.border,
    })
    
    runtime.set_field_value("timestamp", tr("timestamp", "Updated {time}", time=datetime.now().strftime("%H:%M:%S")))


def _apply_audit_result(runtime, payload: object) -> None:
    tr = bind_tr(runtime.services, "sys_audit")
    data = dict(payload) if isinstance(payload, dict) else {}
    
    runtime.set_field_value("profile_card", [
        (tr("card.hardware.host", "Host"), data.get("hostname", "--")),
        (tr("card.hardware.proc", "Processor"), data.get("processor", "--")),
        (tr("card.hardware.arch", "Architecture"), data.get("architecture", "--")),
        (
            tr("card.hardware.cores", "Cores"),
            tr(
                "card.hardware.cores_val",
                "{physical} physical / {logical} logical",
                physical=data.get("physical_cpus", 0),
                logical=data.get("logical_cpus", 0),
            ),
        ),
    ])

    runtime.set_field_value("runtime_card", [
        (tr("card.runtime.system", "System"), data.get("system", "--")),
        (tr("card.runtime.python", "Python"), data.get("python_version", "--")),
        (tr("card.runtime.booted", "Booted"), data.get("booted_at", "--")),
        (
            tr("card.runtime.uptime", "Uptime"),
            tr("card.runtime.hours", "{count} hours", count=data.get("uptime_hours", 0)),
        ),
    ])

    battery_pct = data.get("battery_pct")
    battery_text = "--"
    if battery_pct is not None:
        plugged = _tr_bool(tr, bool(data.get("battery_plugged")))
        battery_text = f"{battery_pct:.0f}% ({plugged})"
        
    runtime.set_field_value("health_card", [
        (tr("card.health.mem", "Memory total"), _fmt_optional(data.get("memory_total_gb"), tr("unit.gb", "GB"))),
        (tr("card.health.disk", "Disk total"), _fmt_optional(data.get("disk_total_gb"), tr("unit.gb", "GB"))),
        (tr("card.health.net", "Network sent"), _fmt_optional(data.get("network_sent_gb"), tr("unit.gb", "GB"))),
        (tr("card.health.battery", "Battery"), battery_text),
    ])

    rows = [
        (tr("row.hostname", "Hostname"), data.get("hostname", "--")),
        (tr("row.os", "Operating system"), data.get("system", "--")),
        (tr("row.arch", "Architecture"), data.get("architecture", "--")),
        (tr("row.proc", "Processor"), data.get("processor", "--")),
        (tr("row.cpu_freq", "CPU frequency"), _fmt_optional(data.get("cpu_frequency_mhz"), tr("unit.mhz", "MHz"))),
        (tr("row.phys_cpus", "Physical CPUs"), str(data.get("physical_cpus", "--"))),
        (tr("row.log_cpus", "Logical CPUs"), str(data.get("logical_cpus", "--"))),
        (tr("row.mem_total", "Memory total"), _fmt_optional(data.get("memory_total_gb"), tr("unit.gb", "GB"))),
        (tr("row.mem_avail", "Memory available"), _fmt_optional(data.get("memory_available_gb"), tr("unit.gb", "GB"))),
        (tr("row.disk_total", "Disk total"), _fmt_optional(data.get("disk_total_gb"), tr("unit.gb", "GB"))),
        (tr("row.disk_free", "Disk free"), _fmt_optional(data.get("disk_free_gb"), tr("unit.gb", "GB"))),
        (tr("row.disk_used", "Disk used"), _fmt_optional(data.get("disk_used_pct"), tr("unit.pct", "%"))),
        (tr("row.python", "Python"), data.get("python_version", "--")),
        (tr("row.booted", "Booted at"), data.get("booted_at", "--")),
        (tr("row.uptime", "Uptime"), tr("card.runtime.hours", "{count} hours", count=data.get("uptime_hours", 0))),
        (tr("row.net_sent", "Network sent"), _fmt_optional(data.get("network_sent_gb"), tr("unit.gb", "GB"))),
        (tr("row.net_recv", "Network received"), _fmt_optional(data.get("network_recv_gb"), tr("unit.gb", "GB"))),
    ]

    runtime.set_field_value("details_table", rows)
    _poll_live_metrics(runtime)


class SystemAuditPlugin(DeclarativePlugin):
    plugin_id = "sys_audit"
    name = "System Overview"
    description = "Monitor live CPU, memory, and disk activity alongside local hardware and runtime details."
    category = "Network & Security"
    preferred_icon = "computer"

    def declare_page(self, services):
        tr = bind_tr(services, self.plugin_id)
        return {
            "refresh": Action(
                label=tr("refresh", "Refresh overview"),
                worker=lambda context: gather_system_audit(context, translate=tr),
                payload_builder=lambda runtime: {},
                on_result=_apply_audit_result,
                auto_run=True,
            ),
            "timestamp": Text(
                label="",
                read_only=True,
                default=tr("timestamp", "Updated {time}", time="--"),
            ),
            "live_metrics_row": Row(
                fields={
                    "cpu_donut": MetricDonut(title=tr("cpu.title", "CPU")),
                    "mem_donut": MetricDonut(title=tr("memory.title", "Memory")),
                    "disk_donut": MetricDonut(title=tr("disk.title", "Disk")),
                }
            ),
            "cards_row": Row(
                fields={
                    "profile_card": InfoCard(title=tr("card.hardware.title", "Hardware Profile")),
                    "runtime_card": InfoCard(title=tr("card.runtime.title", "Runtime Details")),
                    "health_card": InfoCard(title=tr("card.health.title", "System Health")),
                }
            ),
            "details_table": Table(
                title=tr("table.heading", "System details"),
                headers=(tr("table.header.metric", "Metric"), tr("table.header.value", "Value")),
                stretch=1,
            ),
            "poller": TimerTask(interval_ms=2500, on_tick=_poll_live_metrics),
        }

    def declare_command_specs(self, services):
        tr = bind_tr(services, self.plugin_id)
        return (
            CommandSpec(
                command_id="tool.sys_audit.run",
                title=tr("command.run.title", "Run System Audit"),
                description=tr("command.run.description", "Collect local OS, CPU, memory, and disk details."),
                worker=lambda context: gather_system_audit(context, translate=tr),
            ),
        )
