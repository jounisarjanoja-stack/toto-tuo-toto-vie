"""Toto75-voittotodennäköisyys ilman peliosuutta.

Neljä laskuria painottavat eri asioita. Peliosuus tulee mukaan vasta
vertailussa, jotta ero markkinaan ei ole mallin oma syöte.
"""

import math
from statistics import median, pstdev

TEMPERATURE = 0.22
WEIGHTS = {"vire": 0.34, "luokka": 0.24, "ohjastaja": 0.24, "lahto": 0.18}

CAR_POST = {1: 0.74, 2: 0.86, 3: 0.90, 4: 0.84, 5: 0.76, 6: 0.68, 7: 0.60, 8: 0.52}
VOLT_POST = {1: 0.92, 2: 0.86, 3: 0.78, 4: 0.68, 5: 0.58, 6: 0.48, 7: 0.40}


def clip(value, low=0.0, high=1.0):
    return max(low, min(high, value))


def same_person(left, right):
    def norm(value):
        return " ".join((value or "").lower().replace(".", " ").split())

    a, b = norm(left), norm(right)
    if not a or not b:
        return False
    if a == b or a in b or b in a:
        return True
    a_parts, b_parts = a.split(), b.split()
    if a_parts[-1] != b_parts[-1]:
        return False
    return a_parts[0][0] == b_parts[0][0]


def _position_score(result):
    text = str(result or "").strip().lower()
    if not text.isdigit():
        return 0.0
    place = int(text)
    table = {1: 1.0, 2: 0.72, 3: 0.55, 4: 0.40, 5: 0.28, 6: 0.18, 7: 0.12, 8: 0.08}
    if place <= 0:
        return 0.0
    return table.get(place, 0.05)


def _weighted(starts, score_of):
    total = 0.0
    weight = 0.0
    for index, start in enumerate(starts[:8]):
        share = 0.64 ** index
        total += score_of(start) * share
        weight += share
    if weight <= 0:
        return None
    return total / weight


def _softmax(scores):
    if not scores:
        return []
    peak = max(scores)
    shifted = [math.exp((score - peak) / TEMPERATURE) for score in scores]
    total = sum(shifted) or 1
    return [item / total for item in shifted]


def _post_score(start_type, track):
    track = int(track or 8)
    table = VOLT_POST if start_type == "VOLT_START" else CAR_POST
    if track in table:
        return table[track]
    return 0.32 if start_type == "VOLT_START" else 0.34


def _trip(start_type, track, positions, extra, starts):
    track = int(track or 8)
    if start_type == "VOLT_START":
        if track <= 2:
            base = 0.06
        elif track <= 4:
            base = 0.16
        elif track <= 6:
            base = 0.34
        else:
            base = 0.55
    elif track <= 5:
        base = 0.08
    elif track <= 8:
        base = 0.22
    elif track <= 12:
        base = 0.42
    else:
        base = 0.58
    erratic = 0.0
    if len(positions) >= 4:
        spread = pstdev(positions)
        if spread >= 3.2:
            erratic = 0.16
        elif spread >= 2.5:
            erratic = 0.08
    handicap = 0.12 if extra >= 40 else 0.06 if extra >= 20 else 0.0
    wins = [item for item in starts if str(item.get("result")) == "1" and item.get("post")]
    if wins and all((item.get("post") or 9) <= 4 for item in wins) and track >= 8:
        erratic += 0.12
    return clip(base + erratic + handicap)


def _band(value, mild=0.10, hard=0.22):
    if value < mild:
        return "pieni"
    if value < hard:
        return "kohtalainen"
    return "suuri"


def _shrink_rate(rate, starts, prior, strength):
    starts = max(0, starts or 0)
    return ((rate or 0) * starts + prior * strength) / (starts + strength)


