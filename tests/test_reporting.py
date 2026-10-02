import csv
import tempfile
import unittest
from pathlib import Path

from fitness_analyzer.analysis import SessionAnalyzer
from fitness_analyzer.loader import RejectedRecord, SkippedFile
from fitness_analyzer.reporting import (
    REJECTED_FILE,
    REPORT_FILE,
    SUMMARY_COLUMNS,
    SUMMARY_FILE,
    DetailedSessionReport,
    SessionReport,
    format_value,
    write_outputs,
)

from .helpers import make_session


def make_run(rejected=None, empty_session_ids=None, skipped_files=None):
    return {
        "profile_file": "profiles.csv",
        "files_read": [Path("sessions.csv")],
        "skipped_files": skipped_files or [],
        "accepted_rows": 11,
        "usable_rows": 6,
        "rejected": rejected or [],
        "empty_session_ids": empty_session_ids or [],
    }


class TestSessionReport(unittest.TestCase):

    def setUp(self):
        session = make_session([100] * 5, signal_quality=0.3)
        self.result = SessionAnalyzer().analyze(session)

    def test_standard_report_names_the_classification(self):
        self.assertIn("INSUFFICIENT DATA", SessionReport(self.result).render())

    def test_detailed_report_adds_unusable_rows(self):
        standard = SessionReport(self.result).render()
        detailed = DetailedSessionReport(self.result).render()
        self.assertNotIn("Rows not used", standard)
        self.assertIn("Rows not used", detailed)
        self.assertIn("signal_quality 0.3 is below the usable minimum", detailed)

    def test_report_handles_a_session_with_no_usable_rows(self):
        self.assertIn("no usable rows", SessionReport(self.result).render())

    def test_format_value_handles_none(self):
        self.assertEqual(format_value(None), "n/a")


class TestOutputFiles(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.output = Path(self._tmp.name) / "nested" / "output"
        analyzer = SessionAnalyzer()
        self.results = [
            analyzer.analyze(make_session([72] * 6)),
            analyzer.analyze(make_session([100] * 5, signal_quality=0.3)),
        ]
        self.rejected = [
            RejectedRecord("sessions.csv", 7, [("heart_rate", "'fast' is not a number")],
                           session_id="FIT-2026-777"),
            RejectedRecord("sessions.csv", 9, [("temperature", "55 is outside"),
                                               ("skin_response", "-0.5 is below 0")]),
        ]
        self.run = make_run(self.rejected, ["FIT-2026-777"],
                            [SkippedFile("absent.csv", "file not found")])

    def tearDown(self):
        self._tmp.cleanup()

    def write(self):
        return write_outputs(self.output, self.results, self.run)

    def test_creates_folder_and_all_three_files(self):
        created = self.write()
        self.assertEqual([path.name for path in created],
                         [SUMMARY_FILE, REPORT_FILE, REJECTED_FILE])
        for path in created:
            self.assertTrue(path.is_file())

    def test_summary_csv_has_one_row_per_session(self):
        self.write()
        with open(self.output / SUMMARY_FILE, encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            rows = list(reader)
        self.assertEqual(tuple(reader.fieldnames), SUMMARY_COLUMNS)
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["classification"], "resting")
        self.assertEqual((rows[1]["accepted_rows"], rows[1]["usable_rows"]), ("5", "0"))
        self.assertEqual(rows[1]["mean_heart_rate"], "")

    def test_rejected_file_lists_file_line_field_and_reason(self):
        self.write()
        text = (self.output / REJECTED_FILE).read_text(encoding="utf-8")
        self.assertIn("2 row(s) rejected", text)
        lines = [line.split() for line in text.splitlines()]
        self.assertIn(["sessions.csv", "7", "heart_rate", "'fast'", "is", "not", "a", "number"],
                      lines)
        self.assertIn("skin_response", text)
        self.assertIn("absent.csv: file not found", text)

    def test_report_notes_sessions_with_no_valid_rows(self):
        self.write()
        text = (self.output / REPORT_FILE).read_text(encoding="utf-8")
        self.assertIn("FIT-2026-777: no valid rows remained", text)
        self.assertIn("Accepted rows:  11 (6 usable)", text)

    def test_files_are_overwritten_on_each_run(self):
        self.write()
        self.results = self.results[:1]
        self.write()
        with open(self.output / SUMMARY_FILE, encoding="utf-8", newline="") as handle:
            self.assertEqual(len(list(csv.DictReader(handle))), 1)


if __name__ == "__main__":
    unittest.main()
