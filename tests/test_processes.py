import os
import tempfile
import unittest
from pathlib import Path

import psutil

from desktop.processes import ProcessError, ProcessManager


class ProcessManagerTests(unittest.TestCase):
    def setUp(self):
        self.manager = ProcessManager()

    def clean_up_child(self, pid):
        child = self.manager._children.get(pid)
        if child is not None:
            if child.poll() is None:
                child.terminate()
            child.wait(timeout=3)
            self.manager.reap_finished()

    def test_launch_executable_and_terminate_owned_child(self):
        with tempfile.TemporaryDirectory() as directory:
            executable = Path(directory) / "пример с пробелом"
            executable.write_text("#!/bin/sh\nexec /bin/sleep 30\n")
            executable.chmod(0o700)
            pid = self.manager.launch(executable)
            self.addCleanup(self.clean_up_child, pid)
            entry = next(item for item in self.manager.list_processes() if item.pid == pid)
            self.assertTrue(entry.owned)
            self.assertIsNotNone(entry.name)
            self.manager.terminate(pid)
            self.assertFalse(psutil.pid_exists(pid))

    def test_current_process_cannot_be_terminated(self):
        self_entry = next(item for item in self.manager.list_processes() if item.pid == os.getpid())
        self.assertFalse(self_entry.owned)
        with self.assertRaisesRegex(ProcessError, "только процессы"):
            self.manager.terminate(os.getpid())

    def test_nonexistent_executable_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(ProcessError, "существующий исполняемый файл"):
                self.manager.launch(Path(directory) / "missing")

    def test_already_exited_child_reports_an_error(self):
        pid = self.manager.launch(Path("/usr/bin/true"))
        self.addCleanup(self.clean_up_child, pid)
        self.manager._children[pid].wait(timeout=3)
        with self.assertRaisesRegex(ProcessError, "уже завершился"):
            self.manager.terminate(pid)
        self.assertNotIn(pid, self.manager._children)
