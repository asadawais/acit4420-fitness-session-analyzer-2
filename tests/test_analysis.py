import unittest

from fitness_analyzer import analysis
from fitness_analyzer.analysis import (
    SessionAnalyzer,
    average,
    last_third_size,
    minimum_and_maximum,
    peak_to_end_drop,
    percentage,
    summarise,
)
from fitness_analyzer.models import Session

from .helpers import (
    make_mostly_faulty_session,
    make_observation,
    make_participant,
    make_session,
)


class TestStandaloneFunctions(unittest.TestCase):

    def test_average_of_empty_list_is_none(self):
        self.assertIsNone(average([]))

    def test_average_rounds_to_two_places(self):
        self.assertEqual(average([1, 2, 2]), 1.67)

    def test_minimum_and_maximum(self):
        self.assertEqual(minimum_and_maximum([4, 1, 9]), (1, 9))

    def test_minimum_and_maximum_of_empty_list(self):
        self.assertEqual(minimum_and_maximum([]), (None, None))

    def test_summarise_reports_count(self):
        self.assertEqual(summarise([1, 2, 3])["count"], 3)

    def test_percentage_handles_zero_total(self):
        self.assertEqual(percentage(3, 0), 0.0)

    def test_last_third_is_at_least_two_rows(self):
        self.assertEqual(last_third_size(4), 2)
        self.assertEqual(last_third_size(6), 2)
        self.assertEqual(last_third_size(12), 4)

    def test_peak_to_end_drop_detects_decline(self):
        self.assertEqual(peak_to_end_drop([10, 12, 2, 4]), 9.0)

    def test_peak_to_end_drop_needs_enough_values(self):
        self.assertIsNone(peak_to_end_drop([12, 2, 3]))

    def test_peak_in_last_third_gives_no_drop(self):
        self.assertIsNone(peak_to_end_drop([5, 6, 7, 8, 20, 3]))


class TestClassification(unittest.TestCase):
    """Hand-built sessions for each classification. Baseline heart rate is 70."""

    def analyze(self, session):
        return SessionAnalyzer().analyze(session)

    def classify(self, session):
        return self.analyze(session)["classification"]

    def test_resting(self):
        self.assertEqual(self.classify(make_session([72] * 6)), analysis.RESTING)

    def test_moderate(self):
        self.assertEqual(self.classify(make_session([100] * 6)), analysis.MODERATE)

    def test_high(self):
        self.assertEqual(self.classify(make_session([130] * 6)), analysis.HIGH)

    def test_peak_then_fall_is_recovering(self):
        # Shaped like FIT-2026-004: warm-up row, peak, then a clear fall.
        session = make_session([72, 138, 151, 132, 104, 82],
                               [0.20, 0.86, 0.92, 0.70, 0.42, 0.18])
        result = self.analyze(session)
        self.assertEqual(result["classification"], analysis.RECOVERING)
        self.assertEqual(result["trend"]["heart_rate_drop"], 58.0)

    def test_small_fall_after_peak_is_not_recovering(self):
        # Shaped like FIT-2026-002: drops 14 bpm, just under the threshold.
        session = make_session([78, 96, 112, 118, 110, 98],
                               [0.22, 0.45, 0.62, 0.68, 0.58, 0.42])
        result = self.analyze(session)
        self.assertEqual(result["classification"], analysis.MODERATE)
        self.assertEqual(result["trend"]["heart_rate_drop"], 14.0)
        self.assertIn("not recovering", result["reasons"][1])

    def test_heart_rate_fall_without_activity_fall_is_not_recovering(self):
        session = make_session([100, 150, 150, 140, 100, 100], [0.5] * 6)
        self.assertNotEqual(self.classify(session), analysis.RECOVERING)

    def test_peak_in_last_third_is_not_recovering(self):
        session = make_session([100, 100, 100, 100, 160, 110],
                               [0.3, 0.3, 0.3, 0.3, 0.9, 0.3])
        result = self.analyze(session)
        self.assertNotEqual(result["classification"], analysis.RECOVERING)
        self.assertIn("peaked in the last third", result["reasons"][1])

    def test_poor_signal_session_is_insufficient(self):
        # Shaped like FIT-2026-005: five rows, all below the quality minimum.
        session = make_session([76, 79, 95, 101, 88], signal_quality=0.3)
        result = self.analyze(session)
        self.assertEqual(result["classification"], analysis.INSUFFICIENT)
        self.assertIn("low signal quality", result["reasons"][1])

    def test_exactly_minimum_usable_rows_is_classified(self):
        session = make_session([72] * analysis.MINIMUM_USABLE_ROWS)
        self.assertEqual(self.classify(session), analysis.RESTING)

    def test_one_below_minimum_usable_rows_is_insufficient(self):
        session = make_session([72] * (analysis.MINIMUM_USABLE_ROWS - 1))
        self.assertEqual(self.classify(session), analysis.INSUFFICIENT)

    def test_low_usable_ratio_is_insufficient(self):
        result = self.analyze(make_mostly_faulty_session())
        self.assertEqual(result["classification"], analysis.INSUFFICIENT)
        self.assertIn("rows were usable", result["reasons"][0])

    def test_single_row_is_insufficient(self):
        session = Session(make_participant(), [make_observation()])
        self.assertEqual(self.classify(session), analysis.INSUFFICIENT)

    def test_empty_session_is_insufficient(self):
        self.assertEqual(self.classify(make_session([])), analysis.INSUFFICIENT)

    def test_result_is_a_dictionary_with_expected_keys(self):
        result = self.analyze(make_session([72] * 6))
        for key in ("session_id", "participant_id", "participant_name",
                    "classification", "quality", "measurements", "comparison",
                    "trend", "reasons"):
            self.assertIn(key, result)

    def test_every_classification_has_a_reason(self):
        sessions = [
            make_session([72] * 6),
            make_session([130] * 6),
            make_session([100] * 6, signal_quality=0.3),
            make_mostly_faulty_session(),
            make_session([]),
        ]
        for session in sessions:
            self.assertTrue(self.analyze(session)["reasons"])


if __name__ == "__main__":
    unittest.main()
