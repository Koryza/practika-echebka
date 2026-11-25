import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from desktop.file_session import FileRequest, FileSession
from desktop.workspace_files import WorkspaceFiles


class FileSessionTests(unittest.TestCase):
    def test_navigation_reads_each_directory_once_and_refresh_reads_new_entries(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory).resolve()
            root = folder / "root"
            nested = root / "nested"
            nested.mkdir(parents=True)
            (nested / "first.txt").touch()
            session = FileSession(folder / "test.sqlite3")

            with patch.object(
                WorkspaceFiles,
                "list_directory",
                autospec=True,
                side_effect=WorkspaceFiles.list_directory,
            ) as reads:
                root_view, _ = session.execute(FileRequest("root", str(root)))
                nested_view, _ = session.execute(FileRequest("enter", "nested"))
                restored, _ = session.execute(FileRequest("up"))
                self.assertEqual([call.args[1] for call in reads.call_args_list], [(), ("nested",), ()])

            self.assertEqual([item.name for item in root_view.entries], ["nested"])
            self.assertEqual([item.name for item in nested_view.entries], ["first.txt"])
            self.assertEqual(restored.directory, ())
            (root / "new.txt").touch()
            refreshed, _ = session.execute(FileRequest("refresh"))
            self.assertEqual([item.name for item in refreshed.entries], ["nested", "new.txt"])
