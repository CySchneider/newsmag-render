# Sportdaten (API-Football + API-Hockey) für Newsmag – läuft in GitHub Actions, weil API-Sports die Cloudflare-Adressen drosselt.
# Der Worker startet den Job (workflow_dispatch mit Einmal-Token), dieses Skript holt den Auftrag (Ligen, Saison, Zeitfenster,
# bereits gespeicherte Spieldetails), ruft Spiele, Tabellen und Spieldetails ab, kürzt sie und schickt sie an den Worker.
import datetime as dt, json, os, sys, time, urllib.request
HOST = "https://newsmag.ch"
BASE = {"football": "https://v3.football.api-sports.io", "hockey": "https://v1.hockey.api-sports.io"}
KEY, JOB = os.environ["API_SPORTS_KEY"], os.environ["JOB"]
calls = 0
LIVE_F = {"1H", "HT", "2H", "ET", "BT", "P", "LIVE", "INT"}
DONE_F = {"FT", "AET", "PEN", "AWD", "WO"}

def get(sport, path):
    global calls
    d = {}
    for attempt in range(4):
        calls += 1
        req = urllib.request.Request(BASE[sport] + path, headers={"x-apisports-key": KEY})
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                d = json.load(r)
        except Exception as e:
            print("Abruf gescheitert", sport, path, e, file=sys.stderr); time.sleep(5); continue
        err = d.get("errors")
        if err and "rateLimit" in json.dumps(err):
            time.sleep(10 + attempt * 10); continue
        if err: print("Fehler", sport, path, err, file=sys.stderr)
        return d
    return d

def http_json(url, data=None):
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json", "User-Agent": "NewsmagSports/1.0"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.load(r)

job = http_json(f"{HOST}/sports-job?t={JOB}")
season, frm, to = job["season"], job.get("from"), job.get("to")
have_ev = set(job.get("have_ev") or [])
out = {"at": None, "season": season, "leagues": [], "ev": {}, "sub": {}}
want_ev = []  # Fussball-Spiele, deren Details (Tore, Karten) noch fehlen oder live sind

def fmatch(x):
    f, t, g, s = x["fixture"], x["teams"], x["goals"], x["score"]
    pen = s.get("penalty") or {}
    return {"id": f["id"], "t": f["date"], "st": f["status"]["short"], "el": f["status"].get("elapsed"),
            "r": x["league"].get("round"), "h": [t["home"]["id"], t["home"]["name"]], "a": [t["away"]["id"], t["away"]["name"]],
            "g": [g["home"], g["away"]] if g["home"] is not None else None,
            "p": [pen["home"], pen["away"]] if pen.get("home") is not None else None}

def hmatch(x):
    t, sc, per = x["teams"], x.get("scores") or {}, x.get("periods") or {}
    return {"id": x["id"], "t": x["date"], "st": x["status"]["short"], "el": x.get("timer"), "r": x.get("week"),
            "h": [t["home"]["id"], t["home"]["name"]], "a": [t["away"]["id"], t["away"]["name"]],
            "g": [sc["home"], sc["away"]] if sc.get("home") is not None else None, "p": None,
            "per": [per.get(k) for k in ("first", "second", "third", "overtime", "penalties")]}

def football(lg):
    d = get("football", f"/fixtures?league={lg['id']}&season={season}&from={frm}&to={to}&timezone=Europe/Zurich")
    matches = []
    for x in d.get("response") or []:
        f = x["fixture"]; st = f["status"]["short"]
        matches.append(fmatch(x))
        # Aufstellungen (24.10.2026) kommen ca. 20–60 min vor Anpfiff → noch nicht begonnene Spiele ab 90 min vorher mitnehmen
        soon = st == "NS" and 0 < (f.get("timestamp") or 0) - time.time() < 90 * 60
        if lg.get("ev") and (st in LIVE_F or soon): want_ev.insert(0, f["id"])  # laufende zuerst (max. 100 pro Lauf)
        elif lg.get("ev") and st in DONE_F and f["id"] not in have_ev: want_ev.append(f["id"])
    table = None
    if lg.get("table"):
        resp = get("football", f"/standings?league={lg['id']}&season={season}").get("response") or []
        if resp:
            table = [{"r": e["rank"], "id": e["team"]["id"], "n": e["team"]["name"], "sp": e["all"]["played"], "gd": e["goalsDiff"],
                      "pts": e["points"], "f": e.get("form") or "", "d": e.get("description") or "", "grp": e.get("group") or "",
                      "w": e["all"]["win"], "u": e["all"]["draw"], "l": e["all"]["lose"], "gf": e["all"]["goals"]["for"], "ga": e["all"]["goals"]["against"]}
                     for grp in resp[0]["league"]["standings"] for e in grp]
    return {"id": lg["id"], "sport": "football", "matches": matches, "table": table}

