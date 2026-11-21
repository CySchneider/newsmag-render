// Einzel-Reels: node render.mjs reels.json outdir → outdir/<k>/fNNN.png + list.txt (ffmpeg concat), outdir/meta.json (Wellenform-Lage)
// Layout seit 23.10.2026 (Cy, nach Varianten V0–V5): Titelbild = Bild 0 (Rubrik + ganze Schlagzeile, farbig, keine Marke),
// Margareth spricht sofort; in ~0,45 s gleitet die Schlagzeile nach oben und wird kleiner (gleiche Zeilenumbrüche, nur skaliert),
// darunter der Sprechtext Satz für Satz (gesprochenes Wort hervorgehoben), darunter die Wellenform (baut yt.py mit ffmpeg).
// Farben: Sport immer pink, sonst dunkel/hell im Wechsel (Worker: reelThemes). Pink bleibt überall Akzent.
// Sichtbereich: Instagram-Feed schneidet auf 4:5 (y 285–1635), Vollbild deckt oben ~250 px, unten ab ~1480 und rechts ab x ~940 ab
// → alles im Bereich y 340–1470, x 84–880, vertikal zentriert. Platz für den längsten Satz fest reserviert (nichts springt).
// reels.json = { reels: [{ k, kicker, head, theme, list?, caps: [{ text, dur, wt? }], gap, end: { text, dur, w?, type? } }] }
//   end.type "folgen" (13.11.2026): Einblendung «Folg @newsmag.ch» unter dem Text – seit 19.11.2026 aus (Cy: nicht klickbar, überflüssig).
//   list (Runden-Reel, 11.11.2026): alle Sätze stehen als Liste untereinander (Resultate), der gesprochene ist hervorgehoben,
//   Gesagtes voll, Kommendes gedämpft; Sätze mit leerem text werden nur gesprochen (Einleitung).
//   wt = Wortanfänge (s, ab Reel-Beginn) aus den ElevenLabs-Zeitstempeln; fehlen sie, wird nach Zeichenlänge geschätzt.
//   bg (18.11.2026, Plakat = Entwurf C auf newsmag.ch/bildtest/reel, von Cy freigegeben): Pfad zu einem Riso-Bild 1080×1920 →
//   eigener Aufbau 1:1 wie der Entwurf (renderPoster): Bild randlos, Papier-Verlauf unten, Rubrik-Chip in Rubrikfarbe mit kleinem
//   Equalizer (weiche Schlaufe, yt.py legt sie über), Schlagzeile Archivo 900 (76 → 56 px), Sprechtext 52 px (Entwurf 44, Cy: grösser), keine Wellenform (yt.py: nowave).
import { chromium } from 'playwright';
import fs from 'fs';

