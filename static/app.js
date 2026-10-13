const meta = document.querySelector("#meta");
const slip = document.querySelector("#slip");
const races = document.querySelector("#races");
const spotlight = document.querySelector("#spotlight");
const profileNote = document.querySelector("#profile-note");
const stakeSelect = document.querySelector("#stake");
const cardSelect = document.querySelector("#card");
const cardField = document.querySelector("#card-field");
const raceSelect = document.querySelector("#race");
const raceField = document.querySelector("#race-field");
const reloadButton = document.querySelector("#reload");

const NOTES = {
  turvallinen: "Peittää sen, minkä malli pitää todennäköisimpänä.",
  tasapainoinen: "Nostaa alipelatun hevosen riville aiemmin.",
  rohkea: "Ylipelattua suosikkia ei pankiteta. Se tulee mukaan vasta, jos rivejä riittää toiseen hevoseen.",
};

const PARTS = [
  ["win", "Voitto"],
  ["agreement", "Yksimielisyys"],
  ["market", "Markkina"],
  ["conditions", "Lähtö"],
  ["form", "Vire"],
  ["place", "Sija"],
  ["gallop", "Laukka"],
  ["trip", "Juoksunkulku"],
];

const MODELS = [
  ["vire", "Vire"],
  ["luokka", "Luokka"],
  ["ohjastaja", "Ohjastaja"],
  ["lahto", "Lähtö"],
];

let payload = null;
let profile = "turvallinen";
let budget = "10";
let game = "T75";
let raceNumber = "";
let openKey = null;

function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text != null) node.textContent = text;
  return node;
}

function pct(value, digits = 0) {
  if (value == null || Number.isNaN(value)) return "–";
  return `${(value * 100).toFixed(digits).replace(".", ",")} %`;
}

function hitText(value) {
  if (value == null) return "–";
  if (value < 0.0001) return "< 0,01 %";
  return pct(value, value < 0.01 ? 2 : 1);
}

function edgeText(value) {
  if (value == null) return "–";
  const points = Math.round(value * 100);
  if (points === 0) return "0 %";
  const sign = points > 0 ? "+" : "−";
  return `${sign}${Math.abs(points)} %`;
}

function euros(value, digits = 0) {
  if (value == null) return "";
  return new Intl.NumberFormat("fi-FI", {
    style: "currency",
    currency: "EUR",
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  }).format(value);
}

function stakeLabel(value) {
  return `${Number(value).toFixed(2).replace(".", ",")} €`;
}

function labelText(label) {
  if (label === "alipelattu") return "Alipelattu";
  if (label === "ylipelattu") return "Ylipelattu";
  if (label === "pois") return "Pois";
  if (label === "ei markkinaa") return "Ei peliosuutta";
  return "Linjassa";
}

function currentSystem() {
  return payload?.systems?.[profile]?.[budget];
}

function horseMap() {
  const map = new Map();
  (payload?.races || []).forEach((race) => {
    race.horses.forEach((horse) => map.set(`${race.leg}:${horse.number}`, horse));
  });
  return map;
}

function pickedSet(system) {
  const set = new Set();
  (system?.legs || []).forEach((leg) => {
    leg.picks.forEach((number) => set.add(`${leg.leg}:${number}`));
  });
  return set;
}

function renderMeta() {
  const card = payload.card;
  const pool = payload.pool;
  const raceBit = payload.game?.kind === "ordered"
    ? `lähtö ${payload.races[0]?.number ?? ""}`
    : `${payload.races.length} lähtöä`;
  const bits = [payload.game?.name, card.track, card.dateText, card.clock ? `klo ${card.clock}` : "", raceBit];
  if (pool.sales) bits.push(`vaihto ${euros(pool.sales)}`);
  if (pool.jackpot) bits.push(`potti ${euros(pool.jackpot)}`);
  const scratches = payload.scratches || [];
  if (scratches.length === 1) bits.push("1 poisjäänti");
  if (scratches.length > 1) bits.push(`${scratches.length} poisjääntiä`);
  meta.textContent = bits.filter(Boolean).join(" · ");
  if (pool.thin) meta.textContent += " · peliosuus elää vielä";
}

function renderGames() {
  const open = new Map((payload.games || []).map((item) => [item.id, item]));
  document.querySelectorAll("#games button").forEach((button) => {
    const info = open.get(button.dataset.game);
    button.disabled = info ? !info.open : false;
    button.setAttribute("aria-pressed", payload.game?.id === button.dataset.game ? "true" : "false");
  });
  if (payload.game?.id) game = payload.game.id;
}

