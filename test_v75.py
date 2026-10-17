"""Toto75-mallin ja rivin tarkistukset."""

import unittest

import toto
import v75
import v75model
import v75system


def start(result, km=12.5, auto=True, driver="Aimo Ajo", prize=500000, post=1, when="2026-09-01"):
    return {
        "date": "1.9.",
        "when": when,
        "track": "Vermo",
        "result": str(result),
        "kmText": "12,5a",
        "km": km,
        "auto": auto,
        "driver": driver,
        "prize": prize,
        "distance": 2100,
        "post": post,
    }


def horse(**over):
    base = {
        "number": 1,
        "name": "Hepo",
        "driver": "Aimo Ajo",
        "trainer": "Talli",
        "track": 1,
        "distance": 2100,
        "scratched": False,
        "frontShoes": "HAS_SHOES",
        "rearShoes": "HAS_SHOES",
        "frontChanged": False,
        "rearChanged": False,
        "recordAuto": 12.8,
        "recordVolt": 16.0,
        "recordAutoText": "12,8a",
        "recordVoltText": "16,0",
        "year": {
            "starts": 12,
            "wins": 2,
            "seconds": 2,
            "thirds": 1,
            "winRate": 2 / 12,
            "placeRate": 0.4,
            "gallop": 0.08,
            "disq": 0.08,
            "money": 2000000,
        },
        "previous": {
            "starts": 10,
            "wins": 1,
            "seconds": 1,
            "thirds": 1,
            "winRate": 0.1,
            "placeRate": 0.3,
            "gallop": 0.1,
            "disq": 0.1,
            "money": 800000,
        },
        "driverStarts": 4000,
        "driverWins": 480,
        "starts": [start(result, when=f"2026-08-{day:02d}") for day, result in enumerate((4, 5, 3, 2, 6, 4), start=1)],
    }
    base.update(over)
    return base


def race():
    return {"startType": "CAR_START", "distance": 2100, "firstPrize": 1500000, "breed": "L"}


class ModelTest(unittest.TestCase):
    def test_probabilities_sum_to_one(self):
        field = [
            horse(number=1, name="A"),
            horse(number=2, name="B", track=5, recordAuto=13.4),
            horse(number=3, name="C", track=8, recordAuto=14.1, scratched=False),
        ]
        rows = [item for item in v75model.analyze_race(field, race(), {1: 0.5, 2: 0.3, 3: 0.2}) if not item["scratched"]]
        self.assertAlmostEqual(sum(item["ai"] for item in rows), 1, places=6)

    def test_better_form_ranks_first(self):
        strong = horse(
            number=1,
            name="Vahva",
            recordAuto=11.2,
            driverWins=900,
            driverStarts=5000,
            year={
                "starts": 15,
                "wins": 6,
                "seconds": 4,
                "thirds": 2,
                "winRate": 0.4,
                "placeRate": 0.8,
                "gallop": 0.02,
                "disq": 0.0,
                "money": 9000000,
            },
            starts=[start(1, km=11.4, when=f"2026-09-0{i}") for i in range(1, 6)],
        )
        weak = horse(number=2, name="Heikko", track=8, recordAuto=14.2, starts=[start(8, km=14.0, post=8) for _ in range(5)])
        rows = v75model.analyze_race([strong, weak], race(), {1: 0.4, 2: 0.6})
        self.assertEqual(rows[0]["name"], "Vahva")
        self.assertGreater(rows[0]["ai"], rows[1]["ai"])

    def test_scratched_is_left_out_of_the_sum(self):
        rows = v75model.analyze_race(
            [horse(number=1), horse(number=2, name="Pois", scratched=True)],
            race(),
            {1: 0.7, 2: 0.3},
        )
        live = [item for item in rows if not item["scratched"]]
        self.assertEqual(len(live), 1)
        self.assertAlmostEqual(live[0]["ai"], 1, places=6)
        self.assertEqual(rows[-1]["label"], "pois")

    def test_underbet_and_overbet(self):
        rows = v75model.analyze_race(
            [horse(number=1, name="A"), horse(number=2, name="B", track=6)],
            race(),
            {1: 0.20, 2: 0.80},
        )
        by_number = {item["number"]: item for item in rows}
        self.assertIsNotNone(by_number[1]["edge"])
        labels = {item["label"] for item in rows}
        self.assertIn("alipelattu", labels)
        self.assertIn("ylipelattu", labels)

    def test_varma_needs_a_standout(self):
        strong = horse(
            number=4,
            name="Super",
            track=2,
            recordAuto=11.0,
            driverWins=1100,
            driverStarts=6000,
            year={
                "starts": 16,
                "wins": 8,
                "seconds": 4,
                "thirds": 2,
                "winRate": 0.5,
                "placeRate": 0.88,
                "gallop": 0.02,
                "disq": 0.0,
                "money": 12000000,
            },
            starts=[start(1, km=11.2, driver="Aimo Ajo", post=2, when=f"2026-09-{i:02d}") for i in range(1, 7)],
        )
        others = [
            horse(number=number, name=f"H{number}", track=number + 3, recordAuto=13.8, driver="Muu Kuski", driverWins=200, driverStarts=4000)
            for number in (1, 2, 3, 5)
        ]
        rows = v75model.analyze_race([strong, *others], race(), {4: 0.46, 1: 0.16, 2: 0.14, 3: 0.13, 5: 0.11})
        leader = rows[0]
        self.assertEqual(leader["name"], "Super")
        self.assertGreaterEqual(leader["certainty"], 78)
        self.assertTrue(leader["varma"])
        self.assertGreater(leader["ai"], 0.4)


