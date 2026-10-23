// Newsmag Morning Slides: node render.mjs slides.json outdir
// slides.json: { "label": "NEWSMAG · AM MORGEN · SA 10.10.", "slides": [{ "bg": "dark|pink|light", "text": "NATI SCHLÄGT *SLOWENIEN 2:1.*" }] }
// (*…* = Akzentfarbe; label = kleiner Absender oben, optional; altes Format = nur das Array)
import { chromium } from 'playwright';
import fs from 'fs';
import path from 'path';

const [, , file, out] = process.argv;
const data = JSON.parse(fs.readFileSync(file, 'utf8'));
const slides = Array.isArray(data) ? data : data.slides, label = Array.isArray(data) ? '' : (data.label || '');
const mono = fs.readFileSync(new URL('./node_modules/@fontsource/ibm-plex-mono/files/ibm-plex-mono-latin-500-normal.woff2', import.meta.url)).toString('base64');
const font = fs.readFileSync(new URL('./node_modules/@fontsource-variable/archivo/files/archivo-latin-wdth-normal.woff2', import.meta.url)).toString('base64');
const C = { dark: ['#14161A', '#F4F5F7', '#FF00A6', '#8C939D'], pink: ['#FF00A6', '#14161A', '#F4F5F7', '#5C0040'], light: ['#F4F5F7', '#14161A', '#FF00A6', '#7A818B'] };
const esc = s => s.replace(/&/g, '&amp;').replace(/</g, '&lt;');

fs.mkdirSync(out, { recursive: true });
const browser = await chromium.launch({ ...(process.env.CHROME ? { executablePath: process.env.CHROME } : {}) });
const page = await browser.newPage({ viewport: { width: 1080, height: 1920 } });
for (const [i, s] of slides.entries()) {
  const [bg, fg, ac, mu] = C[s.bg];
  // Wörter mit Bindestrich (SVP-Politiker) nicht trennen
  const html = esc(s.text).replace(/[^\s*]+-[^\s*]+/g, w => `<span style="white-space:nowrap">${w}</span>`).replace(/\*(.+?)\*/g, `<span style="color:${ac}">$1</span>`);
  await page.setContent(`<!doctype html><html><head><style>
@font-face{font-family:M;src:url(data:font/woff2;base64,${mono}) format('woff2')}
@font-face{font-family:A;src:url(data:font/woff2;base64,${font}) format('woff2');font-weight:100 900;font-stretch:62% 125%}
html,body{margin:0;width:1080px;height:1920px;background:${bg}}
.w{position:absolute;inset:0;display:flex;align-items:center;padding:0 92px}
h1{margin:0;font-family:A;font-weight:900;font-stretch:68%;font-variation-settings:'wdth' 68,'wght' 900;text-transform:uppercase;color:${fg};
   font-size:${s.size || 180}px;line-height:.92;letter-spacing:-.005em;text-wrap:balance;hyphens:manual}
.lb{position:absolute;left:92px;top:300px;font-family:M;font-size:32px;letter-spacing:.06em;color:${mu}}
</style></head><body>${label ? `<div class="lb">${esc(label)}</div>` : ''}<div class="w"><h1>${html}</h1></div></body></html>`);
  await page.evaluate(() => document.fonts.ready);
  // Schrift verkleinern, bis nichts überläuft
  await page.evaluate(() => { const h = document.querySelector('h1'); let f = parseFloat(getComputedStyle(h).fontSize);
    while ((h.scrollWidth > 896 || h.offsetHeight > 1100) && f > 60) { f -= 4; h.style.fontSize = f + 'px'; } });
  const name = path.join(out, `newsmag-morning-${i + 1}.png`);
  await page.screenshot({ path: name });
  console.log(name);
}
await browser.close();
