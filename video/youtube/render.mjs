// YouTube-Video einer Newscast-Folge (seit 15.10.2026): node render.mjs timeline.json outdir
// timeline.json = { job, frames: [{ dur, scene: title|themes|topic|weather|end, topic, cap, lit, cur }] } (von yt.py)
// Schreibt outdir/fNNN.png (1920×1080), outdir/list.txt (ffmpeg concat) und outdir/thumb.png. Look wie Story-Slides/Podcast-Karten.
import { chromium } from 'playwright';
import fs from 'fs';

const [, , file, out] = process.argv;
const { job, frames } = JSON.parse(fs.readFileSync(file, 'utf8'));
const T = job.topics, WX = job.weather;
const b64 = p => fs.readFileSync(new URL(p, import.meta.url)).toString('base64');
const mono = b64('../node_modules/@fontsource/ibm-plex-mono/files/ibm-plex-mono-latin-500-normal.woff2');
const font = b64('../node_modules/@fontsource-variable/archivo/files/archivo-latin-wdth-normal.woff2');
const logo = b64('./logo-dark.png');
const esc = s => String(s ?? '').replace(/&/g, '&amp;').replace(/</g, '&lt;');
const nw = s => s.replace(/[^\s*]+-[^\s*]+/g, w => `<span class="nw">${w}</span>`); // Bindestrich-Wörter nie trennen
const acc = s => nw(esc(s)).replace(/\*(.+?)\*/g, '<em>$1</em>');
const many = T.length > 8;

const css = `
@font-face{font-family:M;src:url(data:font/woff2;base64,${mono}) format('woff2')}
@font-face{font-family:A;src:url(data:font/woff2;base64,${font}) format('woff2');font-weight:100 900;font-stretch:62% 125%}
*{margin:0;box-sizing:border-box}
:root{--bg:#14161A;--fg:#F4F5F7;--pink:#FF00A6;--mu:#8C939D;--line:#2A2E35}
.light{--bg:#F4F5F7;--fg:#14161A;--mu:#6B727C;--line:#D9DCE1}
.pink{--bg:#FF00A6;--fg:#14161A;--pink:#F4F5F7;--mu:#5C0040;--line:#E0009A}
html,body{width:1920px;height:1080px;overflow:hidden}
body{background:var(--bg);color:var(--fg);font-family:A}
.top{position:absolute;left:96px;right:96px;top:64px;display:flex;align-items:center;gap:16px}
.top img{height:46px}
.light .top img,.pink .top img{filter:brightness(0)}
.brand{font-weight:900;font-stretch:68%;font-size:50px;line-height:1}
.lab{margin-left:auto;font-family:M;font-size:22px;letter-spacing:.08em;color:var(--mu)}
.main{position:absolute;left:96px;top:190px;width:1120px;height:560px;display:flex;flex-direction:column;justify-content:center}
.kick{font-family:M;font-size:26px;letter-spacing:.14em;text-transform:uppercase;color:var(--pink);margin-bottom:26px;display:flex;gap:18px;align-items:center}
.kick b{font-weight:500;background:var(--pink);color:var(--bg);padding:4px 12px}
h1{font-weight:900;font-stretch:68%;font-variation-settings:'wdth' 68,'wght' 900;text-transform:uppercase;font-size:128px;line-height:.92;text-wrap:balance}
h1 em{font-style:normal;color:var(--pink)}
.nw{white-space:nowrap}
.meta{font-family:M;font-size:22px;letter-spacing:.06em;color:var(--mu);margin-top:30px;text-transform:uppercase}
.side{position:absolute;right:96px;top:${many ? 180 : 200}px;width:520px}
.side h3{font-family:M;font-weight:500;font-size:20px;letter-spacing:.14em;color:var(--mu);border-bottom:2px solid var(--line);padding-bottom:12px;margin-bottom:6px}
.row{display:flex;gap:16px;align-items:baseline;padding:${many ? 5 : 8}px 0;font-size:${many ? 22 : 25}px;line-height:1.18;font-weight:600;font-stretch:85%;color:var(--mu);border-bottom:1px solid var(--line)}
.row span{flex:1;min-width:0;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden;text-wrap:pretty}
.row i{font-family:M;font-style:normal;font-size:18px;width:28px;flex:none}
.row.on{color:var(--fg)} .row.on i{color:var(--pink)}
.row.cur{color:var(--pink);font-weight:800}
.cap{position:absolute;left:96px;right:96px;bottom:72px;min-height:150px;display:flex;align-items:center}
.cap p{font-size:44px;font-weight:500;font-stretch:92%;line-height:1.28;max-width:1560px;text-wrap:balance}
.cap:before{content:'';position:absolute;left:0;right:0;top:-26px;border-top:2px solid var(--line)}
.title .main{top:150px;height:700px;width:1600px}
.title h1{font-size:250px;line-height:.86}
.claim{font-weight:700;font-stretch:90%;font-size:56px;color:var(--pink);margin-top:34px}
.themes .list{position:absolute;left:96px;top:200px;right:96px;columns:2;column-gap:120px}
.themes .row{font-size:${many ? 34 : 40}px;padding:${many ? 8 : 12}px 0;break-inside:avoid}
.themes .row i{font-size:24px;width:44px}
.wx{position:absolute;left:96px;right:96px;top:300px;display:grid;grid-template-columns:repeat(5,1fr);gap:28px}
.wx>div{border-top:4px solid var(--fg);padding-top:22px}
.wx .o{font-weight:800;font-stretch:80%;font-size:44px}
.wx .e{font-size:84px;margin:18px 0 10px;font-family:'Noto Color Emoji',A}
.wx .t{font-weight:900;font-stretch:70%;font-size:72px}
.wx .t span{color:var(--mu);font-weight:700}
.wx .x{font-size:26px;color:var(--mu);margin-top:6px}
.src{position:absolute;left:96px;top:760px;font-family:M;font-size:20px;color:var(--mu)}
.end .main{width:1700px}
.end h1{font-size:200px}
.subs{font-family:M;font-size:28px;letter-spacing:.06em;color:var(--fg);margin-top:40px}
.thumb .main{top:130px;width:1730px;height:820px}
.thumb h1{font-size:150px}
.thumb .hl{font-size:118px;margin-top:10px}
`;