const [, , file, out] = process.argv;
const R = JSON.parse(fs.readFileSync(file, 'utf8'));
const b64 = p => fs.readFileSync(new URL(p, import.meta.url)).toString('base64');
const mono = b64('../node_modules/@fontsource/ibm-plex-mono/files/ibm-plex-mono-latin-500-normal.woff2');
const font = b64('../node_modules/@fontsource-variable/archivo/files/archivo-latin-wdth-normal.woff2');
const esc = s => String(s ?? '').replace(/&/g, '&amp;').replace(/</g, '&lt;');
const GLIDE = 0.45, HOLD = 0.25, HOLD_P = 1.5, MAXL = 3, FPS = 30, TOP_SAFE = 340, BOT_SAFE = 1470, CAP_GAP = 56, WAVE_GAP = 44, WAVE_H = 70, FOLLOW_GAP = 40, FOLLOW_H = 44;
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
const RUB_C = { schweiz: '#D52B1E', international: '#2F5DA8', ausland: '#2F5DA8', 'kultur und wissen': '#B0660E', wirtschaft: '#7A4FB0', digital: '#3F5468', technik: '#66741C', kultur: '#B0660E', wissen: '#0F7C8C', medien: '#6E5A4A' };
const PAPER = '241,236,226', INK = '#1D1B19';
const pcss = `
@font-face{font-family:A;src:url(data:font/woff2;base64,${font}) format('woff2');font-weight:100 900;font-stretch:62% 125%}
*{margin:0;box-sizing:border-box}html,body{width:1080px;height:1920px;overflow:hidden}body{font-family:A;position:relative;background:rgb(${PAPER})}
#bgi{position:absolute;left:0;top:0;width:1080px;height:1920px;object-fit:cover}
#fd{position:absolute;left:0;right:0;bottom:0;background:linear-gradient(to bottom,rgba(${PAPER},0) 0%,rgba(${PAPER},.88) 14%,rgb(${PAPER}) 24%)}
.pc{position:absolute;left:84px;display:flex;align-items:center;gap:16px;font-weight:800;font-size:34px;letter-spacing:.06em;text-transform:uppercase;padding:12px 22px;color:#fff}
.eq{display:inline-flex;align-items:flex-end;gap:5px;height:30px;width:43px}.eq i{display:block;width:7px;border-radius:2px;background:#fff}
.ph{position:absolute;left:84px;width:796px;font-weight:900;letter-spacing:-.02em;line-height:1.04;color:${INK}}
.pt{position:absolute;left:84px;width:796px;font-weight:600;font-size:52px;line-height:1.28;color:${INK}}
#fol{position:absolute;left:84px;font-family:A;font-weight:600;font-size:34px;color:${INK}}
`;
// Papierrand des Riso-Bilds finden (19.11.2026, Cy: im Vollbild oben ein «unschöner Balken»): FLUX setzt das Motiv als Druck mit
// Papierrand oben und seitlich auf das Blatt. Gesucht wird der Motiv-Kasten (Zeilen/Spalten, die deutlich vom Papier abweichen);
// das Bild wird so skaliert/verschoben, dass das Motiv oben und seitlich randlos ist. Unten bleibt Papier (Verlauf deckt).
async function motifBox(pg, bgImg) {
  await pg.setContent('<canvas id=c></canvas>');
  return pg.evaluate(async src => {
    const im = new Image(); im.src = src; await im.decode();
    const W = 216, H = Math.round(W * im.naturalHeight / im.naturalWidth), c = document.getElementById('c'); c.width = W; c.height = H;
    const x = c.getContext('2d'); x.drawImage(im, 0, 0, W, H); const d = x.getImageData(0, 0, W, H).data;
    const px = (i, j) => { const o = (j * W + i) * 4; return [d[o], d[o + 1], d[o + 2]]; };
    // Papierfarbe: Median der beiden oberen Ecken
    const pp = []; for (let j = 1; j < 6; j++) for (const i of [1, 2, 3, W - 4, W - 3, W - 2]) pp.push(px(i, j));
    const paper = [0, 1, 2].map(k => pp.map(p => p[k]).sort((a, b) => a - b)[pp.length >> 1]);
    const off = (i, j) => { const p = px(i, j); return Math.abs(p[0] - paper[0]) + Math.abs(p[1] - paper[1]) + Math.abs(p[2] - paper[2]) > 45; };
    const half = Math.round(H * 0.55);
    const row = j => { let n = 0; for (let i = 0; i < W; i++) n += off(i, j); return n / W; };
    const col = i => { let n = 0; for (let j = 0; j < half; j++) n += off(i, j); return n / half; };
    let t = 0; while (t < H * 0.25 && row(t) < 0.35) t++;
    let l = 0; while (l < W * 0.2 && col(l) < 0.35) l++;
    let r = W - 1; while (r > W * 0.8 && col(r) < 0.35) r--;
    if (t >= H * 0.25) t = 0; if (l >= W * 0.2) l = 0; if (r <= W * 0.8) r = W - 1;
    const k = im.naturalWidth / W, m = 2; // 2 Raster-Pixel Sicherheitsrand (fransige Druckkante)
    return { w: im.naturalWidth, h: im.naturalHeight, t: Math.max(0, t + (t ? m : 0)) * k, l: Math.max(0, l + (l ? m : 0)) * k, r: Math.min(W, r + 1 - (r < W - 1 ? m : 0)) * k };
  }, 'data:image/jpeg;base64,' + bgImg);
}

// Equalizer im Chip: weich wie im Entwurf (CSS «w» 0,9 s ease-in-out 18 → 90 %, Versatz 0/.25/.5/.15 s). Bis zum Ende des Gleitens
// steckt er im Bild (pro Bild nach Zeit), danach legt yt.py eine fertige 30-fps-Schlaufe (eq/eNN.png) darüber. Vorher wechselte er
// pro Wort zufällig → wirkte ruckelnd wie ein Ladefehler (Cy 19.11.2026).
const EQ_P = 0.9, EQ_D = [0, .25, .5, .15];
const eqH = tt => EQ_D.map(dl => { const ph = (((tt + dl) % EQ_P) + EQ_P) % EQ_P / EQ_P; return 18 + 72 * (0.5 - 0.5 * Math.cos(2 * Math.PI * ph)); });
const eqBars = tt => eqH(tt).map(h => `<i style="height:${h.toFixed(1)}%"></i>`).join('');

