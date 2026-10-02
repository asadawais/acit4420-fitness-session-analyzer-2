import contextlib
import io
import tempfile
import unittest
from pathlib import Path

import main

from .helpers import write_profiles, write_sessions


class TestCommandLine(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.folder = Path(self._tmp.name)
        self.profiles = write_profiles(self.folder)
        self.valid = write_sessions(self.folder, "valid.csv", [
            "FIT-2026-001,P001,{0},70,1.2,32.4,0.1,0.95".format(t) for t in range(6)
        ])
        self.invalid = write_sessions(self.folder, "invalid.csv", [
            "FIT-2026-002,P002,0,fast,1.6,32.9,0.4,0.95",
            "FIT-2026-002,P002,1,90,1.6,32.9,0.4,0.20",
        ])
        self.output = self.folder / "output"

    def tearDown(self):
        self._tmp.cleanup()

    def run_main(self, *args):
        stdout, stderr = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            code = main.main([str(arg) for arg in args])
        return code, stdout.getvalue(), stderr.getvalue()

    def test_defaults_point_at_the_data_folder(self):
        args = main.build_parser().parse_args([])
        self.assertEqual(args.profiles, Path("data/participants.csv"))
        self.assertEqual(args.sessions, [Path("data/fitness_sessions.csv"),
                                         Path("data/fitness_sessions_invalid.csv")])
        self.assertEqual(args.output, Path("output"))

    def test_full_run_writes_files_and_prints_summary(self):
        code, out, _ = self.run_main(
            "--profiles", self.profiles,
            "--sessions", self.valid, self.invalid,
            "--output", self.output)
        self.assertEqual(code, 0)
        self.assertIn("Accepted rows:       7 (6 usable, 1 not usable", out)
        self.assertIn("Rejected rows:       1", out)
        self.assertEqual(sorted(p.name for p in self.output.iterdir()),
                         ["analysis_report.txt", "analysis_summary.csv",
                          "rejected_records.txt"])

    def test_missing_profile_file_stops_the_run(self):
        code, out, err = self.run_main(
            "--profiles", self.folder / "absent.csv",
            "--sessions", self.valid, "--output", self.output)
        self.assertEqual(code, 1)
        self.assertIn("profile file not found", err)
        self.assertEqual(out, "")
        self.assertFalse(self.output.exists())

    def test_missing_session_file_is_skipped(self):
        code, out, _ = self.run_main(
            "--profiles", self.profiles,
            "--sessions", self.folder / "absent.csv", self.valid,
            "--output", self.output)
        self.assertEqual(code, 0)
        self.assertIn("Session files read:  1 of 2", out)
        self.assertIn("absent.csv: file not found", out)

    def test_no_readable_session_file_is_an_error(self):
        code, _, err = self.run_main(
            "--profiles", self.profiles,
            "--sessions", self.folder / "absent.csv",
            "--output", self.output)
        self.assertEqual(code, 1)
        self.assertIn("none of the session files could be read", err)

    def test_output_path_that_is_a_file_is_reported(self):
        code, _, err = self.run_main(
            "--profiles", self.profiles, "--sessions", self.valid,
            "--output", self.profiles)
        self.assertEqual(code, 1)
        self.assertIn("is not a folder", err)


if __name__ == "__main__":
    unittest.main()