const top = `<div class="top"><img src="data:image/png;base64,${logo}"><span class="brand">NEWSMAG</span><span class="lab">${esc(job.label)}</span></div>`;
const num = k => String(k + 1).padStart(2, '0');
function page(f) {
  const cls = { title: 'pink title', themes: 'themes', topic: '', weather: 'light', end: 'end' }[f.scene] ?? '';
  const cap = f.cap ? `<div class="cap"><p>${nw(esc(f.cap))}</p></div>` : '';
  let body = '';
  if (f.scene === 'title') body = `<div class="main"><div class="kick">Nachrichten aus der Schweiz</div><h1>Newsmag<br>${esc(job.slot_title)}</h1><div class="claim">Bliib uffem Laufendä.</div></div>`;
  if (f.scene === 'themes') body = `<div class="kick" style="position:absolute;left:96px;top:150px">Die Themen</div><div class="list">${T.map((t, k) =>
    `<div class="row ${k === f.cur ? 'cur' : f.lit.includes(k) ? 'on' : ''}"><i>${num(k)}</i><span>${esc(t.chap)}</span></div>`).join('')}</div>`;
  if (f.scene === 'topic' && T[f.topic]) {
    const t = T[f.topic];
    body = `<div class="main"><div class="kick">${t.update ? '<b>NEUES ZU</b>' : ''}${t.recap ? 'Rückblick · ' : ''}${esc(t.kicker)} · ${f.topic + 1}/${T.length}</div><h1 id="h">${acc(t.head)}</h1>
      <div class="meta">${t.publishers > 1 ? `Zusammengefasst aus ${t.publishers} Schweizer Verlagen · ` : ''}newsmag.ch</div></div>
      <div class="side"><h3>DIE THEMEN</h3>${T.map((x, k) => `<div class="row ${k < f.topic ? '' : k === f.topic ? 'cur' : 'on'}"><i>${num(k)}</i><span>${esc(x.chap)}</span></div>`).join('')}</div>`;
  }
  if (f.scene === 'weather') body = WX ? `<div class="kick" style="position:absolute;left:96px;top:190px">${esc(WX.label)} · Deutschschweiz</div><div class="wx">${WX.orte.map(o =>
    `<div><div class="o">${esc(o.ort)}</div><div class="e">${o.emoji || ''}</div><div class="t">${o.max}° <span>/ ${o.min}°</span></div><div class="x">${esc(o.text)}</div></div>`).join('')}</div><div class="src">QUELLE: METEOSCHWEIZ</div>`
    : `<div class="main"><h1>Das Wetter</h1></div>`;
  if (f.scene === 'end') body = `<div class="main"><div class="kick">Alle Themen mit Links zu den Originalartikeln</div><h1>newsmag<em>.ch</em></h1>
    <div class="subs">NEUE FOLGEN 6.30 · 12.30 · 17.30 · 22.30 UHR — JETZT ABONNIEREN</div>
    <div class="meta" style="text-transform:none">Zusammengefasst aus Schweizer Medien. Gesprochen von Margareth, einer KI-Stimme.</div></div>`;
  if (f.scene === 'thumb') {
    const t = T.find(x => !x.recap) || T[0];
    body = `<div class="main"><div class="kick">Newsmag ${esc(job.slot_title)} · ${esc(job.label.split(' · ').slice(1).join(' · '))}</div><h1 class="hl" id="h">${acc(t ? t.head : 'Die Nachrichten')}</h1>
      <div class="claim">+ ${Math.max(0, T.length - 1)} weitere Themen · Bliib uffem Laufendä.</div></div>`;
  }
  return `<!doctype html><html><head><meta charset="utf-8"><style>${css}</style></head><body class="${cls}${f.scene === 'thumb' ? ' pink thumb' : ''}">${top}${body}${cap}</body></html>`;
}