def hockey(lg):
    d = get("hockey", f"/games?league={lg['id']}&season={season}&timezone=Europe/Zurich")
    matches = []
    for x in d.get("response") or []:
        day = x["date"][:10]
        if day < frm or day > to: continue
        matches.append(hmatch(x))
    table = None
    if lg.get("table"):
        resp = get("hockey", f"/standings?league={lg['id']}&season={season}").get("response") or []
        rows = [e for grp in resp for e in (grp if isinstance(grp, list) else [grp])]
        if rows:
            table = [{"r": e["position"], "id": e["team"]["id"], "n": e["team"]["name"], "sp": e["games"]["played"],
                      "w": e["games"]["win"]["total"], "ow": (e["games"].get("win_overtime") or {}).get("total"),
                      "ol": (e["games"].get("lose_overtime") or {}).get("total"), "l": e["games"]["lose"]["total"],
                      "gf": e["goals"]["for"], "ga": e["goals"]["against"], "gd": e["goals"]["for"] - e["goals"]["against"],
                      "pts": e["points"], "f": e.get("form") or "", "d": e.get("description") or "", "grp": (e.get("group") or {}).get("name") or ""}
                     for e in rows]
    return {"id": lg["id"], "sport": "hockey", "matches": matches, "table": table}

for lg in job["leagues"]:
    out["leagues"].append(hockey(lg) if lg.get("sport") == "hockey" else football(lg))

# Spieldetails Fussball: bis 20 Spiele pro Abruf (/fixtures?ids=…) – Tore, Karten, Pausenstand, Stadion, Schiedsrichter
TYPES = {("Goal", "Normal Goal"): "g", ("Goal", "Own Goal"): "og", ("Goal", "Penalty"): "pg", ("Goal", "Missed Penalty"): "mp",
         ("Card", "Yellow Card"): "y", ("Card", "Red Card"): "r", ("Card", "Second Yellow card"): "yr"}
def lineup(x):
    # Aufstellungen (Cy 24.10.2026): nur in /fixtures?ids=, nicht im Live-Abruf. {"h"|"a": [Formation, Trainer, Startelf, Ersatz]},
    # Spieler [Nummer, Name, Position G/D/M/F]. Leere Liste → None (Liga ohne Aufstellungen, z. B. Challenge League)
    out, home = {}, x["teams"]["home"]["id"]
    for t in x.get("lineups") or []:
        pl = lambda L: [[(p.get("player") or {}).get("number"), (p.get("player") or {}).get("name") or "", (p.get("player") or {}).get("pos") or ""] for p in L or []]
        xi = pl(t.get("startXI"))
        if xi: out["h" if (t.get("team") or {}).get("id") == home else "a"] = [t.get("formation") or "", (t.get("coach") or {}).get("name") or "", xi, pl(t.get("substitutes"))]
    return out or None

