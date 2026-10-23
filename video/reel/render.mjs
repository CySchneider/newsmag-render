// Einzel-Reels: node render.mjs reels.json outdir → outdir/<k>/fNNN.png + list.txt (ffmpeg concat), outdir/meta.json (Wellenform-Lage)
// Layout seit 23.10.2026 (Cy, nach Varianten V0–V5): Titelbild = Bild 0 (Rubrik + ganze Schlagzeile, farbig, keine Marke),
// Margareth spricht sofort; in ~0,45 s gleitet die Schlagzeile nach oben und wird kleiner (gleiche Zeilenumbrüche, nur skaliert),
// darunter der Sprechtext Satz für Satz (gesprochenes Wort hervorgehoben), darunter die Wellenform (baut yt.py mit ffmpeg).
// Farben: Sport immer pink, sonst dunkel/hell im Wechsel (Worker: reelThemes). Pink bleibt überall Akzent.
// Sichtbereich: Instagram-Feed schneidet auf 4:5 (y 285–1635), Vollbild deckt oben ~250 px, unten ab ~1480 und rechts ab x ~940 ab
// → alles im Bereich y 340–1470, x 84–880, vertikal zentriert. Platz für den längsten Satz fest reserviert (nichts springt).
// reels.json = { reels: [{ k, kicker, head, theme, caps: [{ text, dur, wt? }], gap, end: { text, dur, w? } }] }
//   wt = Wortanfänge (s, ab Reel-Beginn) aus den ElevenLabs-Zeitstempeln; fehlen sie, wird nach Zeichenlänge geschätzt.
import { chromium } from 'playwright';
import fs from 'fs';

const [, , file, out] = process.argv;
const R = JSON.parse(fs.readFileSync(file, 'utf8'));
const b64 = p => fs.readFileSync(new URL(p, import.meta.url)).toString('base64');
const mono = b64('../node_modules/@fontsource/ibm-plex-mono/files/ibm-plex-mono-latin-500-normal.woff2');
const font = b64('../node_modules/@fontsource-variable/archivo/files/archivo-latin-wdth-normal.woff2');
const esc = s => String(s ?? '').replace(/&/g, '&amp;').replace(/</g, '&lt;');
const GLIDE = 0.45, HOLD = 0.25, FPS = 30, TOP_SAFE = 340, BOT_SAFE = 1470, CAP_GAP = 56, WAVE_GAP = 44, WAVE_H = 70;
// [Hintergrund, Schrift, Akzent in der Schlagzeile, Chip-Hintergrund, Chip-Schrift, Wellenform, Deckkraft «kommt noch»]
const TH = {
  pink: ['#FF00A6', '#14161A', '#FFFFFF', '#14161A', '#FFFFFF', '#14161A', '80'],
  hell: ['#F4F5F7', '#14161A', '#FF00A6', '#FF00A6', '#14161A', '#FF00A6', '66'],
  dunkel: ['#14161A', '#F4F5F7', '#FF00A6', '#FF00A6', '#14161A', '#FF00A6', '66'],
};
const ease = p => p < .5 ? 4 * p * p * p : 1 - Math.pow(-2 * p + 2, 3) / 2;
const css = `
@font-face{font-family:M;src:url(data:font/woff2;base64,${mono}) format('woff2')}
@font-face{font-family:A;src:url(data:font/woff2;base64,${font}) format('woff2');font-weight:100 900;font-stretch:62% 125%}
*{margin:0;box-sizing:border-box}
html,body{width:1080px;height:1920px;overflow:hidden}
body{font-family:A;position:relative}
#blk{position:absolute;left:84px;width:912px;transform-origin:left top}
.chip{display:inline-block;font-family:M;font-weight:500;font-size:30px;letter-spacing:.14em;text-transform:uppercase;padding:8px 16px;margin-bottom:34px}
#ch{font-weight:900;font-stretch:68%;font-variation-settings:'wdth' 68,'wght' 900;text-transform:uppercase;line-height:.9;text-wrap:balance;font-size:190px}
#ch em{font-style:normal}
#cap{position:absolute;left:84px;right:200px;font-size:60px;font-weight:600;font-stretch:90%;line-height:1.22;text-wrap:balance;overflow-wrap:anywhere}
#cap .n{font-weight:800}
`;
const headHtml = (h, acc) => { let pink = false; return String(h).split(/(\*)/).map(t => { if (t === '*') { pink = !pink; return ''; } return pink ? `<em style="color:${acc}">${esc(t)}</em>` : esc(t); }).join(''); };
// Wörter eines Satzes mit Startzeit: aus Zeitstempeln (wt) oder nach Zeichenlänge geschätzt
function timed(text, t0, t1, wt) {
  const w = String(text).split(/\s+/).filter(Boolean);
  if (wt && wt.length) return w.map((x, i) => ({ w: x, s: Math.max(t0, Math.min(t1, wt[Math.min(wt.length - 1, Math.floor(i * wt.length / w.length))])) }));
  const l = w.map(x => x.length + 1.5), tot = l.reduce((a, b) => a + b, 0) || 1; let t = t0;
  return w.map((x, i) => { const s = t; t += l[i] / tot * (t1 - t0); return { w: x, s }; });
}

