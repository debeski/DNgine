from __future__ import annotations

from dngine.sdk.i18n import _pt


def run_task_spec(
    services,
    task_spec,
    payload: dict[str, object],
    *,
    translate=None,
    on_result=None,
    on_error=None,
    on_finished=None,
    on_progress=None,
) -> None:
    running_text = _pt(translate, task_spec.task_id, task_spec.running_text or "Running task...")

    def _worker(context):
        worker_payload = dict(payload)
        if task_spec.payload_builder is not None:
            worker_payload = dict(task_spec.payload_builder(worker_payload))
        return task_spec.worker(context, **worker_payload)

    def _handle_result(result):
        adapted = task_spec.result_adapter(result) if task_spec.result_adapter is not None else result
        if callable(on_result):
            on_result(adapted)

    services.run_task(
        _worker,
        status_text=running_text,
        on_result=_handle_result,
        on_error=on_error,
        on_finished=on_finished,
        on_progress=on_progress,
    )
