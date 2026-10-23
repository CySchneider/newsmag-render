#!/usr/bin/env python3
"""YouTube-Video einer Newscast-Folge (seit 15.10.2026). Aufruf aus .github/workflows/youtube.yml: yt.py <Einmal-Token>
Holt den Auftrag vom Worker (/yt-job), rendert 16:9 (render.mjs), baut das MP4 (ffmpeg), lädt es über die YouTube-API hoch
(Zugriffs-Token von /yt-token, der Refresh-Token bleibt im Worker) und meldet das Ergebnis an /yt-done → Telegram.
Zeiten: Absätze exakt aus dem Mischen im Worker, Sätze darin über Sprechpausen (ffmpeg silencedetect)."""
import json, os, re, subprocess, sys, time, urllib.request, urllib.error

BASE = "https://newsmag.ch"
HERE = os.path.dirname(os.path.abspath(__file__))
TOKEN = sys.argv[1]
UA = {"User-Agent": "newsmag-youtube"}


def http(url, data=None, headers=None, method=None, timeout=120):
    req = urllib.request.Request(url, data=data, headers={**UA, **(headers or {})}, method=method)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.status, dict(r.headers), r.read()


def api_json(url, body=None, token=None, method=None):
    h = {"Content-Type": "application/json"} if body is not None else {}
    if token: h["Authorization"] = "Bearer " + token
    try:
        _, _, raw = http(url, json.dumps(body).encode() if body is not None else None, h, method)
        return json.loads(raw or b"{}")
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"{e.code} {url.split('?')[0]}: {e.read()[:300].decode('utf-8', 'replace')}")


def done(**kw):
    # Zeitüberschreitung ≠ Fehler (23.10.2026): der Worker arbeitet weiter; früher überschrieb der Fehler-Rückruf danach die Short-ID
    try: http(f"{BASE}/yt-done?t={TOKEN}", json.dumps(kw).encode(), {"Content-Type": "application/json"}, "POST", 240)
    except (TimeoutError, OSError) as e:
        if isinstance(e, urllib.error.HTTPError): raise
        print("yt-done: keine Antwort innert 240 s – Worker arbeitet weiter", e)


# ── Untertitel: Sätze, Schreibweise statt Sprechweise ──
RUBRIK = {"Schweiz.", "Ausland.", "Wirtschaft.", "Digital.", "Kultur und Wissen.", "Sport.", "Das Wetter.",
          "Das Wichtigste des Tages.", "Seit dem Abend.", "International."}


def sentences(p):
    out = []
    for x in re.split(r"(?<=[.!?])\s+(?=[A-ZÄÖÜ0-9«])", p):
        if out and re.search(r"(\d\.|\bSt\.|\bNr\.|\bDr\.)$", out[-1]): out[-1] += " " + x
        else: out.append(x)
    res = []
    for x in out:
        if len(x) <= 125: res.append(x); continue
        cur = ""
        for q in re.split(r"(?<=,)\s+", x):
            if cur and len(cur) + len(q) > 110: res.append(cur); cur = q
            else: cur = (cur + " " + q).strip()
        if cur: res.append(cur)
    return res


def written(s):
    s = re.sub(r"(\d+) Uhr (\d+)", r"\1.\2 Uhr", s)
    s = re.sub(r"(\d+) zu (\d+)", r"\1:\2", s)
    return s.replace("newsmag punkt c h", "newsmag.ch")


def silences(mp3):
    err = subprocess.run(["ffmpeg", "-hide_banner", "-i", mp3, "-af", "silencedetect=noise=-38dB:d=0.22", "-f", "null", "-"],
                         capture_output=True, text=True).stderr
    st = [float(x) for x in re.findall(r"silence_start: ([0-9.]+)", err)]
    en = [float(x) for x in re.findall(r"silence_end: ([0-9.]+)", err)]
    return list(zip(st, en))


WORD = re.compile(r"[A-Za-zÄÖÜäöüéèàç]{4,}")


def words(s): return {w.lower() for w in WORD.findall(s or "")}


