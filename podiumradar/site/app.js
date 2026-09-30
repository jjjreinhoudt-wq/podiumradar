(async()=>{
/* ---------- DATA ---------- */
let DATA;
try{ DATA=await fetch("data.json",{cache:"no-store"}).then(r=>r.json()); }
catch(e){ document.querySelector("#main").innerHTML='<div class="empty"><strong>De agenda kon niet laden</strong>Controleer je verbinding en ververs de pagina.</div>'; return; }
const V={}, EV=[];
const THEATER_GENRES=new Set(["Cabaret","Comedy","Musical","Toneel","Dans","Opera","Theater","Jeugd"]);
// Soort locatie (uit de bron) -> tabblad in de app
const TYPE_OF={thea:"thea",film:"thea",museum:"expo",festival:"fest"};
const LBL={pop:["concert","concerten"],thea:["voorstelling","voorstellingen"],expo:["tentoonstelling","tentoonstellingen"],fest:["festival","festivals"]};
const today=new Date(); today.setHours(0,0,0,0);
const toMin=t=>t?(+t.slice(0,2))*60+(+t.slice(3,5)):null;
const dayNr=s=>{const [y,m,dd]=s.split("-").map(Number);return Math.round((new Date(y,m-1,dd)-today)/864e5)};
Object.entries(DATA.venues).forEach(([id,v])=>V[id]={id,...v});
DATA.events.forEach(r=>{
  const [y,m,dd]=r.date.split("-").map(Number);
  const endD=r.end?dayNr(r.end):null;
  let d=dayNr(r.date); if((endD??d)<0) return;
  const v=V[r.v]; if(!v) return;
  // Loopt al (tentoonstelling, festival): toon hem vanaf vandaag
  const date=d<0?new Date(today):new Date(y,m-1,dd); const started=d<0; if(d<0) d=0;
  const type=TYPE_OF[v.type]||(THEATER_GENRES.has(r.genre)?"thea":"pop");
  let head=r.title.replace(/\s*\((festival|festival, dag \d)\)$/i,"").split(" - ")[0].trim();
  let acts=head.replace(/^Popronde:\s*/,"").split(/\s\+\s/).map(s=>s.trim());
  const im=r.title.match(/Instore:\s*(.+)$/); if(im) acts=[im[1]];
  const support=(r.support&&r.support.length)?r.support:acts.slice(1);
  EV.push({id:r.id,title:r.title,artist:acts[0],support,v:r.v,genre:r.genre,type,date,d,
    time:toMin(r.time)??toMin(r.start)??toMin(r.doors), doors:toMin(r.doors), start:toMin(r.start),
    url:r.url,isFest:r.id[0]==="f"||type==="fest",status:r.status||null,firstSeen:r.first_seen,
    endD,endDate:r.end?new Date(...r.end.split("-").map((x,i)=>i===1?x-1:+x)):null,started});
});
const SNAPSHOT=(()=>{const [dpart,t]=DATA.updated.split(" ");const [y,m,d]=dpart.split("-").map(Number);return d+" "+["januari","februari","maart","april","mei","juni","juli","augustus","september","oktober","november","december"][m-1]+" om "+t})();
const recent=e=>e.firstSeen&&(today-new Date(e.firstSeen))/864e5<=3;
const artistKey=n=>n.toLowerCase().normalize("NFD").replace(/[\u0300-\u036f]/g,"").replace(/[^a-z0-9]/g,"");
EV.forEach(e=>e.ak=artistKey(e.artist));

/* ---------- PLACES ---------- */
const HOMES={"Tilburg":[51.5555,5.0913],"Breda":[51.5719,4.7683],"Eindhoven":[51.4416,5.4697],"Den Bosch":[51.6978,5.3037],"Helmond":[51.4793,5.6570],"Oss":[51.7650,5.5180],"Bergen op Zoom":[51.4949,4.2911],"Roosendaal":[51.5308,4.4653],"Amsterdam":[52.3676,4.9041],"Utrecht":[52.0907,5.1214],"Rotterdam":[51.9244,4.4777],"Den Haag":[52.0705,4.3007],"Nijmegen":[51.8126,5.8372],"Arnhem":[51.9851,5.8987],"Zwolle":[52.5168,6.0830],"Groningen":[53.2194,6.5665],"Maastricht":[50.8514,5.6910],"Venlo":[51.3704,6.1724]};
function km(a,b,c,d){const R=6371,x=(c-a)*Math.PI/180,y=(d-b)*Math.PI/180;const h=Math.sin(x/2)**2+Math.cos(a*Math.PI/180)*Math.cos(c*Math.PI/180)*Math.sin(y/2)**2;return 2*R*Math.asin(Math.sqrt(h))}
function travel(vid){const v=V[vid], h=S.homeXY; if(v.lat==null) return {car:null,ov:null,k:null}; const k=km(h[0],h[1],v.lat,v.lon);
  if(k<3) return {car:Math.round(k*4+5),ov:Math.round(k*6+8),k};
  return {car:Math.round(k*1.2/90*60+10), ov:Math.round(k*1.35/65*60+20), k}}

/* ---------- STATE ---------- */
const store={get(k,f){try{const v=localStorage.getItem(k);return v?JSON.parse(v):f}catch{return f}},set(k,v){try{localStorage.setItem(k,JSON.stringify(v))}catch{}}};
const S={type:"pop",view:"list",day:-1,q:"",sort:"date",regio:new Set(),venue:"",genre:new Set(),time:"",maxTravel:0,onlyFav:false,
  fav:new Set(store.get("pr_fav2",[])), alarms:store.get("pr_alarms",[]), home:store.get("pr_home","Tilburg"), homeXY:null};
S.homeXY = S.home==="__geo" ? store.get("pr_geo",HOMES.Tilburg) : (HOMES[S.home]||HOMES.Tilburg);
// nieuw-sinds-laatste-bezoek
let seen=store.get("pr_seen",null);
const NEW=new Set();
if(seen===null){ store.set("pr_seen",EV.map(e=>e.id)); } else { const s=new Set(seen); EV.forEach(e=>{ if(!s.has(e.id)) NEW.add(e.id) }); }
function markSeen(){ store.set("pr_seen",EV.map(e=>e.id)); NEW.clear(); render(); }

/* ---------- HELPERS ---------- */
const $=s=>document.querySelector(s);
const esc=s=>String(s).replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const hm=m=>{m=((m%1440)+1440)%1440;return String(Math.floor(m/60)).padStart(2,"0")+":"+String(m%60).padStart(2,"0")};
const WD=["zo","ma","di","wo","do","vr","za"], MON=["jan","feb","mrt","apr","mei","jun","jul","aug","sep","okt","nov","dec"];
const WDL=["zondag","maandag","dinsdag","woensdag","donderdag","vrijdag","zaterdag"];
const dateOf=d=>{const x=new Date(today);x.setDate(today.getDate()+d);return x};
const dayLabel=d=>{const x=dateOf(d);const b=WDL[x.getDay()]+" "+x.getDate()+" "+MON[x.getMonth()]+(x.getFullYear()!==today.getFullYear()?" "+x.getFullYear():"");
  return d===0?"Vandaag, "+b:d===1?"Morgen, "+b:b.charAt(0).toUpperCase()+b.slice(1)};
const short=e=>WD[e.date.getDay()]+" "+e.date.getDate()+" "+MON[e.date.getMonth()];
const dm=x=>x.getDate()+" "+MON[x.getMonth()]+(x.getFullYear()!==today.getFullYear()?" "+x.getFullYear():"");
// Periode-tekst voor tentoonstellingen en meerdaagse festivals
const range=e=>!e.endDate?null:e.started?"t/m "+dm(e.endDate):dm(e.date)+" – "+dm(e.endDate);
const onDay=(e,day)=>e.endD!=null?e.d<=day&&day<=e.endD:e.d===day;
function toast(t){const el=$("#toast");el.textContent=t;el.classList.add("on");clearTimeout(toast.h);toast.h=setTimeout(()=>el.classList.remove("on"),2200)}
const isFav=e=>S.fav.has(e.ak)||e.support.some(s=>S.fav.has(artistKey(s)));
function toggleFav(ak,name){ if(S.fav.has(ak)){S.fav.delete(ak);toast(name+" niet meer gevolgd")} else {S.fav.add(ak);toast("Je volgt nu "+name)}
  store.set("pr_fav2",[...S.fav]); store.set("pr_favnames",Object.assign(store.get("pr_favnames",{}),{[ak]:name})); render(); }
const favName=ak=>store.get("pr_favnames",{})[ak]||(EV.find(e=>e.ak===ak)||{}).artist||ak;
const alarmHit=e=>S.alarms.find(a=>(e.title+" "+V[e.v].name+" "+V[e.v].city).toLowerCase().includes(a.toLowerCase()));

/* timetable: bron geeft één tijd; de rest is een schatting */
function slots(e){
  if(e.time==null) return [];
  const t=e.start??e.time;
  if(e.type==="thea") return [{k:"door",l:"Zaal open",s:e.doors??t-30,e:t,est:e.doors==null},{k:"main",l:"Voorstelling",a:e.artist,s:t,e:t+120,est:false}];
  if(e.genre==="Feest"||(e.genre==="Dance"&&t>=22*60)) return [{k:"main",l:"Feest",a:e.artist,s:t,e:t+240}];
  if(e.isFest) return [{k:"main",l:"Festival",a:e.artist,s:t,e:t+360}];
  const door=e.doors??e.time, out=[{k:"door",l:e.doors!=null?"Deuren open":"Aanvang (bron)",s:door,e:door+30}];
  const sups=e.support.length?e.support:["Voorprogramma (nog niet bekend)"];
  let mainStart=e.start!=null&&e.start>door?e.start:door+30+55*sups.length;
  let c=mainStart-55*sups.length; if(c<door+15) c=door+15;
  sups.forEach(s=>{out.push({k:"sup",l:"Voorprogramma",a:s,s:c,e:c+40,est:true});c+=55});
  out.push({k:"main",l:"Hoofdact",a:e.artist,s:mainStart,e:mainStart+90,est:e.start==null});
  return out;
}
const endOf=e=>{const s=slots(e);return s.length?s[s.length-1].e:null};

function filtered(ignoreDay){
  const q=S.q.trim().toLowerCase();
  let list=EV.filter(e=>{
    if(e.type!==S.type) return false;
    const v=V[e.v];
    if(!ignoreDay&&S.day>=0&&!onDay(e,S.day)) return false;
    if(S.regio.size&&!S.regio.has(v.prov)) return false;
    if(S.venue&&e.v!==S.venue) return false;
    if(S.genre.size&&!S.genre.has(e.genre)) return false;
    if(S.time){ if(e.time==null) return false;
      if(S.time==="mid"&&!(e.time<18*60)) return false;
      if(S.time==="eve"&&!(e.time>=18*60&&e.time<22*60)) return false;
      if(S.time==="late"&&!(e.time>=22*60)) return false; }
    if(S.maxTravel){const c=travel(e.v).car; if(c==null||c>S.maxTravel) return false;}
    if(S.onlyFav&&!isFav(e)) return false;
    if(q&&![e.title,v.name,v.city,e.genre].join(" ").toLowerCase().includes(q)) return false;
    return true;
  });
  const tm=e=>e.time==null?20*60:e.time;
  const cmp={date:(a,b)=>(b.started-a.started)||a.d-b.d||tm(a)-tm(b),
    az:(a,b)=>a.artist.localeCompare(b.artist,"nl")||a.d-b.d,
    venue:(a,b)=>V[a.v].name.localeCompare(V[b.v].name,"nl")||a.d-b.d,
    near:(a,b)=>(travel(a.v).car??999)-(travel(b.v).car??999)||a.d-b.d}[S.sort];
  return list.sort(cmp);
}
function similar(e,n=4){
  if(["Overig","Feest"].includes(e.genre)) return [];
  const seenA=new Set([e.ak]);
  return EV.filter(x=>x.type===e.type&&x.genre===e.genre&&!seenA.has(x.ak)&&(seenA.add(x.ak),true))
    .sort((a,b)=>(travel(a.v).car??999)-(travel(b.v).car??999)||a.d-b.d).slice(0,n);
}

/* ---------- RENDER ---------- */
function renderDates(){
  const ds=[...new Set(EV.filter(e=>e.type===S.type).map(e=>e.d))].sort((a,b)=>a-b).slice(0,70);
  if(S.view==="grid"&&(S.day<0||!ds.includes(S.day))) S.day=ds[0]??0;
  let h=S.view!=="grid"?`<button class="day all" data-d="-1" aria-pressed="${S.day<0}">Alle data</button>`:"";
  ds.forEach(d=>{const x=dateOf(d),we=x.getDay()===5||x.getDay()===6;
    h+=`<button class="day${we?" we":""}" data-d="${d}" aria-pressed="${S.day===d}" aria-label="${dayLabel(d)}"><small>${d===0?"vand.":WD[x.getDay()]}</small><strong>${x.getDate()}</strong><small>${MON[x.getMonth()]}</small></button>`});
  $("#dates").innerHTML=h;
}
const fcount=()=>S.regio.size+S.genre.size+(S.venue?1:0)+(S.time?1:0)+(S.onlyFav?1:0)+(S.maxTravel?1:0);

function evRow(e,o={}){
  const v=V[e.v], tr=travel(e.v);
  const flag=(NEW.has(e.id)||recent(e))?'<span class="new">Nieuw</span>':"";
  return `<div class="ev" role="button" tabindex="0" data-ev="${e.id}">
    ${e.endDate?`<div class="t" style="font-size:13px;line-height:1.2">${e.started?"nu":short(e)}<small>t/m ${dm(e.endDate)}</small></div>`
      :`<div class="t">${e.time==null?"—":hm(e.time)}<small>${o.showDate?short(e):(e.time==null?"tijd volgt":"aanvang")}</small></div>`}
    <div><div class="a">${esc(e.artist)}${flag}</div>
      ${e.support.length?`<div class="s">met ${esc(e.support.join(", "))}</div>`:(e.title!==e.artist&&!e.title.startsWith(e.artist+" +")?`<div class="s">${esc(e.title.slice(e.artist.length).replace(/^\s*-\s*/,""))}</div>`:"")}
      <div class="v">${esc(v.name)}, ${esc(v.city)}</div>
      <div class="tt">${tr.car==null?"reistijd onbekend":"± "+tr.car+" min met de auto"}</div>
      <span class="tag">${esc(e.genre)}</span>${e.status==="sold"?'<span class="tag sold">Uitverkocht</span>':""}${o.reason?`<div class="s" style="margin-top:4px">${esc(o.reason)}</div>`:""}</div>
    <button class="star" data-fav="${e.ak}" data-name="${esc(e.artist)}" aria-pressed="${S.fav.has(e.ak)}" aria-label="Volg ${esc(e.artist)}">★</button>
  </div>`;
}
function emptyState(){return `<div class="empty"><strong>Niets gevonden</strong>Geen ${LBL[S.type][0]} dat bij deze filters past. Kies een andere datum of haal een filter weg.<br><button class="btn ghost" id="clearAll2" style="display:inline-flex;flex:0">Filters wissen</button></div>`}
const srcNote=()=>`<p class="note">Rechtstreeks van de sites van ${Object.keys(V).length} podia, theaters, musea en festivals, bijgewerkt op ${SNAPSHOT}. ${EV.length} items in totaal. Elke nacht komt er nieuwe data bij. Tijden met ~ zijn geschat.</p>`;

function viewList(){
  const list=filtered(false);
  let h=`<div class="meta"><span>${list.length} ${LBL[S.type][1]}</span>${fcount()||S.q?'<button id="clearAll">Alles wissen</button>':""}</div>`;
  if(!list.length) return h+emptyState()+srcNote();
  if(S.sort==="date"){let cur=null; list.slice(0,300).forEach(e=>{const k=e.started&&S.day<0?"nu":e.d; if(k!==cur){cur=k;h+=`<h2 class="dh">${k==="nu"?"Nu te zien":dayLabel(e.d)}</h2>`} h+=evRow(e)}); if(list.length>300) h+=`<p class="note">De eerste 300 van ${list.length} getoond. Kies een datum of filter om verder te kijken.</p>`}
  else list.slice(0,300).forEach(e=>h+=evRow(e,{showDate:true}));
  if(list.length>300) h+=`<p class="note">De eerste 300 van ${list.length} getoond. Verfijn met datum of filters.</p>`;
  return h+srcNote();
}
function viewGrid(){
  const all=filtered(false), list=all.filter(e=>e.time!=null), unk=all.filter(e=>e.time==null);
  let h=`<div class="meta"><span>${dayLabel(S.day)}: ${all.length} ${LBL[S.type][1]}</span></div>`;
  if(!all.length) return h+emptyState();
  if(list.length){
    const from=Math.floor(Math.min(...list.map(e=>e.time-(e.type==="thea"?30:0)))/60)*60;
    const to=Math.ceil(Math.max(...list.map(endOf))/60)*60, hours=Math.max(3,(to-from)/60), px=96/60;
    const byV={}; list.forEach(e=>(byV[e.v]=byV[e.v]||[]).push(e));
    const vids=Object.keys(byV).sort((a,b)=>S.sort==="near"?(travel(a).car??999)-(travel(b).car??999):Math.min(...byV[a].map(e=>e.time))-Math.min(...byV[b].map(e=>e.time))||V[a].name.localeCompare(V[b].name));
    let ruler=""; for(let i=0;i<=hours;i++) ruler+=`<span style="left:${i*96}px">${hm(from+i*60)}</span>`;
    h+=`<div class="grid-wrap"><div class="grid" style="--hours:${hours}"><div class="ruler"><div class="vname"></div><div class="hrs">${ruler}</div></div>`;
    vids.forEach(vid=>{const v=V[vid]; const rows=byV[vid];
      // stack overlapping events at same venue
      const lanes=[]; rows.sort((a,b)=>a.time-b.time).forEach(e=>{const st=slots(e)[0].s;let i=lanes.findIndex(end=>end<=st);if(i<0){i=lanes.length;lanes.push(0)}lanes[i]=endOf(e);e._lane=i});
      h+=`<div class="lane" style="min-height:${Math.max(1,lanes.length)*64+10}px"><div class="vname"><b>${esc(v.name)}</b><small>${esc(v.city)}${travel(vid).car!=null?", ± "+travel(vid).car+" min":""}</small></div><div class="track">`;
      rows.forEach(e=>slots(e).forEach(s=>{
        const left=(s.s-from)*px, w=Math.max(28,(s.e-s.s)*px-3), top=10+e._lane*64;
        const fav=(s.a&&S.fav.has(artistKey(s.a)))?" fav":"";
        h+=`<button class="blk ${s.k}${fav}" style="left:${left}px;width:${w}px;top:${top}px;bottom:auto;height:54px" data-ev="${e.id}" aria-label="${esc((s.a||s.l)+", "+hm(s.s))}">${s.a?`<b>${esc(s.a)}</b>`:""}${hm(s.s)}${s.est?" ~":""}${!s.a&&w>70?"<br>"+s.l:""}</button>`;
      }));
      h+=`</div></div>`;});
    h+=`</div></div><div class="legend"><span><i style="background:var(--acc)"></i>${S.type==="pop"?"Hoofdact / feest":"Voorstelling"}</span>${S.type==="pop"?'<span><i style="background:var(--acc-soft)"></i>Voorprogramma</span>':""}<span><i style="background:repeating-linear-gradient(135deg,var(--line) 0 3px,transparent 3px 6px)"></i>${S.type==="pop"?"Aanvang":"Zaal open"}</span><span><i style="box-shadow:inset 0 0 0 2px var(--star)"></i>Favoriet</span><span>~ = geschatte tijd</span></div>`;
  }
  if(unk.length) h+=`<div class="unk"><h3>Tijd nog niet bekend</h3>${unk.map(e=>evRow(e)).join("")}</div>`;
  return h;
}
function viewFav(){
  let h="";
  const newList=EV.filter(e=>NEW.has(e.id)&&e.type===S.type);
  const newHits=newList.filter(e=>isFav(e)||alarmHit(e));
  if(NEW.size){ h+=`<div class="banner"><strong>${NEW.size} nieuwe shows sinds je laatste bezoek</strong>${newHits.length?`${newHits.length} daarvan passen bij je favorieten of alarmen.`:"Geen daarvan past bij je favorieten of alarmen."}<div style="margin-top:8px"><button class="btn ghost" id="markSeen" style="display:inline-flex;flex:0">Markeer als gezien</button></div></div>`;
    h+=newHits.map(e=>evRow(e,{showDate:true,reason:isFav(e)?"Nieuw van een artiest die je volgt":"Nieuw voor alarm: "+alarmHit(e)})).join(""); }
  // alarmen
  h+=`<h2 class="dh" style="margin-top:18px">Seintjes</h2><p class="s" style="margin:0">Volg artiesten met de ster, of zet een alarm op een naam, podium of stad. Nieuwe shows krijgen hier een melding zodra de agenda is bijgewerkt.</p>
  <div class="alarmrow"><input id="alarmIn" placeholder="Bijv. Froukje, Mezz of Nijmegen" aria-label="Nieuw alarm"><button class="btn" id="alarmAdd">Toevoegen</button></div>
  <div class="favhead">${S.alarms.map((a,i)=>`<span class="favchip">🔔 ${esc(a)}<button data-alarm="${i}" aria-label="Verwijder alarm ${esc(a)}">✕</button></span>`).join("")}</div>`;
  const hits=S.alarms.length?EV.filter(e=>e.type===S.type&&alarmHit(e)).sort((a,b)=>a.d-b.d):[];
  if(hits.length) h+=`<h2 class="dh">Gevonden voor je alarmen <small>${hits.length}</small></h2>`+hits.slice(0,15).map(e=>evRow(e,{showDate:true,reason:"Alarm: "+alarmHit(e)})).join("");
  // favorieten
  const favs=[...S.fav];
  h+=`<h2 class="dh">Artiesten die je volgt</h2>`;
  if(!favs.length) return h+`<div class="empty"><strong>Nog niemand gevolgd</strong>Tik op de ster bij een ${S.type==="pop"?"artiest":LBL[S.type][0]}. Daarna zie je hier hun shows en tips.</div>`;
  h+=`<div class="favhead">${favs.map(ak=>`<span class="favchip">${esc(favName(ak))}<button data-fav="${ak}" data-name="${esc(favName(ak))}" aria-label="Ontvolg">✕</button></span>`).join("")}</div>`;
  const own=EV.filter(e=>e.type===S.type&&isFav(e)).sort((a,b)=>a.d-b.d||(a.time??0)-(b.time??0));
  h+=`<h2 class="dh">Waar ze spelen <small>${own.length}</small></h2>`+(own.length?own.map(e=>evRow(e,{showDate:true})).join(""):`<p class="s">Geen shows in de huidige agenda.</p>`);
  // genre-tips
  const favGenres={}; EV.filter(isFav).forEach(e=>{if(!["Overig","Feest"].includes(e.genre)) favGenres[e.genre]=e.artist});
  const seenA=new Set(favs);
  const recs=EV.filter(e=>e.type===S.type&&favGenres[e.genre]&&!seenA.has(e.ak)&&(seenA.add(e.ak),true)).sort((a,b)=>(travel(a.v).car??999)-(travel(b.v).car??999)||a.d-b.d).slice(0,6);
  h+=`<h2 class="dh">Zelfde genre, dichtbij</h2>`+(recs.length?recs.map(e=>evRow(e,{showDate:true,reason:e.genre+", net als "+favGenres[e.genre]})).join(""):`<p class="s">Volg nog iemand om tips te krijgen.</p>`);
  h+=`<div class="ai" id="aiBox"><strong>Persoonlijk advies van Claude</strong><p>Claude kent de artiesten en kijkt naar wie je volgt. Daarna kiest het uit de hele agenda wat echt bij je past, met uitleg.</p><button class="btn" id="askAI">Vraag advies</button><div id="aiOut"></div></div>`;
  return h;
}
function render(){
  ["thea","expo","fest"].forEach(t=>document.body.classList.toggle(t,S.type===t));
  document.querySelectorAll(".seg [data-type]").forEach(b=>b.setAttribute("aria-pressed",b.dataset.type===S.type));
  document.querySelectorAll("nav.tabs button").forEach(b=>b.dataset.view===S.view?b.setAttribute("aria-current","page"):b.removeAttribute("aria-current"));
  const n=fcount(); $("#fcount").hidden=!n; $("#fcount").textContent=n;
  $("#newDot").hidden=!EV.some(e=>NEW.has(e.id)&&(isFav(e)||alarmHit(e)));
  $("#dates").style.display=S.view==="fav"?"none":"flex";
  renderDates();
  $("#main").innerHTML=S.view==="list"?viewList():S.view==="grid"?viewGrid():viewFav();
  if(S.view==="fav") setupFav();
}

/* ---------- HOME / LOCATION ---------- */
function buildHome(){
  $("#homeSel").innerHTML=(S.home==="__geo"?`<option value="__geo" selected>Mijn locatie</option>`:"")+Object.keys(HOMES).map(c=>`<option${c===S.home?" selected":""}>${c}</option>`).join("");
}
$("#homeSel").onchange=e=>{S.home=e.target.value; if(S.home!=="__geo"){S.homeXY=HOMES[S.home]} store.set("pr_home",S.home); buildHome(); render();};
$("#geoBtn").onclick=()=>{
  if(!navigator.geolocation){toast("Locatie is hier niet beschikbaar. Kies een plaats.");return}
  navigator.geolocation.getCurrentPosition(p=>{S.homeXY=[p.coords.latitude,p.coords.longitude];S.home="__geo";store.set("pr_geo",S.homeXY);store.set("pr_home","__geo");buildHome();render();toast("Reistijden vanaf je locatie")},
    ()=>toast("Locatie niet gedeeld. Kies een plaats in de lijst."),{timeout:8000});
};

/* ---------- FILTER SHEET ---------- */
function buildFilters(){
  const regios=[...new Set(EV.filter(e=>e.type===S.type).map(e=>V[e.v].prov))].sort();
  const genres=[...new Set(EV.filter(e=>e.type===S.type).map(e=>e.genre))].sort((a,b)=>a.localeCompare(b,"nl"));
  const chip=(on,val,lab)=>`<button class="chip" data-val="${esc(val)}" aria-pressed="${on}">${esc(lab)}</button>`;
  $("#fSort").innerHTML=[["date","Datum"],["az","Artiest A–Z"],["venue","Podium A–Z"],["near","Dichtstbij"]].map(([k,l])=>chip(S.sort===k,k,l)).join("");
  $("#fTravel").innerHTML=[[0,"Alles"],[30,"30 min"],[45,"45 min"],[60,"1 uur"],[90,"1,5 uur"]].map(([k,l])=>chip(S.maxTravel===k,k,l)).join("");
  $("#fRegio").innerHTML=regios.map(r=>chip(S.regio.has(r),r,r)).join("");
  $("#fGenre").innerHTML=genres.map(g=>chip(S.genre.has(g),g,g)).join("");
  $("#fTime").innerHTML=[["","Alles"],["mid","Middag"],["eve","Avond"],["late","Nacht (na 22:00)"]].map(([k,l])=>chip(S.time===k,k,l)).join("");
  const vs=[...new Set(EV.filter(e=>e.type===S.type).map(e=>e.v))].map(id=>V[id]).filter(v=>!S.regio.size||S.regio.has(v.prov)).sort((a,b)=>a.name.localeCompare(b.name,"nl"));
  $("#fVenue").innerHTML=`<option value="">Alle podia</option>`+vs.map(v=>`<option value="${v.id}"${S.venue===v.id?" selected":""}>${esc(v.name)} (${esc(v.city)})</option>`).join("");
  $("#fOnlyFav").checked=S.onlyFav;
}
function openSheet(id){$("#scrim").classList.add("open");$(id).classList.add("open")}
function closeSheets(){$("#scrim").classList.remove("open");document.querySelectorAll(".sheet").forEach(s=>s.classList.remove("open"))}
$("#openFilters").onclick=()=>{buildFilters();openSheet("#filterSheet")};
$("#scrim").onclick=closeSheets;
$("#applyF").onclick=()=>{closeSheets();render()};
function resetFilters(){S.regio.clear();S.genre.clear();S.venue="";S.time="";S.onlyFav=false;S.sort="date";S.maxTravel=0}
$("#resetF").onclick=()=>{resetFilters();buildFilters()};
$("#filterSheet").addEventListener("click",e=>{
  const c=e.target.closest(".chip"); if(!c) return; const val=c.dataset.val, box=c.parentElement.id;
  if(box==="fSort") S.sort=val;
  if(box==="fTravel") S.maxTravel=+val;
  if(box==="fTime") S.time=val;
  if(box==="fRegio"){S.regio.has(val)?S.regio.delete(val):S.regio.add(val); if(S.venue&&S.regio.size&&!S.regio.has(V[S.venue].prov)) S.venue=""}
  if(box==="fGenre") S.genre.has(val)?S.genre.delete(val):S.genre.add(val);
  buildFilters();
});
$("#fVenue").onchange=e=>S.venue=e.target.value;
$("#fOnlyFav").onchange=e=>S.onlyFav=e.target.checked;

/* ---------- DETAIL ---------- */
function openDetail(id){
  const e=EV.find(x=>x.id===id), v=V[e.v], tr=travel(e.v);
  const sl=slots(e);
  const tl=sl.length?sl.map(s=>`<div class="slot${s.k==="main"?" key":""}"><time>${hm(s.s)}</time>${s.a?`<strong>${esc(s.a)}</strong> <span class="s">${s.l.toLowerCase()}</span>`:esc(s.l)} ${s.est?'<span class="est">geschat</span>':""}</div>`).join("")
    :`<p class="s">De tijden zijn nog niet bekend bij de bron. Check de pagina van het podium.</p>`;
  const sims=similar(e);
  $("#detailSheet").innerHTML=`<div class="grab"></div>
   <div class="dhead"><div><div class="dsub">${range(e)?(e.started?"Nu te zien, ":"")+range(e):dayLabel(e.d)}</div><div class="dtitle">${esc(e.artist)}</div>
     ${e.title!==e.artist?`<div class="dsub">${esc(e.title)}</div>`:""}
     <div class="dsub">${esc(v.name)}, ${esc(v.city)}</div></div>
     <button class="star" data-fav="${e.ak}" data-name="${esc(e.artist)}" aria-pressed="${S.fav.has(e.ak)}" aria-label="Volg ${esc(e.artist)}" style="font-size:30px">★</button></div>
   <div class="facts"><div><small>Genre</small><b>${esc(e.genre)}</b></div>${tr.car!=null?`<div><small>Auto</small><b>± ${tr.car} min</b></div><div><small>OV</small><b>± ${tr.ov} min</b></div>`:""}${e.status==="sold"?`<div><small>Kaarten</small><b style="color:var(--warn)">Uitverkocht</b></div>`:""}</div>
   <div class="timeline">${tl}</div>
   <div class="row2"><a class="btn" href="${esc(e.url)}" target="_blank" rel="noopener">Info en kaarten</a></div>
   <div class="row2" style="margin-top:10px">${e.time!=null?`<button class="btn ghost" id="icsBtn">Zet in agenda</button><a class="btn ghost" id="gcal" target="_blank" rel="noopener">Google Agenda</a>`:`<p class="s">Agenda-knop verschijnt zodra de tijd bekend is.</p>`}</div>
   <p class="note">Kaartstatus en prijs staan op de pagina van de bron; die wisselen te snel voor een momentopname.</p>
   <h3>Vergelijkbaar en dichtbij</h3>
   <div class="simlist">${sims.length?sims.map(o=>`<div class="ev" role="button" tabindex="0" data-ev="${o.id}"><div><div class="a">${esc(o.artist)}</div><div class="v">${short(o)}, ${esc(V[o.v].name)} ${travel(o.v).car!=null?"(± "+travel(o.v).car+" min)":""}</div></div><button class="star" data-fav="${o.ak}" data-name="${esc(o.artist)}" aria-pressed="${S.fav.has(o.ak)}" aria-label="Volg ${esc(o.artist)}">★</button></div>`).join(""):'<p class="s">Geen genre-match in de huidige agenda.</p>'}</div>
   <div class="ai" id="simAI" hidden><strong>Wie lijkt hierop?</strong><p>Claude noemt vergelijkbare artiesten en checkt of die in de agenda staan.</p><button class="btn" id="askSim">Vraag Claude</button><div id="simOut"></div></div>`;
  if(e.time!=null){ $("#gcal").href=gcalUrl(e); $("#icsBtn").onclick=()=>saveIcs(e); }
  if(sample){ $("#simAI").hidden=false; $("#askSim").onclick=()=>askSimilar(e); }
  openSheet("#detailSheet"); $("#detailSheet").scrollTop=0;
}
function dt(e,min){const x=new Date(e.date);x.setMinutes(min);return x}
const utc=x=>x.toISOString().replace(/[-:]/g,"").replace(/\.\d{3}/,"");
const descr=e=>slots(e).map(s=>hm(s.s)+" "+(s.a||s.l)+(s.est?" (geschat)":"")).join("\n")+"\n\n"+e.url;
function gcalUrl(e){const v=V[e.v];return "https://calendar.google.com/calendar/render?action=TEMPLATE&text="+encodeURIComponent(e.artist+" @ "+v.name)+"&dates="+utc(dt(e,e.time))+"/"+utc(dt(e,endOf(e)))+"&location="+encodeURIComponent(v.name+", "+v.city)+"&details="+encodeURIComponent(descr(e))}
let downloads=null, sample=null;
async function saveIcs(e){
  const v=V[e.v], tr=travel(e.v);
  const ics=["BEGIN:VCALENDAR","VERSION:2.0","PRODID:-//Podiumradar//NL","BEGIN:VEVENT","UID:"+e.id+"@podiumradar","DTSTAMP:"+utc(new Date()),
    "DTSTART:"+utc(dt(e,e.time)),"DTEND:"+utc(dt(e,endOf(e))),"SUMMARY:"+e.artist+" @ "+v.name,"LOCATION:"+v.name+"\\, "+v.city,"URL:"+e.url,
    "DESCRIPTION:"+descr(e).replace(/\n/g,"\\n"),"BEGIN:VALARM","TRIGGER:-PT"+((tr.car||30)+30)+"M","ACTION:DISPLAY","DESCRIPTION:Vertrekken naar "+e.artist,"END:VALARM","END:VEVENT","END:VCALENDAR"].join("\r\n");
  if(!downloads){const a=document.createElement("a");a.href=URL.createObjectURL(new Blob([ics],{type:"text/calendar"}));a.download=e.artist.replace(/[^\w\- ]/g,"")+".ics";document.body.appendChild(a);a.click();a.remove();toast("Agendabestand gedownload, met vertrekherinnering");return}
  try{await downloads.save({filename:e.artist.replace(/[^\w\- ]/g,"")+".ics",data:new Blob([ics],{type:"text/calendar"})});toast("Agendabestand klaar, met vertrekherinnering")}
  catch(err){if(err&&err.code==="unavailable"){downloads=null;window.open(gcalUrl(e),"_blank","noopener")}}
}

/* ---------- CLAUDE ---------- */
const errCopy=c=>c==="rate_limited"?"Even te veel verzoeken. Probeer het over een minuut opnieuw.":"Het advies lukte niet. Probeer het nog eens.";
async function askSimilar(e){
  const out=$("#simOut"), btn=$("#askSim"); btn.disabled=true; out.innerHTML="<p>Bezig met nadenken…</p>";
  const names=[...new Set(EV.filter(x=>x.type===e.type).map(x=>x.artist))];
  try{
    const r=await sample.json(`Artiest: "${e.artist}" (${e.genre}). Noem 6 artiesten die hierop lijken. Geef ook aan welke namen uit deze agenda-lijst erop lijken: ${JSON.stringify(names)}. Antwoord in het Nederlands met alleen JSON: {"lijkt_op":[{"naam":"","waarom":"korte zin"}],"in_agenda":["exacte naam uit de lijst"]}`,{modelTier:"quick"});
    const inAg=(r.in_agenda||[]).map(n=>EV.filter(x=>x.artist===n&&x.type===e.type).sort((a,b)=>a.d-b.d)[0]).filter(Boolean);
    out.innerHTML=(r.lijkt_op||[]).map(x=>`<p><strong>${esc(x.naam)}</strong>: ${esc(x.waarom)}</p>`).join("")+(inAg.length?`<p><strong>Staat in de agenda:</strong></p>`+inAg.map(x=>evRow(x,{showDate:true})).join(""):"");
  }catch(err){ if(err&&err.code==="not_granted"){ $("#simAI").hidden=true; sample=null } else out.innerHTML=`<p>${errCopy(err&&err.code)}</p>` }
  finally{ btn.disabled=false }
}
function setupFav(){
  const add=()=>{const v=$("#alarmIn").value.trim(); if(!v) return; if(!S.alarms.includes(v)) S.alarms.push(v); store.set("pr_alarms",S.alarms); toast("Alarm gezet voor "+v); render();};
  $("#alarmAdd").onclick=add; $("#alarmIn").onkeydown=e=>{if(e.key==="Enter") add()};
  const ms=$("#markSeen"); if(ms) ms.onclick=markSeen;
  const box=$("#aiBox"); if(!box) return;
  if(!sample){box.style.display="none";return}
  $("#askAI").onclick=async()=>{
    const out=$("#aiOut"), btn=$("#askAI"); btn.disabled=true; out.innerHTML="<p>Bezig met nadenken…</p>";
    const favs=[...S.fav].map(favName);
    const pool=EV.filter(e=>e.type===S.type&&!isFav(e)).slice(0,250).map(e=>({id:e.id,t:e.title,g:e.genre,p:V[e.v].name,dag:short(e),auto_min:travel(e.v).car}));
    try{
      const res=await sample.json(`Je bent een Nederlandse muziek- en theaterkenner en geeft persoonlijk uitgaansadvies.
De gebruiker volgt: ${JSON.stringify(favs)}. Alarmen: ${JSON.stringify(S.alarms)}.
Agenda: ${JSON.stringify(pool)}
Kies de 5 shows die het best passen bij deze smaak (gebruik je kennis van de artiesten, niet alleen het genre). Houd rekening met reistijd. Antwoord met alleen JSON: [{"id":"p123","waarom":"één korte zin"}]`,{modelTier:"default"});
      const picks=(Array.isArray(res)?res:[]).map(p=>({e:EV.find(x=>x.id===p.id),w:p.waarom})).filter(p=>p.e);
      out.innerHTML=picks.length?picks.map(p=>evRow(p.e,{showDate:true,reason:p.w})).join(""):"<p>Geen duidelijke match. Volg nog een artiest.</p>";
    }catch(err){ if(err&&err.code==="not_granted"){box.style.display="none";sample=null} else out.innerHTML=`<p>${errCopy(err&&err.code)}</p>` }
    finally{btn.disabled=false}
  };
}

/* ---------- EVENTS ---------- */
document.addEventListener("click",e=>{
  const f=e.target.closest("[data-fav]"); if(f){e.stopPropagation(); const ak=f.dataset.fav; toggleFav(ak,f.dataset.name||favName(ak));
    document.querySelectorAll(`#detailSheet [data-fav="${ak}"]`).forEach(b=>b.setAttribute("aria-pressed",S.fav.has(ak))); return}
  const al=e.target.closest("[data-alarm]"); if(al){S.alarms.splice(+al.dataset.alarm,1);store.set("pr_alarms",S.alarms);render();return}
  const ev=e.target.closest("[data-ev]"); if(ev){openDetail(ev.dataset.ev);return}
  const d=e.target.closest(".day"); if(d){S.day=+d.dataset.d;render();return}
  const t=e.target.closest("nav.tabs button"); if(t){S.view=t.dataset.view;render();try{window.scrollTo(0,0)}catch{};return}
  if(e.target.id==="clearAll"||e.target.id==="clearAll2"){resetFilters();S.q="";$("#q").value="";if(S.view!=="grid")S.day=-1;render()}
});
document.addEventListener("keydown",e=>{if(e.key==="Escape")closeSheets();if(e.key==="Enter"&&e.target.matches(".ev[data-ev]"))openDetail(e.target.dataset.ev)});
document.querySelectorAll(".seg [data-type]").forEach(b=>b.onclick=()=>{S.type=b.dataset.type;S.genre.clear();S.venue="";if(S.view!=="grid")S.day=-1;render()});
let qt;$("#q").oninput=e=>{clearTimeout(qt);qt=setTimeout(()=>{S.q=e.target.value;render()},150)};

buildHome(); render();
if(window.claude&&claude.use){
  claude.use("sample").then(s=>{sample=s;if(S.view==="fav")render()}).catch(()=>{});
  claude.use("downloads").then(d=>{downloads=d}).catch(()=>{});
}
})();
