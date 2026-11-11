# Eishockey-Daten vom Schweizer Eishockeyverband (SIHF) statt API-Hockey (seit 09.11.2026, Cy: API-Hockey lieferte für Schweizer
# Ligen nur Drittelsresultate und Tabelle, USD 15/Monat zu viel). Keine offizielle Schnittstelle, kein Schlüssel:
# - Spiele pro Tag: Game-Center-Seite www.sihf.ch/de/game-center/spiele/?date=JJJJ-MM-TT (HTML, Spiel-ID, Liga, Teams, Zeit)
# - Spieldetails: data.sihf.ch …/gameoverview?alias=gameDetail (JSON: Resultat, Drittel, Tore mit Assists und Spielsituation,
#   Strafen, Stadion, Zuschauer, Schiedsrichter, Runde, Status)
# - Tabelle: data.sihf.ch …/cache300?alias=standing (JSON, gleiche Zahlen wie API-Hockey)
# Ausgabe im gleichen Format wie hmatch()/hockey() in fetch.py, Teams mit den bisherigen API-Hockey-IDs und -Namen
# (Logos, Kürzel, Spielerkennung bleiben gleich). Liga-IDs SIHF: 1 National League, 2 Swiss League, 100 MyHockey League.
import datetime as dt, json, re, sys, time, urllib.request
from zoneinfo import ZoneInfo

ZH = ZoneInfo("Europe/Zurich")
UA = "Mozilla/5.0 (compatible; NewsmagSports/1.0; +https://newsmag.ch)"
DATA = "https://data.sihf.ch/Statistic/api/cms"
calls = 0

# SIHF-Team-ID → (Name wie bisher von API-Hockey, API-Hockey-ID). Unbekannte Teams (Auf-/Absteiger) behalten SIHF-ID und -Namen.
TEAMS = {
    101139: ("ZSC Lions", 556), 101152: ("Ambrì-Piotta", 545), 103140: ("Genève-Servette", 554), 102127: ("SCL Tigers", 550),
    101144: ("EV Zug", 555), 102126: ("SC Bern", 546), 103138: ("Fribourg-Gottéron", 549), 103141: ("Lausanne HC", 551),
    103144: ("HC Ajoie", 558), 101151: ("HC Davos", 548), 102128: ("EHC Biel", 547), 101150: ("HC Lugano", 552),
    101060: ("Lakers", 553), 101149: ("EHC Kloten", 561),
    105654: ("Sierre", 1475), 105847: ("Basel", 559), 103143: ("Visp", 576), 103139: ("La Chaux-de-Fonds", 564), 102129: ("Olten", 569),
    101154: ("Chur", 919), 103394: ("Thurgau", 575), 105497: ("Bellinzona Snakes", 577), 103330: ("Arosa", 903), 101155: ("GCK Lions", 562),
    101021: ("Dübendorf", 560), 102032: ("Huttwil", 563), 101033: ("EHC Frauenfeld", 905), 103065: ("Franches-Montagnes", 1892),
    102080: ("Thun", 574), 103216: ("Seewen", 571), 101083: ("Wetzikon", 918), 106321: ("Winterthur", 578), 102054: ("Lyss", 921),
    105994: ("Langenthal", 565), 103205: ("Oberthurgau", 568), 101011: ("Bülach", 910),
}
# Zonen in der Tabelle (wie API-Hockey «description», spZone im Worker): NL 1–6 Playoffs, 7–10 Play-in; SL 1–8, MyHockey League 1–10 Playoffs
ZONES = {1: [(6, "Play Offs"), (10, "Play-in")], 2: [(8, "Play Offs")], 100: [(10, "Play Offs")]}
DONE = {"FT", "AOT", "AP"}
# Ligen mit offizieller Runde aus gameDetail: National League, Swiss League (seit 11.11.2026, Cy; vorher nur NL)
RND = {1, 2}


def get(url, js=True):
    global calls
    for attempt in range(3):
        calls += 1
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": UA}), timeout=40) as r:
                raw = r.read().decode("utf-8")
            if not js: return raw
            if raw.lstrip().startswith("/**/"): raw = raw[raw.index("(") + 1:raw.rindex(")")]
            return json.loads(raw)
        except Exception as e:
            print("SIHF-Abruf gescheitert", url[:120], e, file=sys.stderr); time.sleep(3 + attempt * 3)
    return None