def build_timeline(job, sil):
    paras, topics = job["paras"], job["topics"]
    caps, scenes = [], []
    tw = [words(t["title"] + " " + t["lead"] + " " + t["head"]) for t in topics]
    last_topic = None
    for i, p in enumerate(paras):
        text, a, b = p["text"], p["t0"], p["t1"]
        # Szene des Absatzes
        if i == 0: sc = ("title", None)
        elif text.startswith("Die Themen"): sc = ("themes", None)
        elif "newsmag punkt c h" in text or "Margareth von KI" in text: sc = ("end", None)
        elif text.startswith("Das Wetter"): sc = ("weather", None)
        else:
            # Thema mit den meisten gemeinsamen Wörtern (Titel, Lead, Schlagzeile); bei Gleichstand das nächste in Sendereihenfolge
            pw = words(text)
            score = [len(pw & w) + (0.5 if last_topic is not None and k == last_topic + 1 else 0) for k, w in enumerate(tw)]
            best = max(range(len(topics)), key=lambda k: score[k]) if topics else None
            if best is not None and score[best] >= 2: last_topic = best
            sc = ("topic", last_topic) if last_topic is not None else ("title", None)
        scenes.append((max(0.0, a - 0.35), sc))
        # Sätze: Zeit nach Zeichen, an Sprechpausen angelehnt
        ss = sentences(text)
        n = sum(len(x) for x in ss) or 1
        cuts, t = [a], a
        for x in ss[:-1]:
            t += len(x) / n * (b - a)
            near = [s for s in sil if a + 0.4 < (s[0] + s[1]) / 2 < b - 0.4 and abs((s[0] + s[1]) / 2 - t) < 1.8]
            cuts.append((lambda c: (c[0] + c[1]) / 2)(min(near, key=lambda s: abs((s[0] + s[1]) / 2 - t))) if near else t)
        cuts.append(b)
        # Wortanfänge aus den ElevenLabs-Zeitstempeln (seit 23.10.2026, p["w"], s ab Absatzbeginn) → Satzgrenzen exakt
        pw = p.get("w") if p.get("w") and len(p["w"]) == len(text.split()) else None
        wts, off = [], 0
        for j, x in enumerate(ss):
            n = len(x.split()); wts.append([round(a + q, 3) for q in pw[off:off + n]] if pw else None); off += n
            if wts[-1] and j: cuts[j] = wts[-1][0]
        for j, x in enumerate(ss):
            if x.strip() in RUBRIK: continue
            caps.append({"t0": cuts[j], "t1": cuts[j + 1] if j + 1 < len(ss) else b, "text": written(x), **({"wt": wts[j]} if wts[j] else {})})
    # «Die Themen: …» – jedes genannte Thema leuchtet auf, sobald es gesprochen wird
    marks = []
    for p in paras:
        if not p["text"].startswith("Die Themen"): continue
        s = p["text"]; body = s.split(":", 1)[1] if ":" in s else s
        items = [x.strip() for x in re.split(r",\s*|\s+und\s+das Wetter", body) if x.strip()]
        pos = len(s) - len(body)
        for it in items:
            iw = words(it); sc = [len(iw & w) for w in tw]
            k = max(range(len(topics)), key=lambda q: sc[q]) if topics else -1
            if k >= 0 and sc[k] >= 1: marks.append((p["t0"] + pos / len(s) * (p["t1"] - p["t0"]), k))
            pos += len(it) + 2
    return caps, scenes, marks


def frames(job, caps, scenes, marks, end):
    def scene_at(t):
        cur = ("title", None)
        for t0, sc in scenes:
            if t >= t0: cur = sc
        return cur
    cuts = {0.0, end} | {c["t0"] for c in caps} | {c["t1"] for c in caps} | {s[0] for s in scenes} | {m[0] for m in marks}
    cuts = sorted(x for x in cuts if 0 <= x <= end)
    out = []
    for a, b in zip(cuts, cuts[1:]):
        if b - a < 0.04: continue
        m = (a + b) / 2
        sc = scene_at(m)
        cap = next((c["text"] for c in caps if c["t0"] <= m < c["t1"]), "")
        lit = sorted({k for t, k in marks if t <= m}) if sc[0] == "themes" else []
        cur = max(((t, k) for t, k in marks if t <= m), default=(0, -1))[1] if sc[0] == "themes" else -1
        f = {"dur": round(b - a, 3), "scene": sc[0], "topic": sc[1], "cap": cap, "lit": lit, "cur": cur}
        if out and all(out[-1][k] == f[k] for k in ("scene", "topic", "cap", "lit", "cur")): out[-1]["dur"] = round(out[-1]["dur"] + f["dur"], 3)
        else: out.append(f)
    return out


