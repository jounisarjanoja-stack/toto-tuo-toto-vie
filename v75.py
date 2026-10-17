"""Sivun kooste: kortti, arviot ja rivit."""

from datetime import datetime
from zoneinfo import ZoneInfo

import toto
import v75model
import v75system

HELSINKI = ZoneInfo("Europe/Helsinki")
WEEKDAYS = ["maanantai", "tiistai", "keskiviikko", "torstai", "perjantai", "lauantai", "sunnuntai"]
STAKES = (0.05, 0.10, 0.20, 0.50, 1.0)
STARTS = {"CAR_START": "autolähtö", "VOLT_START": "volttilähtö"}
BREEDS = {"L": "lämminveriset", "K": "kylmäveriset"}
COUNT_WORDS = {
    1: "yksi",
    2: "kaksi",
    3: "kolme",
    4: "neljä",
    5: "viisi",
    6: "kuusi",
    7: "seitsemän",
    8: "kahdeksan",
}


def _when(ms):
    if not ms:
        return ""
    moment = datetime.fromtimestamp(ms / 1000, HELSINKI)
    return f"{WEEKDAYS[moment.weekday()]} {moment.day}.{moment.month}. klo {moment.hour:02d}.{moment.minute:02d}"


def _day(iso):
    if not iso:
        return ""
    year, month, day = (int(part) for part in iso.split("-"))
    moment = datetime(year, month, day)
    return f"{WEEKDAYS[moment.weekday()]} {day}.{month}."


def _euros(cents):
    return round((cents or 0) / 100, 2)


def _round(value, digits=4):
    if value is None:
        return None
    return round(value, digits)


def _horse_out(horse, base_distance):
    distance = horse.get("distance")
    extra = None
    if distance and base_distance and distance > base_distance:
        extra = distance - base_distance
    year = horse.get("year") or {}
    payload = {
        "number": horse.get("number"),
        "name": horse.get("name") or "",
        "driver": horse.get("driver") or "",
        "trainer": horse.get("trainer") or "",
        "track": horse.get("track"),
        "distance": distance,
        "extra": extra,
        "scratched": bool(horse.get("scratched")),
        "ai": _round(horse.get("ai")),
        "place": _round(horse.get("place")),
        "market": _round(horse.get("market")),
        "edge": _round(horse.get("edge")),
        "label": horse.get("label") or "",
        "certainty": horse.get("certainty"),
        "varma": bool(horse.get("varma")),
        "favorite": bool(horse.get("favorite")),
        "likely": bool(horse.get("likely")),
        "gallop": horse.get("gallop"),
        "trip": horse.get("trip"),
        "models": None
        if not horse.get("models")
        else {key: _round(value) for key, value in horse["models"].items()},
        "parts": horse.get("parts"),
        "recordAuto": horse.get("recordAuto") or "",
        "recordVolt": horse.get("recordVolt") or "",
        "shoes": horse.get("shoes") or "",
        "odds": _round(horse.get("odds"), 2),
        "year": None
        if not year
        else {
            "starts": year.get("starts") or 0,
            "wins": year.get("wins") or 0,
            "seconds": year.get("seconds") or 0,
            "thirds": year.get("thirds") or 0,
            "winRate": _round(year.get("winRate"), 3),
            "placeRate": _round(year.get("placeRate"), 3),
            "gallop": _round(year.get("gallop"), 3),
        },
        "driverStarts": horse.get("driverStarts") or 0,
        "driverWins": horse.get("driverWins") or 0,
        "starts": [
            {
                "date": item.get("date") or "",
                "track": item.get("track") or "",
                "result": item.get("result") or "",
                "km": item.get("kmText") or "",
                "driver": item.get("driver") or "",
                "distance": item.get("distance"),
            }
            for item in (horse.get("starts") or [])[:8]
        ],
    }
    return payload