def team(sid, name):
    t = TEAMS.get(int(sid or 0))
    if t: return [t[1], t[0]]
    return [int(sid or 0), re.sub(r"^(EHC|HC|SC|EV|GDT)\s+", "", name or "").strip() or name]


# Doppelte Nachnamen ohne Vorsilbe, die die Regel in pname() falsch drehen würde (SIHF: «Worge Kreü William»)
NAME_FIX = {"Worge Kreü William": "William Worge Kreü"}


def pname(full):
    """«Le Coultre Simon» → «Simon Le Coultre», «Fust Raymond Taylor» → «Raymond Taylor Fust» (SIHF: Nachname zuerst)."""
    full = " ".join((full or "").split())
    if full in NAME_FIX: return NAME_FIX[full]
    t = full.split()
    if len(t) < 2: return full or ""
    n = 1
    while n < len(t) - 1 and t[n - 1].lower() in {"de", "di", "da", "du", "le", "la", "von", "van", "der", "del", "dal", "mc"}: n += 1
    return " ".join(t[n:] + t[:n])


def day_list(day):
    """Spiele eines Tages aus dem Game Center: [{id, lg, h:[id,name], a:[id,name], tm:'20:15'|'Ende'|…, live}] oder None (Abruf gescheitert)."""
    h = get(f"https://www.sihf.ch/de/game-center/spiele/?date={day}", js=False)
    if h is None or "c-game-preview" not in h and "live-games" not in h: return None
    out = []
    for blk in re.findall(r'<a href="[^"]*/game-center/game/\d+"(.*?)</a>', h, re.S):
        g = lambda k: (re.search(k + r'="([^"]*)"', blk) or [None, ""])[1]
        names = [x.strip() for x in re.findall(r'c-game-preview__team-name">([^<]*)<', blk)]
        tm = re.search(r'c-game-preview__time">\s*([^<]*?)\s*</div>', blk)
        if not g("data-game-id") or len(names) < 2: continue
        out.append({"id": int(g("data-game-id")), "lg": int(g("data-league-id") or 0), "h": [g("data-home-team-id"), names[0]],
                    "a": [g("data-away-team-id"), names[1]], "tm": tm.group(1).strip() if tm else "", "live": g("data-is-live") == "true"})
    return out


def detail(gid):
    return get(f"{DATA}/gameoverview?alias=gameDetail&searchQuery={gid}&language=de")


def iso(day, hm):
    y, m, d = map(int, day.split("-")); hh, mm = map(int, hm.split(":"))
    return dt.datetime(y, m, d, hh, mm, tzinfo=ZH).isoformat()


