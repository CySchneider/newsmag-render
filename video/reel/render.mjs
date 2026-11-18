// Einzel-Reels: node render.mjs reels.json outdir → outdir/<k>/fNNN.png + list.txt (ffmpeg concat), outdir/meta.json (Wellenform-Lage)
// Layout seit 23.10.2026 (Cy, nach Varianten V0–V5): Titelbild = Bild 0 (Rubrik + ganze Schlagzeile, farbig, keine Marke),
// Margareth spricht sofort; in ~0,45 s gleitet die Schlagzeile nach oben und wird kleiner (gleiche Zeilenumbrüche, nur skaliert),
// darunter der Sprechtext Satz für Satz (gesprochenes Wort hervorgehoben), darunter die Wellenform (baut yt.py mit ffmpeg).
// Farben: Sport immer pink, sonst dunkel/hell im Wechsel (Worker: reelThemes). Pink bleibt überall Akzent.
// Sichtbereich: Instagram-Feed schneidet auf 4:5 (y 285–1635), Vollbild deckt oben ~250 px, unten ab ~1480 und rechts ab x ~940 ab
// → alles im Bereich y 340–1470, x 84–880, vertikal zentriert. Platz für den längsten Satz fest reserviert (nichts springt).
// reels.json = { reels: [{ k, kicker, head, theme, list?, caps: [{ text, dur, wt? }], gap, end: { text, dur, w?, type? } }] }
//   end.type "folgen" (13.11.2026): während des Endsatzes steht unter der Wellenform klein «Folg @newsmag.ch» (Platz fest reserviert).
//   list (Runden-Reel, 11.11.2026): alle Sätze stehen als Liste untereinander (Resultate), der gesprochene ist hervorgehoben,
//   Gesagtes voll, Kommendes gedämpft; Sätze mit leerem text werden nur gesprochen (Einleitung).
//   wt = Wortanfänge (s, ab Reel-Beginn) aus den ElevenLabs-Zeitstempeln; fehlen sie, wird nach Zeichenlänge geschätzt.
//   bg (18.11.2026, Plakat = Entwurf C auf newsmag.ch/bildtest/reel, von Cy freigegeben): Pfad zu einem Riso-Bild 1080×1920 →
//   eigener Aufbau 1:1 wie der Entwurf (renderPoster): Bild randlos, Papier-Verlauf unten, Rubrik-Chip in Rubrikfarbe mit kleinem
//   Equalizer, Schlagzeile Archivo 900 (76 → 56 px), Sprechtext 52 px (Entwurf 44, Cy: grösser), keine Wellenform (yt.py: nowave).
import { chromium } from 'playwright';
import fs from 'fs';

