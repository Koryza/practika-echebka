import os
import stat
import tempfile
import unittest
from pathlib import Path

from desktop.workspace_files import WorkspaceError, WorkspaceFiles


class WorkspaceFilesTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.base = Path(temp.name).resolve()
        self.root = self.base / "root"
        self.root.mkdir()
        self.workspace = WorkspaceFiles(self.root)

    def test_create_copy_move_rename_and_delete(self):
        self.workspace.create((), "docs", folder=True)
        self.workspace.create((), "note.txt", folder=False)
        (self.root / "note.txt").write_text("Учебный файл")
        self.workspace.copy((), "note.txt", ("docs",))
        self.assertEqual((self.root / "docs" / "note.txt").read_text(), "Учебный файл")
        self.workspace.move((), "note.txt", (), "draft.txt")
        self.workspace.move((), "draft.txt", ("docs",), "draft.txt")
        self.assertEqual(
            [item.name for item in self.workspace.list_directory(("docs",))],
            ["draft.txt", "note.txt"],
        )
        self.workspace.delete((), "docs")
        self.assertEqual(self.workspace.list_directory(()), [])

    def test_existing_entries_are_not_overwritten(self):
        target = self.root / "target.txt"
        target.write_text("Сохранить")
        (self.root / "source.txt").write_text("Источник")
        with self.assertRaises(FileExistsError):
            self.workspace.move((), "source.txt", (), "target.txt")
        with self.assertRaises(FileExistsError):
            self.workspace.create((), "target.txt", folder=False)
        self.assertEqual(target.read_text(), "Сохранить")
        self.assertEqual((self.root / "source.txt").read_text(), "Источник")

    def test_external_paths_and_symlinks_are_blocked(self):
        outside = self.base / "outside"
        outside.mkdir()
        target = outside / "untouched.txt"
        target.write_text("Оставить")
        (self.root / "jump").symlink_to(outside, target_is_directory=True)
        (self.root / "reference").symlink_to(target)
        for destination in (("..", "outside"), ("jump",)):
            with self.subTest(destination=destination), self.assertRaises((OSError, WorkspaceError)):
                self.workspace.create(destination, "other.txt", folder=False)
        with self.assertRaises(WorkspaceError):
            self.workspace.delete((), "reference")
        with self.assertRaises(OSError):
            self.workspace.toggle_read_only((), "reference")
        self.assertEqual(list(outside.iterdir()), [target])
        self.assertEqual(target.read_text(), "Оставить")

    def test_directory_copy_cleans_up_after_rejected_child(self):
        source = self.root / "source"
        source.mkdir()
        (source / "normal").write_text("Текст")
        (source / "reference").symlink_to(self.base)
        destination = self.root / "destination"
        destination.mkdir()
        with self.assertRaises(WorkspaceError):
            self.workspace.copy((), "source", ("destination",))
        self.assertEqual(list(destination.iterdir()), [])
        self.assertTrue((source / "reference").is_symlink())
        with self.assertRaises(WorkspaceError):
            self.workspace.copy((), "source", ("source",))

    def test_read_only_attribute_and_hard_link_protection(self):
        file = self.root / "one.txt"
        file.touch()
        self.workspace.toggle_read_only((), file.name)
        self.assertTrue(self.workspace.list_directory(())[0].read_only)
        self.workspace.toggle_read_only((), file.name)
        self.assertTrue(file.stat().st_mode & stat.S_IWUSR)
        copy = self.base / "hard-link"
        os.link(file, copy)
        with self.assertRaises(WorkspaceError):
            self.workspace.toggle_read_only((), file.name)
        self.assertTrue(copy.stat().st_mode & stat.S_IWUSR)
