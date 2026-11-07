"""Offline invariants for the recorded incident suite."""

import unittest

from demo.fixtures import EXPECTED_PAGE, INCIDENTS, SERVICES


class FixtureInvariantTests(unittest.TestCase):
    def test_all_six_incidents_have_expected_decisions(self) -> None:
        self.assertEqual(len(INCIDENTS), 6)
        self.assertEqual(set(INCIDENTS), set(EXPECTED_PAGE))

    def test_each_incident_names_exactly_one_known_service(self) -> None:
        for incident_id, prompt in INCIDENTS.items():
            mentioned = [name for name in SERVICES if name in prompt]
            self.assertEqual(
                len(mentioned),
                1,
                f"{incident_id} must name exactly one fixture service",
            )

    def test_expected_pages_follow_service_state_and_owner(self) -> None:
        for incident_id, prompt in INCIDENTS.items():
            service_name = next(name for name in SERVICES if name in prompt)
            service = SERVICES[service_name]
            state = service["status"]["state"]
            expected = EXPECTED_PAGE[incident_id]

            if state in {"degraded", "down"}:
                self.assertEqual(expected, service["owner"], incident_id)
            elif state == "healthy":
                self.assertIsNone(expected, incident_id)
            else:
                self.fail(f"{incident_id} has unsupported state {state!r}")

    def test_fixture_statuses_include_positive_and_negative_cases(self) -> None:
        states = {service["status"]["state"] for service in SERVICES.values()}
        self.assertTrue({"healthy", "degraded", "down"}.issubset(states))
        self.assertTrue(any(team is None for team in EXPECTED_PAGE.values()))
        self.assertTrue(any(team is not None for team in EXPECTED_PAGE.values()))


if __name__ == "__main__":
    unittest.main()