def _edge_label(ai, market):
    if market is None:
        return "ei markkinaa"
    edge = ai - market
    # Pieni peliosuus ja parin prosentin ero ei vielä ole pelillinen poikkeama.
    if edge >= 0.04 and ai >= 0.08 and market >= 0.02:
        return "alipelattu"
    if edge <= -0.05 and market >= 0.08:
        return "ylipelattu"
    return "linjassa"


def _features(horse, race, field):
    starts = horse.get("starts") or []
    auto_race = race["startType"] != "VOLT_START"
    form = _weighted(starts, lambda item: _position_score(item.get("result")))
    if form is None:
        form = 0.42

    times = [item["km"] for item in starts[:6] if item.get("km") and item.get("auto") == auto_race]
    time_score = 0.5
    if times and field["time"] is not None:
        own = median(times)
        time_score = clip(0.5 + (field["time"] - own) / 1.2)

    recent = [_position_score(item.get("result")) for item in starts[:3]]
    older = [_position_score(item.get("result")) for item in starts[3:7]]
    if recent and older:
        trend = clip(0.5 + (sum(recent) / len(recent) - sum(older) / len(older)))
    else:
        trend = 0.5

    prizes = [item["prize"] for item in starts[:5] if item.get("prize")]
    today = race.get("firstPrize") or 0
    if prizes and today:
        class_move = clip(0.5 + 0.18 * math.log((median(prizes) + 1) / (today + 1)))
    else:
        class_move = 0.5
    vire = 0.58 * form + 0.24 * time_score + 0.10 * trend + 0.08 * class_move

    year = horse.get("year") or {}
    win_rate = _shrink_rate(year.get("winRate"), year.get("starts"), 0.12, 8)
    win_score = clip((win_rate - 0.04) / 0.28)
    money = (year.get("money") or 0) / 100
    per_start = money / max(year.get("starts") or 0, 1)
    if field["earn"] and per_start > 0:
        earn_score = clip(0.5 + (math.log(per_start) - math.log(field["earn"])) / 1.2)
    elif year:
        earn_score = 0.45
    else:
        earn_score = 0.4
    record = horse.get("recordAuto") if auto_race else horse.get("recordVolt")
    if record and field["record"]:
        record_score = clip(0.5 + (field["record"] - record) / 1.4)
    else:
        record_score = 0.48
    place_score = clip((year.get("placeRate") or 0) / 0.70)
    if not year:
        luokka = 0.40
    else:
        luokka = 0.34 * win_score + 0.28 * earn_score + 0.28 * record_score + 0.10 * place_score

    driver_rate = _shrink_rate(
        (horse.get("driverWins") or 0) / horse["driverStarts"] if horse.get("driverStarts") else 0.10,
        horse.get("driverStarts"),
        0.10,
        200,
    )
    driver_score = clip((driver_rate - 0.05) / 0.14)
    together = [item for item in starts if same_person(item.get("driver"), horse.get("driver"))]
    if together:
        partner = sum(_position_score(item.get("result")) for item in together) / len(together)
    else:
        partner = 0.48
    previous = horse.get("previous") or {}
    if year and previous and previous.get("starts"):
        delta = clip(0.5 + ((year.get("winRate") or 0) - (previous.get("winRate") or 0)) / 0.50)
    else:
        delta = 0.5
    ohjastaja = 0.46 * driver_score + 0.34 * partner + 0.20 * delta

    extra = max(0, (horse.get("distance") or race.get("distance") or 0) - field["distance"])
    distance_score = clip(1 - extra / 80)
    bare = horse.get("frontShoes") == "NO_SHOES"
    shoe = 0.55
    if bare:
        shoe = 0.84 if horse.get("frontChanged") else 0.72
    if horse.get("rearShoes") == "NO_SHOES":
        shoe = min(1, shoe + 0.04)
    lahto = 0.46 * _post_score(race["startType"], horse.get("track")) + 0.22 * distance_score + 0.16 * shoe + 0.16 * record_score

    gallop = _shrink_rate(max(year.get("gallop") or 0, year.get("disq") or 0), year.get("starts"), 0.08, 4)
    finished = [item for item in starts[:8] if str(item.get("result") or "").strip()]
    dnf = 0
    if finished:
        dnf = sum(1 for item in finished if not str(item["result"]).isdigit()) / len(finished)
    gallop = clip(0.72 * gallop + 0.28 * dnf)

    positions = [int(item["result"]) for item in starts[:8] if str(item.get("result") or "").isdigit()]
    trip = _trip(race["startType"], horse.get("track"), positions, extra, starts)

    conditions = clip(
        0.42 * _post_score(race["startType"], horse.get("track"))
        + 0.28 * distance_score
        + 0.30 * record_score
    )
    top3 = [item for item in starts[:8] if str(item.get("result") or "").isdigit() and int(item["result"]) <= 3]
    recent_place = (len(top3) / min(len(starts), 8)) if starts else (year.get("placeRate") or 0.3)

    return {
        "vire": clip(vire),
        "luokka": clip(luokka),
        "ohjastaja": clip(ohjastaja),
        "lahto": clip(lahto),
        "form": clip(form),
        "conditions": conditions,
        "gallop": gallop,
        "trip": trip,
        "recentPlace": clip(recent_place),
        "placeRate": year.get("placeRate") or 0,
    }