# ── Einzel-Reels (seit 21.10.2026): ein Reel pro Thema aus Margareths Absatz, 9:16, Untertitel Satz für Satz ──
# Der Worker gibt in job["reel_ids"] die Themen-Indizes vor (ohne Rückblick, ohne heute schon gepostete). Pro Thema der erste
# zusammenhängende Absatz-Block; Rubrik-Ansage («Schweiz.») fällt weg, im Sport die Resultat-Liste («In den weiteren Spielen …»).
SPORT_TAIL = re.compile(r"^(In den weiteren Spielen|In weiteren Spielen|Im weiteren Spiel|In der (Super|Challenge|National|Swiss) League|In der Champions League|Noch im Gang|Die weiteren Resultate)")
REEL_MAX = 88.0


def reel_specs(job, caps, scenes):
    out = []
    for k in job.get("reel_ids") or []:
        if k >= len(job["topics"]): continue
        idx = [i for i, (_, sc) in enumerate(scenes) if sc == ("topic", k)]
        if not idx: continue
        run = [idx[0]]
        for i in idx[1:]:
            if i == run[-1] + 1: run.append(i)
            else: break
        a, b = job["paras"][run[0]]["t0"], job["paras"][run[-1]]["t1"]
        cs = [c for c in caps if c["t0"] >= a - 0.05 and c["t1"] <= b + 0.05]
        if job["topics"][k].get("kicker") == "Sport":
            for j, c in enumerate(cs):
                if j and SPORT_TAIL.search(c["text"]): cs = cs[:j]; break
        while len(cs) > 1 and cs[-1]["t1"] - cs[0]["t0"] > REEL_MAX: cs = cs[:-1]
        if not cs: continue
        t0, t1 = max(0.0, cs[0]["t0"] - 0.12), cs[-1]["t1"] + 0.08
        if t1 - t0 < 8: continue
        rc = [{"text": c["text"], "dur": round((cs[j + 1]["t0"] if j + 1 < len(cs) else t1) - (t0 if j == 0 else c["t0"]), 3),
               **({"wt": [round(x - t0, 3) for x in c["wt"]]} if c.get("wt") else {})} for j, c in enumerate(cs)]
        t = job["topics"][k]
        theme = (job.get("reel_themes") or {}).get(str(k)) or ("pink" if t.get("kicker") == "Sport" else "dunkel")
        out.append({"k": k, "id": t["id"], "a": round(t0, 3), "b": round(t1, 3), "kicker": t.get("kicker") or "", "head": t["head"],
                    "publishers": t.get("publishers") or 0, "update": bool(t.get("update")), "theme": theme, "caps": rc})
    return out


def reel_outros(job):
    """Endsätze (Margareth, einmalig gesprochen, Worker: reelOutroList) als WAV holen; Fehler → Reels ohne Endsatz."""
    got = []
    for o in job.get("reel_outros") or []:
        try:
            if os.environ.get("YT_JOB_FILE") and o.get("file"): got.append(dict(o)); continue  # lokaler Test
            _, _, data = http(f"{BASE}/yt-outro?t={TOKEN}&i={o['i']}", timeout=60)
            f = f"outro-{o['i']}.wav"; open(f, "wb").write(data); got.append({**o, "file": f})
        except Exception as e:
            print("Endsatz fehlt", o.get("i"), e)
    return got


