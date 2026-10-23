// Newsmag Karussell (Instagram-Feed, 4:5 = 1080×1350): node carousel.mjs carousel.json outdir
// carousel.json: { "label": "NEWSMAG · DER TAG · MI 14.10.", "slides": [
//   { "type": "cover", "bg": "dark|pink|light", "kicker": "DER TAG", "title": "Was heute *wichtig* war.", "sub": "7 Themen …" },
//   { "type": "item",  "bg": "dark|light|pink", "num": "1/7", "tag": "SCHWEIZ", "title": "…", "text": "2–3 Sätze", "foot": "aus 7 Schweizer Medien" },
//   { "type": "end",   "bg": "pink", "title": "…", "text": "…" } ] }
// *…* = Akzentfarbe. Wichtiges liegt in der Mitte (Raster schneidet auf 3:4 zu → links/rechts je ~35 px weg).
import { chromium } from 'playwright';
import fs from 'fs';
import path from 'path';

const [, , file, out] = process.argv;
const data = JSON.parse(fs.readFileSync(file, 'utf8'));
const label = data.label || '';
const mono = fs.readFileSync(new URL('./node_modules/@fontsource/ibm-plex-mono/files/ibm-plex-mono-latin-500-normal.woff2', import.meta.url)).toString('base64');
const font = fs.readFileSync(new URL('./node_modules/@fontsource-variable/archivo/files/archivo-latin-wdth-normal.woff2', import.meta.url)).toString('base64');
// [Hintergrund, Schrift, Akzent, gedämpft]
const C = { dark: ['#14161A', '#F4F5F7', '#FF00A6', '#8C939D'], pink: ['#FF00A6', '#14161A', '#F4F5F7', '#5C0040'], light: ['#F4F5F7', '#14161A', '#FF00A6', '#7A818B'] };
const esc = s => String(s || '').replace(/&/g, '&amp;').replace(/</g, '&lt;');
const rich = (s, ac) => esc(s).replace(/[^\s*]+-[^\s*]+/g, w => `<span style="white-space:nowrap">${w}</span>`).replace(/\*(.+?)\*/g, `<span style="color:${ac}">$1</span>`);