async function renderPoster(pg, r, bgImg) {
  const chipC = r.theme === 'pink' ? '#FF00A6' : RUB_C[String(r.kicker || '').toLowerCase()] || '#14161A';
  const head = String(r.head).replace(/\*/g, '');
  // Sätze mit Wortzeiten; lange Sätze werden in Häppchen von höchstens MAXL Zeilen geteilt (19.11.2026, Cy: «nicht alles nach oben
  // gequetscht» – der Platz richtet sich nach dem längsten Häppchen, vorher nach dem längsten Satz, z. B. 5 Zeilen)
  const sl = []; let t = 0;
  for (const [ci, c] of r.caps.entries()) { sl.push([timed(c.text, t, t + c.dur, c.wt), ci]); t += c.dur; }
  const V_END = t, E0 = V_END + (r.gap || 0.35), T_END = E0 + (r.end ? r.end.dur : 0) + 0.6;
  if (r.end) sl.push([timed(r.end.text, E0, E0 + r.end.dur, r.end.w && r.end.w.map(x => E0 + x)), -1]);
  await pg.setContent(`<!doctype html><html><head><meta charset="utf-8"><style>${pcss}</style></head><body><div class="pt" id="pt"></div></body></html>`);
  await pg.evaluate(() => document.fonts.ready);
  const cuts = await pg.evaluate(([L, maxl]) => {
    const p = document.getElementById('pt'), lh = 52 * 1.28, fits = w => { p.textContent = w.join(' '); return p.offsetHeight <= maxl * lh + 4; };
    return L.map(w => {
      if (fits(w)) return [w.length];
      let n = 0; for (let i = 0; i < w.length;) { let j = i + 1; while (j < w.length && fits(w.slice(i, j + 1))) j++; i = j; n++; } // gierig: Anzahl Häppchen
      for (; ; n++) { // gleichmässig auf n Häppchen verteilen, bevorzugt nach Satzzeichen
        const out = []; let i = 0, ok = true;
        for (let k = 0; k < n; k++) {
          let j = k === n - 1 ? w.length : Math.round((k + 1) * w.length / n);
          for (const d of [0, 1, -1, 2, -2]) { const q = j + d; if (k < n - 1 && q > i + 1 && q < w.length && /[,;:–]$/.test(w[q - 1])) { j = q; break; } }
          if (!fits(w.slice(i, j))) { ok = false; break; } out.push(j - i); i = j;
        }
        if (ok) return out;
        if (n > w.length) return [w.length];
      }
    });
  }, [sl.map(([ws]) => ws.map(x => x.w)), MAXL]);
  const ev = [];
  sl.forEach(([ws, ci], si) => { let i = 0; for (const n of cuts[si]) { const ch = ws.slice(i, i + n); ch.forEach((x, j) => ev.push([x.s, ch, j, ci])); i += n; } });
  ev.sort((a, b) => a[0] - b[0]);
  const fol = false; // «Folg @newsmag.ch» als Einblendung weg (19.11.2026, Cy: nicht klickbar, Hinweise gibt es genug; Endsatz bleibt gesprochen + als Text)
  const mb = await motifBox(pg, bgImg), bs = 1080 / (mb.r - mb.l); // Motiv randlos auf 1080 Breite
  const bgCss = `left:${(-mb.l * bs).toFixed(1)}px;top:${(-mb.t * bs).toFixed(1)}px;width:${(mb.w * bs).toFixed(1)}px;height:${(mb.h * bs).toFixed(1)}px`;
  // Masse wie im Entwurf: Höhe der Schlagzeile bei 76/56 px und des längsten Satzes bei 52 px (Breite 796)
  await pg.setContent(`<!doctype html><html><head><meta charset="utf-8"><style>${pcss}</style></head><body><div class="ph" id="h76" style="font-size:76px">${esc(head)}</div><div class="ph" id="h56" style="font-size:56px">${esc(head)}</div><div class="pt" id="pt"></div></body></html>`);
  await pg.evaluate(() => document.fonts.ready);
  const sents = [...new Set(ev.map(e => e[1].map(x => x.w).join(' ')))];
  const M = await pg.evaluate(ss => { const p = document.getElementById('pt'); let m = 0; for (const x of ss) { p.textContent = x; m = Math.max(m, p.offsetHeight); } return { h76: document.getElementById('h76').offsetHeight, h56: document.getElementById('h56').offsetHeight, th: m }; }, sents);
  const SAFE = 1470, folH = fol ? 60 : 0;
  // Bild 0: Chip 1130, Schlagzeile +100 (76 px); danach Chip 1020, Schlagzeile +92 (56 px), Text +28 – nach oben verschoben, falls unten zu knapp
  // (19.11.2026: Chip → Schlagzeile vorher +80/+70, Cy: zu wenig Abstand)
  const HG0 = 100, HG1 = 92;
  const yc0 = Math.min(1130, SAFE - HG0 - M.h76), yc1 = Math.min(1020, SAFE - (HG1 + M.h56 + 28 + M.th + folH));
  const fade0 = 48, fade1 = Math.round((1920 - yc1 + 90) / 19.2);
  const capH = (ws, j) => ws.map((x, q) => `<span style="opacity:${q <= j ? 1 : .32}">${esc(x.w)}</span>`).join(' ');
  const page = (p, w, tt) => {
    const e = ease(p), yc = yc0 + (yc1 - yc0) * e, fsz = 76 + (56 - 76) * e, yh = yc + HG0 + (HG1 - HG0) * e, yt = yc1 + HG1 + M.h56 + 28;
    const op = Math.max(0, (p - .85) / .15), fd = fade0 + (fade1 - fade0) * e, end = w && w[2] === -1;
    return `<!doctype html><html><head><meta charset="utf-8"><style>${pcss}</style></head><body>
      <img id="bgi" style="${bgCss}" src="data:image/jpeg;base64,${bgImg}"><div id="fd" style="height:${fd}%"></div>
      <div class="pc" style="top:${yc}px;background:${chipC}"><span class="eq" id="eq">${tt == null ? '' : eqBars(tt)}</span>${esc(r.kicker || 'Newsmag')}</div>
      <div class="ph" style="top:${yh}px;font-size:${fsz}px">${esc(head)}</div>
      <div class="pt" style="top:${yt}px;opacity:${op}">${w ? capH(w[0], w[1]) : ''}</div>
      ${fol && end ? `<div id="fol" style="top:${yt + M.th + 18}px">Folg <span style="color:#FF00A6">@newsmag.ch</span></div>` : ''}</body></html>`;
  };
  // Bild-Liste: [Gleit-Fortschritt, Wort, Dauer, Zeit für den Equalizer (null = leer, Schlaufe von yt.py)]
  // Titelbild steht HOLD_P = 1,5 s (19.11.2026, Cy: erst den Titel lesen), Margareth spricht trotzdem sofort (keine stille Pause am Anfang)
  const frames = [[0, null, HOLD_P, null]], nG = Math.round(GLIDE * FPS), at = tt => ev.filter(x => x[0] <= tt).at(-1);
  for (let i = 1; i <= nG; i++) { const e = at(HOLD_P + i / FPS); frames.push([i / nG, e ? [e[1], e[2], e[3]] : null, 1 / FPS, HOLD_P + i / FPS]); }
  const t1 = HOLD_P + GLIDE + 1 / FPS, first = at(t1);
  const seq = [...(first ? [[t1, first[1], first[2], first[3]]] : []), ...ev.filter(x => x[0] > t1)];
  for (let i = 0; i < seq.length; i++) frames.push([1, [seq[i][1], seq[i][2], seq[i][3]], (i + 1 < seq.length ? seq[i + 1][0] : T_END) - seq[i][0], null]);
  const dir = `${out}/${r.k}`; fs.mkdirSync(dir, { recursive: true });
  const list = [];
  // Lage des Equalizers im Endzustand messen, Schlaufe (27 Bilder = 0,9 s) mit Phase ab t = 0 rendern
  const EQ_T0 = +(HOLD_P + GLIDE).toFixed(3); // = Beginn des ersten Bilds nach dem Gleiten
  const eqAt = async p => { await pg.setContent(page(p, null, 0)); await pg.evaluate(() => document.fonts.ready);
    return pg.evaluate(() => { const b = document.getElementById('eq').getBoundingClientRect(); return { x: Math.round(b.left), y: Math.round(b.top), w: Math.round(b.width), h: Math.round(b.height) }; }); };
  const eqR = await eqAt(1), eqY0 = (await eqAt(0)).y; // Schlaufe auch während das Titelbild steht (Lage y0 bis HOLD_P)
  fs.mkdirSync(`${dir}/eq`, { recursive: true });
  const nEq = Math.round(EQ_P * FPS);
  for (let i = 0; i < nEq; i++) {
    await pg.setContent(`<!doctype html><html><head><style>${pcss}html,body{width:${eqR.w}px;height:${eqR.h}px;background:transparent}.eq{position:absolute;left:0;top:0}</style></head><body style="background:transparent"><span class="eq">${eqBars(i / FPS)}</span></body></html>`);
    await pg.screenshot({ path: `${dir}/eq/e${String(i).padStart(2, '0')}.png`, omitBackground: true, clip: { x: 0, y: 0, width: eqR.w, height: eqR.h } });
  }
  for (const [i, [p, w, dur, tt]] of frames.entries()) {
    await pg.setContent(page(p, w, tt)); await pg.evaluate(() => document.fonts.ready);
    const name = `f${String(i).padStart(3, '0')}.png`; await pg.screenshot({ path: `${dir}/${name}` });
    list.push(`file '${name}'\nduration ${Math.max(dur, 0.02).toFixed(3)}`);
  }
  list.push(list.at(-1).split('\n')[0]);
  fs.writeFileSync(`${dir}/list.txt`, list.join('\n') + '\n');
  return { k: r.k, v: +V_END.toFixed(3), e0: +E0.toFixed(3), T: +T_END.toFixed(3), waveY: 0, wave: INK, nowave: true, eq: { ...eqR, t0: EQ_T0, n: nEq, y0: eqY0, h0: HOLD_P } };
}