def build_reels(job, caps, scenes):
    specs = reel_specs(job, caps, scenes)
    if not specs: return []
    outros = reel_outros(job)
    for n, r in enumerate(specs):
        o = outros[(n + sum(map(ord, job.get("id", "")))) % len(outros)] if outros else None  # Endsatz wechselt pro Reel und Folge
        r["gap"] = 0.35
        r["end"] = {"text": o["text"], "dur": o["dur"], "w": o.get("w"), "file": o["file"]} if o else None
    json.dump({"reels": specs}, open("reels.json", "w"), ensure_ascii=False)
    subprocess.run(["node", os.path.join(HERE, "..", "reel", "render.mjs"), "reels.json", "reels"], check=True)
    meta = {m["k"]: m for m in json.load(open("reels/meta.json"))}
    beat = os.path.join(HERE, "..", "news-beat.m4a")
    done_list = []
    for r in specs:
        m, out = meta[r["k"]], f"reels/reel-{r['k']}.mp4"
        v, T, wy, wc = r["b"] - r["a"], m["T"], m["waveY"], m["wave"]
        e = r.get("end")
        ins = ["-f", "concat", "-safe", "0", "-i", f"reels/{r['k']}/list.txt", "-i", "ep.mp3", "-stream_loop", "-1", "-i", beat] + (["-i", e["file"]] if e else [])
        voice = f"[1:a]atrim=start={r['a']:.3f}:end={r['b']:.3f},asetpts=PTS-STARTPTS,volume=1.25[v0];"
        if e: voice += f"[3:a]asetpts=PTS-STARTPTS,adelay={int(m['e0'] * 1000)}:all=1,volume=1.25[v1];[v0][v1]amix=inputs=2:normalize=0:duration=longest[vm];"
        else: voice += "[v0]anull[vm];"
        nv = bool(job.get("novoice"))  # ohne Stimme: keine Wellenform, Beat trägt (lauter)
        fc = (voice + f"[vm]apad=whole_dur={T:.3f},asplit=2[vx][vw];"
              f"[vw]volume=2.2,showwaves=s=796x{70}:mode=cline:rate=30:colors={wc}:scale=sqrt:draw=full,format=yuva420p[w];"
              + ("[0:v]fps=30,format=yuv420p[vout];[w]nullsink;" if nv else
                 f"[0:v]fps=30,format=yuv420p,drawbox=x=84:y={wy + 34}:w=796:h=2:c={wc}@0.5:t=fill:enable='gte(t,0.7)'[bl];[bl][w]overlay=84:{wy}:shortest=0:enable='gte(t,0.25)',format=yuv420p[vout];") +
              f"[2:a]atrim=0:{T:.3f},asetpts=PTS-STARTPTS,volume={0.32 if nv else 0.10},afade=t=out:st={T - 0.95:.3f}:d=0.95[beat];"
              f"[vx][beat]amix=inputs=2:normalize=0:duration=longest,atrim=0:{T:.3f},alimiter=limit=0.95[aout]")
        try:
            subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y"] + ins + ["-filter_complex", fc, "-map", "[vout]", "-map", "[aout]", "-t", f"{T:.3f}",
                            "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-r", "30", "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart", out], check=True)
            if os.environ.get("YT_JOB_FILE"): done_list.append({"k": r["k"], "id": r["id"], "dur": round(T, 1)}); continue  # lokaler Test: nicht hochladen
            data = open(out, "rb").read()
            for attempt in range(3):  # Hochladen bis 3× (23.10.2026: 2 von 6 Reels gingen durch eine Zeitüberschreitung verloren)
                try: http(f"{BASE}/yt-reel?t={TOKEN}&k={r['k']}", data, {"Content-Type": "video/mp4"}, "POST", 300); break
                except Exception as ue:
                    print("Reel-Upload Versuch", attempt + 1, r["k"], ue)
                    if attempt == 2: raise
                    time.sleep(10)
            done_list.append({"k": r["k"], "id": r["id"], "dur": round(T, 1)})
            print("Reel", r["k"], r["theme"], round(T, 1), "s", os.path.getsize(out) // 1024, "KB")
        except Exception as ex:
            print("Reel FEHLER", r["k"], ex)
    return done_list


def mmss(t): t = int(t); return f"{t // 60}:{t % 60:02d}"


def chapters(job, scenes):
    ch, seen = [("0:00", "Begrüssung und Themen")], set()
    for t0, (kind, k) in scenes:
        if kind == "topic" and k not in seen:
            seen.add(k); label = ("Rückblick: " if job["topics"][k]["recap"] else "") + job["topics"][k]["chap"]
            ch.append((mmss(t0), label))
        if kind == "weather" and "w" not in seen: seen.add("w"); ch.append((mmss(t0), "Das Wetter"))
    # YouTube: Kapitel mindestens 10 s auseinander, aufsteigend
    res = []
    for c in ch:
        sec = int(c[0].split(":")[0]) * 60 + int(c[0].split(":")[1])
        if res and sec - res[-1][2] < 10: continue
        res.append((c[0], c[1], sec))
    return [(a, b) for a, b, _ in res]


def describe(job, ch):
    y = job["yt"]
    d = y["intro"] + "\n\n" + "\n".join(f"{a} {b}" for a, b in ch) + "\n\nZum Nachlesen, mit Links zu den Originalartikeln:\n" + "\n".join(y["links"]) + "\n\n" + y["outro"]
    d = d.replace("<", "‹").replace(">", "›")
    while len(d.encode()) > 4900: d = d[:-200]
    return d


def upload(job, mp4, thumb, desc):
    tok = api_json(f"{BASE}/yt-token?t={TOKEN}")["access_token"]
    y = job["yt"]
    meta = {"snippet": {"title": y["title"][:100].replace("<", "").replace(">", ""), "description": desc, "categoryId": "25",
                        "tags": ["Newsmag", "Nachrichten", "Schweiz", "News Schweiz", "Nachrichten Schweiz", job["edition"]],
                        "defaultLanguage": "de", "defaultAudioLanguage": "de"},
            "status": {"privacyStatus": "public", "selfDeclaredMadeForKids": False, "embeddable": True, "containsSyntheticMedia": True}}
    size = os.path.getsize(mp4)
    try:
        _, hd, _ = http("https://www.googleapis.com/upload/youtube/v3/videos?uploadType=resumable&part=snippet,status",
                        json.dumps(meta).encode(), {"Authorization": "Bearer " + tok, "Content-Type": "application/json; charset=UTF-8",
                                                    "X-Upload-Content-Type": "video/mp4", "X-Upload-Content-Length": str(size)}, "POST")
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"Upload-Start {e.code}: {e.read()[:400].decode('utf-8', 'replace')}")
    loc = hd.get("Location") or hd.get("location")
    with open(mp4, "rb") as f: data = f.read()
    try:
        _, _, raw = http(loc, data, {"Authorization": "Bearer " + tok, "Content-Type": "video/mp4"}, "PUT", 900)
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"Upload {e.code}: {e.read()[:400].decode('utf-8', 'replace')}")
    v = json.loads(raw)
    vid, privacy, notes = v["id"], v.get("status", {}).get("privacyStatus"), []
    try:  # eigenes Vorschaubild (braucht einen per Telefon bestätigten Kanal)
        with open(thumb, "rb") as f:
            http(f"https://www.googleapis.com/upload/youtube/v3/thumbnails/set?videoId={vid}", f.read(), {"Authorization": "Bearer " + tok, "Content-Type": "image/jpeg"}, "POST")
    except Exception as e:
        notes.append("Vorschaubild nicht gesetzt (" + str(getattr(e, "code", e))[:3] + ") – Kanal in YouTube Studio per Telefon bestätigen")
    try:  # Playlist pro Ausgabe («Newsmag am Morgen» usw.), wird beim ersten Mal angelegt
        pl = api_json("https://www.googleapis.com/youtube/v3/playlists?part=snippet&mine=true&maxResults=50", token=tok)
        pid = next((p["id"] for p in pl.get("items", []) if p["snippet"]["title"] == y["playlist"]), None)
        if not pid:
            pid = api_json("https://www.googleapis.com/youtube/v3/playlists?part=snippet,status", {"snippet": {"title": y["playlist"],
                           "description": f"Alle Folgen «{y['playlist']}» – die Nachrichten aus der Schweiz. newsmag.ch", "defaultLanguage": "de"},
                           "status": {"privacyStatus": "public"}}, tok)["id"]
        # Direkt nach dem Upload antwortet YouTube oft mit 409 «operation aborted» (Video noch in Verarbeitung,
        # neue Playlist noch nicht bereit) → ohne feste Position und mit Wartezeit bis zu 4× versuchen (15.10.2026)
        import time
        for k in range(4):
            try:
                api_json("https://www.googleapis.com/youtube/v3/playlistItems?part=snippet", {"snippet": {"playlistId": pid,
                         "resourceId": {"kind": "youtube#video", "videoId": vid}}}, tok)
                break
            except RuntimeError as e:
                if not str(e).startswith("409") or k == 3: raise
                time.sleep(15 * (k + 1))
    except Exception as e:
        notes.append("Playlist nicht ergänzt (" + str(e)[:3] + ")")
    return vid, privacy, notes


