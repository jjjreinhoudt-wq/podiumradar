// Zie fake_spotify.py voor het gebruik.
const { chromium } = require(process.env.PWPATH);
const fs = require('fs');
const base = process.argv[2], expect = JSON.parse(fs.readFileSync(process.argv[3], 'utf8'));
(async () => {
  const b = await chromium.launch(); const errs = [];
  const p = await b.newPage({ viewport:{width:384,height:832}, hasTouch:true, isMobile:true });
  p.on('pageerror', e=>errs.push(e.message));
  await p.goto(base); await p.waitForTimeout(1500);
  // alle ids die de app kent (zichtbaar in de agenda): neem een steekproef over alle soorten
  const ids = Object.keys(expect);
  const known = await p.evaluate(()=>{ const out=new Set(); return null });
  let rnd = 7; const rand = ()=>{ rnd=(rnd*1103515245+12345)&0x7fffffff; return rnd/0x7fffffff };
  const sample = ids.filter(()=>rand()<0.045);
  let checked=0, skipped=0, mism=[];
  const stats={link:0,none:0,search:0,skip:0,trailer:0};
  for (const id of sample) {
    await p.evaluate(i=>{ location.hash=i }, id); await p.waitForTimeout(70);
    const r = await p.evaluate(()=>{ const sh=document.querySelector('#detailSheet'); if(!sh.classList.contains('open')) return null;
      const row=[...sh.querySelectorAll('.row2')].find(x=>/Route/.test(x.textContent)); const items=[...row.children].map(c=>({t:c.textContent.replace(/\s+/g,' ').trim(), h:c.getAttribute('href')||'', d:c.disabled===true}));
      return items });
    if (!r) { skipped++; continue; }
    checked++;
    const sp = r.find(x=>/^Spotify/.test(x.t)), yt = r.find(x=>/^(YouTube|Trailer)/.test(x.t));
    const exp = expect[id]; let got;
    if (!sp) got='skip'; else if (sp.d) got='none'; else if (/\/artist\//.test(sp.h)) got='link:'+sp.h.split('/artist/')[1]; else got='search';
    stats[got.startsWith('link')?'link':got]++;
    if (got !== exp.spot) mism.push({id, got, want: exp.spot});
    const wantYt = exp.film ? 'Trailer' : (exp.spot==='skip' ? null : 'YouTube');
    const gotYt = yt ? yt.t.replace(/\s.*/,'') : null;
    if (gotYt !== wantYt) mism.push({id, yt: gotYt, wantYt});
    if (exp.film) stats.trailer++;
    await p.evaluate(()=>document.querySelector('#detailSheet [data-close]').click()); await p.waitForTimeout(40);
  }
  console.log({sample:sample.length, checked, skipped, stats, mismatches: mism.length}); console.log(mism.slice(0,10)); console.log('errors', errs);
  await b.close();
})();
