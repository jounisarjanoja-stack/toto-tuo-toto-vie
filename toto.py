"""Veikkauksen totokortti: lähdöt, hevoset ja peliosuudet.

Pelit ovat voittajarivejä (Toto4, Toto5, Toto64, Toto65, Toto75, Toto85,
Toto86 ja kahden lähdön Päivän Duo), yhden lähdön voittaja- ja sijapelejä
tai yhden lähdön järjestyspelejä (Kaksari, Troikka, Quarte+, Quinte+).
"""

import gzip
import json
import threading
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor

CARDS_URL = "https://www.veikkaus.fi/api/toto-info/v1/cards/active"
CARD_RACES = "https://www.veikkaus.fi/api/toto-info/v1/card/{card_id}/races"
CARD_POOLS = "https://www.veikkaus.fi/api/toto-info/v1/card/{card_id}/pools"
RACE_RUNNERS = "https://www.veikkaus.fi/api/toto-info/v1/race/{race_id}/runners"
POOL_ODDS = "https://www.veikkaus.fi/api/toto-info/v1/pool/{pool_id}/odds"

LIVE_MAX_AGE = 90
_lock = threading.Lock()
_cache = {}

# Järjestys on valikon järjestys. Toto75 pysyy mukana, vaikka sitä ei laajennuksessa nimetty.
GAMES = (
    {"id": "VOI", "name": "Voittaja", "kind": "winners", "pickRace": True},
    {"id": "SIJ", "name": "Sija", "kind": "place", "pickRace": True, "places": 3},
    {"id": "T4", "name": "Toto4", "kind": "winners"},
    {"id": "T5", "name": "Toto5", "kind": "winners"},
    {"id": "TRO", "name": "Troikka", "kind": "ordered", "places": 3},
    {"id": "KAK", "name": "Kaksari", "kind": "ordered", "places": 2},
    {"id": "DUO", "name": "Päivän Duo", "kind": "winners"},
    {"id": "QRT", "name": "Quarte+", "kind": "ordered", "places": 4},
    {"id": "QNT", "name": "Quinte+", "kind": "ordered", "places": 5},
    {"id": "T64", "name": "Toto64", "kind": "winners"},
    {"id": "T65", "name": "Toto65", "kind": "winners"},
    {"id": "T75", "name": "Toto75", "kind": "winners"},
    {"id": "T85", "name": "Toto85", "kind": "winners"},
    {"id": "T86", "name": "Toto86", "kind": "winners"},
)
GAME_BY_ID = {game["id"]: game for game in GAMES}


def _read_response(response):
    raw = response.read()
    encoding = (response.headers.get("Content-Encoding") or "").lower()
    if encoding == "gzip" or raw[:2] == b"\x1f\x8b":
        raw = gzip.decompress(raw)
    return raw


def veikkaus_json(url):
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/json",
            "Content-Type": "application/json",
            "X-ESA-API-Key": "ROBOT",
            "User-Agent": "toto75/1.0",
        },
    )
    with urllib.request.urlopen(request, timeout=25) as response:
        return json.loads(_read_response(response).decode("utf-8"))


def clear_cache():
    with _lock:
        _cache.clear()


def _collection(payload):
    if isinstance(payload, dict):
        return payload.get("collection") or []
    return payload or []


def _cards():
    return _collection(veikkaus_json(CARDS_URL))


def _open_types(cards):
    found = set()
    for card in cards:
        if card.get("cancelled"):
            continue
        found.update(card.get("pools") or [])
    return found


def _default_game(cards):
    open_types = _open_types(cards)
    if "T75" in open_types:
        return "T75"
    for game in GAMES:
        if game["id"] in open_types:
            return game["id"]
    return "T75"


def _matching_cards(cards, game_id):
    found = []
    for card in cards:
        if card.get("cancelled"):
            continue
        if game_id not in (card.get("pools") or []):
            continue
        found.append(card)
    found.sort(key=lambda card: ((card.get("country") != "FI"), card.get("firstRaceStart") or 0))
    return found


def _choose(cards, game_id, card_id):
    pool = _matching_cards(cards, game_id)
    game = GAME_BY_ID[game_id]
    if not pool:
        raise LookupError(f"Avoinna ei ole peliä {game['name']}.")
    if card_id is not None:
        for card in pool:
            if card.get("cardId") == card_id:
                return card
    return pool[0]


def _pick_race(game_info):
    return bool(game_info.get("pickRace")) or game_info["kind"] == "ordered"


def _odds_style(odds):
    rows = odds.get("odds") or []
    if not rows:
        return "empty"
    row = rows[0]
    if row.get("runnerNumber1") is not None and row.get("runnerNumber2") is not None and row.get("runnerNumber3") is None:
        return "duo"
    if row.get("percentage") is not None:
        return "percent"
    if row.get("runnerNumber") is not None:
        return "amount"
    return "empty"


