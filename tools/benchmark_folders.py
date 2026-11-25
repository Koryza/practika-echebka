"""Измеряет время перехода в подпапку и обратно в файловой вкладке."""

import json
from pathlib import Path
from statistics import median
from tempfile import TemporaryDirectory
from time import perf_counter_ns
from unittest.mock import patch

from desktop.file_session import FileRequest, FileSession
from desktop.workspace_files import WorkspaceFiles

FILES_PER_FOLDER = 2500
WARMUP_ROUNDS = 4
TIMED_ROUNDS = 21


def main() -> None:
    with TemporaryDirectory(prefix="system-monitor-benchmark-") as directory:
        fixture = Path(directory).resolve()
        root = fixture / "root"
        nested = root / "nested"
        nested.mkdir(parents=True)
        for folder in (root, nested):
            for index in range(FILES_PER_FOLDER):
                (folder / f"file-{index:04d}.txt").touch()

        session = FileSession(fixture / "benchmark.sqlite3")
        view, message = session.execute(FileRequest("root", str(root)))
        assert view is not None and len(view.entries) == FILES_PER_FOLDER + 1, message

        def round_trip() -> None:
            inner, message = session.execute(FileRequest("enter", "nested"))
            assert inner is not None and len(inner.entries) == FILES_PER_FOLDER, message
            outer, message = session.execute(FileRequest("up"))
            assert outer is not None and len(outer.entries) == FILES_PER_FOLDER + 1, message

        for _ in range(WARMUP_ROUNDS):
            round_trip()

        timings = []
        for _ in range(TIMED_ROUNDS):
            start = perf_counter_ns()
            round_trip()
            timings.append((perf_counter_ns() - start) / 1_000_000)

        with patch.object(
            WorkspaceFiles,
            "list_directory",
            autospec=True,
            side_effect=WorkspaceFiles.list_directory,
        ) as scans:
            round_trip()
        result = {
            "files_per_folder": FILES_PER_FOLDER,
            "warmups": WARMUP_ROUNDS,
            "runs": TIMED_ROUNDS,
            "median_ms": round(median(timings), 3),
            "scans_per_round_trip": scans.call_count,
            "samples_ms": [round(value, 3) for value in timings],
        }
        print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