const [, , file, out] = process.argv;
const R = JSON.parse(fs.readFileSync(file, 'utf8'));
const b64 = p => fs.readFileSync(new URL(p, import.meta.url)).toString('base64');
const mono = b64('../node_modules/@fontsource/ibm-plex-mono/files/ibm-plex-mono-latin-500-normal.woff2');
const font = b64('../node_modules/@fontsource-variable/archivo/files/archivo-latin-wdth-normal.woff2');
const esc = s => String(s ?? '').replace(/&/g, '&amp;').replace(/</g, '&lt;');
const GLIDE = 0.45, HOLD = 0.25, FPS = 30, TOP_SAFE = 340, BOT_SAFE = 1470, CAP_GAP = 56, WAVE_GAP = 44, WAVE_H = 70, FOLLOW_GAP = 40, FOLLOW_H = 44;
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
#cap.list{font-size:56px;line-height:1.3;text-wrap:wrap}
#cap.list div{margin-bottom:6px}
#fol{position:absolute;left:84px;font-family:M;font-weight:500;font-size:34px;line-height:44px;letter-spacing:.04em}
`;
const headHtml = (h, acc) => { let pink = false; return String(h).split(/(\*)/).map(t => { if (t === '*') { pink = !pink; return ''; } return pink ? `<em style="color:${acc}">${esc(t)}</em>` : esc(t); }).join(''); };
// Wörter eines Satzes mit Startzeit: aus Zeitstempeln (wt) oder nach Zeichenlänge geschätzt
function timed(text, t0, t1, wt) {
  const w = String(text).split(/\s+/).filter(Boolean);
  if (wt && wt.length) return w.map((x, i) => ({ w: x, s: Math.max(t0, Math.min(t1, wt[Math.min(wt.length - 1, Math.floor(i * wt.length / w.length))])) }));
  const l = w.map(x => x.length + 1.5), tot = l.reduce((a, b) => a + b, 0) || 1; let t = t0;
  return w.map((x, i) => { const s = t; t += l[i] / tot * (t1 - t0); return { w: x, s }; });
}

// ---- Plakat (Entwurf C) ----
const RUB_C = { schweiz: '#D52B1E', international: '#2F5DA8', wirtschaft: '#7A4FB0', digital: '#3F5468', technik: '#66741C', kultur: '#B0660E', wissen: '#0F7C8C', medien: '#6E5A4A' };
const PAPER = '241,236,226', INK = '#1D1B19';
const pcss = `
@font-face{font-family:A;src:url(data:font/woff2;base64,${font}) format('woff2');font-weight:100 900;font-stretch:62% 125%}
*{margin:0;box-sizing:border-box}html,body{width:1080px;height:1920px;overflow:hidden}body{font-family:A;position:relative;background:rgb(${PAPER})}
#bgi{position:absolute;left:0;top:0;width:1080px;height:1920px;object-fit:cover}
#fd{position:absolute;left:0;right:0;bottom:0;background:linear-gradient(to bottom,rgba(${PAPER},0) 0%,rgba(${PAPER},.88) 14%,rgb(${PAPER}) 24%)}
.pc{position:absolute;left:84px;display:flex;align-items:center;gap:16px;font-weight:800;font-size:34px;letter-spacing:.06em;text-transform:uppercase;padding:12px 22px;color:#fff}
.eq{display:inline-flex;align-items:flex-end;gap:5px;height:30px}.eq i{display:block;width:7px;border-radius:2px;background:#fff}
.ph{position:absolute;left:84px;width:796px;font-weight:900;letter-spacing:-.02em;line-height:1.04;color:${INK}}
.pt{position:absolute;left:84px;width:796px;font-weight:600;font-size:52px;line-height:1.28;color:${INK}}
#fol{position:absolute;left:84px;font-family:A;font-weight:600;font-size:34px;color:${INK}}
`;
async function renderPoster(pg, r, bgImg) {
  const chipC = r.theme === 'pink' ? '#FF00A6' : RUB_C[String(r.kicker || '').toLowerCase()] || '#14161A';
  const head = String(r.head).replace(/\*/g, '');
  const ev = []; let t = 0;
  for (const [ci, c] of r.caps.entries()) { const ws = timed(c.text, t, t + c.dur, c.wt); ws.forEach((x, j) => ev.push([x.s, ws, j, ci])); t += c.dur; }
  const V_END = t, E0 = V_END + (r.gap || 0.35), T_END = E0 + (r.end ? r.end.dur : 0) + 0.6;
  if (r.end) { const ws = timed(r.end.text, E0, E0 + r.end.dur, r.end.w && r.end.w.map(x => E0 + x)); ws.forEach((x, j) => ev.push([x.s, ws, j, -1])); }
  ev.sort((a, b) => a[0] - b[0]);
  const fol = r.end && r.end.type === 'folgen';
  // Masse wie im Entwurf: Höhe der Schlagzeile bei 76/56 px und des längsten Satzes bei 52 px (Breite 796)
  await pg.setContent(`<!doctype html><html><head><meta charset="utf-8"><style>${pcss}</style></head><body><div class="ph" id="h76" style="font-size:76px">${esc(head)}</div><div class="ph" id="h56" style="font-size:56px">${esc(head)}</div><div class="pt" id="pt"></div></body></html>`);
  await pg.evaluate(() => document.fonts.ready);
  const sents = [...new Set(ev.map(e => e[1].map(x => x.w).join(' ')))];
  const M = await pg.evaluate(ss => { const p = document.getElementById('pt'); let m = 0; for (const x of ss) { p.textContent = x; m = Math.max(m, p.offsetHeight); } return { h76: document.getElementById('h76').offsetHeight, h56: document.getElementById('h56').offsetHeight, th: m }; }, sents);
  const SAFE = 1470, folH = fol ? 60 : 0;
  // Bild 0: Chip 1130, Schlagzeile 1210 (76 px); danach Chip 1020, Schlagzeile +70 (56 px), Text +28 – nach oben verschoben, falls unten zu knapp
  const yc0 = Math.min(1130, SAFE - 80 - M.h76), yc1 = Math.min(1020, SAFE - (70 + M.h56 + 28 + M.th + folH));
  const fade0 = 48, fade1 = Math.round((1920 - yc1 + 90) / 19.2);
  let n = 0;
  const eq = () => { const k = n++; return [0, 1, 2, 3].map(b => `<i style="height:${Math.round(30 + 70 * Math.abs(Math.sin(k * 1.7 + b * 2.3)))}%"></i>`).join(''); };
  const capH = (ws, j) => ws.map((x, q) => `<span style="opacity:${q <= j ? 1 : .32}">${esc(x.w)}</span>`).join(' ');
  const page = (p, w) => {
    const e = ease(p), yc = yc0 + (yc1 - yc0) * e, fsz = 76 + (56 - 76) * e, yh = yc + 80 - 10 * e, yt = yc1 + 70 + M.h56 + 28;
    const op = Math.max(0, (p - .6) / .4), fd = fade0 + (fade1 - fade0) * e, end = w && w[2] === -1;
    return `<!doctype html><html><head><meta charset="utf-8"><style>${pcss}</style></head><body>
      <img id="bgi" src="data:image/jpeg;base64,${bgImg}"><div id="fd" style="height:${fd}%"></div>
      <div class="pc" style="top:${yc}px;background:${chipC}"><span class="eq">${eq()}</span>${esc(r.kicker || 'Newsmag')}</div>
      <div class="ph" style="top:${yh}px;font-size:${fsz}px">${esc(head)}</div>
      <div class="pt" style="top:${yt}px;opacity:${op}">${w ? capH(w[0], w[1]) : ''}</div>
      ${fol && end ? `<div id="fol" style="top:${yt + M.th + 18}px">Folg <span style="color:#FF00A6">@newsmag.ch</span></div>` : ''}</body></html>`;
  };
  const frames = [[0, null, HOLD]], nG = Math.round(GLIDE * FPS), at = tt => ev.filter(x => x[0] <= tt).at(-1);
  for (let i = 1; i <= nG; i++) { const e = at(HOLD + i / FPS); frames.push([i / nG, e ? [e[1], e[2], e[3]] : null, 1 / FPS]); }
  const t1 = HOLD + GLIDE + 1 / FPS, first = at(t1);
  const seq = [...(first ? [[t1, first[1], first[2], first[3]]] : []), ...ev.filter(x => x[0] > t1)];
  for (let i = 0; i < seq.length; i++) frames.push([1, [seq[i][1], seq[i][2], seq[i][3]], (i + 1 < seq.length ? seq[i + 1][0] : T_END) - seq[i][0]]);
  const dir = `${out}/${r.k}`; fs.mkdirSync(dir, { recursive: true });
  const list = [];
  for (const [i, [p, w, dur]] of frames.entries()) {
    await pg.setContent(page(p, w)); await pg.evaluate(() => document.fonts.ready);
    const name = `f${String(i).padStart(3, '0')}.png`; await pg.screenshot({ path: `${dir}/${name}` });
    list.push(`file '${name}'\nduration ${Math.max(dur, 0.02).toFixed(3)}`);
  }
  list.push(list.at(-1).split('\n')[0]);
  fs.writeFileSync(`${dir}/list.txt`, list.join('\n') + '\n');
  return { k: r.k, v: +V_END.toFixed(3), e0: +E0.toFixed(3), T: +T_END.toFixed(3), waveY: 0, wave: INK, nowave: true };
}

fs.mkdirSync(out, { recursive: true });
const browser = await chromium.launch(process.env.CHROME ? { executablePath: process.env.CHROME } : {});
const pg = await browser.newPage({ viewport: { width: 1080, height: 1920 } });
const meta = [];
for (const r of R.reels) {
  if (r.bg && fs.existsSync(r.bg)) { meta.push(await renderPoster(pg, r, fs.readFileSync(r.bg).toString('base64'))); continue; } // Plakat (Entwurf C)
  const [bg, fg, acc, cb, cf, wave, dim] = TH[r.theme] || TH.dunkel;
  const fol = r.end && r.end.type === 'folgen';
  const doc = (capHtml, g) => `<!doctype html><html><head><meta charset="utf-8"><style>${css}</style></head><body style="background:${bg};color:${fg}">
    <div id="blk" style="top:${g.top}px;transform:scale(${g.s})"><span class="chip" style="background:${cb};color:${cf}">${esc(r.kicker || 'Newsmag')}</span><h1 id="ch">${headHtml(r.head, acc)}</h1></div>
    <div id="cap"${r.list ? ' class="list"' : ''} style="top:${g.capTop}px;opacity:${g.capOp}">${capHtml}</div>${g.fol ? `<div id="fol" style="top:${g.folTop}px;color:${fg}">Folg <span style="color:${acc === '#FFFFFF' ? '#FFFFFF' : '#FF00A6'}">@newsmag.ch</span></div>` : ''}</body></html>`;
  // Ereignisse: [Zeit, Wörter des Satzes, Index des gesprochenen Wortes]
  const ev = []; let t = 0;
  for (const [ci, c] of r.caps.entries()) { const ws = timed(c.text, t, t + c.dur, c.wt); ws.forEach((x, j) => ev.push([x.s, ws, j, ci])); t += c.dur; }
  const V_END = t, E0 = V_END + (r.gap || 0.35), T_END = E0 + (r.end ? r.end.dur : 0) + 0.6;
  if (r.end) { const ws = timed(r.end.text, E0, E0 + r.end.dur, r.end.w && r.end.w.map(x => E0 + x)); ws.forEach((x, j) => ev.push([x.s, ws, j, -1])); }
  ev.sort((a, b) => a[0] - b[0]);
  // Geometrie
  await pg.setContent(doc('', { top: 0, s: 1, capTop: 0, capOp: 0 })); await pg.evaluate(() => document.fonts.ready);
  const H = await pg.evaluate(() => { const h = document.getElementById('ch'); let s = 190; while ((h.scrollWidth > 912 || h.offsetHeight > 1000) && s > 80) { s -= 4; h.style.fontSize = s + 'px'; } return { fs: s, bh: document.getElementById('blk').offsetHeight }; });
  const sents = [...new Set(ev.map(e => e[1].map(x => x.w).join(' ')))];
  const lines = r.caps.map((c, i) => ({ i, text: String(c.text || '').trim() })).filter(l => l.text);
  const listAll = () => lines.map(l => `<div>${l.text.split(/\s+/).map(x => `<span${/\d/.test(x) ? ' class="n"' : ''}>${esc(x)}</span>`).join(' ')}</div>`).join('');
  const capMax = r.list
    ? await pg.evaluate(h => { const c = document.getElementById('cap'); c.className = 'list'; c.innerHTML = h; const m = c.offsetHeight; c.innerHTML = ''; c.className = ''; return m; }, listAll())
    : await pg.evaluate(ss => { const c = document.getElementById('cap'); let m = 0; for (const t of ss) { c.textContent = t; m = Math.max(m, c.offsetHeight); } c.textContent = ''; return m; }, sents);
  const folH = fol ? FOLLOW_GAP + FOLLOW_H : 0;
  const s1 = Math.max(0.35, Math.min(0.8, (BOT_SAFE - TOP_SAFE - CAP_GAP - capMax - WAVE_GAP - WAVE_H - folH) / H.bh));
  const blockH = H.bh * s1 + CAP_GAP + capMax + WAVE_GAP + WAVE_H + folH;
  const top1 = TOP_SAFE + Math.max(0, (BOT_SAFE - TOP_SAFE - blockH) / 2), top0 = TOP_SAFE + Math.max(0, (BOT_SAFE - TOP_SAFE - H.bh) / 2);
  const capTop = top1 + H.bh * s1 + CAP_GAP, waveY = Math.round(capTop + capMax + WAVE_GAP), folTop = Math.min(BOT_SAFE - FOLLOW_H, waveY + WAVE_H + FOLLOW_GAP);
  const geo = (p, f = false) => ({ top: top0 + (top1 - top0) * ease(p), s: 1 + (s1 - 1) * ease(p), capTop, capOp: Math.max(0, (p - .6) / .4), fol: f, folTop });
  const now = acc === '#FFFFFF' ? '#FFFFFF' : '#FF00A6';
  const capOne = (ws, j) => ws.map((x, q) => `<span style="color:${q === j ? now : q < j ? fg : fg + dim}"${/\d/.test(x.w) ? ' class="n"' : ''}>${esc(x.w)}</span>`).join(' ');
  // Liste: vor dem gesprochenen Satz voll, danach gedämpft; während des Endsatzes (ci −1) alles voll; vor dem ersten Satz alles gedämpft
  const capList = (ws, j, ci) => lines.map(l => l.i === ci ? `<div>${capOne(ws, j)}</div>`
    : `<div style="color:${ci === -1 || (ci != null && l.i < ci) ? fg : fg + dim}">${l.text.split(/\s+/).map(x => `<span${/\d/.test(x) ? ' class="n"' : ''}>${esc(x)}</span>`).join(' ')}</div>`).join('');
  const capHtml = (ws, j, ci) => r.list ? capList(ws, j, ci) : capOne(ws, j);
  // Bilder: Titelbild stehen lassen, gleiten (je Bild), danach ein Bild pro Wort
  const frames = [[0, null, HOLD]];
  const nG = Math.round(GLIDE * FPS);
  const at = tt => ev.filter(x => x[0] <= tt).at(-1);
  for (let i = 1; i <= nG; i++) { const e = at(HOLD + i / FPS); frames.push([i / nG, e ? [e[1], e[2], e[3]] : null, 1 / FPS]); }
  const t1 = HOLD + GLIDE + 1 / FPS, first = at(t1);
  const seq = [...(first ? [[t1, first[1], first[2], first[3]]] : []), ...ev.filter(x => x[0] > t1)];
  if (r.list && !first) frames.push([1, null, (seq.length ? seq[0][0] : T_END) - t1]); // Liste schon zeigen, bevor der erste Satz läuft
  for (let i = 0; i < seq.length; i++) frames.push([1, [seq[i][1], seq[i][2], seq[i][3]], (i + 1 < seq.length ? seq[i + 1][0] : T_END) - seq[i][0]]);
  const dir = `${out}/${r.k}`; fs.mkdirSync(dir, { recursive: true });
  const list = [];
  for (const [i, [p, w, dur]] of frames.entries()) {
    await pg.setContent(doc(w ? capHtml(w[0], w[1], w[2]) : r.list ? capList([], -1, null) : '', geo(p, fol && w && w[2] === -1))); await pg.evaluate(() => document.fonts.ready);
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
