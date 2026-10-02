import tempfile
import unittest
from pathlib import Path

from fitness_analyzer.exceptions import DataFileError
from fitness_analyzer.loader import SessionLoader, load_participants

from .helpers import (
    PROFILE_HEADER,
    write_lines,
    write_profiles,
    write_sessions,
)


VALID_ROWS = [
    "FIT-2026-001,P001,0,70,1.2,32.4,0.1,0.95",
    "FIT-2026-001,P001,1,72,1.2,32.4,0.1,0.95",
    "FIT-2026-002,P002,0,90,1.6,32.9,0.4,0.95",
]


class LoaderTestCase(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.folder = Path(self._tmp.name)
        self.participants, _ = load_participants(write_profiles(self.folder))

    def tearDown(self):
        self._tmp.cleanup()

    def load(self, *paths):
        return SessionLoader(self.participants).load_files(paths)


class TestLoadParticipants(LoaderTestCase):

    def test_valid_profiles(self):
        self.assertEqual(sorted(self.participants), ["P001", "P002"])
        self.assertEqual(self.participants["P002"].baseline_heart_rate, 74.0)

    def test_missing_profile_file_raises(self):
        with self.assertRaises(FileNotFoundError):
            load_participants(self.folder / "absent.csv")

    def test_bad_and_duplicate_profiles_are_rejected(self):
        path = write_profiles(self.folder, [
            "P001,Test Person,70,1.2,32.4",
            "P001,Copy,71,1.2,32.4",
            "P003,Bad,fast,1.2,32.4",
        ])
        participants, rejected = load_participants(path)
        self.assertEqual(list(participants), ["P001"])
        self.assertEqual([record.line for record in rejected], [3, 4])

    def test_header_without_required_column_raises(self):
        path = write_lines(self.folder, "people.csv", ["participant_id,name", "P001,A"])
        with self.assertRaises(DataFileError):
            load_participants(path)


class TestLoadSessions(LoaderTestCase):

    def test_valid_rows_are_grouped_by_session(self):
        loader = self.load(write_sessions(self.folder, "s.csv", VALID_ROWS))
        sessions = loader.sessions()
        self.assertEqual([s.session_id for s in sessions], ["FIT-2026-001", "FIT-2026-002"])
        self.assertEqual(sessions[0].total_count, 2)
        self.assertIs(sessions[1].participant, self.participants["P002"])
        self.assertEqual(loader.accepted_rows, 3)
        self.assertEqual(loader.rejected, [])

    def test_invalid_rows_are_recorded_and_loading_continues(self):
        path = write_sessions(self.folder, "s.csv", [
            "FIT-2026-001,P001,0,70,1.2,32.4,0.1,0.95",
            "FIT-2026-001,P001,1,fast,1.2,32.4,0.1,0.95",
            "FIT-2026-001,P999,2,70,1.2,32.4,0.1,0.95",
            "FIT-2026-001,P001,3,70,1.2,32.4,0.1",
            "FIT-2026-001,P001,4,70,1.2,32.4,0.1,0.95",
        ])
        loader = self.load(path)
        self.assertEqual(loader.accepted_rows, 2)
        rejected = [(r.source.name, r.line, r.problems[0][0]) for r in loader.rejected]
        self.assertEqual(rejected, [
            ("s.csv", 3, "heart_rate"),
            ("s.csv", 4, "participant_id"),
            ("s.csv", 5, "row"),
        ])
        self.assertIn("7 columns", loader.rejected[2].problems[0][1])

    def test_missing_file_is_skipped_and_next_file_is_read(self):
        missing = self.folder / "absent.csv"
        present = write_sessions(self.folder, "s.csv", VALID_ROWS)
        loader = self.load(missing, present)
        self.assertEqual(loader.files_read, [present])
        self.assertEqual(len(loader.skipped_files), 1)
        self.assertEqual(loader.skipped_files[0].reason, "file not found")
        self.assertEqual(loader.accepted_rows, 3)

    def test_wrong_header_and_empty_file_are_skipped(self):
        wrong = write_lines(self.folder, "wrong.csv", [PROFILE_HEADER, "P001,A,70,1,32"])
        empty = self.folder / "empty.csv"
        empty.write_text("", encoding="utf-8")
        loader = self.load(wrong, empty)
        reasons = [skipped.reason for skipped in loader.skipped_files]
        self.assertIn("header is missing", reasons[0])
        self.assertEqual(reasons[1], "the file is empty")

    def test_csv_error_keeps_rows_read_before_it(self):
        path = write_sessions(self.folder, "s.csv", [
            VALID_ROWS[0],
            "FIT-2026-001,P001,1,7\x000,1.2,32.4,0.1,0.95",
        ])
        loader = self.load(path)
        self.assertEqual(loader.accepted_rows, 1)
        self.assertIn("CSV format error", loader.skipped_files[0].reason)

    def test_blank_lines_are_ignored(self):
        path = write_sessions(self.folder, "s.csv", [VALID_ROWS[0], "", VALID_ROWS[1]])
        loader = self.load(path)
        self.assertEqual(loader.accepted_rows, 2)
        self.assertEqual(loader.rejected, [])

    def test_byte_order_mark_in_header_is_accepted(self):
        path = write_sessions(self.folder, "s.csv", VALID_ROWS)
        text = path.read_text(encoding="utf-8")
        path.write_text("﻿" + text, encoding="utf-8")
        self.assertEqual(self.load(path).accepted_rows, 3)

    def test_conflicting_participant_is_rejected(self):
        path = write_sessions(self.folder, "s.csv", [
            "FIT-2026-001,P001,0,70,1.2,32.4,0.1,0.95",
            "FIT-2026-001,P002,1,70,1.2,32.4,0.1,0.95",
        ])
        loader = self.load(path)
        field, reason = loader.rejected[0].problems[0]
        self.assertEqual(field, "participant_id")
        self.assertIn("already belongs to P001", reason)
        self.assertEqual(loader.sessions()[0].total_count, 1)

    def test_duplicate_timestamp_is_rejected(self):
        path = write_sessions(self.folder, "s.csv", [
            "FIT-2026-001,P001,0,70,1.2,32.4,0.1,0.95",
            "FIT-2026-001,P001,0,71,1.2,32.4,0.1,0.95",
        ])
        loader = self.load(path)
        field, reason = loader.rejected[0].problems[0]
        self.assertEqual(field, "timestamp")
        self.assertIn("duplicate timestamp 0", reason)

    def test_gap_in_timestamps_is_allowed(self):
        path = write_sessions(self.folder, "s.csv", [
            "FIT-2026-001,P001,0,70,1.2,32.4,0.1,0.95",
            "FIT-2026-001,P001,1,bad,1.2,32.4,0.1,0.95",
            "FIT-2026-001,P001,2,72,1.2,32.4,0.1,0.95",
        ])
        loader = self.load(path)
        self.assertEqual(len(loader.rejected), 1)
        timestamps = [o.timestamp for o in loader.sessions()[0].observations]
        self.assertEqual(timestamps, [0, 2])

    def test_session_split_over_two_files_is_merged(self):
        first = write_sessions(self.folder, "a.csv", [VALID_ROWS[0]])
        second = write_sessions(self.folder, "b.csv", [VALID_ROWS[1]])
        session = self.load(first, second).sessions()[0]
        self.assertEqual(session.total_count, 2)
        self.assertEqual([p.name for p in session.sources], ["a.csv", "b.csv"])

    def test_session_with_only_rejected_rows_is_listed(self):
        path = write_sessions(self.folder, "s.csv", [
            VALID_ROWS[0],
            "FIT-2026-003,P999,0,70,1.2,32.4,0.1,0.95",
            "FIT-2026-004,P001,0,70",
            "FIT-26-005,P001,0,70,1.2,32.4,0.1,0.95",
        ])
        loader = self.load(path)
        self.assertEqual(loader.empty_session_ids(), ["FIT-2026-003", "FIT-2026-004"])


if __name__ == "__main__":
    unittest.main()
