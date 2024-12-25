# pylint: disable-all
# flake8: noqa

from datetime import datetime
from unittest import TestCase

from netkan.status import ModStatus


class TestModStatusRestore(TestCase):
    def item_data(self):
        return {
            "frozen": False,
            "game_id": "ksp2",
            "last_checked": "2023-04-11T13:40:16.261429+00:00",
            "last_downloaded": "2023-04-11T13:40:16.261429+00:00",
            "last_error": None,
            "last_indexed": "2023-04-11T14:40:18.673421+00:00",
            "last_inflated": "2023-04-13T08:10:15+00:00",
            "last_warnings": "No plugin matching the identifier, manual installations won't be detected: BepInEx/plugins/utilityuplift/utilityuplift.dll",
            "release_date": "2023-04-11T13:34:15.550546+00:00",
            "failed": False
        }

    def test_datetime_types(self):
        values = self.item_data()
        ModStatus.normalise_item('TestMod', values)
        for val in ['last_checked', 'last_downloaded', 'last_indexed', 'last_inflated', 'release_date']:
            self.assertIsInstance(values.get(val), datetime)

    def test_success_true(self):
        values = self.item_data()
        ModStatus.normalise_item('SuccessMod', values)
        self.assertTrue(values.get('success'))

    def test_success_false(self):
        values = self.item_data()
        values.update(failed=True)
        ModStatus.normalise_item('FailedMod', values)
        self.assertFalse(values.get('success'))

    def test_default_game(self):
        values = self.item_data()
        values.update(game_id=None)
        ModStatus.normalise_item('DefaultMod', values)
        self.assertEqual(values.get('game_id'), 'ksp')

    def test_modidentifier(self):
        values = self.item_data()
        ModStatus.normalise_item('TheMod', values)
        self.assertEqual(values.get('ModIdentifier'), 'TheMod')