def upload_short(sh, mp4):
    """Einzel-Reel als YouTube-Short (senkrecht, < 3 min → YouTube erkennt es als Short). Kein eigenes Vorschaubild, keine Playlist."""
    tok = api_json(f"{BASE}/yt-token?t={TOKEN}")["access_token"]
    meta = {"snippet": {"title": sh["title"][:100].replace("<", "").replace(">", ""), "description": sh["desc"][:4900], "categoryId": "25",
                        "tags": ["Newsmag", "Nachrichten", "Schweiz", "News Schweiz", "Shorts"], "defaultLanguage": "de", "defaultAudioLanguage": "de"},
            "status": {"privacyStatus": "public", "selfDeclaredMadeForKids": False, "embeddable": True, "containsSyntheticMedia": True}}
    size = os.path.getsize(mp4)
    try:
        _, hd, _ = http("https://www.googleapis.com/upload/youtube/v3/videos?uploadType=resumable&part=snippet,status",
                        json.dumps(meta).encode(), {"Authorization": "Bearer " + tok, "Content-Type": "application/json; charset=UTF-8",
                                                    "X-Upload-Content-Type": "video/mp4", "X-Upload-Content-Length": str(size)}, "POST")
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"Upload-Start {e.code}: {e.read()[:300].decode('utf-8', 'replace')}")
    with open(mp4, "rb") as f: data = f.read()
    try:
        _, _, raw = http(hd.get("Location") or hd.get("location"), data, {"Authorization": "Bearer " + tok, "Content-Type": "video/mp4"}, "PUT", 600)
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"Upload {e.code}: {e.read()[:300].decode('utf-8', 'replace')}")
    return json.loads(raw)["id"]