def _amount_shares(odds):
    rows = odds.get("odds") or []
    net = odds.get("netSales") or sum((row.get("amount") or 0) for row in rows)
    shares = {}
    if not net:
        return shares
    for row in rows:
        number = row.get("runnerNumber")
        if number is None:
            continue
        shares[number] = (row.get("amount") or 0) / net
    return shares


def _amount_prices(rows):
    prices = {}
    for row in rows:
        number = row.get("runnerNumber")
        if number is None:
            continue
        low = row.get("minProbable")
        high = row.get("maxProbable")
        if low and high:
            prices[number] = (low + high) / 200
        elif row.get("probable"):
            prices[number] = row["probable"] / 100
        elif row.get("winProbable"):
            prices[number] = row["winProbable"] / 100
    return prices


def _duo_shares(odds):
    """Hevosen osuus Päivän Duon vaihdosta. Listalla näkymätön hevonen jää pois."""
    rows = odds.get("odds") or []
    net = odds.get("netSales") or 0
    legs = [{}, {}]
    if not net:
        return legs
    for row in rows:
        amount = row.get("amount") or 0
        for index, key in enumerate(("runnerNumber1", "runnerNumber2")):
            number = row.get(key)
            if number is None:
                continue
            legs[index][number] = legs[index].get(number, 0.0) + amount / net
    return legs


def _race_number(pool):
    races = pool.get("races") or []
    if not races:
        return 0
    return races[0].get("raceNumber") or 0


def _pick_pool(pools, game_id, race_number):
    candidates = [pool for pool in pools if pool.get("poolType") == game_id and pool.get("races")]
    if not candidates:
        game = GAME_BY_ID[game_id]
        raise LookupError(f"Kortilla ei ole peliä {game['name']}.")
    candidates.sort(key=_race_number)
    if race_number is not None:
        for pool in candidates:
            if _race_number(pool) == race_number:
                return pool, candidates
    return candidates[0], candidates


def _km(text):
    """Sekunnit ja onko kyse autolähdön ajasta. None, jos lukua ei ole."""
    import re

    raw = (text or "").strip().lower().replace(" ", "")
    match = re.match(r"(\d+)[,.](\d)", raw)
    if not match:
        return None
    seconds = int(match.group(1)) + int(match.group(2)) / 10
    return seconds, "a" in raw


def _records(block):
    auto = volt = None
    auto_text = volt_text = ""
    if not isinstance(block, dict):
        return auto, volt, auto_text, volt_text
    for key in ("record1", "record2"):
        text = block.get(key) or ""
        parsed = _km(text)
        if not parsed:
            continue
        seconds, is_auto = parsed
        if is_auto and (auto is None or seconds < auto):
            auto, auto_text = seconds, text
        if not is_auto and (volt is None or seconds < volt):
            volt, volt_text = seconds, text
    return auto, volt, auto_text, volt_text


def _year(block):
    if not isinstance(block, dict):
        return None
    starts = int(block.get("starts") or 0)
    return {
        "starts": starts,
        "wins": int(block.get("position1") or 0),
        "seconds": int(block.get("position2") or 0),
        "thirds": int(block.get("position3") or 0),
        "winRate": (block.get("winningPercent") or 0) / 100,
        "placeRate": (block.get("placementPercent") or 0) / 100,
        "gallop": (block.get("gallopPercent") or 0) / 100,
        "disq": (block.get("disqualificationPercent") or 0) / 100,
        "money": int(block.get("winMoney") or 0),
    }


def _driver_stats(text):
    import re

    match = re.search(r"(\d+)\s+(\d+)-(\d+)-(\d+)", text or "")
    if not match:
        return 0, 0
    return int(match.group(1)), int(match.group(2))


