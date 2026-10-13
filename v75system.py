"""Rivi budjetin sisään.

Voittajapeleissä jokainen lähtö on rankingin etuliite. Järjestyspeleissä
laatikko on samojen hevosten kaikki järjestykset. Jos laatikko ei mahdu
budjettiin, riviin otetaan todennäköisimmät yksittäiset järjestykset
ilman että kaikki yhdistelmät pidetään muistissa.
"""

import heapq
import itertools

BUDGETS = (5, 10, 20, 50, 100)
PROFILES = ("turvallinen", "tasapainoinen", "rohkea")
TITLES = {
    "turvallinen": "Turvallinen",
    "tasapainoinen": "Tasapainoinen",
    "rohkea": "Rohkea",
}


def _value_key(horse):
    edge = horse.get("edge") or 0
    return horse["ai"] + 1.15 * max(edge, 0) - 0.85 * max(-edge, 0)


def _rank(horses, profile):
    active = [horse for horse in horses if not horse.get("scratched") and horse.get("ai")]
    if profile == "turvallinen":
        active.sort(key=lambda horse: horse["ai"], reverse=True)
        return active, None
    if profile == "tasapainoinen":
        active.sort(
            key=lambda horse: horse["ai"] + 0.70 * max(horse.get("edge") or 0, 0) - 0.30 * max(-(horse.get("edge") or 0), 0),
            reverse=True,
        )
        return active, None

    favorite = max(active, key=lambda horse: horse.get("market") or 0, default=None)
    rest = [horse for horse in active if horse is not favorite]
    rest.sort(key=_value_key, reverse=True)
    overbet = (
        favorite
        and favorite.get("label") == "ylipelattu"
        and (favorite.get("market") or 0) >= 0.15
    )
    if not overbet:
        active.sort(key=_value_key, reverse=True)
        return active, None
    # Heikko suosikki jää kokonaan pois. Vahvempi suosikki ei saa olla pankki,
    # mutta se tulee mukaan heti toisena, jos rivejä riittää.
    if favorite["ai"] < 0.12:
        return rest, favorite
    if not rest:
        return [favorite], None
    return [rest[0], favorite, *rest[1:]], favorite


def _allocate(rankings, max_rows):
    """Suurin osumistodennäköisyys, kun jokainen lähtö on rankingin etuliite."""
    dp = {1: (1.0, ())}
    for horses in rankings:
        cumulative = []
        covered = 0.0
        for horse in horses:
            covered += horse["ai"]
            cumulative.append(covered)
        if not cumulative:
            return None
        nxt = {}
        for rows, (hit, choice) in dp.items():
            for size, cover in enumerate(cumulative, start=1):
                used = rows * size
                if used > max_rows:
                    continue
                score = hit * cover
                current = nxt.get(used)
                if current is None or score > current[0]:
                    nxt[used] = (score, choice + (size,))
        if not nxt:
            return None
        dp = nxt
    rows, (hit, choice) = max(dp.items(), key=lambda item: (item[1][0], -item[0]))
    return rows, hit, choice


def build_one(races, profile, budget, stake):
    if stake <= 0 or budget < stake:
        return {
            "profile": profile,
            "title": TITLES[profile],
            "budget": budget,
            "stake": stake,
            "rows": 0,
            "cost": 0,
            "hit": None,
            "legs": [],
            "notes": ["Budjetti ei riitä yhteen riviin."],
            "formula": "",
        }
    max_rows = int(budget / stake + 1e-9)
    rankings = []
    skipped = []
    for race in races:
        ordered, left_out = _rank(race["horses"], profile)
        rankings.append(ordered)
        if left_out:
            skipped.append((race, left_out))
    found = _allocate(rankings, max_rows)
    if found is None:
        return {
            "profile": profile,
            "title": TITLES[profile],
            "budget": budget,
            "stake": stake,
            "rows": 0,
            "cost": 0,
            "hit": None,
            "legs": [],
            "notes": ["Riviä ei voitu koota."],
            "formula": "",
        }
    rows, hit, sizes = found
    legs = []
    for race, ordered, size in zip(races, rankings, sizes):
        picks = ordered[:size]
        covered = sum(horse["ai"] for horse in picks)
        banker = len(picks) == 1 and picks[0].get("varma")
        legs.append(
            {
                "leg": race["leg"],
                "raceNumber": race["number"],
                "picks": [horse["number"] for horse in picks],
                "names": [horse["name"] for horse in picks],
                "varma": banker,
                "covered": covered,
            }
        )
    notes = []
    for race, horse in skipped:
        if any(horse["number"] == number for number in next(leg["picks"] for leg in legs if leg["leg"] == race["leg"])):
            continue
        notes.append(
            {
                "leg": race["leg"],
                "raceNumber": race["number"],
                "number": horse["number"],
                "name": horse["name"],
                "ai": horse["ai"],
                "market": horse["market"],
            }
        )
    formula = " × ".join(str(size) for size in sizes)
    return {
        "profile": profile,
        "title": TITLES[profile],
        "budget": budget,
        "stake": stake,
        "rows": rows,
        "cost": round(rows * stake, 2),
        "hit": hit,
        "legs": legs,
        "notes": notes,
        "formula": f"{formula} = {rows}",
    }


def _harville(order, probs):
    remaining = 1.0
    chance = 1.0
    for number in order:
        share = probs.get(number) or 0.0
        if share <= 0 or remaining <= 1e-12:
            return 0.0
        chance *= share / remaining
        remaining -= share
    return chance


def _box_rows(count, places):
    rows = 1
    for offset in range(places):
        rows *= count - offset
    return rows