def main():
    if os.environ.get("YT_JOB_FILE"): job = json.load(open(os.environ["YT_JOB_FILE"]))  # lokaler Test
    else: job = json.loads(http(f"{BASE}/yt-job?t={TOKEN}")[2])
    if not job or job.get("token") != TOKEN: sys.exit("Auftrag nicht gefunden oder veraltet")
    print(job["edition"], job["id"], len(job["paras"]), "Absätze,", len(job["topics"]), "Themen")
    try:
        if job.get("novoice"):  # Reel von Hand ohne Folge (23.10.2026): stille Tonspur, Text im Lesetempo, Beat lauter
            T = float(job["paras"][0]["t1"])
            subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi", "-i", "anullsrc=r=44100:cl=mono", "-t", f"{T + 1:.2f}", "ep.mp3"], check=True)
            text = job["paras"][0]["text"]; ss = sentences(text); n = sum(len(x) for x in ss) or 1; t = 0.0; caps = []
            for x in ss: d = len(x) / n * T; caps.append({"t0": round(t, 3), "t1": round(t + d, 3), "text": written(x)}); t += d
            scenes = [(0.0, ("topic", 0))]
            reels, note = [], ""
            try: reels = build_reels(job, caps, scenes)
            except Exception as e: note = str(e)[:300]; print("Reels FEHLER", e)
            done(reelsOnly=True, reels=reels, reelNote=note or ("" if reels else "kein Reel hochgeladen"))
            return
        _, _, mp3 = http(job["audio"], timeout=300)
        open("ep.mp3", "wb").write(mp3)
        end = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", "ep.mp3"], capture_output=True, text=True).stdout.strip())
        caps, scenes, marks = build_timeline(job, silences("ep.mp3"))
        if os.environ.get("YT_DRY") in ("2", "3"):  # 2 = «reels neu»; 3 = Standard seit 23.10.2026: Reels + wichtigstes als YouTube-Short
            reels, note = [], ""
            try: reels = build_reels(job, caps, scenes)
            except Exception as e: note = str(e)[:300]; print("Reels FEHLER", e)
            short = {}
            if os.environ.get("YT_DRY") == "3" and job.get("short"):
                f = f"reels/reel-{job['short']['k']}.mp4"
                try:
                    if not os.path.exists(f): raise RuntimeError("Reel-Datei fehlt")
                    if os.environ.get("YT_JOB_FILE"): print("lokal, kein Short-Upload", f)
                    else: short["shortId"] = upload_short(job["short"], f); print("Short hochgeladen", short["shortId"])
                except Exception as e:
                    print("Short FEHLER", e); short["shortError"] = str(e)[:300]
            done(reelsOnly=True, reels=reels, reelNote=note or ("" if reels else "kein Reel hochgeladen"), **short)
            return
        fr = frames(job, caps, scenes, marks, end)
        json.dump({"job": job, "frames": fr}, open("timeline.json", "w"), ensure_ascii=False)
        subprocess.run(["node", os.path.join(HERE, "render.mjs"), "timeline.json", "fr"], check=True)
        subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "concat", "-safe", "0", "-i", "fr/list.txt", "-i", "ep.mp3",
                        "-f", "lavfi", "-i", "color=c=0xFF00A6:s=1920x8:r=25", "-filter_complex",
                        "[0:v]fps=25,format=yuv420p,drawbox=x=0:y=ih-8:w=iw:h=8:color=0x2A2E35@1:t=fill[bg];"
                        "[1:a]asplit[a1][a2];[a2]showwaves=s=300x70:mode=cline:scale=sqrt:colors=0xFF00A6:rate=25[w];"
                        "[bg][w]overlay=x=W-96-300:y=H-50-70[v1];"
                        f"[v1][2:v]overlay=x='-W+W*t/{end:.2f}':y=H-8:eval=frame:shortest=1[v]",
                        "-map", "[v]", "-map", "[a1]", "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-tune", "stillimage",
                        "-c:a", "aac", "-b:a", "160k", "-t", f"{end:.2f}", "-movflags", "+faststart", "newsmag-youtube.mp4"], check=True)
        subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", "fr/thumb.png", "-vf", "scale=1280:720", "-q:v", "3", "thumb.jpg"], check=True)
        site_note = ""
        try:  # Website-Fassung (seit 16.10.2026): MP4 + Vorschaubild auch nach newsmag.ch (R2), scharf und ohne YouTube-Untertitel
            with open("newsmag-youtube.mp4", "rb") as f:
                http(f"{BASE}/yt-video?t={TOKEN}", f.read(), {"Content-Type": "video/mp4"}, "POST", 600)
            with open("thumb.jpg", "rb") as f:
                http(f"{BASE}/yt-video?t={TOKEN}&poster=1", f.read(), {"Content-Type": "image/jpeg"}, "POST", 120)
            print("Website-Video hochgeladen", os.path.getsize("newsmag-youtube.mp4") // 1024, "KB")
        except Exception as e:
            print("Website-Video FEHLER", e)
            site_note = "Website-Video nicht hochgeladen: " + str(getattr(e, "code", e))[:120]
        reels, reel_note = [], ""
        if job.get("reel_ids") and os.environ.get("YT_DRY") != "1":
            try: reels = build_reels(job, caps, scenes)
            except Exception as e: print("Reels FEHLER", e); reel_note = str(e)[:300]
        ch = chapters(job, scenes)
        desc = describe(job, ch)
        open("beschreibung.txt", "w").write(job["yt"]["title"] + "\n\n" + desc)
        if os.environ.get("YT_DRY") == "1":  # nur Website-Video (Telegram «youtube website»)
            print(desc); done(site=not site_note, note=site_note); return
        if os.environ.get("YT_JOB_FILE"): print("lokal, kein Upload", reels); return
        try: vid, privacy, notes = upload(job, "newsmag-youtube.mp4", "thumb.jpg", desc)
        except Exception as e:
            done(error=str(e)[:500], reels=reels); e.reported = True; raise
        if site_note: notes.append(site_note)
        print("hochgeladen", vid, privacy, notes)
        done(videoId=vid, privacy=privacy, note="\n".join(notes), reels=reels, reelNote=reel_note)
    except Exception as e:
        print("FEHLER", e)
        if getattr(e, "reported", False): raise
        try: done(error=str(e)[:500])
        finally: raise


if __name__ == "__main__":
    main()