fs.mkdirSync(out, { recursive: true });
const browser = await chromium.launch({ ...(process.env.CHROME ? { executablePath: process.env.CHROME } : {}) });
const page = await browser.newPage({ viewport: { width: 1080, height: 1350 } });
const total = data.slides.length;
for (const [i, s] of data.slides.entries()) {
  const [bg, fg, ac, mu] = C[s.bg] || C.dark;
  const head = `<div class="top"><span>${esc(label)}</span></div>`; // keine eigene Seitenzahl: Instagram blendet oben rechts «1/7» ein
  let body = '';
  if (s.type === 'cover') body = `${head}
    <div class="mid"><div class="kick">${esc(s.kicker)}</div><h1 class="big">${rich(s.title, ac)}</h1>${s.sub ? `<p class="sub">${rich(s.sub, ac)}</p>` : ''}</div>
    <div class="bot"><span>NEWSMAG.CH</span></div><div class="pill"><span>Wischen</span><svg viewBox="0 0 34 24" aria-hidden="true"><path d="M2 12h28M20 3l10 9-10 9" fill="none" stroke="currentColor" stroke-width="4.5" stroke-linecap="square"/></svg></div>`;
  else if (s.type === 'end') body = `${head}
    <div class="mid"><h1 class="big">${rich(s.title, ac)}</h1>${s.text ? `<p class="sub">${rich(s.text, ac)}</p>` : ''}</div>
    <div class="bot"><span>BLIIB UFFEM LAUFENDÄ.</span><span>NEWSMAG.CH</span></div>`;
  else body = `${head}
    <div class="mid item">${s.tag ? `<div class="kick">${esc(s.num ? s.num + ' · ' : '')}${esc(s.tag)}</div>` : ''}<h2>${rich(s.title, ac)}</h2><p class="txt">${rich(s.text, ac)}</p></div>
    <div class="bot"><span>${esc(s.foot || 'NEWSMAG.CH')}</span></div><div class="nx"><span>Weiter</span><svg viewBox="0 0 34 24" aria-hidden="true"><path d="M2 12h28M20 3l10 9-10 9" fill="none" stroke="currentColor" stroke-width="4.5" stroke-linecap="square"/></svg></div>`;
  await page.setContent(`<!doctype html><html><head><style>
@font-face{font-family:M;src:url(data:font/woff2;base64,${mono}) format('woff2')}
@font-face{font-family:A;src:url(data:font/woff2;base64,${font}) format('woff2');font-weight:100 900;font-stretch:62% 125%}
html,body{margin:0;width:1080px;height:1350px;background:${bg};color:${fg};overflow:hidden}
body{position:relative;font-family:A}
.top,.bot{position:absolute;left:96px;right:96px;display:flex;justify-content:space-between;font-family:M;font-size:26px;letter-spacing:.06em;color:${mu}}
.top{top:72px}.bot{bottom:72px}
/* Wisch-Hinweis (14.10.2026, Cy: im Feed sah man nicht, dass es weitergeht): Titelbild = Pille, Inhalt = «Weiter →» */
.pill,.nx{position:absolute;right:72px;bottom:56px;display:flex;align-items:center;gap:14px;font-weight:900;font-stretch:72%;font-variation-settings:'wdth' 72,'wght' 900;text-transform:uppercase;letter-spacing:.01em}
.pill{background:${ac};color:#14161A;font-size:46px;padding:26px 34px 26px 38px;border-radius:999px}
/* Pfeil als SVG, vertikal auf die Grossbuchstaben zentriert (text-box schneidet Ober-/Unterlänge weg) */
.pill span,.nx span{text-box:trim-both cap alphabetic;line-height:1}
.pill svg,.nx svg{width:.95em;height:.68em;flex:none}
.nx{color:${ac};font-size:40px;bottom:62px;right:88px}
.mid{position:absolute;left:96px;right:96px;top:170px;bottom:170px;display:flex;flex-direction:column;justify-content:center}
.kick{font-family:M;font-size:30px;letter-spacing:.08em;color:${ac};margin-bottom:34px;text-transform:uppercase}
h1,h2{margin:0;font-weight:900;font-stretch:68%;font-variation-settings:'wdth' 68,'wght' 900;text-transform:uppercase;text-wrap:balance;hyphens:manual;letter-spacing:-.005em}
h1.big{font-size:150px;line-height:.92}
h2{font-size:104px;line-height:.94}
.sub{margin:44px 0 0;font-size:42px;line-height:1.3;font-weight:500;font-stretch:100%;font-variation-settings:'wdth' 100,'wght' 500;text-wrap:pretty}
.txt{margin:40px 0 0;font-size:40px;line-height:1.38;font-weight:420;font-stretch:100%;font-variation-settings:'wdth' 100,'wght' 420;text-wrap:pretty}
</style></head><body>${body}</body></html>`);
  await page.evaluate(() => document.fonts.ready);
  // Überlauf: zuerst Titel, dann Fliesstext verkleinern
  await page.evaluate(() => {
    const mid = document.querySelector('.mid'), h = mid.querySelector('h1,h2'), t = mid.querySelector('.txt,.sub');
    const over = () => mid.scrollHeight > mid.clientHeight + 1 || h.scrollWidth > h.clientWidth + 1;
    let f = parseFloat(getComputedStyle(h).fontSize), min = f * 0.6;
    while (over() && f > min) { f -= 3; h.style.fontSize = f + 'px'; }
    if (t) { let g = parseFloat(getComputedStyle(t).fontSize); while (over() && g > 30) { g -= 1; t.style.fontSize = g + 'px'; } }
    while (over() && f > 40) { f -= 3; h.style.fontSize = f + 'px'; }
  });
  const name = path.join(out, `newsmag-carousel-${String(i + 1).padStart(2, '0')}.jpg`);
  await page.screenshot({ path: name, type: 'jpeg', quality: 92 });
  console.log(name);
}
await browser.close();
