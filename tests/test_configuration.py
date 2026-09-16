import json
import tempfile
import unittest
from pathlib import Path

from RoshElectroptics import rosh_thorlabs_tafnit as app


PROFILE = {
    "tafnit_host": "tafnit.example.edu", "supplier_code": "900001",
    "agent_code": "9", "research_group": "900002", "requester": "900003",
    "department": "900004", "building": "90", "floor": "9", "room": "901",
    "contact_building": "91", "contact_floor": "8", "contact_room": "902",
    "budget_note": "Charge the example research budget",
}


class ConfigurationTests(unittest.TestCase):
    def test_configuration_is_required_and_has_no_personal_fallback(self):
        self.assertTrue(hasattr(app, "load_config"), "Personal defaults must move to local configuration")
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(app.AutomationError, "config"):
                app.load_config(Path(directory) / "missing.local.json")

    def test_blank_example_cannot_operate_desktop(self):
        self.assertTrue(hasattr(app, "load_config"), "Config validation is required")
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.local.json"
            path.write_text(json.dumps({k: "" for k in PROFILE}))
            with self.assertRaisesRegex(app.AutomationError, "blank"):
                app.load_config(path)

    def test_local_profile_controls_header_verification(self):
        self.assertTrue(hasattr(app, "load_config"), "Config loader is required")
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.local.json"
            path.write_text(json.dumps(PROFILE))
            config = app.load_config(path)
        self.assertEqual(config.requester, "900003")
        self.assertEqual(config.budget_note, PROFILE["budget_note"])
        ui = object.__new__(app.TafnitDesktop)
        ui.config = config
        values = {"SUGD": "4", "MHTD": "1", "KM": "1", "SEIF": "",
                  "MEHKAR": "900002", "IZAM": "900003", "MHLK": "900004",
                  "SPK": "900001", "SOCHEN": "9", "REMARKINS": config.budget_note,
                  "Building": "90", "Floor": "9", "Room": "901",
                  "CBuilding": "91", "CFloor": "8", "CRoom": "902"}
        class Reader:
            def read(self, expression):
                return values
        ui.reader = Reader()
        class Quote:
            phone = ""
        ui.verify_header(Quote(), config.budget_note)
        for field in ("SPK", "SEIF", "REMARKINS", "IZAM"):
            previous = values[field]
            values[field] = "unexpected"
            with self.assertRaisesRegex(app.AutomationError, field):
                ui.verify_header(Quote(), config.budget_note)
            values[field] = previous


if __name__ == "__main__":
    unittest.main()