def _system_out(system):
    return {
        "profile": system["profile"],
        "title": system["title"],
        "budget": system["budget"],
        "stake": system["stake"],
        "rows": system["rows"],
        "cost": system["cost"],
        "hit": _round(system["hit"]),
        "formula": system["formula"],
        "mode": system.get("mode") or "winners",
        "box": bool(system.get("box")),
        "hitLabel": system.get("hitLabel") or "",
        "lines": [
            {
                "picks": line["picks"],
                "ai": _round(line.get("ai")),
                "market": _round(line.get("market")),
            }
            for line in system.get("lines") or []
        ],
        "legs": [
            {
                "leg": leg["leg"],
                "raceNumber": leg["raceNumber"],
                "picks": leg["picks"],
                "varma": leg["varma"],
                "covered": _round(leg["covered"]),
            }
            for leg in system["legs"]
        ],
        "skipped": [
            {
                "leg": note["leg"],
                "raceNumber": note["raceNumber"],
                "number": note["number"],
                "name": note["name"],
                "ai": _round(note["ai"]),
                "market": _round(note["market"]),
            }
            for note in system["notes"]
            if isinstance(note, dict)
        ],
        "message": next((note for note in system["notes"] if isinstance(note, str)), ""),
    }


def _scratches(race):
    return [
        {
            "leg": race["leg"],
            "raceNumber": race["number"],
            "number": horse.get("number"),
            "name": horse.get("name") or "",
        }
        for horse in race["horses"]
        if horse.get("scratched")
    ]


def _spotlight(races):
    rows = []
    for race in races:
        for horse in race["horses"]:
            if horse.get("scratched") or horse.get("edge") is None:
                continue
            rows.append((race, horse))
    under = [
        item
        for item in rows
        if item[1]["edge"] >= 0.04 and item[1]["ai"] >= 0.08 and item[1]["market"] >= 0.02
    ]
    over = [item for item in rows if item[1]["edge"] <= -0.06 and item[1]["market"] >= 0.10]
    under.sort(key=lambda item: item[1]["edge"], reverse=True)
    over.sort(key=lambda item: item[1]["edge"])
    picked = under[:3] + over[:2]

    def pack(race, horse):
        return {
            "leg": race["leg"],
            "raceNumber": race["number"],
            "number": horse["number"],
            "name": horse["name"],
            "ai": _round(horse["ai"]),
            "market": _round(horse["market"]),
            "edge": _round(horse["edge"]),
            "label": horse["label"],
        }

    return [pack(race, horse) for race, horse in picked]


def _in_the_money(probs, places):
    """Todennäköisyys olla sijoilla 1..places. Summa on paikkojen määrä."""
    numbers = [number for number, prob in probs.items() if prob > 0]
    slots = min(places, len(numbers))
    chance = {number: 0.0 for number in probs}
    if slots <= 0:
        return chance

    def walk(used, used_prob, path_prob, depth):
        if depth == slots or used_prob >= 1 - 1e-12:
            return
        for number in numbers:
            if number in used:
                continue
            step = path_prob * probs[number] / (1 - used_prob)
            chance[number] += step
            used.add(number)
            walk(used, used_prob + probs[number], step, depth + 1)
            used.remove(number)

    walk(set(), 0.0, 1.0, 0)
    return chance


def _apply_place(horses, market, places):
    """Sijapelin malli on sijoittumistodennäköisyys jaettuna sijojen määrällä, jotta se on samassa mitassa kuin potin osuus."""
    market = market or {}
    active = [horse for horse in horses if horse.get("ai") and not horse.get("scratched")]
    chances = _in_the_money({horse["number"]: horse["ai"] for horse in active}, places)
    for horse in active:
        chance = chances.get(horse["number"], 0.0)
        fair = chance / places if places else 0.0
        share = market.get(horse["number"])
        horse["place"] = chance
        horse["ai"] = fair
        horse["market"] = share
        horse["edge"] = None if share is None else fair - share
        horse["label"] = v75model._edge_label(fair, share)
    horses.sort(key=lambda horse: (bool(horse.get("scratched")), -(horse.get("ai") or 0)))
    priced = [horse for horse in active if horse.get("market") is not None]
    favorite = max(priced, key=lambda horse: horse["market"])["number"] if priced else None
    likely = max(active, key=lambda horse: horse["ai"])["number"] if active else None
    for horse in horses:
        horse["favorite"] = horse.get("number") == favorite
        horse["likely"] = horse.get("number") == likely and not horse.get("scratched")


def _hit_label(game, legs):
    if game["kind"] == "place":
        return "Sijat mukana"
    if game["kind"] == "ordered":
        places = game.get("places") or 2
        return {
            2: "Oikea järjestys mukana",
            3: "Oikea kolmen kärki mukana",
            4: "Oikea neljän kärki mukana",
            5: "Oikea viiden kärki mukana",
        }.get(places, "Oikea järjestys mukana")
    if legs == 1:
        return "Voittaja mukana"
    if legs == 2:
        return "Molemmat voittajat mukana"
    word = COUNT_WORDS.get(legs, str(legs))
    return f"Kaikki {word} voittajaa mukana"