def _field(horses, race):
    auto_race = race["startType"] != "VOLT_START"
    times = []
    records = []
    earns = []
    distances = []
    for horse in horses:
        if horse.get("scratched"):
            continue
        own = [item["km"] for item in (horse.get("starts") or [])[:6] if item.get("km") and item.get("auto") == auto_race]
        if own:
            times.append(median(own))
        record = horse.get("recordAuto") if auto_race else horse.get("recordVolt")
        if record:
            records.append(record)
        year = horse.get("year") or {}
        if year.get("starts") and year.get("money"):
            earns.append((year["money"] / 100) / year["starts"])
        if horse.get("distance"):
            distances.append(horse["distance"])
    return {
        "time": median(times) if times else None,
        "record": median(records) if records else None,
        "earn": median(earns) if earns else None,
        "distance": min(distances) if distances else (race.get("distance") or 0),
    }


def _model_agreement(index, model_probs):
    """Ykkössijan yksimielisyys ja todennäköisyyksien läheisyys."""
    probs = [model_probs[name][index] for name in WEIGHTS]
    firsts = sum(1 for name in WEIGHTS if abs(model_probs[name][index] - max(model_probs[name])) < 1e-12)
    rank_part = firsts / len(WEIGHTS)
    close = 1 - min(1, (max(probs) - min(probs)) / 0.45)
    return clip(0.72 * rank_part + 0.28 * close)


def _certainty(ai, place, features, market, agreement):
    if market is None:
        confirm = 0.45
    else:
        close = 1 - min(1, abs(ai - market) / 0.28)
        height = min(1, market / 0.35)
        confirm = close * (0.35 + 0.65 * height)
    raw = {
        "win": 46 * min(1, ai / 0.55),
        "agreement": 14 * agreement,
        "market": 12 * confirm,
        "conditions": 10 * features["conditions"],
        "form": 10 * features["form"],
        "place": 8 * min(1, place / 0.85),
        "gallop": -14 * features["gallop"],
        "trip": -10 * features["trip"],
    }
    parts = {key: int(round(value)) for key, value in raw.items()}
    score = max(0, min(100, sum(parts.values())))
    return score, parts, agreement


