# Regenradar für newsmag.ch (seit 22.11.2026): holt die letzten Radarbilder von MeteoSchweiz (Open Data, «Quelle: MeteoSchweiz»),
# färbt die Regenrate ein und schickt sie als PNG an den Worker. Gestartet vom Worker mit Einmal-Token (JOB), wie die Sportdaten.
# Produkt RZC = Niederschlagsrate in mm/h, alle 5 min, 1-km-Raster 710 × 640 (LV95, x 2'255–2'965 km, y 840–1'480 km, Zeile 0 = Norden).
import base64, io, json, os, sys, urllib.request
from datetime import datetime, timedelta, timezone
import h5py, numpy as np
from PIL import Image

HOST = os.environ.get("HOST", "https://newsmag.ch")
JOB = os.environ.get("JOB", "")
STAC = "https://data.geo.admin.ch/api/stac/v1/collections/ch.meteoschweiz.ogd-radar-precip/items/"
UA = "Mozilla/5.0 (compatible; Newsmag/1.0; +https://newsmag.ch/so-entsteht-newsmag)"
X0, Y0, W, H = 205, 160, 400, 270   # Ausschnitt Schweiz mit Rand (Pixel = km), muss zur Karte im Worker passen (RADAR_BOX)
FRAMES = 13                          # eine Stunde in 5-Minuten-Schritten
# Farbstufen (mm/h): ab Wert → RGBA
STEPS = [(0.1, (158, 202, 225, 170)), (0.5, (107, 174, 214, 200)), (1, (49, 130, 206, 215)), (2, (33, 97, 176, 225)),
         (5, (242, 208, 59, 235)), (10, (243, 154, 43, 240)), (20, (226, 65, 44, 245)), (50, (176, 33, 138, 250))]

def get(url, data=None, ctype=None):
    req = urllib.request.Request(url, data=data, headers={"User-Agent": UA, **({"Content-Type": ctype} if ctype else {})})
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read()

def files():
    out = {}
    now = datetime.now(timezone.utc)
    for d in (now - timedelta(days=1), now):
        try:
            a = json.loads(get(STAC + d.strftime("%Y%m%d") + "-ch")).get("assets", {})
        except Exception as e:
            print("STAC", d.date(), e); continue
        for k, v in a.items():
            if k.startswith("rzc") and k.endswith(".h5"):
                out[k[3:12]] = v["href"]   # YYDDDHHMM
    keys = sorted(out)[-FRAMES:]
    return [(k, out[k]) for k in keys]

def when(k):  # «263260855» → ISO (UTC)
    d = datetime(2000 + int(k[:2]), 1, 1, tzinfo=timezone.utc) + timedelta(days=int(k[2:5]) - 1, hours=int(k[5:7]), minutes=int(k[7:9]))
    return d.strftime("%Y-%m-%dT%H:%M:00Z")

def render(raw):
    with h5py.File(io.BytesIO(raw), "r") as f:
        a = f["dataset1/data1/data"][()]
        w = f["dataset1/data1/what"].attrs
        a = a * float(w.get("gain", 1.0)) + float(w.get("offset", 0.0))
    a = np.nan_to_num(a[Y0:Y0 + H, X0:X0 + W], nan=0.0)
    img = np.zeros((H, W, 4), dtype=np.uint8)
    for lim, rgba in STEPS:
        img[a >= lim] = rgba
    buf = io.BytesIO()
    Image.fromarray(img).save(buf, "PNG", optimize=True)
    return buf.getvalue(), float(np.mean(a >= 0.1))

def main():
    out = []
    for k, href in files():
        try:
            png, wet = render(get(href))
            out.append({"t": when(k), "wet": round(wet, 4), "png": base64.b64encode(png).decode()})
        except Exception as e:
            print("Bild", k, e)
    print(len(out), "Bilder,", sum(len(x["png"]) for x in out) // 1024, "KB")
    if not out:
        sys.exit("keine Radarbilder")
    if os.environ.get("OUT"):   # lokaler Test: Bilder in einen Ordner schreiben statt senden
        for x in out:
            open(os.path.join(os.environ["OUT"], x["t"][11:16].replace(":", "") + ".png"), "wb").write(base64.b64decode(x["png"]))
        return
    print(get(f"{HOST}/radar-push?t={JOB}", json.dumps({"frames": out}).encode(), "application/json").decode()[:300])

main()
