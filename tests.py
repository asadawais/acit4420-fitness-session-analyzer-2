"""Unit tests. Run with: python3 tests.py"""

import unittest

from fitness_analyzer import analysis
from fitness_analyzer.analysis import (
    SessionAnalyzer,
    average,
    minimum_and_maximum,
    percentage,
    split_half_difference,
    summarise,
)
from fitness_analyzer.models import Observation, Participant, Session
from fitness_analyzer.reporting import (
    DetailedSessionReport,
    SessionReport,
    format_value,
)
from fitness_analyzer.validation import (
    ImpossibleValueRule,
    MissingValueRule,
    ObservationValidator,
    OrderedTimestampRule,
    SignalQualityRule,
)


def make_observation(**overrides):
    """A valid observation, with any field overridden for a specific test."""
    fields = {
        "timestamp": 0,
        "heart_rate": 110,
        "skin_response": 2.0,
        "temperature": 33.0,
        "activity_level": 0.5,
        "signal_quality": 0.9,
    }
    fields.update(overrides)
    return Observation(**fields)


def make_participant():
    return Participant("P001", 70, 1.8, 32.5)


def make_session(heart_rates, activity_levels=None, signal_quality=0.9):
    """A hand-built session with one window per heart rate value."""
    if activity_levels is None:
        activity_levels = [0.5] * len(heart_rates)
    observations = [
        make_observation(timestamp=index, heart_rate=rate,
                         activity_level=level, signal_quality=signal_quality)
        for index, (rate, level) in enumerate(zip(heart_rates, activity_levels))
    ]
    return Session(make_participant(), observations, label="t")


def make_mostly_faulty_session():
    """Four usable windows out of nine, so under half survive."""
    observations = [
        Observation(0, 104, 2.1, 33.0, 0.52, 0.93),
        Observation(1, 106, 2.2, 33.1, 0.54, 0.92),
        Observation(2, 108, 2.2, 33.0, 0.55, 0.91),
        Observation(3, 105, 2.1, 33.1, 0.53, 0.90),
        Observation(4, None, 2.2, 33.0, 0.54, 0.91),
        Observation(5, 265, 2.1, 33.1, 0.52, 0.92),
        Observation(6, 107, None, 33.0, 0.55, 0.90),
        Observation(7, 106, 2.2, 33.1, -0.30, 0.91),
        Observation(8, 105, 2.1, 33.0, 0.53, 0.20),
    ]
    return Session(make_participant(), observations, label="mostly faulty")


class TestParticipant(unittest.TestCase):

    def test_baseline_is_read_only(self):
        participant = make_participant()
        with self.assertRaises(AttributeError):
            participant.baseline_heart_rate = 200

    def test_empty_identifier_is_rejected(self):
        with self.assertRaises(ValueError):
            Participant("   ", 70, 1.8, 32.5)

    def test_comparison_against_baseline(self):
        participant = make_participant()
        self.assertEqual(participant.heart_rate_above_baseline(100), 30.0)


class TestObservation(unittest.TestCase):

    def test_unvalidated_observation_is_not_usable(self):
        observation = make_observation()
        self.assertFalse(observation.is_validated)
        self.assertFalse(observation.is_usable)

    def test_recording_no_problems_marks_it_usable(self):
        observation = make_observation()
        observation.record_validation([])
        self.assertTrue(observation.is_usable)

    def test_problems_list_cannot_be_edited_from_outside(self):
        observation = make_observation()
        observation.record_validation([("heart_rate", "a problem")])
        observation.problems.append("injected")
        self.assertEqual(len(observation.problems), 1)


class TestSession(unittest.TestCase):

    def test_rejects_wrong_participant_type(self):
        with self.assertRaises(TypeError):
            Session("not a participant", [])

    def test_rejects_wrong_observation_type(self):
        with self.assertRaises(TypeError):
            Session(make_participant(), [{"timestamp": 0}])

    def test_observation_list_is_a_copy(self):
        session = Session(make_participant(), [make_observation()])
        session.observations.append(make_observation())
        self.assertEqual(session.total_count, 1)


class TestValidationRules(unittest.TestCase):

    def test_missing_value_is_caught(self):
        problems = MissingValueRule().check(make_observation(heart_rate=None))
        self.assertEqual(len(problems), 1)

    def test_boolean_is_not_accepted_as_a_number(self):
        problems = MissingValueRule().check(make_observation(heart_rate=True))
        self.assertEqual(len(problems), 1)

    def test_impossible_heart_rate_is_caught(self):
        problems = ImpossibleValueRule().check(make_observation(heart_rate=265))
        self.assertEqual(len(problems), 1)

    def test_negative_activity_is_caught(self):
        problems = ImpossibleValueRule().check(make_observation(activity_level=-0.2))
        self.assertEqual(len(problems), 1)

    def test_missing_value_is_not_reported_twice(self):
        problems = ImpossibleValueRule().check(make_observation(heart_rate=None))
        self.assertEqual(problems, [])

    def test_low_signal_quality_is_caught(self):
        problems = SignalQualityRule().check(make_observation(signal_quality=0.3))
        self.assertEqual(len(problems), 1)

    def test_good_signal_quality_passes(self):
        self.assertEqual(SignalQualityRule().check(make_observation()), [])

    def test_nan_is_rejected(self):
        problems = MissingValueRule().check(
            make_observation(heart_rate=float("nan")))
        self.assertEqual(len(problems), 1)

    def test_nan_does_not_slip_past_the_range_check(self):
        observation = make_observation(heart_rate=float("nan"))
        self.assertEqual(ImpossibleValueRule().check(observation), [])
        self.assertEqual(len(MissingValueRule().check(observation)), 1)

    def test_negative_timestamp_is_caught(self):
        problems = OrderedTimestampRule().check(make_observation(timestamp=-1))
        self.assertEqual(len(problems), 1)

    def test_base_rule_must_be_overridden(self):
        from fitness_analyzer.validation import ValidationRule
        with self.assertRaises(NotImplementedError):
            ValidationRule("base").check(make_observation())


