# Testabrufe API-Sports aus GitHub Actions (Cloudflare-Adressen werden gedrosselt). Schlüssel nur aus dem Secret, nie ausgeben.
import json, os, sys, time, urllib.request
BASE = {"football": "https://v3.football.api-sports.io", "hockey": "https://v1.hockey.api-sports.io"}
key = os.environ["API_SPORTS_KEY"]
for i, q in enumerate(json.loads(os.environ["PROBE"])):
    if i: time.sleep(7)
    req = urllib.request.Request(BASE[q["api"]] + q["path"], headers={"x-apisports-key": key})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            body = r.read().decode("utf-8", "replace"); rem = r.headers.get("x-ratelimit-requests-remaining")
    except Exception as e:
        body, rem = str(e), None
    print(f"===== {q['api']} {q['path']} (übrig heute: {rem})")
    print(body[: q.get("max", 4000)])
    # Kurzfassung als Annotation (über die REST-API lesbar, auch wenn das Protokoll nicht erreichbar ist)
    try:
        d = json.loads(body); short = json.dumps({"errors": d.get("errors"), "results": d.get("results"), "rem": rem, "resp": [{"id": (x.get("league") or x).get("id"), "name": (x.get("league") or x).get("name"), "type": (x.get("league") or x).get("type"), "cur": [s.get("year", s.get("season")) for s in x.get("seasons", []) if s.get("current")]} for x in d["response"]] if os.environ.get("LIST") and isinstance(d.get("response"), list) else d.get("response")}, ensure_ascii=False)
    except Exception:
        short = body
    print(f"::notice title={q['api']} {q['path']}::" + short[: q.get("max", 4000)].replace("%", "%25").replace("\r", "").replace("\n", "%0A"))
    sys.stdout.flush()