def evof(x, lu=False):
    f, s, home = x["fixture"], x["score"], x["teams"]["home"]["id"]
    ev = []
    sb = []  # Wechsel (24.10.2026) nur für die Aufstellung: [Minute, Nachspielzeit, h/a, Spieler, Vorlage-Feld] – wer raus/rein, bestimmt die Seite über die Startelf (API vertauscht die Felder teils)
    for e in x.get("events") or []:
        if (e.get("type") or "").lower() == "subst":
            sb.append([e["time"]["elapsed"], e["time"].get("extra"), "h" if e["team"]["id"] == home else "a", (e.get("player") or {}).get("name") or "", (e.get("assist") or {}).get("name") or ""])
            continue
        ty = TYPES.get((e.get("type"), e.get("detail")))
        if not ty: continue
        ev.append([e["time"]["elapsed"], e["time"].get("extra"), "h" if e["team"]["id"] == home else "a", ty,
                   (e.get("player") or {}).get("name") or "", (e.get("assist") or {}).get("name") or ""])
    ht = s.get("halftime") or {}
    # endgültig erst, wenn alle Namen da sind (live/Cup fehlen sie oft und kommen später) – spätestens 24 h nach Anpfiff
    named = all(e[4] for e in ev)
    old = dt.datetime.now(dt.timezone.utc).timestamp() - (f.get("timestamp") or 0) > 24 * 3600
    r = {"final": f["status"]["short"] in DONE_F and (named or old), "ht": [ht.get("home"), ht.get("away")] if ht.get("home") is not None else None,
            "v": ", ".join(v for v in [(f.get("venue") or {}).get("name"), (f.get("venue") or {}).get("city")] if v),
            "ref": (f.get("referee") or "").split(",")[0], "ev": ev, "sb": sb}
    if lu: r["lu"] = lineup(x)  # nur aus /fixtures?ids= (Live-Abruf hat keine) → Worker behält sonst die gespeicherte
    return r

if job.get("mode") == "live":
    # Live-Abruf: nur laufende Spiele. Fussball 1 Abruf für alle Ligen (inkl. Ereignisse), Eishockey 1 Abruf pro Liga (heutige Spiele).
    fb = [l["id"] for l in job["live"] if l["sport"] == "football"]
    if fb:
        by = {}
        # «live=<id>» mit nur einer Liga lehnt die API ab (verlangt id-id… oder all) → alle laufenden Spiele, selbst gefiltert
        for x in get("football", "/fixtures?live=all&timezone=Europe/Zurich").get("response") or []:
            if x["league"]["id"] not in fb: continue
            by.setdefault(x["league"]["id"], []).append(fmatch(x))
            out["ev"][str(x["fixture"]["id"])] = evof(x)
        out["leagues"] += [{"id": i, "sport": "football", "matches": by.get(i, [])} for i in fb]
    for l in job["live"]:
        if l["sport"] != "hockey": continue
        res = get("hockey", f"/games?league={l['id']}&season={season}&date={job['day']}&timezone=Europe/Zurich").get("response") or []
        out["leagues"].append({"id": l["id"], "sport": "hockey", "matches": [hmatch(x) for x in res]})
    out["mode"], out["at"], out["calls"] = "live", dt.datetime.now(dt.timezone.utc).isoformat(), calls
    res = http_json(f"{HOST}/sports-push?t={JOB}", json.dumps(out).encode())
    print("live gesendet:", res, "Abrufe:", calls, "Spiele:", sum(len(l["matches"]) for l in out["leagues"]))
    sys.exit(0)

for i in range(0, min(len(want_ev), 100), 20):
    ids = "-".join(str(x) for x in want_ev[i:i + 20])
    for x in get("football", f"/fixtures?ids={ids}&timezone=Europe/Zurich").get("response") or []:
        out["ev"][str(x["fixture"]["id"])] = evof(x, True)

for sport in ("football", "hockey"):
    if any((lg.get("sport") or "football") == sport for lg in job["leagues"]):
        st = get(sport, "/status").get("response") or {}
        if isinstance(st, dict):
            out["sub"][sport] = {"plan": (st.get("subscription") or {}).get("plan"), "end": (st.get("subscription") or {}).get("end"),
                                 "used": (st.get("requests") or {}).get("current"), "limit": (st.get("requests") or {}).get("limit_day")}
out["at"] = dt.datetime.now(dt.timezone.utc).isoformat()
out["calls"] = calls
res = http_json(f"{HOST}/sports-push?t={JOB}", json.dumps(out).encode())
print("gesendet:", res, "Abrufe:", calls, "Ligen:", len(out["leagues"]), "Spiele:", sum(len(l["matches"]) for l in out["leagues"]), "Details:", len(out["ev"]))