class TestValidator(unittest.TestCase):

    def test_clean_session_passes_every_window(self):
        session = make_session([100] * 12)
        summary = ObservationValidator().validate_session(session)
        self.assertEqual(summary["usable_rows"], 12)
        self.assertEqual(summary["problem_counts"], {})

    def test_poor_quality_session_is_rejected(self):
        session = make_session([100] * 12, signal_quality=0.3)
        summary = ObservationValidator().validate_session(session)
        self.assertEqual(summary["usable_rows"], 0)

    def test_empty_session_does_not_divide_by_zero(self):
        session = Session(make_participant(), [], label="empty")
        summary = ObservationValidator().validate_session(session)
        self.assertEqual(summary["usable_ratio"], 0.0)


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

    def test_split_half_difference_detects_decline(self):
        self.assertEqual(split_half_difference([10, 10, 2, 2]), 8.0)

    def test_split_half_difference_needs_enough_values(self):
        self.assertIsNone(split_half_difference([1, 2, 3]))

    def test_percentage_handles_zero_total(self):
        self.assertEqual(percentage(3, 0), 0.0)

    def test_format_value_handles_none(self):
        self.assertEqual(format_value(None), "n/a")


class TestClassification(unittest.TestCase):
    """Hand-built sessions for each classification. Baseline heart rate is 70."""

    def classify(self, session):
        return SessionAnalyzer().analyze(session)["classification"]

    def test_resting(self):
        self.assertEqual(self.classify(make_session([72] * 8)), analysis.RESTING)

    def test_moderate(self):
        self.assertEqual(self.classify(make_session([100] * 8)), analysis.MODERATE)

    def test_high(self):
        self.assertEqual(self.classify(make_session([130] * 8)), analysis.HIGH)

    def test_recovery(self):
        session = make_session([140] * 4 + [90] * 4, [0.9] * 4 + [0.2] * 4)
        self.assertEqual(self.classify(session), analysis.RECOVERING)

    def test_poor_quality(self):
        session = make_session([100] * 8, signal_quality=0.3)
        self.assertEqual(self.classify(session), analysis.INSUFFICIENT)

    def test_low_usable_ratio_is_insufficient(self):
        result = SessionAnalyzer().analyze(make_mostly_faulty_session())
        self.assertEqual(result["classification"], analysis.INSUFFICIENT)
        self.assertIn("rows were usable", result["reasons"][0])

    def test_single_window_is_insufficient(self):
        session = Session(make_participant(), [make_observation()], label="one")
        result = SessionAnalyzer().analyze(session)
        self.assertEqual(result["classification"], analysis.INSUFFICIENT)

    def test_empty_session_is_insufficient(self):
        session = Session(make_participant(), [], label="empty")
        result = SessionAnalyzer().analyze(session)
        self.assertEqual(result["classification"], analysis.INSUFFICIENT)

    def test_result_is_a_dictionary_with_expected_keys(self):
        result = SessionAnalyzer().analyze(make_session([72] * 8))
        for key in ("classification", "quality", "measurements", "comparison",
                    "trend", "reasons"):
            self.assertIn(key, result)

    def test_every_classification_has_a_reason(self):
        sessions = [
            make_session([72] * 8),
            make_session([130] * 8),
            make_session([100] * 8, signal_quality=0.3),
            make_mostly_faulty_session(),
            Session(make_participant(), [], label="empty"),
        ]
        for session in sessions:
            result = SessionAnalyzer().analyze(session)
            self.assertTrue(result["reasons"], session.label)


class TestReporting(unittest.TestCase):

    def setUp(self):
        session = make_session([100] * 12, signal_quality=0.3)
        self.result = SessionAnalyzer().analyze(session)

    def test_standard_report_names_the_classification(self):
        text = SessionReport(self.result).render()
        self.assertIn("INSUFFICIENT DATA", text)

    def test_detailed_report_adds_rejected_windows(self):
        standard = SessionReport(self.result).render()
        detailed = DetailedSessionReport(self.result).render()
        self.assertNotIn("Rows not used", standard)
        self.assertIn("Rows not used", detailed)

    def test_detailed_report_overrides_the_title(self):
        self.assertIn("[detailed]", DetailedSessionReport(self.result).title())

    def test_report_handles_a_session_with_no_usable_windows(self):
        text = SessionReport(self.result).render()
        self.assertIn("no usable rows", text)


if __name__ == "__main__":
    unittest.main(verbosity=2)
