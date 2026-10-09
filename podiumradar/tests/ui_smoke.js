/* Rooktest voor de app (geen internet nodig). Draaien, vanuit de map podiumradar/:
     PWPATH=$(npm root -g)/playwright node tests/ui_smoke.js
   (of zonder PWPATH als 'playwright' in node_modules staat). Verwacht: "ALLES GOED".
   Start zelf een webserver op een vrije poort voor site/, en test onder andere: opstarten zonder fouten, geen verzoeken naar
   buiten, tabbladen, zoeken, detailscherm, 'Klopt niet?' (geen openbaar bericht), Ik ga, agendabestand, Terug sluit schermen,
   waarschuwing bij oude data, en dat kapotte rijen of kapotte opgeslagen gegevens de app niet leegmaken. */
const http = require('http'), fs = require('fs'), path = require('path');
const { chromium } = require(process.env.PWPATH || 'playwright');
const SITE = path.resolve(__dirname, '../site');
const MIME = { '.html': 'text/html', '.js': 'text/javascript', '.json': 'application/json', '.css': 'text/css', '.svg': 'image/svg+xml', '.png': 'image/png', '.woff2': 'font/woff2' };
let dataOverride = null;
const server = http.createServer((req, res) => {
  const u = decodeURIComponent(req.url.split('?')[0]); let f = path.join(SITE, u === '/' ? 'index.html' : u);
  if (!f.startsWith(SITE) || !fs.existsSync(f) || fs.statSync(f).isDirectory()) { res.writeHead(404); return res.end('nee'); }
  const body = (u === '/data.json' && dataOverride) ? Buffer.from(JSON.stringify(dataOverride)) : fs.readFileSync(f);
  res.writeHead(200, { 'content-type': MIME[path.extname(f)] || 'application/octet-stream', 'cache-control': 'no-store' }); res.end(body);
});
let fouten = 0;
const check = (naam, ok, extra) => { if (!ok) fouten++; console.log((ok ? 'ok   ' : 'FOUT ') + naam + (ok || extra === undefined ? '' : ' -> ' + JSON.stringify(extra))); };
const real = JSON.parse(fs.readFileSync(path.join(SITE, 'data.json'), 'utf8'));