function renderRaceSelect() {
  const ordered = payload.game?.kind === "ordered";
  raceField.hidden = !ordered;
  raceSelect.replaceChildren();
  (payload.raceOptions || []).forEach((option) => {
    const node = el("option", null, `Lähtö ${option.number}`);
    node.value = String(option.number);
    raceSelect.append(node);
  });
  const selected = (payload.raceOptions || []).find((option) => option.selected) || (payload.raceOptions || [])[0];
  if (selected) {
    raceSelect.value = String(selected.number);
    raceNumber = String(selected.number);
  }
}

function renderSelects() {
  const stake = String(payload.stake);
  stakeSelect.replaceChildren();
  payload.stakes.forEach((value) => {
    const option = el("option", null, stakeLabel(value));
    option.value = String(value);
    stakeSelect.append(option);
  });
  stakeSelect.value = payload.stakes.map(String).includes(stake) ? stake : String(payload.stakes[0]);

  cardSelect.replaceChildren();
  payload.options.forEach((option) => {
    const node = el("option", null, `${option.track} · ${option.dateText}${option.country && option.country !== "FI" ? ` · ${option.country}` : ""}`);
    node.value = String(option.id);
    cardSelect.append(node);
  });
  const selected = payload.options.find((option) => option.selected) || payload.options[0];
  if (selected) cardSelect.value = String(selected.id);
  cardField.hidden = payload.options.length < 2;
  renderGames();
  renderRaceSelect();
}

function renderSpotlight() {
  spotlight.replaceChildren();
  (payload.spotlight || []).forEach((item) => {
    const button = el("button", `spot ${item.label}`);
    button.type = "button";
    button.append(
      el("b", null, item.label === "ylipelattu" ? "Ylipelattu" : "Alipelattu"),
      el("span", null, `lähtö ${item.raceNumber} · ${item.number} ${item.name}`),
      el("span", null, `${pct(item.ai)} malli · ${pct(item.market)} peliosuus · ${edgeText(item.edge)}`),
    );
    button.addEventListener("click", () => {
      openKey = `${item.leg}:${item.number}`;
      render();
      document.getElementById(`race-${item.leg}`)?.scrollIntoView({ behavior: "smooth", block: "start" });
    });
    spotlight.append(button);
  });
}

function renderSlip() {
  slip.replaceChildren();
  const system = currentSystem();
  if (!system) {
    slip.append(el("p", "status", "Riviä ei saatu."));
    return;
  }
  const head = el("div", "slip-head");
  head.append(el("h2", null, system.title));
  const costDigits = Number.isInteger(system.cost) ? 0 : 2;
  head.append(el("p", "slip-cost", system.rows ? `${system.rows} riviä · ${euros(system.cost, costDigits)}` : "Ei riviä"));
  slip.append(head);
  if (system.message) {
    slip.append(el("p", "formula", system.message));
    return;
  }
  slip.append(el("p", "formula", system.formula));
  const hit = el("p", "hit");
  hit.append(el("span", null, `${system.hitLabel || "Osuma mukana"} `), el("strong", null, hitText(system.hit)));
  slip.append(hit);

  const names = horseMap();
  const legs = el("div", "legs");
  if (system.mode === "ordered" && !system.box) {
    system.lines.forEach((line) => {
      const row = el("div", "leg");
      const picks = el("div", "picks");
      picks.append(document.createTextNode(line.picks.join("–")));
      const title = line.picks.map((number) => names.get(`${system.legs[0]?.leg}:${number}`)?.name).filter(Boolean).join(" – ");
      if (title) picks.title = title;
      row.append(el("span", "leg-no", ""), picks, el("span", "covered", pct(line.ai)));
      legs.append(row);
    });
  } else {
    system.legs.forEach((leg) => {
      const row = el("div", "leg");
      row.append(el("span", "leg-no", system.box ? String(leg.raceNumber) : String(leg.leg)));
      const picks = el("div", "picks");
      picks.append(document.createTextNode(leg.picks.join(", ")));
      if (leg.varma) picks.append(el("span", "pill", "Varma"));
      const title = leg.picks.map((number) => names.get(`${leg.leg}:${number}`)?.name).filter(Boolean).join(", ");
      if (title) picks.title = title;
      row.append(picks);
      if (!system.box) row.append(el("span", "covered", pct(leg.covered)));
      legs.append(row);
    });
  }
  slip.append(legs);

  const scratches = payload.scratches || [];
  if (scratches.length) {
    const block = el("div", "scratches");
    block.append(el("p", "scratch-title", "Poisjäännit"));
    scratches.forEach((horse) => {
      block.append(el(
        "p",
        "scratch",
        `Lähtö ${horse.raceNumber} · ${horse.number} ${horse.name}. Ei pelata.`,
      ));
    });
    slip.append(block);
  }

  system.skipped.forEach((note) => {
    slip.append(el(
      "p",
      "skip",
      `Lähtö ${note.raceNumber}, hevonen ${note.number} ${note.name} jää tältä riviltä. Arvio ${pct(note.ai)}, peliosuus ${pct(note.market)}. Ylipelattu suosikki.`,
    ));
  });
}

