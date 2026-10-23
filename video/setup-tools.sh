#!/usr/bin/env bash
# Werkzeuge für Story-Video, YouTube/Reels und Karussell (seit 23.10.2026).
# Hintergrund: Die Ubuntu-Paketquelle auf den GitHub-Rechnern hing am 22./23.10. mehrmals
# (playwright --with-deps, apt-get install ffmpeg) → Video fehlte oder lief ohne ffprobe los.
# Darum möglichst ohne apt: vorinstalliertes Google Chrome, ffmpeg als fertige Datei von GitHub,
# Emoji-Schrift direkt herunterladen. apt nur noch als Notlösung, mit Zeitlimit.
# Aufruf: setup-tools.sh [ffmpeg] [emoji]
set -uo pipefail
want() { [[ " $ARGS " == *" $1 "* ]]; }
ARGS=" $* "
fail() { echo "::error::$1"; exit 1; }
retry() { local n=$1 t=$2; shift 2; for i in $(seq 1 "$n"); do timeout "$t" "$@" && return 0; echo "Versuch $i/$n abgebrochen: $*"; sleep 5; done; return 1; }

# 1) Browser: Chrome ist auf den GitHub-Rechnern vorinstalliert (inkl. aller Systembibliotheken)
CH=$(command -v google-chrome || command -v google-chrome-stable || true)
smoke() { CHROME="$CH" timeout 60 node -e 'const {chromium}=require("playwright");(async()=>{const b=await chromium.launch({executablePath:process.env.CHROME});const p=await b.newPage();await p.setContent("<p>ok 😀</p>");await p.screenshot();await b.close()})().catch(e=>{console.error(e.message);process.exit(1)})'; }
if [ -n "$CH" ] && smoke; then
  echo "Browser: $("$CH" --version) (vorinstalliert, Test ok)"
  echo "CHROME=$CH" >> "${GITHUB_ENV:-/dev/null}"
else
  echo "Kein Chrome vorinstalliert → Playwright-Chromium"
  retry 3 240 npx playwright install --with-deps chromium || fail "Browser-Installation gescheitert"
fi

# 2) ffmpeg/ffprobe als fertige Datei (GitHub-Release, ohne apt)
if want ffmpeg && ! { command -v ffmpeg && command -v ffprobe; } >/dev/null; then
  if retry 3 120 curl -fsSL -o /tmp/ffmpeg.tar.xz https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-linux64-gpl.tar.xz \
     && tar -xJf /tmp/ffmpeg.tar.xz -C /tmp && sudo install -m 755 /tmp/ffmpeg-*/bin/ffmpeg /tmp/ffmpeg-*/bin/ffprobe /usr/local/bin/; then
    echo "ffmpeg aus GitHub-Release"
  else
    echo "GitHub-Download gescheitert → apt"
    retry 2 300 sudo apt-get install -y ffmpeg >/dev/null || true
  fi
  ffprobe -version >/dev/null 2>&1 || fail "ffmpeg/ffprobe nicht installiert"
  echo "$(ffmpeg -version | head -1)"
fi

# 3) Emoji-Schrift (nur YouTube/Reels) – fehlt sie, gibt es das Video trotzdem, nur ohne farbige Emojis
if want emoji && ! fc-list | grep -qi "Noto Color Emoji"; then
  mkdir -p ~/.local/share/fonts
  if retry 3 60 curl -fsSL -o ~/.local/share/fonts/NotoColorEmoji.ttf https://raw.githubusercontent.com/googlefonts/noto-emoji/main/fonts/NotoColorEmoji.ttf; then
    fc-cache -f >/dev/null; echo "Emoji-Schrift geladen"
  else
    retry 1 180 sudo apt-get install -y fonts-noto-color-emoji >/dev/null || echo "::warning::Emoji-Schrift fehlt"
  fi
fi
exit 0