def _offered_stakes(min_stake):
    offered = [item for item in STAKES if item + 1e-9 >= min_stake]
    if not offered:
        offered = [round(min_stake, 2)]
    return offered


def build(card_id=None, refresh=False, stake=0.10, game=None, race_number=None):
    raw = toto.load(card_id=card_id, game=game, race_number=race_number, refresh=refresh)
    min_stake = max(0.05, _euros(raw["pool"]["minStakeCents"]))
    offered = _offered_stakes(min_stake)
    if stake not in offered:
        stake = min(offered, key=lambda item: abs(item - max(stake, min_stake)))
    races = []
    for race in raw["races"]:
        odds = race.get("odds") if (race.get("salesCents") or 0) >= 5000 else {}
        if raw["game"]["kind"] == "place":
            horses = v75model.analyze_race(race["runners"], race, None, odds)
            _apply_place(horses, race.get("market"), raw["game"].get("places") or 3)
        else:
            horses = v75model.analyze_race(race["runners"], race, race.get("market"), odds)
        base = race.get("distance") or 0
        distances = [horse.get("distance") or base for horse in race["runners"] if horse.get("distance")]
        if distances:
            base = min(distances)
        races.append(
            {
                "leg": race["leg"],
                "number": race["number"],
                "distance": race.get("distance"),
                "baseDistance": base,
                "startType": race.get("startType") or "",
                "start": STARTS.get(race.get("startType"), "lähtö"),
                "breed": BREEDS.get(race.get("breed"), ""),
                "title": race.get("title") or "",
                "prize": _euros(race.get("firstPrize")),
                "monte": race.get("monte") or False,
                "horses": horses,
                "combos": race.get("combos") or [],
            }
        )
    game_info = raw["game"]
    systems = v75system.build_all(
        races,
        stake,
        kind=game_info["kind"],
        places=game_info.get("places") or 2,
        hit_label=_hit_label(game_info, len(races)),
    )
    card = raw["card"]
    pool = raw["pool"]
    return {
        "game": {
            "id": game_info["id"],
            "name": game_info["name"],
            "kind": game_info["kind"],
            "places": game_info.get("places") or 0,
            "pickRace": bool(game_info.get("pickRace")),
        },
        "games": [
            {"id": item["id"], "name": item["name"], "open": item["open"], "selected": item["id"] == game_info["id"]}
            for item in raw["games"]
        ],
        "card": {
            "id": card["id"],
            "track": card["track"],
            "country": card["country"],
            "date": card["date"],
            "dateText": _day(card["date"]),
            "startText": _when(card["startMs"]),
            "clock": _when(card["startMs"]).split("klo ")[-1] if card.get("startMs") else "",
        },
        "options": [
            {
                "id": option["id"],
                "track": option["track"],
                "country": option["country"],
                "dateText": _day(option["date"]),
                "selected": option["id"] == card["id"],
            }
            for option in raw["options"]
        ],
        "pool": {
            "sales": _euros(pool["salesCents"]),
            "net": _euros(pool["netCents"]),
            "jackpot": _euros(pool["jackpotCents"]),
            "minStake": min_stake,
            "thin": _euros(pool["salesCents"]) < 500,
        },
        "raceOptions": [
            {
                "number": option["number"],
                "sales": _euros(option.get("salesCents")),
                "selected": option.get("selected"),
            }
            for option in raw.get("raceOptions") or []
        ],
        "stake": stake,
        "stakes": offered,
        "budgets": list(v75system.BUDGETS),
        "spotlight": _spotlight(races),
        "scratches": [item for race in races for item in _scratches(race)],
        "races": [
            {
                "leg": race["leg"],
                "number": race["number"],
                "distance": race["distance"],
                "start": race["start"],
                "breed": race["breed"],
                "title": race["title"],
                "prize": race["prize"],
                "monte": race["monte"],
                "scratches": _scratches(race),
                "horses": [_horse_out(horse, race["baseDistance"]) for horse in race["horses"]],
            }
            for race in races
        ],
        "systems": {
            profile: {budget: _system_out(system) for budget, system in budgets.items()}
            for profile, budgets in systems.items()
        },
    }