fs.mkdirSync(out, { recursive: true });
const browser = await chromium.launch(process.env.CHROME ? { executablePath: process.env.CHROME } : {});
const pg = await browser.newPage({ viewport: { width: 1080, height: 1920 } });
const meta = [];
for (const r of R.reels) {
  const [bg, fg, acc, cb, cf, wave, dim] = TH[r.theme] || TH.dunkel;
  const doc = (capHtml, g) => `<!doctype html><html><head><meta charset="utf-8"><style>${css}</style></head><body style="background:${bg};color:${fg}">
    <div id="blk" style="top:${g.top}px;transform:scale(${g.s})"><span class="chip" style="background:${cb};color:${cf}">${esc(r.kicker || 'Newsmag')}</span><h1 id="ch">${headHtml(r.head, acc)}</h1></div>
    <div id="cap" style="top:${g.capTop}px;opacity:${g.capOp}">${capHtml}</div></body></html>`;
  // Ereignisse: [Zeit, Wörter des Satzes, Index des gesprochenen Wortes]
  const ev = []; let t = 0;
  for (const c of r.caps) { const ws = timed(c.text, t, t + c.dur, c.wt); ws.forEach((x, j) => ev.push([x.s, ws, j])); t += c.dur; }
  const V_END = t, E0 = V_END + (r.gap || 0.35), T_END = E0 + (r.end ? r.end.dur : 0) + 0.6;
  if (r.end) { const ws = timed(r.end.text, E0, E0 + r.end.dur, r.end.w && r.end.w.map(x => E0 + x)); ws.forEach((x, j) => ev.push([x.s, ws, j])); }
  ev.sort((a, b) => a[0] - b[0]);
  // Geometrie
  await pg.setContent(doc('', { top: 0, s: 1, capTop: 0, capOp: 0 })); await pg.evaluate(() => document.fonts.ready);
  const H = await pg.evaluate(() => { const h = document.getElementById('ch'); let s = 190; while ((h.scrollWidth > 912 || h.offsetHeight > 1000) && s > 80) { s -= 4; h.style.fontSize = s + 'px'; } return { fs: s, bh: document.getElementById('blk').offsetHeight }; });
  const sents = [...new Set(ev.map(e => e[1].map(x => x.w).join(' ')))];
  const capMax = await pg.evaluate(ss => { const c = document.getElementById('cap'); let m = 0; for (const t of ss) { c.textContent = t; m = Math.max(m, c.offsetHeight); } c.textContent = ''; return m; }, sents);
  const s1 = Math.max(0.35, Math.min(0.8, (BOT_SAFE - TOP_SAFE - CAP_GAP - capMax - WAVE_GAP - WAVE_H) / H.bh));
  const blockH = H.bh * s1 + CAP_GAP + capMax + WAVE_GAP + WAVE_H;
  const top1 = TOP_SAFE + Math.max(0, (BOT_SAFE - TOP_SAFE - blockH) / 2), top0 = TOP_SAFE + Math.max(0, (BOT_SAFE - TOP_SAFE - H.bh) / 2);
  const capTop = top1 + H.bh * s1 + CAP_GAP, waveY = Math.round(capTop + capMax + WAVE_GAP);
  const geo = p => ({ top: top0 + (top1 - top0) * ease(p), s: 1 + (s1 - 1) * ease(p), capTop, capOp: Math.max(0, (p - .6) / .4) });
  const now = acc === '#FFFFFF' ? '#FFFFFF' : '#FF00A6';
  const capHtml = (ws, j) => ws.map((x, q) => `<span style="color:${q === j ? now : q < j ? fg : fg + dim}"${/\d/.test(x.w) ? ' class="n"' : ''}>${esc(x.w)}</span>`).join(' ');
  // Bilder: Titelbild stehen lassen, gleiten (je Bild), danach ein Bild pro Wort
  const frames = [[0, null, HOLD]];
  const nG = Math.round(GLIDE * FPS);
  const at = tt => ev.filter(x => x[0] <= tt).at(-1);
  for (let i = 1; i <= nG; i++) { const e = at(HOLD + i / FPS); frames.push([i / nG, e ? [e[1], e[2]] : null, 1 / FPS]); }
  const t1 = HOLD + GLIDE + 1 / FPS, first = at(t1);
  const seq = [...(first ? [[t1, first[1], first[2]]] : []), ...ev.filter(x => x[0] > t1)];
  for (let i = 0; i < seq.length; i++) frames.push([1, [seq[i][1], seq[i][2]], (i + 1 < seq.length ? seq[i + 1][0] : T_END) - seq[i][0]]);
  const dir = `${out}/${r.k}`; fs.mkdirSync(dir, { recursive: true });
  const list = [];
  for (const [i, [p, w, dur]] of frames.entries()) {
    await pg.setContent(doc(w ? capHtml(w[0], w[1]) : '', geo(p))); await pg.evaluate(() => document.fonts.ready);
    await pg.evaluate(fs => { document.getElementById('ch').style.fontSize = fs + 'px'; }, H.fs);
    const name = `f${String(i).padStart(3, '0')}.png`; await pg.screenshot({ path: `${dir}/${name}` });
    list.push(`file '${name}'\nduration ${Math.max(dur, 0.02).toFixed(3)}`);
  }
  list.push(list.at(-1).split('\n')[0]); // ffmpeg concat: letztes Bild doppelt
  fs.writeFileSync(`${dir}/list.txt`, list.join('\n') + '\n');
  meta.push({ k: r.k, v: +V_END.toFixed(3), e0: +E0.toFixed(3), T: +T_END.toFixed(3), waveY, wave });
}
fs.writeFileSync(`${out}/meta.json`, JSON.stringify(meta));
await browser.close();
console.log(R.reels.length, 'Reels');