def _completion_bound(prob, remaining, used, ranked, need):
    """Yläraja: jäljellä olevista isoimmat todennäköisyydet järjestyksessä."""
    if need <= 0:
        return prob
    chance = prob
    rest = remaining
    taken = 0
    for number, share in ranked:
        if number in used or share <= 0:
            continue
        if rest <= 1e-12:
            return 0.0
        chance *= share / rest
        rest -= share
        taken += 1
        if taken == need:
            return chance
    return 0.0


def _top_orders(numbers, probs, places, limit):
    """Todennäköisimmät järjestykset. Ei rakenna koko kombinatoriikkaa."""
    if limit <= 0:
        return []
    ranked = sorted(
        ((number, probs.get(number) or 0.0) for number in numbers),
        key=lambda item: item[1],
        reverse=True,
    )
    bound = _completion_bound(1.0, 1.0, (), ranked, places)
    heap = [(-bound, 0, 1.0, 1.0, ())]
    found = []
    counter = 1
    while heap and len(found) < limit and counter < 100000:
        neg, _seq, prob, remaining, order = heapq.heappop(heap)
        if len(order) == places:
            found.append((-neg, order))
            continue
        used = set(order)
        need = places - len(order) - 1
        for number, share in ranked:
            if number in used or share <= 0 or remaining <= 1e-12:
                continue
            chance = prob * (share / remaining)
            rest = remaining - share
            nxt = chance if need == 0 else _completion_bound(chance, rest, used | {number}, ranked, need)
            if nxt <= 0:
                continue
            heapq.heappush(heap, (-nxt, counter, chance, rest, order + (number,)))
            counter += 1
    return found


def build_ordered(race, profile, budget, stake, places):
    """Yhden lähdön kaksari tai troikka. Laatikko, jos se mahtuu budjettiin."""

    def empty(message):
        return {
            "profile": profile,
            "title": TITLES[profile],
            "budget": budget,
            "stake": stake,
            "rows": 0,
            "cost": 0,
            "hit": None,
            "legs": [],
            "notes": [message],
            "formula": "",
            "mode": "ordered",
            "box": False,
            "lines": [],
        }

    if stake <= 0 or budget < stake:
        return empty("Budjetti ei riitä yhteen riviin.")
    ordered, left_out = _rank(race["horses"], profile)
    if len(ordered) < places:
        return empty("Lähdössä ei ole tarpeeksi hevosia.")
    max_rows = int(budget / stake + 1e-9)
    total = sum(horse["ai"] for horse in ordered) or 1
    probs = {horse["number"]: horse["ai"] / total for horse in ordered}
    names = {horse["number"]: horse.get("name") or "" for horse in race["horses"]}
    shares = {
        tuple(combo["numbers"]): combo.get("share") or 0
        for combo in race.get("combos") or []
    }

    box_size = None
    for size in range(places, len(ordered) + 1):
        if _box_rows(size, places) <= max_rows:
            box_size = size
        else:
            break

    def finish(picks, rows, hit, box, lines, formula):
        notes = []
        if left_out and left_out["number"] not in picks:
            notes.append(
                {
                    "leg": race["leg"],
                    "raceNumber": race["number"],
                    "number": left_out["number"],
                    "name": left_out["name"],
                    "ai": left_out["ai"],
                    "market": left_out["market"],
                }
            )
        return {
            "profile": profile,
            "title": TITLES[profile],
            "budget": budget,
            "stake": stake,
            "rows": rows,
            "cost": round(rows * stake, 2),
            "hit": hit,
            "legs": [
                {
                    "leg": race["leg"],
                    "raceNumber": race["number"],
                    "picks": picks,
                    "names": [names.get(number, "") for number in picks],
                    "varma": False,
                    "covered": hit,
                }
            ],
            "notes": notes,
            "formula": formula,
            "mode": "ordered",
            "box": box,
            "lines": lines,
        }

    if box_size is not None:
        picks = [horse["number"] for horse in ordered[:box_size]]
        hit = sum(_harville(order, probs) for order in itertools.permutations(picks, places))
        rows = _box_rows(box_size, places)
        return finish(picks, rows, hit, True, [], f"{box_size} hevosta, kaikki {rows} järjestystä")

    ranked = _top_orders([horse["number"] for horse in ordered], probs, places, max_rows)
    if not ranked:
        return empty("Riviä ei voitu koota.")
    lines = []
    used = []
    hit = 0.0
    for chance, order in ranked:
        hit += chance
        picks = list(order)
        for number in picks:
            if number not in used:
                used.append(number)
        key = tuple(picks)
        lines.append(
            {
                "picks": picks,
                "names": [names.get(number, "") for number in picks],
                "ai": chance,
                "market": shares.get(key),
            }
        )
    return finish(used, len(lines), hit, False, lines, f"{len(lines)} riviä")


def build_all(races, stake, budgets=BUDGETS, kind="winners", places=2, hit_label=""):
    systems = {}
    for profile in PROFILES:
        systems[profile] = {}
        for budget in budgets:
            if kind == "ordered":
                system = build_ordered(races[0], profile, budget, stake, places) if races else {
                    "profile": profile,
                    "title": TITLES[profile],
                    "budget": budget,
                    "stake": stake,
                    "rows": 0,
                    "cost": 0,
                    "hit": None,
                    "legs": [],
                    "notes": ["Riviä ei voitu koota."],
                    "formula": "",
                    "mode": "ordered",
                    "box": False,
                    "lines": [],
                }
            else:
                system = build_one(races, profile, budget, stake)
                system["mode"] = "winners"
                system["box"] = False
                system["lines"] = []
            system["hitLabel"] = hit_label
            systems[profile][str(budget)] = system
    return systems