def _runner(row):
    stats = row.get("stats") or {}
    total = stats.get("total") if isinstance(stats, dict) else None
    auto, volt, auto_text, volt_text = _records(total or {})
    driver_starts, driver_wins = _driver_stats(row.get("driverStats"))
    starts = []
    for item in row.get("prevStarts") or []:
        parsed = _km(item.get("kmTime"))
        starts.append(
            {
                "date": item.get("shortMeetDate") or "",
                "when": item.get("meetDate") or "",
                "track": item.get("trackName") or "",
                "result": str(item.get("result") or "").strip(),
                "kmText": item.get("kmTime") or "",
                "km": None if parsed is None else parsed[0],
                "auto": False if parsed is None else parsed[1],
                "driver": item.get("driverFullName") or item.get("driver") or "",
                "prize": int(item.get("firstPrize") or 0),
                "distance": item.get("distance"),
                "post": item.get("startTrack"),
            }
        )
    starts.sort(key=lambda item: item["when"], reverse=True)
    return {
        "number": row.get("startNumber"),
        "name": row.get("horseName") or "",
        "driver": row.get("driverName") or "",
        "trainer": row.get("coachName") or "",
        "track": row.get("startTrack") or row.get("startNumber"),
        "distance": row.get("distance"),
        "scratched": bool(row.get("scratched")),
        "frontShoes": row.get("frontShoes") or "",
        "rearShoes": row.get("rearShoes") or "",
        "frontChanged": bool(row.get("frontShoesChanged")),
        "rearChanged": bool(row.get("rearShoesChanged")),
        "recordAuto": auto,
        "recordVolt": volt,
        "recordAutoText": auto_text,
        "recordVoltText": volt_text,
        "year": _year(stats.get("currentYear") if isinstance(stats, dict) else None),
        "previous": _year(stats.get("previousYear") if isinstance(stats, dict) else None),
        "total": _year(total),
        "driverStarts": driver_starts,
        "driverWins": driver_wins,
        "starts": starts[:10],
    }


def _runners(rows, scratched_numbers):
    """Poisjäänti voi tulla hevosen tai peliosuuden tiedosta. Molemmat riittävät."""
    runners = []
    for row in rows:
        runner = _runner(row)
        if runner.get("number") in scratched_numbers:
            runner["scratched"] = True
        runners.append(runner)
    return runners


def _combo_rows(odds, places):
    """Kaksarin ja troikan peliosuus on yhdistelmän osuus vaihdosta."""
    sales = int((odds or {}).get("netSales") or 0)
    first = {}
    combos = []
    for row in (odds or {}).get("odds") or []:
        numbers = tuple(row.get(f"runnerNumber{index}") for index in range(1, places + 1))
        if any(number is None for number in numbers):
            continue
        amount = int(row.get("amount") or 0)
        share = amount / sales if sales else 0
        probable = (row.get("probable") or 0) / 100
        combos.append({"numbers": numbers, "share": share, "odds": probable or None})
        first[numbers[0]] = first.get(numbers[0], 0) + share
    return first, combos


def _market(odds):
    shares = {}
    prices = {}
    for row in (odds or {}).get("odds") or []:
        number = row.get("runnerNumber")
        if number is None:
            continue
        if row.get("percentage") is not None:
            shares[number] = row["percentage"] / 10000
        probable = row.get("winProbable") or row.get("probable") or 0
        if probable:
            prices[number] = probable / 100
    return shares, prices


