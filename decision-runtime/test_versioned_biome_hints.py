import copy
import unittest
from unittest.mock import patch

from versioned_biome_hints import calibrate, predict, search, seed_hash, seed_value


SEED = "1009504104802950675"


def survey():
    return {"id": "native-test", "world_session": "current-world", "phase": None,
            "snow_biome_survey": {"loaded_samples": 5, "unloaded_samples": 0,
                                  "requested_samples": 5,
                                  "samples": [{"pos": [100+i*16, 70, 200],
                                               "biome": "minecraft:plains" if i < 3 else "minecraft:meadow"}
                                              for i in range(5)]}}


def matching(exe, seed, table, points):
    return ["minecraft:plains" if p[0] < 148 else "minecraft:meadow" for p in points]


def calibrated():
    return calibrate(SEED, "1.19.3", survey(),
                     {"hasHashedSeed": True, "hashedSeed": -2531438672007079198},
                     "unused", predictor=matching)


class VersionedBiomeHintsTest(unittest.TestCase):
    def test_seed_precision_and_known_current_login_hash(self):
        self.assertEqual(1009504104802950675, seed_value(SEED))
        self.assertEqual(-2531438672007079198, seed_hash(SEED))
        self.assertEqual(-(1 << 63), seed_value(str(-(1 << 63))))
        for bad in (1009504104802950675, float(SEED), "1e18", str(1 << 63)):
            with self.assertRaises(ValueError):
                seed_value(bad)

    def test_both_version_tables_must_match(self):
        self.assertTrue(calibrated()["hint_use_allowed"])
        def conflicting(exe, seed, table, points):
            return matching(exe, seed, table, points) if table == "1.19.2" else ["minecraft:desert"]*len(points)
        result = calibrate(SEED, "1.19.3", survey(),
                           {"hasHashedSeed": True, "hashedSeed": seed_hash(SEED)},
                           "unused", predictor=conflicting)
        self.assertFalse(result["hint_use_allowed"])
        with self.assertRaises(ValueError):
            search(result, [100, 200], 64, 32, {"minecraft:desert"}, 800000, "unused")

    def test_wrong_seed_hash_and_common_ocean_do_not_authorize_hints(self):
        for login in ({"hasHashedSeed": False}, {"hasHashedSeed": True, "hashedSeed": 1}):
            self.assertFalse(calibrate(SEED, "1.19.3", survey(), login,
                                       "unused", predictor=matching)["hint_use_allowed"])
        s = survey()
        for sample in s["snow_biome_survey"]["samples"]:
            sample["biome"] = "minecraft:ocean"
        result = calibrate(SEED, "1.19.3", s,
                           {"hasHashedSeed": True, "hashedSeed": seed_hash(SEED)},
                           "unused", predictor=lambda *a: ["minecraft:ocean"]*5)
        self.assertFalse(result["hint_use_allowed"])

    def test_unscoped_partial_duplicate_and_error_surveys_rejected(self):
        for change in (lambda s: s.update(world_session=""),
                       lambda s: s.update(phase="error"),
                       lambda s: s["snow_biome_survey"].update(loaded_samples=4),
                       lambda s: s["snow_biome_survey"]["samples"][1].update(pos=[100, 70, 200])):
            s = survey(); change(s)
            with self.assertRaises(ValueError):
                calibrate(SEED, "1.19.3", s, {}, "unused", predictor=matching)

    def test_current_client_version_is_never_silently_substituted(self):
        with self.assertRaises(ValueError):
            calibrate(SEED, "26.1.2", survey(), {}, "unused", predictor=matching)

    def test_border_and_disagreement_filter_even_nearby_deserts(self):
        def biome(exe, seed, table, points):
            return ["minecraft:plains" if table == "1.19.2" and p[0] == 799940
                    else "minecraft:desert" for p in points]
        result = search(calibrated(), [799940, 200], 512, 32,
                        {"minecraft:desert"}, 800000, "unused", predictor=biome)
        self.assertTrue(result["candidates"])
        self.assertTrue(all(abs(c["pos"][0]) < 799968 and c["pos"][0] != 799940
                            for c in result["candidates"]))
        self.assertEqual(0, result["inventory_credit"])
        self.assertTrue(result["actual_blocks_required"])

    def test_missing_table_and_outside_origin_rejected(self):
        bad = copy.deepcopy(calibrated()); del bad["models"]["1.19.2"]
        for c, origin in ((bad, [100, 200]), (calibrated(), [800000, 200])):
            with self.assertRaises(ValueError):
                search(c, origin, 64, 32, {"minecraft:desert"}, 800000, "unused")

    def test_generator_response_cannot_reassign_or_omit_coordinates(self):
        for output in ("", "101 70 200 2 desert\n", "100 70 200 2 unknown\n"):
            with patch("versioned_biome_hints.subprocess.run") as run:
                run.return_value.stdout = output
                with self.assertRaises(ValueError):
                    predict("unused", SEED, "1.19.4", [[100, 70, 200]])


if __name__ == "__main__":
    unittest.main()
