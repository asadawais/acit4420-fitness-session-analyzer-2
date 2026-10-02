import unittest

from fitness_analyzer.models import Participant, Session

from .helpers import make_observation, make_participant


class TestParticipant(unittest.TestCase):

    def test_baseline_is_read_only(self):
        participant = make_participant()
        with self.assertRaises(AttributeError):
            participant.baseline_heart_rate = 200

    def test_empty_identifier_is_rejected(self):
        with self.assertRaises(ValueError):
            Participant("   ", 70, 1.8, 32.5)

    def test_name_is_stored(self):
        self.assertEqual(make_participant().name, "Test Person")

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
        observation.problems.append(("x", "injected"))
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

    def test_observations_are_kept_in_timestamp_order(self):
        rows = [make_observation(timestamp=t) for t in (4, 0, 2)]
        session = Session(make_participant(), rows)
        self.assertEqual([o.timestamp for o in session.observations], [0, 2, 4])


if __name__ == "__main__":
    unittest.main()