function metric(label, value, className) {
  const node = el("span", className ? `metric ${className}` : "metric");
  node.append(el("i", null, label), document.createTextNode(value));
  return node;
}

function renderDetail(horse) {
  const detail = el("div", "detail");
  if (horse.scratched) {
    detail.append(el("p", null, "Poisjäänti. Hevonen ei lähde, eikä sitä pelata."));
    return detail;
  }
  const models = el("div", "models");
  MODELS.forEach(([key, name]) => {
    models.append(el("span", null, `${name} ${pct(horse.models?.[key])}`));
  });
  detail.append(models);

  const year = horse.year;
  if (year && year.starts) {
    detail.append(el(
      "p",
      null,
      `Tämä vuosi ${year.wins}-${year.seconds}-${year.thirds} / ${year.starts}. Voitto ${pct(year.winRate)}, sijoitus ${pct(year.placeRate)}, laukka ${pct(year.gallop)}.`,
    ));
  }
  const records = [horse.recordAuto && `autoennätys ${horse.recordAuto}`, horse.recordVolt && `tasoitusennätys ${horse.recordVolt}`].filter(Boolean);
  const bits = [];
  if (records.length) bits.push(records.join(" · "));
  if (horse.driverStarts) {
    bits.push(`ohjastaja ${horse.driverWins} voittoa / ${horse.driverStarts} starttia`);
  }
  if (horse.shoes) bits.push(horse.shoes);
  if (horse.odds) bits.push(`voittokerroin ${String(horse.odds).replace(".", ",")}`);
  if (bits.length) detail.append(el("p", "quiet", bits.join(" · ")));

  if (horse.gallop || horse.trip) {
    detail.append(el(
      "p",
      null,
      `Laukkariski ${horse.gallop?.label || "–"}. Juoksunkulun riippuvuus ${horse.trip?.label || "–"}. Sijoittuminen ${pct(horse.place)}.`,
    ));
  }

  if (horse.parts) {
    const parts = el("div", "parts");
    PARTS.forEach(([key, name]) => {
      const value = horse.parts[key];
      if (value == null) return;
      const sign = value > 0 ? "+" : value < 0 ? "−" : "";
      parts.append(el("span", value < 0 ? "part neg" : "part", `${name} ${sign}${Math.abs(value)}`));
    });
    detail.append(el("p", "quiet", `Varmuus ${horse.certainty ?? "–"}`), parts);
  }

  if (horse.starts?.length) {
    const list = el("ul", "lines");
    horse.starts.forEach((start) => {
      const item = el("li");
      const place = el("span", "place", start.result || "–");
      if (start.result === "1") place.classList.add("win");
      if (start.result && !/^\d+$/.test(start.result)) place.classList.add("dnf");
      item.append(
        el("span", null, start.date),
        place,
        el("span", null, `${start.track} ${start.km}`.trim()),
        el("span", "quiet when-driver", start.driver),
      );
      list.append(item);
    });
    detail.append(list);
  }
  return detail;
}

function renderHorse(race, horse, picked) {
  const key = `${race.leg}:${horse.number}`;
  const open = openKey === key;
  const button = el("button", "horse");
  button.type = "button";
  button.setAttribute("aria-expanded", open ? "true" : "false");
  if (picked.has(key)) button.classList.add("is-in");
  if (open && !picked.has(key)) button.classList.add("is-open");
  if (horse.scratched) button.classList.add("is-out");

  const who = el("span", "who");
  who.append(el("span", "name", horse.name));
  const metaBits = [horse.driver, horse.trainer].filter(Boolean);
  if (horse.extra) metaBits.push(`+${horse.extra} m`);
  if (horse.track && horse.track !== horse.number) metaBits.push(`rata ${horse.track}`);
  who.append(el("span", "who-meta", metaBits.join(" · ")));

  const stats = el("span", "stats");
  const edgeClass = horse.edge > 0.005 ? "up" : horse.edge < -0.005 ? "down" : "";
  stats.append(
    metric("Malli", horse.scratched ? "–" : pct(horse.ai), ""),
    metric("Peliosuus", pct(horse.market), ""),
    metric("Ero", edgeText(horse.edge), edgeClass ? `edge ${edgeClass}` : "edge"),
    metric("Varmuus", horse.certainty == null ? "–" : String(horse.certainty), ""),
  );

  const marks = el("span", "marks");
  if (horse.varma) marks.append(el("span", "pill", "Varma"));
  if (horse.label && horse.label !== "linjassa") {
    const tagClass = horse.label === "ei markkinaa" ? "ei" : horse.label;
    marks.append(el("span", `tag ${tagClass}`, labelText(horse.label)));
  }

  button.append(el("span", "num", String(horse.number)), who, stats, marks);
  button.addEventListener("click", () => {
    openKey = open ? null : key;
    render();
  });

  const wrap = el("div");
  wrap.append(button);
  if (open) wrap.append(renderDetail(horse));
  return wrap;
}