// ---- Duoton (21.11.2026, Cy: «Newsmag Instagram wird wieder Typo. Riso weg.»; docs/social.md «Reels im Duoton-Look») ----
// r.duo = { kz, rub, heikel, aufmacher, credit, kind }, r.img = Graustufenbild (optional).
// Fassung 2 (21.11.2026 abends, Cy): kein Logo, keine Ausgabe («am Mittag» sagt im Feed niemandem etwas), kein «Aufmacher», keine Medienzahl;
// Schrift so gross wie möglich; Bild läuft mit Verlauf hinter den Text statt harter Kante (wie die neue Website).
// Aufbau: Duoton-Bild randlos oben (multiply auf der Rubrikfarbe), Verlauf in die Fläche; Chip (Rubrik/Sportart + Equalizer) + Kurzzeile riesig;
// nach HOLD_P gleitet der Block nach oben, Kurzzeile kleiner, Sprechtext Wort für Wort. Pink = wichtigstes Thema der Folge (wie der pinke
// Aufmacher der Website, ohne Wort), Schwarz = heikel. Ränder: Text x 72–900, y bis 1450; oben nur Bild; unten nur Rubrikwort als Dekor.
const DUO_C = { // [Fläche, Schrift] – Farbstand 21.11.2026 (docs/website.md «Farben neu»)
  aufmacher: ['#FF00A6', '#14161A'], schweiz: ['#E30613', '#FFFFFF'], international: ['#3D74FF', '#FFFFFF'], ausland: ['#3D74FF', '#FFFFFF'],
  wirtschaft: ['#FF6A00', '#14161A'], sport: ['#00F07A', '#14161A'], kultur: ['#9D4BFF', '#FFFFFF'], medien: ['#9D4BFF', '#FFFFFF'],
  entertainment: ['#FFE500', '#14161A'], digital: ['#00D9E8', '#14161A'], technik: ['#C9CED6', '#14161A'], wissen: ['#C9CED6', '#14161A'],
  heikel: ['#14161A', '#FFFFFF'] };