class SystemTest(unittest.TestCase):
    def races(self):
        def leg(index, horses):
            return {"leg": index, "number": index + 4, "horses": horses}

        def runner(number, ai, market, label="linjassa", varma=False, name=""):
            return {
                "number": number,
                "name": name or str(number),
                "ai": ai,
                "market": market,
                "edge": ai - market,
                "label": label,
                "varma": varma,
                "scratched": False,
            }

        return [
            leg(1, [runner(1, 0.62, 0.58, varma=True, name="Super"), runner(2, 0.2, 0.22), runner(3, 0.18, 0.2)]),
            leg(
                2,
                [
                    runner(3, 0.29, 0.47, "ylipelattu", name="Suosikki"),
                    runner(7, 0.27, 0.18, "alipelattu", name="Ali"),
                    runner(4, 0.22, 0.2),
                    runner(1, 0.22, 0.15),
                ],
            ),
        ]

    def test_budget_limits_rows(self):
        system = v75system.build_one(self.races(), "turvallinen", 5, 0.5)
        self.assertGreaterEqual(system["rows"], 1)
        self.assertLessEqual(system["rows"] * 0.5, 5 + 1e-9)
        self.assertAlmostEqual(system["cost"], round(system["rows"] * 0.5, 2))

    def test_safe_keeps_the_likely_winner_first(self):
        system = v75system.build_one(self.races(), "turvallinen", 1, 0.5)
        first = system["legs"][0]
        self.assertEqual(first["picks"][0], 1)
        self.assertTrue(first["varma"])

    def test_bold_does_not_bank_the_overbet_favorite(self):
        tight = v75system.build_one(self.races(), "rohkea", 0.5, 0.5)
        second = tight["legs"][1]
        self.assertEqual(second["picks"], [7])
        self.assertEqual(tight["notes"][0]["name"], "Suosikki")

        wider = v75system.build_one(self.races(), "rohkea", 1, 0.5)
        picks = wider["legs"][1]["picks"]
        self.assertEqual(picks[0], 7)
        self.assertIn(3, picks)

    def test_scratched_horse_is_not_played(self):
        races = self.races()
        races[0]["horses"][0]["scratched"] = True
        system = v75system.build_one(races, "turvallinen", 1, 0.5)
        self.assertNotIn(1, system["legs"][0]["picks"])
        self.assertTrue(system["legs"][0]["picks"])

    def test_kaksari_box_fits_the_budget(self):
        race = self.races()[0]
        system = v75system.build_ordered(race, "turvallinen", 5, 0.5, 2)
        self.assertTrue(system["box"])
        self.assertEqual(system["rows"], 6)
        self.assertEqual(system["legs"][0]["picks"], [1, 2, 3])
        self.assertAlmostEqual(system["hit"], 1, places=5)

    def test_troikka_lists_lines_when_the_box_does_not_fit(self):
        race = self.races()[0]
        system = v75system.build_ordered(race, "turvallinen", 1, 0.5, 3)
        self.assertFalse(system["box"])
        self.assertEqual(system["rows"], 2)
        self.assertEqual(system["lines"][0]["picks"], [1, 2, 3])
        self.assertEqual(system["lines"][1]["picks"][0], 1)

    def test_quinte_lists_the_best_orders_inside_the_budget(self):
        def runner(number, ai):
            return {
                "number": number,
                "name": str(number),
                "ai": ai,
                "market": 0.1,
                "edge": ai - 0.1,
                "label": "linjassa",
                "varma": False,
                "scratched": False,
            }

        horses = [runner(number, ai) for number, ai in enumerate((0.30, 0.20, 0.15, 0.13, 0.12, 0.10), start=1)]
        race = {"leg": 1, "number": 4, "horses": horses}
        system = v75system.build_ordered(race, "turvallinen", 10, 2, 5)
        self.assertFalse(system["box"])
        self.assertEqual(system["rows"], 5)
        self.assertEqual(len(system["lines"][0]["picks"]), 5)
        self.assertEqual(system["lines"][0]["picks"][0], 1)

    def test_scratched_horse_is_not_in_the_kaksari(self):
        race = self.races()[0]
        race["horses"][0]["scratched"] = True
        system = v75system.build_ordered(race, "turvallinen", 5, 0.5, 2)
        self.assertNotIn(1, system["legs"][0]["picks"])
        self.assertEqual(system["rows"], 2)

    def test_too_small_budget(self):
        system = v75system.build_one(self.races(), "turvallinen", 0.02, 0.1)
        self.assertEqual(system["rows"], 0)
        self.assertTrue(system["notes"])

    def test_place_chances_use_the_same_scale_as_the_pool(self):
        horses = [
            {"number": 1, "ai": 0.40, "scratched": False, "market": None, "label": "ei markkinaa"},
            {"number": 2, "ai": 0.30, "scratched": False, "market": None, "label": "ei markkinaa"},
            {"number": 3, "ai": 0.20, "scratched": False, "market": None, "label": "ei markkinaa"},
            {"number": 4, "ai": 0.10, "scratched": False, "market": None, "label": "ei markkinaa"},
        ]
        chances = v75._in_the_money({horse["number"]: horse["ai"] for horse in horses}, 3)
        self.assertAlmostEqual(sum(chances.values()), 3, places=6)
        self.assertGreater(chances[1], chances[4])
        v75._apply_place(horses, {1: 0.10, 2: 0.30, 3: 0.30, 4: 0.30}, 3)
        self.assertAlmostEqual(sum(horse["ai"] for horse in horses), 1, places=6)
        self.assertGreater(horses[0]["place"], horses[0]["ai"])
        self.assertEqual(horses[0]["number"], 1)
        self.assertEqual(horses[0]["label"], "alipelattu")

    def test_single_winner_and_place_labels(self):
        self.assertEqual(v75._hit_label({"kind": "winners"}, 1), "Voittaja mukana")
        self.assertEqual(v75._hit_label({"kind": "place"}, 1), "Sijat mukana")
        self.assertEqual(v75._hit_label({"kind": "winners"}, 8), "Kaikki kahdeksan voittajaa mukana")

    def test_duo_share_ignores_horses_missing_from_the_price_list(self):
        shares = toto._duo_shares({
            "netSales": 100,
            "odds": [
                {"runnerNumber1": 1, "runnerNumber2": 4, "amount": 60},
                {"runnerNumber1": 2, "runnerNumber2": 4, "amount": 40},
            ],
        })
        self.assertAlmostEqual(shares[0][1], 0.6)
        self.assertAlmostEqual(shares[0][2], 0.4)
        self.assertAlmostEqual(shares[1][4], 1)
        self.assertNotIn(3, shares[0])


if __name__ == "__main__":
    unittest.main()