def analyze_race(horses, race, market=None, odds=None):
    """Palauta hevoset voittotodennäköisyyksineen. Summa on 1."""
    market = market or {}
    odds = odds or {}
    active = [horse for horse in horses if not horse.get("scratched") and horse.get("number") is not None]
    if not active:
        return []
    field = _field(active, race)
    prepared = [(horse, _features(horse, race, field)) for horse in active]
    model_probs = {
        name: _softmax([features[name] for _horse, features in prepared])
        for name in WEIGHTS
    }
    raw_market = []
    for horse, _features_row in prepared:
        share = market.get(horse["number"])
        raw_market.append(0 if share is None else share)
    market_total = sum(raw_market)
    consensus = []
    for index, (_horse, _features_row) in enumerate(prepared):
        consensus.append(sum(WEIGHTS[name] * model_probs[name][index] for name in WEIGHTS))
    total = sum(consensus) or 1
    ranked = sorted(consensus, reverse=True)
    second = ranked[1] if len(ranked) > 1 else 0
    leader = ranked[0] if ranked else 0

    rows = []
    for index, (horse, features) in enumerate(prepared):
        ai = consensus[index] / total
        share = None if market_total <= 0 else raw_market[index] / market_total
        place = clip(max(ai, 0.45 * features["recentPlace"] + 0.25 * features["placeRate"] + 0.30 * min(0.95, ai * 2.3)), ai, 0.96)
        agreement = _model_agreement(index, model_probs)
        score, parts, agreement = _certainty(ai, place, features, share, agreement)
        edge = None if share is None else ai - share
        label = _edge_label(ai, share)
        varma = (
            score >= 78
            and ai >= 0.40
            and abs(ai - leader) < 1e-9
            and ai - second >= 0.08
            and (edge is None or edge >= -0.04)
            and features["gallop"] < 0.20
            and agreement >= 0.58
            and features["trip"] < 0.55
        )
        rows.append(
            {
                "number": horse["number"],
                "name": horse.get("name") or "",
                "driver": horse.get("driver") or "",
                "trainer": horse.get("trainer") or "",
                "track": horse.get("track"),
                "distance": horse.get("distance"),
                "scratched": False,
                "ai": ai,
                "place": place,
                "market": share,
                "edge": edge,
                "ratio": None if not share else ai / share,
                "label": label,
                "certainty": score,
                "parts": parts,
                "varma": varma,
                "gallop": {"value": features["gallop"], "label": _band(features["gallop"])},
                "trip": {"value": features["trip"], "label": _band(features["trip"], 0.18, 0.40)},
                "models": {name: model_probs[name][index] for name in WEIGHTS},
                "recordAuto": horse.get("recordAutoText") or "",
                "recordVolt": horse.get("recordVoltText") or "",
                "year": horse.get("year"),
                "driverStarts": horse.get("driverStarts") or 0,
                "driverWins": horse.get("driverWins") or 0,
                "odds": odds.get(horse["number"]),
                "shoes": _shoes(horse),
                "starts": horse.get("starts") or [],
                "agreement": agreement,
            }
        )
    rows.sort(key=lambda item: item["ai"], reverse=True)
    favorite_number = None
    priced = [row for row in rows if row["market"] is not None]
    if priced:
        favorite_number = max(priced, key=lambda item: item["market"])["number"]
    likely_number = rows[0]["number"] if rows else None
    for row in rows:
        row["favorite"] = row["number"] == favorite_number
        row["likely"] = row["number"] == likely_number
    scratched = []
    for horse in horses:
        if not horse.get("scratched"):
            continue
        scratched.append(
            {
                "number": horse.get("number"),
                "name": horse.get("name") or "",
                "driver": horse.get("driver") or "",
                "trainer": horse.get("trainer") or "",
                "track": horse.get("track"),
                "distance": horse.get("distance"),
                "scratched": True,
                "ai": None,
                "market": None,
                "edge": None,
                "label": "pois",
                "certainty": None,
                "varma": False,
                "starts": [],
            }
        )
    rows.extend(scratched)
    return rows


def _shoes(horse):
    front = horse.get("frontShoes") == "NO_SHOES"
    rear = horse.get("rearShoes") == "NO_SHOES"
    if front and rear:
        text = "kengätön"
    elif front:
        text = "edestä kengätön"
    elif rear:
        text = "takaa kengätön"
    else:
        text = ""
    if horse.get("frontChanged") or horse.get("rearChanged"):
        text = (text + " · varustemuutos").strip(" ·")
    return text