const DUO_DECO = { international: 'International', schweiz: 'Schweiz', wirtschaft: 'Wirtschaft', sport: 'Sport', kultur: 'Kultur', medien: 'Medien',
  entertainment: 'Entertainment', digital: 'Digital', technik: 'Technik', wissen: 'Wissen', ausland: 'International' };
// IMG0/IMG1 = Bildhöhe Titel/Sprechen, FD = Verlauf (Anteil der Bildhöhe: ab .. bis deckend), KZ = grösste Kurzzeile, CAP = Sprechtext
const D = { L: 72, W: 828, IMG0: 1240, IMG1: 820, FD: [0.42, 0.9], KZ: 210, KZMIN: 96, KZ1: 0.56, CAP: 84, CAPLH: 1.12, MAXL: 4, BOT: 1450, Y1: 470 };
const dcss = `
@font-face{font-family:M;src:url(data:font/woff2;base64,${mono}) format('woff2')}
@font-face{font-family:A;src:url(data:font/woff2;base64,${font}) format('woff2');font-weight:100 900;font-stretch:62% 125%}
*{margin:0;box-sizing:border-box}html,body{width:1080px;height:1920px;overflow:hidden}body{font-family:A;position:relative}
#im{position:absolute;left:0;top:0;width:1080px;overflow:hidden}
#im img{width:100%;height:100%;object-fit:cover;object-position:50% 25%;display:block}
#im .fd{position:absolute;inset:0}
#cr{position:absolute;right:26px;top:330px;writing-mode:vertical-rl;transform:rotate(180deg);font-family:M;font-size:18px;letter-spacing:.03em;opacity:.55;white-space:nowrap}
#dc{position:absolute;left:44px;bottom:-44px;font-weight:900;font-stretch:70%;font-variation-settings:'wdth' 70,'wght' 900;text-transform:uppercase;font-size:330px;line-height:.8;opacity:.12;white-space:nowrap}
#tx{position:absolute;left:${D.L}px;width:${D.W}px}
.ch{display:inline-flex;align-items:center;gap:16px;padding:8px 20px;border-radius:10px;font-family:M;font-weight:500;font-size:34px;letter-spacing:.06em;text-transform:uppercase;height:60px}
.eq{display:inline-flex;align-items:flex-end;gap:6px;height:30px;width:45px}.eq i{display:block;width:9px;border-radius:2px;background:var(--eqc)}
#kz{font-weight:900;font-stretch:76%;font-variation-settings:'wdth' 76,'wght' 900;text-transform:uppercase;line-height:.88;margin-top:28px;text-wrap:balance}
#cp{position:absolute;left:${D.L}px;width:${D.W}px;font-weight:700;font-stretch:86%;font-variation-settings:'wdth' 86,'wght' 700;font-size:${D.CAP}px;line-height:${D.CAPLH};text-wrap:balance}
#cp mark{padding:0 10px;border-radius:10px;font-weight:900}
`;
async function renderDuo(pg, r, img) {
  const d = r.duo || {}, rk = String(r.rub || d.rub || r.kicker || '').toLowerCase();
  const key = d.heikel ? 'heikel' : d.aufmacher ? 'aufmacher' : (DUO_C[rk] ? rk : 'aufmacher');
  const [bgc, fgc] = DUO_C[key], dark = fgc === '#FFFFFF';
  const chipBg = dark ? '#FFFFFF' : '#14161A', chipFg = dark ? '#14161A' : '#FFFFFF';
  const markBg = dark ? '#FFFFFF' : '#14161A', markFg = dark ? '#14161A' : (key === 'aufmacher' ? '#FFFFFF' : bgc);
  const kz = String(d.kz || r.head || '').replace(/\*/g, '').trim();
  const chip = r.kicker || d.rub || 'Newsmag';
  const deco = DUO_DECO[rk] || '';
  const hasImg = !!img;
  const imgTag = hasImg ? `<img src="data:image/jpeg;base64,${img}" style="${d.heikel ? 'filter:contrast(1.08) brightness(.86)' : 'mix-blend-mode:multiply'}">` : '';
  const fade = `linear-gradient(to bottom,${bgc}00 0%,${bgc}00 ${D.FD[0] * 100}%,${bgc}D9 ${((D.FD[0] + D.FD[1]) / 2) * 100}%,${bgc} ${D.FD[1] * 100}%)`;
  const sl = []; let t = 0;
  for (const [ci, c] of r.caps.entries()) { sl.push([timed(c.text, t, t + c.dur, c.wt), ci]); t += c.dur; }
  const V_END = t, E0 = V_END + (r.gap || 0.35), T_END = E0 + (r.end ? r.end.dur : 0) + 0.6;
  if (r.end) sl.push([timed(r.end.text, E0, E0 + r.end.dur, r.end.w && r.end.w.map(x => E0 + x)), -1]);
  const shell = body => `<!doctype html><html><head><meta charset="utf-8"><style>${dcss}</style></head><body style="background:${bgc};color:${fgc};--eqc:${chipFg}">${body}</body></html>`;
  // Kurzzeile so gross wie möglich: passt in die Breite, höchstens 3 Zeilen, Block (Chip + Kurzzeile) über D.BOT
  await pg.setContent(shell(`<div id="tx"><span class="ch">x</span><div id="kz" style="font-size:${D.KZ}px">${esc(kz)}</div></div><div id="cp"></div>`));
  await pg.evaluate(() => document.fonts.ready);
  const K = await pg.evaluate(([max, min]) => { const h = document.getElementById('kz'), tx = document.getElementById('tx'); let s = max;
    const lines = () => Math.round(h.offsetHeight / (s * .88));
    while ((h.scrollWidth > tx.offsetWidth + 2 || lines() > 3) && s > min) { s -= 4; h.style.fontSize = s + 'px'; }
    return { fs: s, bh: tx.offsetHeight }; }, [D.KZ, D.KZMIN]);
  const cuts = await pg.evaluate(([L, maxl, fsz, lhk]) => {
    const p = document.getElementById('cp'), lh = fsz * lhk, fits = w => { p.textContent = w.join(' '); return p.offsetHeight <= maxl * lh + 4; };
    return L.map(w => {
      if (fits(w)) return [w.length];
      let n = 0; for (let i = 0; i < w.length;) { let j = i + 1; while (j < w.length && fits(w.slice(i, j + 1))) j++; i = j; n++; }
      for (; ; n++) {
        const out = []; let i = 0, ok = true;
        for (let k = 0; k < n; k++) {
          let j = k === n - 1 ? w.length : Math.round((k + 1) * w.length / n);
          for (const dd of [0, 1, -1, 2, -2]) { const q = j + dd; if (k < n - 1 && q > i + 1 && q < w.length && /[,;:–]$/.test(w[q - 1])) { j = q; break; } }
          if (!fits(w.slice(i, j))) { ok = false; break; } out.push(j - i); i = j;
        }
        if (ok) return out;
        if (n > w.length) return [w.length];
      }
    });
  }, [sl.map(([ws]) => ws.map(x => x.w)), D.MAXL, D.CAP, D.CAPLH]);
  const ev = [];
  sl.forEach(([ws, ci], si) => { let i = 0; for (const n of cuts[si]) { const ch = ws.slice(i, i + n); ch.forEach((x, j) => ev.push([x.s, ch, j, ci])); i += n; } });
  ev.sort((a, b) => a[0] - b[0]);
  // Titelbild: Block unten bündig über D.BOT; ohne Bild etwas höher (optische Mitte)
  const y0 = hasImg ? D.BOT - K.bh : Math.min(D.BOT - K.bh, 760), y1 = D.Y1;
  const kz1 = hasImg ? D.KZ1 : 0.66;
  const capH = (ws, j) => ws.map((x, q) => { const w = esc(x.w), dig = /\d/.test(x.w) && !/^\d{1,2}\.$/.test(x.w); // Zahlen markieren, Ordnungszahlen («1. FC») nicht
    const inner = dig ? `<mark style="background:${markBg};color:${markFg}">${w}</mark>` : w; return `<span style="opacity:${q <= j ? 1 : .32}">${inner}</span>`; }).join(' ');
  const page = (p, w, tt, capTop) => {
    const e = ease(p), ih = D.IMG0 + (D.IMG1 - D.IMG0) * e, y = y0 + (y1 - y0) * e, kf = K.fs * (1 + (kz1 - 1) * e), op = Math.max(0, (p - .85) / .15);
    return shell(`${hasImg ? `<div id="im" style="height:${ih.toFixed(1)}px;background:${bgc}">${imgTag}<div class="fd" style="background:${fade}"></div></div>` : ''}
      ${hasImg && d.credit ? `<div id="cr" style="color:${d.heikel ? '#fff' : '#14161A'}">${esc(d.credit)}</div>` : ''}
      <div id="dc" style="color:${fgc}">${esc(deco)}</div>
      <div id="tx" style="top:${y.toFixed(1)}px">
        <span class="ch" style="background:${chipBg};color:${chipFg}"><span class="eq" id="eq">${tt == null ? '' : eqBars(tt)}</span>${esc(chip)}</span>
        <div id="kz" style="font-size:${kf.toFixed(1)}px">${esc(kz)}</div>
      </div>
      <div id="cp" style="top:${capTop}px;opacity:${op}">${w ? capH(w[0], w[1]) : ''}</div>`);
  };
  await pg.setContent(page(1, null, 0, 0)); await pg.evaluate(() => document.fonts.ready);
  const capTop = await pg.evaluate(() => Math.round(document.getElementById('kz').getBoundingClientRect().bottom)) + 44;
  const P = (p, w, tt) => page(p, w, tt, capTop);
  const frames = [[0, null, HOLD_P, null]], nG = Math.round(GLIDE * FPS), at = tt => ev.filter(x => x[0] <= tt).at(-1);
  for (let i = 1; i <= nG; i++) { const e = at(HOLD_P + i / FPS); frames.push([i / nG, e ? [e[1], e[2], e[3]] : null, 1 / FPS, HOLD_P + i / FPS]); }
  const t1 = HOLD_P + GLIDE + 1 / FPS, first = at(t1);
  const seq = [...(first ? [[t1, first[1], first[2], first[3]]] : []), ...ev.filter(x => x[0] > t1)];
  for (let i = 0; i < seq.length; i++) frames.push([1, [seq[i][1], seq[i][2], seq[i][3]], (i + 1 < seq.length ? seq[i + 1][0] : T_END) - seq[i][0], null]);
  const dir = `${out}/${r.k}`; fs.mkdirSync(dir, { recursive: true });
  const list = [];
  const EQ_T0 = +(HOLD_P + GLIDE).toFixed(3);
  const eqAt = async p => { await pg.setContent(P(p, null, 0)); await pg.evaluate(() => document.fonts.ready);
    return pg.evaluate(() => { const b = document.getElementById('eq').getBoundingClientRect(); return { x: Math.round(b.left), y: Math.round(b.top), w: Math.round(b.width), h: Math.round(b.height) }; }); };
  const eqR = await eqAt(1), eqY0 = (await eqAt(0)).y;
  fs.mkdirSync(`${dir}/eq`, { recursive: true });
  const nEq = Math.round(EQ_P * FPS);
  for (let i = 0; i < nEq; i++) {
    await pg.setContent(`<!doctype html><html><head><style>${dcss}html,body{width:${eqR.w}px;height:${eqR.h}px;background:transparent}.eq{position:absolute;left:0;top:0}</style></head><body style="background:transparent;--eqc:${chipFg}"><span class="eq">${eqBars(i / FPS)}</span></body></html>`);
    await pg.screenshot({ path: `${dir}/eq/e${String(i).padStart(2, '0')}.png`, omitBackground: true, clip: { x: 0, y: 0, width: eqR.w, height: eqR.h } });
  }
  for (const [i, [p, w, dur, tt]] of frames.entries()) {
    await pg.setContent(P(p, w, tt)); await pg.evaluate(() => document.fonts.ready);
    const name = `f${String(i).padStart(3, '0')}.png`; await pg.screenshot({ path: `${dir}/${name}` });
    list.push(`file '${name}'\nduration ${Math.max(dur, 0.02).toFixed(3)}`);
  }
  list.push(list.at(-1).split('\n')[0]);
  fs.writeFileSync(`${dir}/list.txt`, list.join('\n') + '\n');
  return { k: r.k, v: +V_END.toFixed(3), e0: +E0.toFixed(3), T: +T_END.toFixed(3), waveY: 0, wave: fgc, nowave: true, eq: { ...eqR, t0: EQ_T0, n: nEq, y0: eqY0, h0: HOLD_P } };
}

fs.mkdirSync(out, { recursive: true });
const browser = await chromium.launch(process.env.CHROME ? { executablePath: process.env.CHROME } : {});
const pg = await browser.newPage({ viewport: { width: 1080, height: 1920 } });
const meta = [];
for (const r of R.reels) {
  if (r.duo && !r.list) { meta.push(await renderDuo(pg, r, r.img && fs.existsSync(r.img) ? fs.readFileSync(r.img).toString('base64') : null)); continue; } // Duoton (21.11.2026)
  if (r.bg && fs.existsSync(r.bg)) { meta.push(await renderPoster(pg, r, fs.readFileSync(r.bg).toString('base64'))); continue; } // Plakat (Entwurf C)
  const [bg, fg, acc, cb, cf, wave, dim] = TH[r.theme] || TH.dunkel;
  const fol = false; // Einblendung «Folg @newsmag.ch» weg (19.11.2026, Cy)
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
