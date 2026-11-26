# Eishockey-Daten vom Schweizer Eishockeyverband (SIHF) statt API-Hockey (seit 09.11.2026, Cy: API-Hockey lieferte für Schweizer
# Ligen nur Drittelsresultate und Tabelle, USD 15/Monat zu viel). Keine offizielle Schnittstelle, kein Schlüssel:
# - Spiele pro Tag: Game-Center-Seite www.sihf.ch/de/game-center/spiele/?date=JJJJ-MM-TT (HTML, Spiel-ID, Liga, Teams, Zeit)
# - Spieldetails: data.sihf.ch …/gameoverview?alias=gameDetail (JSON: Resultat, Drittel, Tore mit Assists und Spielsituation,
#   Strafen, Stadion, Zuschauer, Schiedsrichter, Runde, Status)
# - Tabelle: data.sihf.ch …/cache300?alias=standing (JSON, gleiche Zahlen wie API-Hockey)
# Ausgabe im gleichen Format wie hmatch()/hockey() in fetch.py, Teams mit den bisherigen API-Hockey-IDs und -Namen
# (Logos, Kürzel, Spielerkennung bleiben gleich). Liga-IDs SIHF: 1 National League, 2 Swiss League, 100 MyHockey League.
import urllib.parse, urllib.error
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
# Offizielle Runde (26.11.2026, Cy: «wie kann die Runde 25 eine Mannschaft mehrfach drin haben?»): Highlightlys «week» ist keine Runde
# (27. NL-Runde hatte 11 Spiele, Teams doppelt) und wird nicht mehr genommen. Runden aus gameDetail tragen "ro": 1. Gespeicherte Runden
# ohne Marker gelten als offiziell, wenn das Spiel vor RO_LEGACY liegt (vor der Sperre am 24.11. mit +10 Tagen Fenster von der SIHF
# geholt); spätere stammen aus «week» → verworfen. Spiele ohne offizielle Runde zeigt der Worker als Spieltag (roundKey «d:<Tag>»).
# Eigene Rundennummern verworfen: offizielle Runden überlappen (25. und 26. Runde beide Fr/So), Nachtragsspiele sind am Spielplan nicht erkennbar.
RO_LEGACY = "2026-12-04"


def off_r(k):
    """Offizielle Runde eines gespeicherten Spiels oder None."""
    if not k or not k.get("r"): return None
    return k["r"] if k.get("ro") or (k.get("t") or "")[:10] < RO_LEGACY else None


def keep(k):
    """Gespeichertes Spiel zurückgeben, Runde nur, wenn offiziell."""
    m = {a: b for a, b in k.items() if a not in ("fin", "sid", "r", "ro")}
    r = off_r(k)
    return {**m, "r": r, **({"ro": 1} if r else {})}


BLOCKED = set()  # Hosts, die in diesem Lauf mit 403 geantwortet haben → nicht weiter anfragen (SIHF sperrt seit 24.11.2026)


def get(url, js=True):
    global calls
    host = urllib.parse.urlparse(url).netloc
    if host in BLOCKED: return None
    for attempt in range(3):
        calls += 1
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": UA}), timeout=40) as r:
                raw = r.read().decode("utf-8")
            if not js: return raw
            if raw.lstrip().startswith("/**/"): raw = raw[raw.index("(") + 1:raw.rindex(")")]
            return json.loads(raw)
        except urllib.error.HTTPError as e:
            print("SIHF-Abruf gescheitert", url[:120], e, file=sys.stderr)
            if e.code == 403:
                BLOCKED.add(host); print("SIHF sperrt", host, "– keine weiteren Abrufe in diesem Lauf", file=sys.stderr); return None
            time.sleep(3 + attempt * 3)
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
    if m["r"]: m["ro"] = 1
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


# ---- Ausweichquelle Highlightly (seit 25.11.2026, Cy): data.sihf.ch sperrt seit 24.11. mit 403. Spiele und IDs kommen weiter aus der
# SIHF-Tagesliste (www.sihf.ch geht noch), Resultat/Drittel/Status und Tabelle von Highlightly (Gratisstufe, 100 Abrufe/Tag,
# keine Torschützen/Strafen). Nur wenn die SIHF-Details fehlen. Schlüssel: Secret HIGHLIGHTLY_KEY.
import os, unicodedata
HL_KEY = os.environ.get("HIGHLIGHTLY_KEY", "")
HL_LG = {1: 44185, 2: 45036, 100: 90139}  # SIHF-Liga → Highlightly-Liga
hl_calls, hl_rem, HL_DAYS, HL_IDS = 0, None, {}, {}  # HL_IDS: Highlightly-Team-ID → [unsere ID, Name] (aus zugeordneten Spielen)