function renderRaces() {
  races.replaceChildren();
  const system = currentSystem();
  const picked = pickedSet(system);
  payload.races.forEach((race) => {
    const section = el("section", "race");
    section.id = `race-${race.leg}`;
    const head = el("div", "race-head");
    const prize = race.prize ? ` · ${euros(race.prize)}` : "";
    const gameName = payload.game?.name || "Toto";
    const kicker = payload.game?.kind === "ordered"
      ? `${gameName} · lähtö ${race.number}`
      : `${gameName} ${race.leg} · lähtö ${race.number}`;
    head.append(el("p", "race-kicker", kicker));
    head.append(el("h2", null, `${race.start} · ${race.distance || "–"} m${race.breed ? ` · ${race.breed}` : ""}${prize}`));
    if (race.title) head.append(el("p", "race-title", race.title));
    const out = (race.scratches || []).length
      ? race.scratches
      : race.horses.filter((horse) => horse.scratched);
    if (out.length) {
      const names = out.map((horse) => `${horse.number} ${horse.name}`).join(", ");
      head.append(el("p", "scratch", `Pois: ${names}. Prosentit ja rivi on laskettu ilman ${out.length === 1 ? "hevosta" : "heitä"}.`));
    }
    const likely = race.horses.find((horse) => horse.likely && horse.label === "ylipelattu");
    if (likely) {
      head.append(el("p", "race-title", `${likely.number} ${likely.name} on todennäköisin voittaja ja silti ylipelattu.`));
    }
    section.append(head);

    const columns = el("div", "cols");
    ["", "Hevonen", "Malli", "Peliosuus", "Ero", "Varmuus", ""].forEach((text) => columns.append(el("span", null, text)));
    section.append(columns);
    race.horses.forEach((horse) => section.append(renderHorse(race, horse, picked)));
    races.append(section);
  });
}

function render() {
  if (!payload || payload.error) {
    meta.textContent = "Tietoja ei saatu.";
    slip.replaceChildren();
    races.replaceChildren(el("p", "status", payload?.error || "Kohteita ei saatu."));
    spotlight.replaceChildren();
    return;
  }
  profileNote.textContent = NOTES[profile] || "";
  renderMeta();
  renderSpotlight();
  renderSlip();
  renderRaces();
}

async function load(refresh) {
  meta.textContent = refresh ? "Päivitetään…" : "Haetaan lähtöjä…";
  const params = new URLSearchParams();
  if (refresh) params.set("refresh", "1");
  if (game) params.set("game", game);
  if (raceNumber) params.set("race", raceNumber);
  if (stakeSelect.value) params.set("stake", stakeSelect.value);
  if (cardSelect.value) params.set("card", cardSelect.value);
  try {
    const response = await fetch(`/api/card?${params}`);
    payload = await response.json();
  } catch (error) {
    payload = { error: "Yhteys laskuriin katkesi." };
  }
  if (!payload.error) renderSelects();
  render();
}

document.querySelectorAll("#profiles button").forEach((button) => {
  button.addEventListener("click", () => {
    profile = button.dataset.profile;
    document.querySelectorAll("#profiles button").forEach((item) => {
      item.setAttribute("aria-pressed", item === button ? "true" : "false");
    });
    render();
  });
});

document.querySelectorAll("#budgets button").forEach((button) => {
  button.addEventListener("click", () => {
    budget = button.dataset.budget;
    document.querySelectorAll("#budgets button").forEach((item) => {
      item.setAttribute("aria-pressed", item === button ? "true" : "false");
    });
    render();
  });
});

document.querySelectorAll("#games button").forEach((button) => {
  button.addEventListener("click", () => {
    if (button.disabled || button.dataset.game === game) return;
    game = button.dataset.game;
    raceNumber = "";
    document.querySelectorAll("#games button").forEach((item) => {
      item.setAttribute("aria-pressed", item === button ? "true" : "false");
    });
    load(false);
  });
});

stakeSelect.addEventListener("change", () => load(false));
cardSelect.addEventListener("change", () => {
  raceNumber = "";
  load(false);
});
raceSelect.addEventListener("change", () => {
  raceNumber = raceSelect.value;
  load(false);
});
reloadButton.addEventListener("click", () => load(true));
load(false);
