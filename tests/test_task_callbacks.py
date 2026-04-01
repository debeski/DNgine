from __future__ import annotations

import threading
import time
import unittest

from PySide6.QtCore import QCoreApplication, QObject, QThread, Slot

from dngine.core.services import _TaskCallbackBridge
from dngine.core.workers import Worker


class _DummyServices(QObject):
    def __init__(self):
        super().__init__()
        self.errors: list[object] = []

    @Slot(object)
    def _default_worker_error(self, payload: object) -> None:
        self.errors.append(payload)


class TaskCallbackBridgeTests(unittest.TestCase):
    def test_worker_callbacks_are_dispatched_back_to_main_thread(self) -> None:
        app = QCoreApplication.instance() or QCoreApplication([])
        services = _DummyServices()
        result_on_main: list[bool] = []
        finished_on_main: list[bool] = []
        finished_event = threading.Event()

        bridge = _TaskCallbackBridge(
            services,
            on_result=lambda _payload: result_on_main.append(QThread.currentThread() == app.thread()),
            on_finished=lambda: (finished_on_main.append(QThread.currentThread() == app.thread()), finished_event.set()),
        )

        worker = Worker(lambda _context: {"ok": True})
        worker._task_callback_bridge = bridge
        worker.signals.result.connect(bridge.handle_result)
        worker.signals.error.connect(bridge.handle_error)
        worker.signals.finished.connect(bridge.handle_finished)

        thread = threading.Thread(target=worker.run, daemon=True)
        thread.start()

        deadline = time.time() + 2.0
        while not finished_event.is_set() and time.time() < deadline:
            app.processEvents()
            time.sleep(0.01)

        thread.join(timeout=1.0)
        self.assertTrue(finished_event.is_set(), "Timed out waiting for worker callbacks.")
        self.assertEqual(result_on_main, [True])
        self.assertEqual(finished_on_main, [True])
        self.assertEqual(services.errors, [])


if __name__ == "__main__":
    unittest.main()