def hl_get(path):
    global hl_calls, hl_rem
    if not HL_KEY or (hl_rem is not None and hl_rem < 3): return None
    try:
        hl_calls += 1
        with urllib.request.urlopen(urllib.request.Request("https://hockey.highlightly.net" + path, headers={"x-rapidapi-key": HL_KEY, "User-Agent": UA}), timeout=30) as r:
            rem = r.headers.get("x-ratelimit-requests-remaining")
            if rem and rem.isdigit(): hl_rem = int(rem)
            return json.loads(r.read().decode("utf-8"))
    except Exception as e:
        print("Highlightly-Abruf gescheitert", path, e, file=sys.stderr)
        if isinstance(e, urllib.error.HTTPError) and e.code in (401, 403, 429): hl_rem = 0
        return None


def hl_day(day):
    if day not in HL_DAYS:
        d = hl_get(f"/matches?countryCode=CH&date={day}&timezone=Europe/Zurich")
        HL_DAYS[day] = (d or {}).get("data") if d else None
    return HL_DAYS[day]


def toks(*names):
    out = set()
    for n in names:
        n = unicodedata.normalize("NFKD", str(n or "")).encode("ascii", "ignore").decode().lower()
        out |= {w for w in re.split(r"[^a-z0-9]+", n) if len(w) >= 3 and w not in {"ehc", "club", "hockey"}}
    if "zurich" in out: out.add("zsc")
    if "zsc" in out: out.add("zurich")
    return out


def hl_find(day, sid, hn, an):
    """Highlightly-Spiel zu einem SIHF-Spiel (gleicher Tag, gleiche Liga, beide Teams per Namensteilen)."""
    for g in hl_day(day) or []:
        if (g.get("league") or {}).get("id") != HL_LG.get(sid): continue
        if toks(*hn) & toks(g["homeTeam"]["name"]) and toks(*an) & toks(g["awayTeam"]["name"]): return g
    return None


def pair(x):
    m = re.match(r"\s*(\d+)\s*-\s*(\d+)", x or "")
    return [int(m.group(1)), int(m.group(2))] if m else None


HL_ST = {"finished": "FT", "finished after overtime": "AOT", "finished after penalties": "AP", "not started": "NS", "first period": "P1",
         "second period": "P2", "third period": "P3", "1st period": "P1", "2nd period": "P2", "3rd period": "P3", "break time": "BT", "break": "BT", "overtime": "OT", "penalties": "PT",
         "postponed": "PST", "cancelled": "CANC", "canceled": "CANC", "interrupted": "INTR", "abandoned": "ABD"}


def from_hl(g, mid, t, r, h, a):
    sc = (g.get("state") or {}).get("score") or {}
    desc = ((g.get("state") or {}).get("description") or "").strip().lower()
    st = HL_ST.get(desc)
    if not st:  # 26.11.2026: im 3. Drittel stand «1. Dr.» – unbekannte Schreibweise fiel auf P1 zurück
        n = re.search(r"\b(1|2|3|first|second|third)(st|nd|rd|th)?\s*(period|drittel)", desc)
        if n: st = "P" + str({"first": 1, "second": 2, "third": 3}.get(n.group(1), n.group(1)))
        elif re.search(r"overtime|extra", desc): st = "OT"
        elif re.search(r"penalt|shoot", desc): st = "PT"
        elif re.search(r"break|interm|pause", desc): st = "BT"
        elif re.search(r"finish|ended|final", desc): st = "FT"
        elif pair(sc.get("current")):  # sonst aus den Dritteln: Drittel nach dem letzten mit Stand
            done = sum(1 for k in ("firstPeriod", "secondPeriod", "thirdPeriod") if pair(sc.get(k)))
            st = "P" + str(max(1, min(3, done)))
        else: st = "NS"
        print("Highlightly: unbekannter Status", repr(desc), "→", st, file=sys.stderr)
    if st in DONE and st == "FT" and pair(sc.get("penalties")): st = "AP"
    elif st == "FT" and pair(sc.get("overTime")) and sum(pair(sc.get("overTime"))): st = "AOT"
    HL_IDS[g["homeTeam"]["id"]], HL_IDS[g["awayTeam"]["id"]] = h, a
    fmt = lambda x: "-".join(map(str, pair(x))) if pair(x) else None
    per = [fmt(sc.get(k)) for k in ("firstPeriod", "secondPeriod", "thirdPeriod", "overTime", "penalties")]
    m = {"id": mid, "t": t, "st": st, "el": None, "r": r, "h": h, "a": a, "g": pair(sc.get("current")) if st != "NS" else None, "p": None, "per": per}
    if r: m["ro"] = 1  # r kommt nur noch als offizielle (gespeicherte) Runde herein
    # endgültig markieren, damit spätere Läufe das Spiel nicht nochmals anfragen (spart Abrufe; Torschützen gibt es hier nicht)
    info = {"final": True, "ht": None, "v": "", "ref": "", "ev": [], "sb": [], "lu": None, "zu": None, "src": "hl"} if st in DONE else None
    return m, info


