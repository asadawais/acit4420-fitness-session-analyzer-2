import unittest

from fitness_analyzer.exceptions import InvalidIdentifierError, InvalidRecordError
from fitness_analyzer.validation import (
    MINIMUM_SIGNAL_QUALITY,
    ImpossibleValueRule,
    MissingValueRule,
    ObservationValidator,
    OrderedTimestampRule,
    SignalQualityRule,
    ValidationRule,
    check_participant_id,
    check_session_id,
    parse_participant_row,
    parse_session_row,
)

from .helpers import make_observation, make_participant, make_session, session_row


PARTICIPANTS = {"P001": make_participant()}


def fields_of(error):
    return [field for field, _ in error.problems]


class TestIdentifiers(unittest.TestCase):

    def test_valid_participant_id(self):
        self.assertEqual(check_participant_id("P001"), "P001")

    def test_invalid_participant_ids(self):
        for text in ("001", "P01", "P0001", "p001", "P00A", "P001\n", "xP001"):
            with self.subTest(text=text):
                with self.assertRaises(InvalidIdentifierError):
                    check_participant_id(text)

    def test_valid_session_id(self):
        self.assertEqual(check_session_id("FIT-2026-001"), "FIT-2026-001")

    def test_invalid_session_ids(self):
        for text in ("FIT-26-102", "FIT-2026-1023", "fit-2026-001", "FIT-2026-001 x"):
            with self.subTest(text=text):
                with self.assertRaises(InvalidIdentifierError):
                    check_session_id(text)

    def test_identifier_error_is_a_value_error(self):
        self.assertTrue(issubclass(InvalidIdentifierError, ValueError))
        self.assertTrue(issubclass(InvalidRecordError, ValueError))


class TestParseSessionRow(unittest.TestCase):

    def parse(self, **overrides):
        return parse_session_row(session_row(**overrides), PARTICIPANTS)

    def rejected_fields(self, **overrides):
        with self.assertRaises(InvalidRecordError) as caught:
            self.parse(**overrides)
        return fields_of(caught.exception)

    def test_valid_row_is_converted_to_numbers(self):
        session_id, participant, observation = self.parse()
        self.assertEqual(session_id, "FIT-2026-001")
        self.assertIs(participant, PARTICIPANTS["P001"])
        self.assertIsInstance(observation.timestamp, int)
        self.assertIsInstance(observation.heart_rate, float)
        self.assertEqual(observation.signal_quality, 0.95)

    def test_surrounding_spaces_are_ignored(self):
        session_id, _, observation = self.parse(session_id=" FIT-2026-001 ",
                                                heart_rate=" 80 ")
        self.assertEqual(session_id, "FIT-2026-001")
        self.assertEqual(observation.heart_rate, 80.0)

    # The cases below mirror the official invalid file.

    def test_text_heart_rate(self):
        self.assertEqual(self.rejected_fields(heart_rate="fast"), ["heart_rate"])

    def test_participant_id_without_prefix(self):
        self.assertEqual(self.rejected_fields(participant_id="001"), ["participant_id"])

    def test_empty_activity_level(self):
        self.assertEqual(self.rejected_fields(activity_level=""), ["activity_level"])

    def test_signal_quality_above_one(self):
        self.assertEqual(self.rejected_fields(signal_quality="1.40"), ["signal_quality"])

    def test_short_session_id(self):
        self.assertEqual(self.rejected_fields(session_id="FIT-26-102"), ["session_id"])

    def test_unknown_participant(self):
        with self.assertRaises(InvalidRecordError) as caught:
            self.parse(participant_id="P999")
        field, reason = caught.exception.problems[0]
        self.assertEqual(field, "participant_id")
        self.assertIn("unknown participant P999", reason)

    def test_text_timestamp(self):
        self.assertEqual(self.rejected_fields(timestamp="two"), ["timestamp"])

    def test_negative_heart_rate(self):
        self.assertEqual(self.rejected_fields(heart_rate="-15"), ["heart_rate"])

    def test_several_bad_values_are_all_reported(self):
        fields = self.rejected_fields(skin_response="-0.50", temperature="55.0",
                                      activity_level="1.30")
        self.assertEqual(sorted(fields),
                         ["activity_level", "skin_response", "temperature"])

    def test_conversion_and_range_problems_together(self):
        fields = self.rejected_fields(heart_rate="fast", temperature="55")
        self.assertEqual(sorted(fields), ["heart_rate", "temperature"])

    def test_nan_and_infinity_are_rejected(self):
        for text in ("nan", "inf", "-inf"):
            with self.subTest(text=text):
                self.assertEqual(self.rejected_fields(heart_rate=text), ["heart_rate"])

    def test_decimal_timestamp_is_rejected(self):
        self.assertEqual(self.rejected_fields(timestamp="2.5"), ["timestamp"])

    # Boundary values.

    def test_values_on_the_limits_are_accepted(self):
        accepted = [
            {"heart_rate": "35"}, {"heart_rate": "205"},
            {"temperature": "25"}, {"temperature": "42"},
            {"activity_level": "0"}, {"activity_level": "1"},
            {"signal_quality": "0"}, {"signal_quality": "1"},
            {"skin_response": "0"}, {"timestamp": "0"},
        ]
        for overrides in accepted:
            with self.subTest(**overrides):
                self.parse(**overrides)

    def test_values_just_past_the_limits_are_rejected(self):
        rejected = [
            {"heart_rate": "34.9"}, {"heart_rate": "205.1"},
            {"temperature": "24.9"}, {"temperature": "42.1"},
            {"activity_level": "-0.01"}, {"activity_level": "1.01"},
            {"signal_quality": "-0.01"}, {"signal_quality": "1.01"},
            {"skin_response": "-0.01"}, {"timestamp": "-1"},
        ]
        for overrides in rejected:
            with self.subTest(**overrides):
                self.assertEqual(self.rejected_fields(**overrides), list(overrides))