def from_detail(d, sid):
    """Spiel (Format wie hmatch) und Details (Format wie evof, Eishockey-Typen) aus gameDetail."""
    det, res, st0 = d.get("details") or {}, d.get("result") or {}, d.get("status") or {}
    hid = (det.get("homeTeam") or {}).get("id")
    scores = res.get("scores") or []
    periods = (d.get("summary") or {}).get("periods") or []
    goals = [g for p in periods for g in p.get("goals") or []]
    so_goal = any(g.get("isShootout") or (g.get("situation") or {}).get("code") == "SO" for g in goals)
    nm, pc, started = (st0.get("name") or ""), st0.get("percent") or 0, bool(scores)
    if st0.get("canceled"): st = "CANC"
    elif pc >= 100 or nm == "Ende":
        st = "AP" if so_goal else "AOT" if len(scores) > 3 else "FT"
    elif re.search(r"pause", nm, re.I): st = "BT"
    elif re.search(r"shootout|penalty", nm, re.I) or (started and so_goal): st = "PT"
    elif re.search(r"verlängerung", nm, re.I): st = "OT"
    elif re.match(r"(\d)\. ?Drittel", nm): st = "P" + re.match(r"(\d)", nm).group(1)
    elif 0 < pc < 100 or started: st = {1: "P1", 2: "P2", 3: "P3"}.get(len(scores), "OT")
    elif re.search(r"verschoben", nm, re.I): st = "PST"
    else: st = "NS"
    gnum = lambda x: int(x) if str(x).lstrip("-").isdigit() else None
    g = [gnum(res.get("homeTeam")), gnum(res.get("awayTeam"))]
    g = g if st not in ("NS", "PST", "CANC") and None not in g else None
    # Drittel wie API-Hockey: «h-a» für 1.–3. Drittel, Verlängerung (ohne Shootout-Tor), Penaltyschiessen (verwandelte Penaltys)
    per = [None] * 5
    for i, s in enumerate(scores[:3]): per[i] = f"{gnum(s.get('homeTeam')) or 0}-{gnum(s.get('awayTeam')) or 0}"
    pl = {p.get("id"): p for p in d.get("players") or []}
    if len(scores) > 3:
        # Abschnitte ohne Ereignis fehlen in summary.periods (ZSC–Lausanne 03.10.2026: kein «1. Drittel») → Verlängerung über den Namen
        ot = [x for p in periods if re.search(r"verlängerung", p.get("name") or "", re.I) for x in p.get("goals") or []
              if not (x.get("isShootout") or (x.get("situation") or {}).get("code") == "SO")]
        per[3] = f"{sum(x.get('teamId') == hid for x in ot)}-{sum(x.get('teamId') != hid for x in ot)}"
    shots = ((d.get("summary") or {}).get("shootout") or {}).get("shoots") or []
    if shots:
        sh = [(pl.get(x.get("scorerLicenceNr")) or {}).get("teamId") == hid for x in shots if x.get("scored")]
        per[4] = f"{sum(sh)}-{len(sh) - sum(sh)}"
    t = st0.get("startDateTime") or d.get("startDateTime")
    m = {"id": int(d["gameId"]), "t": dt.datetime.fromisoformat(t).isoformat() if t else None, "st": st, "el": None,
         "r": d["round"] + 1 if sid in RND and isinstance(d.get("round"), int) else None, "h": team(hid, (det.get("homeTeam") or {}).get("name")),
         "a": team((det.get("awayTeam") or {}).get("id"), (det.get("awayTeam") or {}).get("name")), "g": g, "p": None, "per": per}
    if st == "NS": return m, None
    # Ereignisse: Tor [Minute, None, h/a, "g", Torschütze, Assists, Zusatz, "mm:ss"], Strafe [Minute, None, h/a, "hp", Spieler, "2' Grund", None, "mm:ss"]
    who = lambda lic: pname((pl.get(lic) or {}).get("fullName") or "") if lic else ""
    secs = lambda x: x.get("timeInSeconds") if x.get("timeInSeconds") is not None else sum(int(a) * b for a, b in zip((x.get("time") or "0:0").split(":"), (60, 1)))
    ev = []
    for x in goals:
        sit = (x.get("situation") or {}).get("code") or ""
        if x.get("isShootout") or sit == "SO": continue
        if not sit: sit = (re.match(r"\*\*([^*]*)\*\*", x.get("text") or "") or [None, ""])[1]
        lab = [l for c, l in (("PP", "Überzahl"), ("SH", "Unterzahl")) if c in sit]
        if x.get("isEmptyNet") or "EN" in sit.split(","): lab.append("ins leere Tor")
        if x.get("isPenaltyShot") or "PS" in sit.split(","): lab.append("Penalty")
        name = who(x.get("scorerLicenceNr")) or pname((re.search(r"- \*\*([^*(]+)", x.get("text") or "") or [None, ""])[1].strip())
        ass = ", ".join(n for n in (who(x.get("assist1LicenceNr")), who(x.get("assist2LicenceNr"))) if n)
        s = secs(x)
        ev.append([s // 60 + 1, None, "h" if x.get("teamId") == hid else "a", "g", name, ass, ", ".join(lab) or None, x.get("time"), s])
    fl = {}
    for p in periods:
        for x in p.get("fouls") or []:
            if not x.get("minutes"): continue  # 0 Min = Penaltyschuss (steht beim Tor)
            k = (x.get("playerLicenceNr"), x.get("time"), x.get("teamId"))
            if k in fl: fl[k][0].append(x.get("minutes")); continue
            fl[k] = ([x.get("minutes")], (x.get("name") or "").strip(), x)
    for (lic, tm, tid), (mins, why, x) in fl.items():
        s = secs(x)
        ev.append([s // 60 + 1, None, "h" if tid == hid else "a", "hp", who(lic) or "Teamstrafe", " + ".join(map(str, sorted(mins))) + "' " + why, None, tm, s])
    ev.sort(key=lambda e: e[8])
    for e in ev: e.pop()
    v = det.get("venue") or {}
    city = re.sub(r"\s+[A-Z]{2}$", "", v.get("city") or "")
    zu = gnum(v.get("spectators"))
    named = all(e[4] for e in ev if e[3] == "g")
    old = m["t"] and time.time() - dt.datetime.fromisoformat(m["t"]).timestamp() > 24 * 3600
    info = {"final": st in DONE and (named or bool(old)), "ht": None, "v": ", ".join(x for x in [v.get("name"), city] if x),
            "ref": ", ".join(r.get("fullName") for r in det.get("referees") or [] if r.get("fullName")), "ev": ev, "sb": [], "lu": None,
            "zu": zu if zu else None}
    return m, info


def standing(sid, season):
    d = get(f"{DATA}/cache300?alias=standing&searchQuery=1/{season}/{sid}&filterQuery={season}/{sid}&filterBy=Season,League&language=de&callback=x")
    rows = (d or {}).get("data") or []
    if not rows: return None
    n = lambda x: int(x) if str(x).lstrip("-").isdigit() else 0
    out = []
    # Spalten: Rang, Team, Spiele, Punkte, Punkte/Spiel, S, SnV, SnP, NnV, NnP, N, Tore, Gegentore, Differenz, Form
    for x in rows:
        tid, name = team(x[1].get("id"), x[1].get("name"))
        r = n(x[0])
        out.append({"r": r, "id": tid, "n": name, "sp": n(x[2]), "w": n(x[5]), "ow": n(x[6]) + n(x[7]), "ol": n(x[8]) + n(x[9]), "l": n(x[10]),
                    "gf": n(x[11]), "ga": n(x[12]), "gd": n(x[13]), "pts": n(x[3]), "f": "",
                    "d": next((z for lim, z in ZONES.get(sid, []) if r <= lim), ""), "grp": ""})
    return out


def exhibition(d):
    """Testspiele (Phase «NL Exhibition Games» u. ä.)."""
    return bool(re.search(r"exhibition|test|vorbereitung", ((d.get("phase") or {}).get("name") or ""), re.I))


def fix_rounds(ms):
    """Nachtrags- und vorgezogene Spiele: SIHF führt sie unter der ursprünglichen Runde (Lugano–Bern am 11.11.2026 als «2. Runde»).
    Wie bei API-Hockey zählen sie zur zeitlich nächsten regulären Runde – Ausreisser = Runde weicht um mehr als 2 vom Median
    der 6 zeitlich nächsten anderen Spiele ab. Sonst zerfiele der Rundenbericht in Ein-Spiel-Runden."""
    ts = lambda m: dt.datetime.fromisoformat(m["t"]).timestamp()
    rs = [m for m in ms if m.get("r") and m.get("t")]
    out = set()
    for m in rs:
        near = sorted(x["r"] for x in sorted((x for x in rs if x is not m), key=lambda x: abs(ts(x) - ts(m)))[:6])
        if len(near) < 3: continue
        k = len(near); med = (near[(k - 1) // 2] + near[k // 2]) / 2
        if abs(m["r"] - med) > 2: out.add(m["id"])
    reg = [m for m in rs if m["id"] not in out]
    for m in rs:
        if m["id"] in out and reg:
            m["r"] = min(reg, key=lambda x: (abs(ts(x) - ts(m)), -ts(x)))["r"]


def run(job, leagues, out, frm, to):
    """Voller Abruf: Tageslisten im Zeitfenster, Details nur wo nötig (laufend, beendet ohne endgültige Details, NL/SwL ohne Runde)."""
    season = int(job["season"]) + 1  # SIHF zählt 2026/27 als 2027
    sids = {lg["sid"]: lg for lg in leagues}
    # gespeicherte Spiele pro Liga (vom Worker, lg["hk"]), "fin": Details endgültig → kein erneuter Abruf
    known = {int(k): {**v, "sid": lg["sid"]} for lg in leagues for k, v in (lg.get("hk") or {}).items()}
    now = time.time()
    by = {sid: [] for sid in sids}
    d0, d1 = dt.date.fromisoformat(frm), dt.date.fromisoformat(to)
    want, seen = [], set()
    day = d0
    while day <= d1:
        lst = day_list(day.isoformat())
        if lst is None:  # Tag nicht abrufbar → gespeicherte Spiele dieses Tages behalten
            for gid, k in known.items():
                if k.get("t", "")[:10] == day.isoformat() and k.get("sid") in by: by[k["sid"]].append({x: y for x, y in k.items() if x not in ("fin", "sid")}); seen.add(gid)
        for x in lst or []:
            if x["lg"] not in sids or x["id"] in seen: continue
            seen.add(x["id"])
            k = known.get(x["id"])
            hm = re.fullmatch(r"\d{1,2}:\d{2}", x["tm"])
            t = iso(day.isoformat(), x["tm"]) if hm else (k or {}).get("t") or iso(day.isoformat(), "19:45")
            begun = dt.datetime.fromisoformat(t).timestamp() < now + 10 * 60
            if k and k.get("st") in DONE and k.get("fin"):
                by[x["lg"]].append({a: b for a, b in k.items() if a not in ("fin", "sid")}); continue
            if begun or x["live"] or not hm or (x["lg"] in RND and not (k or {}).get("r")):
                want.append((x, t)); continue
            by[x["lg"]].append({"id": x["id"], "t": t, "st": "NS", "el": None, "r": (k or {}).get("r"), "h": team(*x["h"]), "a": team(*x["a"]),
                                "g": None, "p": None, "per": [None] * 5})
        day += dt.timedelta(days=1)
    cap = 400 if (d1 - d0).days > 30 else 150  # Archiv-Füllung (Fenster bis 60 Tage zurück): ca. 250 Spiele
    for x, t in want[cap:]:  # über der Grenze: gespeicherten Stand behalten statt das Spiel zu verlieren
        k = known.get(x["id"])
        if k: by[x["lg"]].append({a: b for a, b in k.items() if a not in ("fin", "sid")})
    for x, t in want[:cap]:
        d = detail(x["id"])
        if not d or not d.get("gameId"):
            k = known.get(x["id"])
            by[x["lg"]].append({a: b for a, b in k.items() if a not in ("fin", "sid")} if k else
                               {"id": x["id"], "t": t, "st": "NS", "el": None, "r": None, "h": team(*x["h"]), "a": team(*x["a"]), "g": None, "p": None, "per": [None] * 5})
            continue
        if exhibition(d): continue  # Testspiele vor der Saison stehen in der Tagesliste unter derselben Liga
        m, info = from_detail(d, x["lg"])
        by[x["lg"]].append(m)
        if info: out["ev"][str(m["id"])] = info
        time.sleep(0.2)
    for sid in RND:
        if sid in by: fix_rounds(by[sid])
    for sid, lg in sids.items():
        table = standing(sid, season) if lg.get("table") else None
        out["leagues"].append({"id": lg["id"], "sport": "hockey", "src": "sihf", "matches": sorted(by[sid], key=lambda m: m["t"] or ""), "table": table})


def live(job, leagues, out):
    """Live-Abruf: Details der laufenden Spiele (IDs vom Worker)."""
    for lg in leagues:
        ms = []
        for gid in lg.get("ids") or []:
            d = detail(gid)
            if not d or not d.get("gameId"): continue
            m, info = from_detail(d, lg["sid"])
            m.pop("r", None)  # Runde bleibt die gespeicherte (Nachtragsspiele sind dort schon zugeordnet, siehe fix_rounds)
            ms.append(m)
            if info: out["ev"][str(m["id"])] = info
        out["leagues"].append({"id": lg["id"], "sport": "hockey", "matches": ms})