def hl_table(sid):
    d = hl_get(f"/standings?leagueId={HL_LG[sid]}&season={dt.date.today().year if dt.date.today().month >= 8 else dt.date.today().year - 1}")
    rows = [x for gr in (d or {}).get("groups") or [] for x in gr.get("standings") or []]
    if not rows: return None
    out = []
    for x in sorted(rows, key=lambda x: x.get("position") or 99):
        tm = x["team"]
        tid, name = HL_IDS.get(tm["id"]) or next(([v[1], v[0]] for v in TEAMS.values() if toks(v[0]) & toks(tm["name"])), [tm["id"], tm["name"]])
        w, l, ow, ol = (x.get("wins") or 0), (x.get("loses") or 0), (x.get("winsOvertime") or 0), (x.get("losesOvertime") or 0)
        # Highlightly zählt uneinheitlich: NL wins/loses inkl. n.V./n.P. (w + l = Spiele), MyHockey League ohne (w + l + ow + ol = Spiele)
        if w + l + ow + ol == (x.get("gamesPlayed") or 0) and w + l != (x.get("gamesPlayed") or 0): w, l = w + ow, l + ol
        gf, ga, r = x.get("scoredGoals") or 0, x.get("receivedGoals") or 0, x.get("position") or 0
        out.append({"r": r, "id": tid, "n": name, "sp": x.get("gamesPlayed") or 0, "w": w - ow, "ow": ow, "ol": ol, "l": l - ol,
                    "gf": gf, "ga": ga, "gd": gf - ga, "pts": 3 * (w - ow) + 2 * ow + ol, "f": "", "grp": ""})
    # Highlightlys «position» stimmt nicht (26.11.2026: NL Biel 24 Pkt vor Davos 27, Fribourg 30 vor Lausanne 32) → selbst sortieren:
    # Punkte, weniger Spiele, Tordifferenz, Tore; Rang und Zone danach neu
    out.sort(key=lambda t: (-t["pts"], t["sp"], -t["gd"], -t["gf"]))
    for i, t in enumerate(out, 1):
        t["r"] = i; t["d"] = next((z for lim, z in ZONES.get(sid, []) if i <= lim), "")
    return out