class TestParseParticipantRow(unittest.TestCase):

    def row(self, **overrides):
        row = {
            "participant_id": "P010",
            "name": "Test Person",
            "baseline_heart_rate": "65",
            "baseline_skin_response": "1.1",
            "baseline_temperature": "32.3",
        }
        row.update(overrides)
        return row

    def test_valid_row(self):
        participant = parse_participant_row(self.row())
        self.assertEqual(participant.participant_id, "P010")
        self.assertEqual(participant.name, "Test Person")
        self.assertEqual(participant.baseline_heart_rate, 65.0)

    def test_bad_values_are_reported_by_field(self):
        with self.assertRaises(InvalidRecordError) as caught:
            parse_participant_row(self.row(participant_id="10", name="",
                                           baseline_heart_rate="high"))
        self.assertEqual(sorted(fields_of(caught.exception)),
                         ["baseline_heart_rate", "name", "participant_id"])

    def test_baseline_out_of_range(self):
        with self.assertRaises(InvalidRecordError) as caught:
            parse_participant_row(self.row(baseline_temperature="50"))
        self.assertEqual(fields_of(caught.exception), ["baseline_temperature"])


class TestValidationRules(unittest.TestCase):

    def test_missing_value_is_caught(self):
        problems = MissingValueRule().check(make_observation(heart_rate=None))
        self.assertEqual(problems, [("heart_rate", "is missing")])

    def test_boolean_is_not_accepted_as_a_number(self):
        problems = MissingValueRule().check(make_observation(heart_rate=True))
        self.assertEqual(len(problems), 1)

    def test_impossible_heart_rate_is_caught(self):
        problems = ImpossibleValueRule().check(make_observation(heart_rate=265))
        self.assertEqual([field for field, _ in problems], ["heart_rate"])

    def test_negative_activity_is_caught(self):
        problems = ImpossibleValueRule().check(make_observation(activity_level=-0.2))
        self.assertEqual(len(problems), 1)

    def test_missing_value_is_not_reported_twice(self):
        problems = ImpossibleValueRule().check(make_observation(heart_rate=None))
        self.assertEqual(problems, [])

    def test_nan_does_not_slip_past_the_range_check(self):
        observation = make_observation(heart_rate=float("nan"))
        self.assertEqual(ImpossibleValueRule().check(observation), [])
        self.assertEqual(len(MissingValueRule().check(observation)), 1)

    def test_negative_timestamp_is_caught(self):
        problems = OrderedTimestampRule().check(make_observation(timestamp=-1))
        self.assertEqual(len(problems), 1)

    def test_base_rule_must_be_overridden(self):
        with self.assertRaises(NotImplementedError):
            ValidationRule("base").check(make_observation())


class TestSignalQualityThreshold(unittest.TestCase):
    """Poor signal quality makes a row unusable, not rejected."""

    def usable(self, quality):
        return SignalQualityRule().check(make_observation(signal_quality=quality)) == []

    def test_threshold_is_documented_value(self):
        self.assertEqual(MINIMUM_SIGNAL_QUALITY, 0.60)

    def test_exactly_at_threshold_is_usable(self):
        self.assertTrue(self.usable(0.60))

    def test_just_below_threshold_is_not_usable(self):
        self.assertFalse(self.usable(0.59))

    def test_zero_is_not_usable(self):
        self.assertFalse(self.usable(0.0))

    def test_one_is_usable(self):
        self.assertTrue(self.usable(1.0))

    def test_low_quality_row_is_still_accepted_by_the_parser(self):
        _, _, observation = parse_session_row(
            session_row(signal_quality="0.30"), PARTICIPANTS)
        self.assertEqual(observation.signal_quality, 0.30)


class TestValidator(unittest.TestCase):

    def test_clean_session_passes_every_row(self):
        summary = ObservationValidator().validate_session(make_session([100] * 6))
        self.assertEqual(summary["usable_rows"], 6)
        self.assertEqual(summary["problem_counts"], {})

    def test_poor_quality_session_is_counted_by_rule(self):
        session = make_session([100] * 5, signal_quality=0.3)
        summary = ObservationValidator().validate_session(session)
        self.assertEqual(summary["usable_rows"], 0)
        self.assertEqual(summary["problem_counts"], {"low signal quality": 5})

    def test_empty_session_does_not_divide_by_zero(self):
        summary = ObservationValidator().validate_session(make_session([]))
        self.assertEqual(summary["usable_ratio"], 0.0)


if __name__ == "__main__":
    unittest.main()
