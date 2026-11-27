import contextlib, io, json, tempfile, unittest
from pathlib import Path
from unittest.mock import patch

from places_lookup import lookup

CONFIG = {'savedPlaces': [
    {'name': '远处农场', 'x': 1000.0, 'z': 0.0, 'cruiseY': 90, 'dimension': 'minecraft:overworld', 'home': False},
    {'name': '家', 'x': 5000.0, 'z': 0.0, 'cruiseY': 80, 'dimension': 'minecraft:overworld', 'home': True},
    {'name': '近处矿洞', 'x': 30.0, 'z': 40.0, 'cruiseY': 70, 'dimension': 'minecraft:overworld', 'home': False},
    {'name': '下界门', 'x': 1.0, 'z': 1.0, 'cruiseY': 120, 'dimension': 'minecraft:the_nether', 'home': False},
    {'name': '坏记录'}],
    'hasDeathPoint': True, 'deathX': 1.0, 'deathY': 60.0, 'deathZ': 2.0, 'deathDimension': 'minecraft:the_end',
    'deathKiller': '末影人', 'deathTimeEpochMillis': 123}
HERE = {'pos': [0, 64, 0], 'dimension': 'minecraft:overworld'}


class PlacesLookupTest(unittest.TestCase):
    def test_home_first_then_nearest_with_distance_only_in_this_dimension(self):
        out = lookup(CONFIG, HERE)
        self.assertEqual(['家', '近处矿洞', '远处农场', '下界门'], [p['name'] for p in out['places']])
        self.assertEqual(50, out['places'][1]['distance'])
        self.assertNotIn('distance', out['places'][3])
        self.assertEqual('末影人', out['death']['killer'])

    def test_offline_and_name_filter(self):
        out = lookup(CONFIG, {}, match='矿')
        self.assertEqual(['近处矿洞'], [p['name'] for p in out['places']])
        self.assertNotIn('distance', out['places'][0]); self.assertNotIn('death', out)

    def test_cli_works_without_a_running_game(self):
        import kit_cli
        with tempfile.TemporaryDirectory() as tmp:
            game = Path(tmp); (game / 'config').mkdir(); (game / 'config/twob2tkit.json').write_text(json.dumps(CONFIG))
            buf = io.StringIO()
            with patch('kit_cli.send') as send, contextlib.redirect_stdout(buf):
                self.assertEqual(0, kit_cli.main(['--game-dir', tmp, 'places', '--match', '家']))
            send.assert_not_called()
            self.assertEqual('家', json.loads(buf.getvalue())['places'][0]['name'])


if __name__ == '__main__': unittest.main()