def run(job, leagues, out, frm, to):
    """Voller Abruf: Tageslisten im Zeitfenster, Details nur wo nötig (laufend, beendet ohne endgültige Details, NL/SwL ohne Runde)."""
    season = int(job["season"]) + 1  # SIHF zählt 2026/27 als 2027
    sids = {lg["sid"]: lg for lg in leagues}
    # gespeicherte Spiele pro Liga (vom Worker, lg["hk"]), "fin": Details endgültig → kein erneuter Abruf
    known = {int(k): {**v, "sid": lg["sid"]} for lg in leagues for k, v in (lg.get("hk") or {}).items()}
    now = time.time()
    by = {sid: [] for sid in sids}
    d0, d1 = dt.date.fromisoformat(frm), dt.date.fromisoformat(to)
    want, seen, newfin = [], set(), set()
    day = d0
    while day <= d1:
        lst = day_list(day.isoformat())
        if lst is None:  # Tag nicht abrufbar → gespeicherte Spiele dieses Tages behalten
            for gid, k in known.items():
                if k.get("t", "")[:10] == day.isoformat() and k.get("sid") in by: by[k["sid"]].append(keep(k)); seen.add(gid)
        for x in lst or []:
            if x["lg"] not in sids or x["id"] in seen: continue
            seen.add(x["id"])
            k = known.get(x["id"])
            hm = re.fullmatch(r"\d{1,2}:\d{2}", x["tm"])
            t = iso(day.isoformat(), x["tm"]) if hm else (k or {}).get("t") or iso(day.isoformat(), "19:45")
            begun = dt.datetime.fromisoformat(t).timestamp() < now + 10 * 60
            if k and k.get("st") in DONE and k.get("fin"):
                by[x["lg"]].append(keep(k)); continue
            if begun or x["live"] or not hm or (x["lg"] in RND and not off_r(k)):
                want.append((x, t)); continue
            by[x["lg"]].append({"id": x["id"], "t": t, "st": "NS", "el": None, "r": off_r(k), "h": team(*x["h"]), "a": team(*x["a"]),
                                "g": None, "p": None, "per": [None] * 5, **({"ro": 1} if off_r(k) else {})})
        day += dt.timedelta(days=1)
    cap = 400 if (d1 - d0).days > 30 else 150  # Archiv-Füllung (Fenster bis 60 Tage zurück): ca. 250 Spiele
    for x, t in want[cap:]:  # über der Grenze: gespeicherten Stand behalten statt das Spiel zu verlieren
        k = known.get(x["id"])
        if k: by[x["lg"]].append(keep(k))
    for x, t in want[:cap]:
        d = detail(x["id"])
        if not d or not d.get("gameId"):
            k = known.get(x["id"])
            nb = not x["live"] and hm and dt.datetime.fromisoformat(t).timestamp() > now + 10 * 60  # nur wegen fehlender Runde angefragt
            if nb:  # Highlightly liefert keine Runde → keinen Abruf verbrauchen, Spiel ohne Runde (Spieltag)
                by[x["lg"]].append({**(keep(k) if k else {}), "id": x["id"], "t": t, "st": "NS", "el": None, "r": off_r(k), "h": team(*x["h"]), "a": team(*x["a"]),
                                    "g": None, "p": None, "per": [None] * 5, **({"ro": 1} if off_r(k) else {})})
                continue
            g = hl_find(t[:10], x["lg"], [x["h"][1], team(*x["h"])[1]], [x["a"][1], team(*x["a"])[1]]) if HL_KEY else None
            if g:
                m, info = from_hl(g, x["id"], t, off_r(k) if x["lg"] in RND else None, team(*x["h"]), team(*x["a"]))
                by[x["lg"]].append(m)
                if info: out["ev"][str(m["id"])] = info
                if m["st"] in DONE and (k or {}).get("st") not in DONE: newfin.add(x["lg"])
                continue
            by[x["lg"]].append(keep(k) if k else
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
        # Ausweichquelle: Tabelle nur, wenn in diesem Lauf ein Spiel fertig wurde oder noch keine da ist (Abrufe sparen);
        # sonst None → der Worker behält die gespeicherte Tabelle
        if table is None and lg.get("table") and HL_KEY and (sid in newfin or not lg.get("tb")): table = hl_table(sid)
        out["leagues"].append({"id": lg["id"], "sport": "hockey", "src": "sihf", "matches": sorted(by[sid], key=lambda m: m["t"] or ""), "table": table})


def live(job, leagues, out):
    """Live-Abruf: Details der laufenden Spiele (IDs vom Worker)."""
    for lg in leagues:
        ms = []
        known = next((l2.get("hk") or {} for l2 in job.get("leagues") or [] if l2.get("id") == lg["id"]), {})
        for gid in lg.get("ids") or []:
            d = detail(gid)
            if not d or not d.get("gameId"):
                # Ausweichquelle nur jeden zweiten Live-Lauf (alle 10 statt 5 min, Tageslimit 100 Abrufe)
                k = known.get(str(gid)) or known.get(gid)
                if not k or not HL_KEY or (dt.datetime.now().minute // 5) % 2 or (hl_rem is not None and hl_rem < 30): continue
                g = hl_find(dt.datetime.fromisoformat(k["t"]).astimezone(ZH).date().isoformat(), lg["sid"], [k["h"][1]], [k["a"][1]])
                if not g: continue
                m, info = from_hl(g, k["id"], k["t"], None, k["h"], k["a"])
                m.pop("r", None); ms.append(m)
                if info: out["ev"][str(m["id"])] = info
                continue
            m, info = from_detail(d, lg["sid"])
            m.pop("r", None)  # Runde bleibt die gespeicherte (Nachtragsspiele sind dort schon zugeordnet, siehe fix_rounds)
            ms.append(m)
            if info: out["ev"][str(m["id"])] = info
        out["leagues"].append({"id": lg["id"], "sport": "hockey", "matches": ms})
