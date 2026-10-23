# Holt den Video-Auftrag vom Worker und schreibt slides.json, ig.txt, wa.txt, edition.txt
import json, sys, urllib.request
token = sys.argv[1]
req = urllib.request.Request(f"https://newsmag.ch/video-job?t={token}", headers={"User-Agent": "newsmag-video"})
job = json.load(urllib.request.urlopen(req, timeout=30))
if not job or job.get("token") != token: sys.exit("Auftrag nicht gefunden oder veraltet")
json.dump(job["slides"], open("slides.json", "w"), ensure_ascii=False)
for k in ("ig", "wa", "edition"): open(f"{k}.txt", "w").write(job[k])
print(job["edition"], len(job["slides"]["slides"]), "Schlagzeilen")