fs.mkdirSync(out, { recursive: true });
const browser = await chromium.launch(process.env.CHROME ? { executablePath: process.env.CHROME } : {});
const pg = await browser.newPage({ viewport: { width: 1920, height: 1080 } });
const fit = (maxW, maxH) => pg.evaluate(([w, hgt]) => { const h = document.getElementById('h'); if (!h) return;
  let s = parseFloat(getComputedStyle(h).fontSize); while ((h.scrollWidth > w || h.offsetHeight > hgt) && s > 56) { s -= 4; h.style.fontSize = s + 'px'; } }, [maxW, maxH]);
const list = [];
for (const [i, f] of frames.entries()) {
  await pg.setContent(page(f));
  await pg.evaluate(() => document.fonts.ready);
  await fit(1120, 400);
  await pg.evaluate(() => { // Themenliste darf nie in die Untertitel-Zone laufen (lange Titel auf zwei Zeilen)
    const box = document.querySelector('.side') || document.querySelector('.list'); if (!box) return;
    const rows = [...box.querySelectorAll('.row')]; let s = rows.length ? parseFloat(getComputedStyle(rows[0]).fontSize) : 0;
    while (box.getBoundingClientRect().bottom > 815 && s > 16) { s -= 1; rows.forEach(r => { r.style.fontSize = s + 'px'; r.style.paddingTop = r.style.paddingBottom = Math.max(3, s * 0.2) + 'px'; }); } });
  const name = `f${String(i).padStart(3, '0')}.png`;
  await pg.screenshot({ path: `${out}/${name}` });
  list.push(`file '${name}'\nduration ${f.dur}`);
}
list.push(`file 'f${String(frames.length - 1).padStart(3, '0')}.png'`); // ffmpeg concat: letztes Bild doppelt
fs.writeFileSync(`${out}/list.txt`, list.join('\n') + '\n');
// Vorschaubild (Variante B, Cy 15.10.2026): Marke gross, Ausgabe riesig, Datum/Uhrzeit, ein Stichwort zum Hauptthema; Farbe je Ausgabe
const TH = { morgen: ['#FF00A6', '#14161A', '#F4F5F7'], mittag: ['#F4F5F7', '#14161A', '#FF00A6'], abend: ['#14161A', '#F4F5F7', '#FF00A6'], nacht: ['#0E1B3D', '#F4F5F7', '#FF00A6'] };
const [tbg, tfg, tac] = TH[job.slot] || TH.abend, light = job.slot === 'morgen' || job.slot === 'mittag';
const lead = T.find(x => !x.recap) || T[0], hook = (lead && (lead.hook || lead.chap)) || '';
await pg.setViewportSize({ width: 1280, height: 720 });
await pg.setContent(`<!doctype html><meta charset="utf-8"><style>
@font-face{font-family:M;src:url(data:font/woff2;base64,${mono}) format('woff2')}
@font-face{font-family:A;src:url(data:font/woff2;base64,${font}) format('woff2');font-weight:100 900;font-stretch:62% 125%}
*{margin:0}body{width:1280px;height:720px;background:${tbg};color:${tfg};font-family:A;position:relative;overflow:hidden}
.top{position:absolute;left:70px;top:58px;display:flex;align-items:center;gap:22px}.top img{height:92px;${light ? 'filter:brightness(0)' : ''}}
.br{font-weight:900;font-stretch:68%;font-size:104px;line-height:1}
.ed{position:absolute;left:66px;top:${hook ? 205 : 230}px;font-weight:900;font-stretch:66%;font-size:${hook ? 205 : 245}px;line-height:.86;color:${job.slot === 'morgen' ? '#F4F5F7' : tac};white-space:nowrap}
.dt{position:absolute;left:72px;top:${hook ? 405 : 470}px;font-family:M;font-size:46px;letter-spacing:.04em}
#hk{position:absolute;left:70px;bottom:52px;background:${tfg};color:${tbg};font-weight:900;font-stretch:72%;font-size:74px;line-height:1;padding:18px 28px;text-transform:uppercase;white-space:nowrap}
</style><div class="top"><img src="data:image/png;base64,${logo}"><span class="br">NEWSMAG</span></div>
<div class="ed">${esc(job.label.split(' · ')[0])}</div><div class="dt">${esc(job.label.split(' · ').slice(1).join(' · '))}</div>${hook ? `<div id="hk">${esc(hook)}</div>` : ''}`);
await pg.evaluate(() => document.fonts.ready);
await pg.evaluate(() => { const h = document.getElementById('hk'); if (!h) return; let s = 74; while (h.offsetWidth > 1140 && s > 40) { s -= 3; h.style.fontSize = s + 'px'; } });
await pg.screenshot({ path: `${out}/thumb.png` });
await browser.close();
console.log(frames.length, 'Bilder');