(async () => {
  await new Promise(r => server.listen(0, '127.0.0.1', r));
  const BASE = 'http://127.0.0.1:' + server.address().port + '/';
  const browser = await chromium.launch();
  const newPage = async (opts = {}) => {
    const ctx = await browser.newContext({ viewport: { width: 390, height: 844 }, timezoneId: 'Europe/Amsterdam', locale: 'nl-NL', acceptDownloads: true, ...opts });
    await ctx.grantPermissions(['clipboard-read', 'clipboard-write'], { origin: BASE.slice(0, -1) }).catch(() => {});
    const p = await ctx.newPage(); p.errs = []; p.ext = [];
    p.on('pageerror', e => p.errs.push(e.message)); p.on('console', m => { if (m.type() === 'error') p.errs.push(m.text()); });
    p.on('request', r => { if (!r.url().startsWith(BASE) && !r.url().startsWith('data:') && !r.url().startsWith('blob:')) p.ext.push(r.url()); });
    return p;
  };
  const start = async p => { await p.goto(BASE + 'index.html'); await p.waitForSelector('.ev', { timeout: 20000 }); };

  // 1. opstarten
  let p = await newPage(); await start(p);
  check('opstarten zonder fouten', p.errs.length === 0, p.errs);
  check('geen verzoeken naar andere sites', p.ext.length === 0, p.ext);
  check('kaarten getoond', (await p.locator('#main .ev').count()) > 5);
  check('noindex in index.html', (await p.locator('meta[name=robots]').getAttribute('content')) === 'noindex, nofollow');
  check('geen waarschuwing bij verse data', (await p.locator('.stale').count()) === 0 || real.updated < '2000');

  // 2. tabbladen en zoeken
  for (const t of ['thea', 'film', 'expo', 'fest', 'kids', 'pop']) { await p.click(`.seg [data-type="${t}"]`); await p.waitForTimeout(120); }
  check('tabbladen zonder fouten', p.errs.length === 0, p.errs);
  await p.fill('#q', 'jazz'); await p.waitForTimeout(500);
  check('zoeken geeft resultaat of melding', (await p.locator('#main .ev, #main .empty').count()) > 0);
  await p.fill('#q', ''); await p.waitForTimeout(300);

  // 3. detailscherm
  await p.locator('#main .ev').first().click(); await p.waitForSelector('#detailSheet.open');
  check('detailscherm: geen link naar GitHub', (await p.locator('#detailSheet a[href*="github.com"]').count()) === 0);
  check('detailscherm: Klopt niet?-knop en linkrij', (await p.locator('#wrongBtn').count()) === 1 && (await p.locator('#linkRow .btn').count()) >= 1);
  check('detailscherm: toelichting reistijd', (await p.locator('.travnote').count()) <= 1);
  await p.click('#wrongBtn'); await p.waitForTimeout(400);
  const klem = await p.evaluate(() => navigator.clipboard.readText().catch(() => ''));
  check('Klopt niet?: kant-en-klaar bericht gekopieerd', /^Klopt niet in Podiumradar:/.test(klem), klem.slice(0, 60));
  check('Klopt niet?: geen nieuw tabblad', p.context().pages().length === 1);
  const heeftIcs = (await p.locator('#icsBtn').count()) === 1;
  if (heeftIcs) {
    const [dl] = await Promise.all([p.waitForEvent('download'), p.click('#icsBtn')]);
    const ics = fs.readFileSync(await dl.path(), 'utf8');
    const regels = ics.split('\r\n').filter(Boolean); const props = /^(BEGIN|END|VERSION|PRODID|UID|DTSTAMP|DTSTART|DTEND|SUMMARY|LOCATION|URL|DESCRIPTION|TRIGGER|ACTION):/;
    check('agendabestand: geldig, elke regel een bekende eigenschap', regels[0] === 'BEGIN:VCALENDAR' && regels.at(-1) === 'END:VCALENDAR' && regels.every(r => props.test(r)), regels.filter(r => !props.test(r)).slice(0, 3));
  }
  await p.click('#goBtn'); check('Ik ga: aan', (await p.locator('#goBtn').getAttribute('aria-pressed')) === 'true');
  await p.goBack(); await p.waitForTimeout(300);
  check('Terug sluit het scherm', !(await p.evaluate(() => document.querySelector('#detailSheet').classList.contains('open'))));
  await p.reload(); await p.waitForSelector('.ev');
  check('plan blijft na herladen', (await p.evaluate(() => Object.keys(JSON.parse(localStorage.getItem('pr_going') || '{}')).length)) === 1);
  check('na alles: geen fouten', p.errs.length === 0, p.errs);
  await p.context().close();

  // 4. verouderde data geeft een waarschuwing
  const upd = new Date(+real.updated.slice(0, 4), +real.updated.slice(5, 7) - 1, +real.updated.slice(8, 10), +real.updated.slice(11, 13), +real.updated.slice(14, 16));
  p = await newPage(); await p.clock.install({ time: new Date(upd.getTime() + 3 * 864e5) }); await start(p);
  check('waarschuwing bij data van 3 dagen oud', (await p.locator('.stale').count()) === 1 && /niet bijgewerkt/.test(await p.locator('.stale').innerText()));
  await p.context().close();

  // 5. kapotte rijen en kwaadaardige velden: de app blijft werken en voert niets uit
  const kapot = JSON.parse(JSON.stringify(real)); const v0 = Object.keys(kapot.venues)[0];
  const basis = kapot.events[0];
  kapot.events.push({ ...basis, id: 'x1', title: null }, { ...basis, id: 'x2', date: null }, { ...basis, id: 'x3', time: 2000 }, { ...basis, id: 'x4', support: 'abc' },
    { ...basis, id: '"><img src=x onerror=window.__x=1>', title: 'kwaad' }, { ...basis, id: 'x6', v: '"><svg onload=window.__x=1>' },
    { ...basis, id: 'x7', title: '<img src=x onerror=window.__x=1>', url: 'javascript:window.__x=1' }, { ...basis, id: 'x8', url: 'https://a.nl/x\r\nEND:VEVENT' });
  dataOverride = kapot; p = await newPage(); await start(p);
  check('kapotte rijen: app toont toch kaarten', (await p.locator('#main .ev').count()) > 5, p.errs);
  check('kwaadaardige velden voeren niets uit', !(await p.evaluate(() => window.__x)) && (await p.locator('img[src="x"], svg[onload]').count()) === 0);
  await p.context().close(); dataOverride = null;

  // 6. kapotte opgeslagen gegevens
  p = await newPage();
  await p.addInitScript(() => { try { localStorage.setItem('pr_fav2', '{"a":1}'); localStorage.setItem('pr_going', '[1,2]'); localStorage.setItem('pr_home', '{"x":1}'); localStorage.setItem('pr_hideV', '"tekst"'); localStorage.setItem('pr_geo', 'null'); } catch (e) {} });
  await start(p);
  check('kapotte opgeslagen gegevens: app start', (await p.locator('#main .ev').count()) > 5 && p.errs.length === 0, p.errs);
  await p.context().close();

  // 7. over-pagina en niets persoonlijks in de site
  p = await newPage(); const r = await p.goto(BASE + 'over.html');
  check('over.html laadt, noindex', r.status() === 200 && (await p.locator('meta[name=robots]').getAttribute('content')) === 'noindex, nofollow');
  await p.context().close();
  const alles = fs.readdirSync(SITE).filter(f => /\.(html|js|json|css|svg)$/.test(f) && f !== 'data.json' && f !== 'nl.json').map(f => fs.readFileSync(path.join(SITE, f), 'utf8')).join('\n');
  check('geen e-mailadres in de site', !/[\w.+-]+@(gmail|hotmail|outlook|icloud)\.[a-z]+/i.test(alles));

  await browser.close(); server.close();
  console.log('\n' + (fouten ? fouten + ' FOUT(EN)' : 'ALLES GOED')); process.exit(fouten ? 1 : 0);
})().catch(e => { console.error(e); process.exit(2); });