def load(card_id=None, game=None, race_number=None, refresh=False):
    now = time.time()
    if game in GAME_BY_ID and not refresh:
        key = (game, card_id or 0, race_number or 0)
        with _lock:
            cached = _cache.get(key)
            if cached and now - cached["loaded"] < LIVE_MAX_AGE:
                return cached["value"]

    cards = _cards()
    game_id = game if game in GAME_BY_ID else _default_game(cards)
    game_info = GAME_BY_ID[game_id]
    key = (game_id, card_id or 0, race_number or 0)
    if not refresh:
        with _lock:
            cached = _cache.get(key)
            if cached and now - cached["loaded"] < LIVE_MAX_AGE:
                return cached["value"]

    chosen = _choose(cards, game_id, card_id)
    cid = chosen["cardId"]
    races = _collection(veikkaus_json(CARD_RACES.format(card_id=cid)))
    pools = _collection(veikkaus_json(CARD_POOLS.format(card_id=cid)))
    selected, game_pools = _pick_pool(pools, game_id, race_number)

    by_id = {race["raceId"]: race for race in races}
    legs = []
    for index, leg in enumerate(sorted(selected.get("races") or [], key=lambda item: item.get("raceNumber") or 0), start=1):
        race = by_id.get(leg.get("raceId"))
        if race is None:
            continue
        legs.append((index, race))

    voi_pools = {}
    wanted = {race["raceId"] for _, race in legs}
    for pool in pools:
        if pool.get("poolType") != "VOI":
            continue
        for leg in pool.get("races") or []:
            if leg.get("raceId") in wanted:
                voi_pools[leg.get("raceId")] = pool["poolId"]

    with ThreadPoolExecutor(max_workers=6) as pool:
        runner_jobs = {
            pool.submit(veikkaus_json, RACE_RUNNERS.format(race_id=race["raceId"])): race["raceId"]
            for _, race in legs
        }
        odds_job = pool.submit(veikkaus_json, POOL_ODDS.format(pool_id=selected["poolId"]))
        voi_jobs = {
            pool.submit(veikkaus_json, POOL_ODDS.format(pool_id=pool_id)): race_id
            for race_id, pool_id in voi_pools.items()
        }
        runners = {race_id: _collection(job.result()) for job, race_id in runner_jobs.items()}
        odds = odds_job.result()
        voi = {}
        for job, race_id in voi_jobs.items():
            try:
                voi[race_id] = job.result()
            except (OSError, ValueError, TimeoutError):
                voi[race_id] = None

    places = game_info.get("places") or 1
    style = _odds_style(odds)
    if game_info["kind"] == "ordered":
        first_shares, combos = _combo_rows(odds, places)
    else:
        first_shares, combos = {}, []
    duo_shares = _duo_shares(odds) if style == "duo" and game_info["kind"] != "ordered" else []
    amount_shares = _amount_shares(odds) if style == "amount" else {}
    amount_prices = _amount_prices(odds.get("odds") or []) if style == "amount" else {}
    shares, _prices = _market(odds)
    scratched_odds = {}
    for row in (odds.get("odds") or []):
        if row.get("scratched"):
            scratched_odds.setdefault(row.get("raceId"), set()).add(row.get("runnerNumber"))
    built_races = []
    for index, race in legs:
        voi_odds = voi.get(race["raceId"]) or {}
        _share, win_prices = _market(voi_odds)
        out = scratched_odds.get(race["raceId"], set())
        sales_cents = int((voi_odds or {}).get("netSales") or 0)
        prices = win_prices
        if game_info["kind"] == "ordered":
            race_shares = dict(first_shares)
            race_combos = combos
        elif duo_shares:
            race_combos = []
            race_shares = duo_shares[index - 1] if index - 1 < len(duo_shares) else {}
        elif amount_shares or style == "amount":
            race_combos = []
            race_shares = dict(amount_shares)
            prices = amount_prices
            sales_cents = int(odds.get("netSales") or selected.get("netSales") or 0)
        else:
            race_combos = []
            race_shares = {
                row.get("runnerNumber"): row.get("percentage") / 10000
                for row in (odds.get("odds") or [])
                if row.get("raceId") == race["raceId"] and row.get("percentage") is not None
            }
            if not race_shares:
                race_shares = {
                    number: share
                    for number, share in shares.items()
                    if any(item.get("startNumber") == number for item in runners.get(race["raceId"]) or [])
                }
        built_races.append(
            {
                "raceId": race["raceId"],
                "leg": index,
                "number": race.get("number"),
                "distance": race.get("distance"),
                "startType": race.get("startType") or "",
                "breed": race.get("breed") or "",
                "title": race.get("seriesSpecification") or "",
                "firstPrize": int(race.get("firstPrize") or 0),
                "monte": bool(race.get("monte")),
                "startMs": race.get("startTime"),
                "salesCents": sales_cents,
                "runners": _runners(runners.get(race["raceId"]) or [], out),
                "market": race_shares,
                "odds": prices,
                "combos": race_combos,
            }
        )

    open_types = _open_types(cards)
    options = [
        {
            "id": card["cardId"],
            "track": card.get("trackName") or "",
            "country": card.get("country") or "",
            "date": card.get("meetDate") or "",
            "startMs": card.get("firstRaceStart"),
        }
        for card in _matching_cards(cards, game_id)
    ]
    race_options = [
        {
            "number": _race_number(pool),
            "salesCents": int(pool.get("netSales") or 0),
            "selected": pool.get("poolId") == selected.get("poolId"),
        }
        for pool in game_pools
    ]
    rules = selected.get("rules") or {}
    payload = {
        "game": {
            "id": game_info["id"],
            "name": game_info["name"],
            "kind": game_info["kind"],
            "places": game_info.get("places") or 0,
            "pickRace": _pick_race(game_info),
        },
        "games": [
            {"id": item["id"], "name": item["name"], "open": item["id"] in open_types}
            for item in GAMES
        ],
        "card": {
            "id": cid,
            "track": chosen.get("trackName") or "",
            "country": chosen.get("country") or "",
            "date": chosen.get("meetDate") or "",
            "startMs": selected.get("firstRaceStartTime") or chosen.get("firstRaceStart"),
        },
        "options": options,
        "raceOptions": race_options,
        "pool": {
            "id": selected.get("poolId"),
            "salesCents": int(selected.get("netSales") or 0),
            "netCents": int(selected.get("netPool") or 0),
            "jackpotCents": int(selected.get("jackpot") or 0),
            "minStakeCents": int(rules.get("minimumStake") or 5),
            "cents": bool(rules.get("allowsCentsWagering", True)),
        },
        "races": built_races,
    }
    stored = (game_id, card_id or 0, race_number or 0)
    resolved = (game_id, cid, _race_number(selected) if _pick_race(game_info) else 0)
    with _lock:
        packed = {"loaded": time.time(), "value": payload}
        _cache[stored] = packed
        _cache[resolved] = packed
    return payload
