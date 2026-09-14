"""Tests for the standalone structured-artifact rerun helper."""

import tempfile
import unittest
from pathlib import Path

from persistence.paths import RunPaths
from rerun import collect_selection, load_or_create_selection, write_summary


class RerunTests(unittest.TestCase):
    """Verify deterministic source discovery without launching Chrome."""

    def _source_run(self, root: Path) -> Path:
        """Create minimal structured source journals for selection tests."""
        not_found = root / "workers/browser-01/checkpoints/not_found/not_found_batch_0001.jsonl"
        errors = root / "workers/browser-02/metrics/errors.jsonl"
        not_found.parent.mkdir(parents=True)
        errors.parent.mkdir(parents=True)
        not_found.write_text(
            '{"id": 10, "status": 404}\n'
            '{"id": 20, "status": 410}\n'
            '{"id": 10, "status": 404}\n'
            '{"id": 99, "status": 500}\n',
            encoding="utf-8",
        )
        errors.write_text(
            '{"id": 20, "classification": "error"}\n'
            '{"id": 30, "classification": "error"}\n'
            '{"id": 30, "classification": "error"}\n'
            '{"id": 40, "classification": "waf"}\n',
            encoding="utf-8",
        )
        return root

    def test_collects_unique_structured_ids_in_deterministic_order(self) -> None:
        """Not-found has priority and logs/WAF records are excluded."""
        with tempfile.TemporaryDirectory() as directory:
            source = self._source_run(Path(directory) / "source")
            before = {
                path.relative_to(source): path.read_bytes()
                for path in source.rglob("*.jsonl")
            }
            selection = collect_selection(source)

            self.assertEqual(selection.ids, [10, 20, 30])
            self.assertEqual(selection.not_found_count, 2)
            self.assertEqual(selection.error_count, 2)
            self.assertEqual(selection.duplicates_removed, 3)
            after = {
                path.relative_to(source): path.read_bytes()
                for path in source.rglob("*.jsonl")
            }
            self.assertEqual(after, before)

    def test_resume_reuses_fixed_selection_and_summary_uses_checkpoints(self) -> None:
        """Rerun metadata survives source changes and output is checkpoint-derived."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = self._source_run(root / "source")
            rerun_paths = RunPaths(root / "rerun")
            rerun_paths.root.mkdir()
            selection = load_or_create_selection(source, rerun_paths.root)
            errors = source / "workers/browser-02/metrics/errors.jsonl"
            errors.write_text(errors.read_text(encoding="utf-8") + '{"id": 50, "classification": "error"}\n', encoding="utf-8")
            self.assertEqual(load_or_create_selection(source, rerun_paths.root), selection)

            success = rerun_paths.root / "workers/browser-01/checkpoints/success/success_batch_0001.jsonl"
            not_found = rerun_paths.root / "workers/browser-02/checkpoints/not_found/not_found_batch_0001.jsonl"
            success.parent.mkdir(parents=True)
            not_found.parent.mkdir(parents=True)
            success.write_text('{"id": 10}\n', encoding="utf-8")
            not_found.write_text('{"id": 20, "status": 404}\n', encoding="utf-8")
            rerun_paths.summary.write_text('{"browser_error_count": 1, "waf_count": 0}\n', encoding="utf-8")

            summary = write_summary(rerun_paths.root, source, selection)

            self.assertEqual(summary["recovered_successes"], 1)
            self.assertEqual(summary["remaining_not_found"], 1)
            self.assertEqual(summary["remaining_unfinished_or_error"], 1)
            self.assertTrue((rerun_paths.root / "rerun_summary.json").exists())
