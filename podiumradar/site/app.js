(async()=>{
/* ---------- DATA ---------- */
let DATA;
// "no-cache": altijd bij de server navragen, maar onveranderde data komt uit de browsercache (304), dus geen 700 KB per bezoek
try{ DATA=await fetch("data.json",{cache:"no-cache"}).then(r=>r.json()); }
catch(e){ document.querySelector("#main").innerHTML='<div class="empty"><strong>De agenda kon niet laden</strong>Controleer je verbinding en ververs de pagina.</div>'; return; }
const V={}, EV=[];
const THEATER_GENRES=new Set(["Cabaret","Comedy","Musical","Toneel","Dans","Opera","Theater","Jeugd"]);
// Soort locatie (uit de bron) -> tabblad in de app
const TYPE_OF={thea:"thea",film:"film",museum:"expo",festival:"fest"};
// Kids: alles wat voor kinderen/gezinnen is, over alle soorten heen (herkend aan titel en genre)
const KIDS_WORDS=/kinder(?!loos|achtig)|\bkids?\b|familie(voorstelling|concert|film|dag|theater|middag|musical|tour|tentoonstelling|programma|zondag|weekend|activiteit|vertelling)|familietheater|voor (het hele )?gezin|gezinsvoorstelling|\bjeugd(theater|voorstelling|film|concert|orkest)|peuter|kleuter|\bjunior|voorlees|poppenkast|poppentheater|sprookje|sinterklaas|\bsint\b|nijntje|dikkie dik|kikker|buurman en buurman|pieter post|paw patrol|k3\b|samson|bumba|woezel|pip|minoes|pluk van de petteflet|jip en janneke|taartrovers|cinemini|kidsclub|kinderfeest|schoolvoorstelling|nederlandse versie|nl versie|\(nl\)|2d nl|nl gesproken|nederlands gesproken/i;
const ageOf=t=>{const m=String(t).match(/\(?\b(\d{1,2})\s*\+\)?|\bvanaf\s+(\d{1,2})\s+jaar/i);return m?+(m[1]||m[2]):null};
function isKids(title,genre){const a=ageOf(title); if(a!=null) return a<=12; if(/\b(16|18)\s*\+|\bvolwassen/i.test(title)) return false;
  return KIDS_WORDS.test(title)}  // genre "Jeugd" alleen niet genoeg: dat komt soms van "familie" in een titel
const LBL={kids:["activiteit voor kinderen","activiteiten voor kinderen"],pop:["concert","concerten"],thea:["voorstelling","voorstellingen"],film:["filmvoorstelling","filmvoorstellingen"],expo:["tentoonstelling","tentoonstellingen"],fest:["festival","festivals"]};
const today=new Date(); today.setHours(0,0,0,0);
const toMin=t=>t?(+t.slice(0,2))*60+(+t.slice(3,5)):null;
const dayNr=s=>{const [y,m,dd]=s.split("-").map(Number);return Math.round((new Date(y,m-1,dd)-today)/864e5)};
// Prijs (optioneel): laagste prijs in euro, 0 = gratis, ontbreekt = onbekend
const priceOf=p=>typeof p==="number"&&isFinite(p)&&p>=0&&p<10000?Math.round(p*100)/100:null;
// Echte settijden (optioneel): [{a:"Naam",s:"20:30"}]; na middernacht telt door (00:30 -> 24:30)
function timesOf(t){
  if(!Array.isArray(t)) return null;
  const out=[]; t.forEach(x=>{ if(!x||typeof x.a!=="string"||!x.a.trim()||typeof x.s!=="string") return;
    const m=x.s.trim().match(/^(\d{1,2})[:.](\d{2})$/); if(!m||+m[1]>29||+m[2]>59) return;
    let s=(+m[1])*60+(+m[2]); if(out.length&&s<out[0].s-6*60) s+=1440; out.push({a:x.a.trim(),s}) });
  return out.length?out.sort((a,b)=>a.s-b.s):null;
}
Object.entries(DATA.venues).forEach(([id,v])=>V[id]={id,...v});
const filmSeen=new Set();
DATA.events.forEach(r=>{
  const [y,m,dd]=r.date.split("-").map(Number);
  const endD=r.end?dayNr(r.end):null;
  let d=dayNr(r.date); if((endD??d)<0) return;
  const v=V[r.v]; if(!v) return;
  // Loopt al (tentoonstelling, festival): toon hem vanaf vandaag
  const date=d<0?new Date(today):new Date(y,m-1,dd); const started=d<0; if(d<0) d=0;
  // Films bij podia, theaters en musea (Cacaofabriek, Melkweg, Chassé, Eye...) horen bij Film; filmfestivals blijven festivals
  // Exposities bij theaters en podia (Chassé, Tolhuistuin, De Doelen...) horen bij Musea
  const type=r.genre==="Film"&&v.type!=="festival"?"film":r.genre==="Tentoonstelling"&&v.type!=="festival"?"expo":TYPE_OF[v.type]||(THEATER_GENRES.has(r.genre)?"thea":"pop");
  // Zelfde voorstelling via de podiumagenda én de filmagenda van hetzelfde huis: één keer tonen
  if(type==="film"){const k=[v.name.toLowerCase(),r.date,r.time,r.title.toLowerCase().replace(/[^a-z0-9]/g,"")].join("|"); if(filmSeen.has(k)) return; filmSeen.add(k)}
  let head=r.title.replace(/\s*\((festival|festival, dag \d)\)$/i,"").split(" - ")[0].trim();
  let acts=head.replace(/^Popronde:\s*/,"").split(/\s\+\s/).map(s=>s.trim());
  const im=r.title.match(/Instore:\s*(.+)$/); if(im) acts=[im[1]];
  const support=(r.support&&r.support.length)?r.support:acts.slice(1);
  EV.push({id:r.id,title:r.title,artist:acts[0],support,v:r.v,genre:r.genre,type,date,d,
    time:toMin(r.time)??toMin(r.start)??toMin(r.doors), doors:toMin(r.doors), start:toMin(r.start),
    // alleen echte webadressen als link (geen javascript:-links uit een bron)
    url:/^https?:\/\//i.test(r.url||"")?r.url:"#",isFest:r.id[0]==="f"||type==="fest",status:r.status||null,firstSeen:r.first_seen,
    dur:r.dur||null,kids:!!r.kids||isKids(r.title,r.genre),endD,endDate:r.end?new Date(...r.end.split("-").map((x,i)=>i===1?x-1:+x)):null,started,
    rawDate:r.date, price:priceOf(r.price), times:timesOf(r.times)});
});
const SNAPSHOT=(()=>{const [dpart,t]=DATA.updated.split(" ");const [y,m,d]=dpart.split("-").map(Number);return d+" "+["januari","februari","maart","april","mei","juni","juli","augustus","september","oktober","november","december"][m-1]+" om "+t})();
const recent=e=>e.firstSeen&&(today-new Date(e.firstSeen))/864e5<=3;
const artistKey=n=>n.toLowerCase().normalize("NFD").replace(/[\u0300-\u036f]/g,"").replace(/[^a-z0-9]/g,"");
EV.forEach(e=>{e.ak=artistKey(e.artist); if(e.time==null&&e.times) e.time=e.times[0].s});

/* ---------- PLACES ---------- */
const HOMES={"Tilburg":[51.5555,5.0913],"Breda":[51.5719,4.7683],"Eindhoven":[51.4416,5.4697],"Den Bosch":[51.6978,5.3037],"Helmond":[51.4793,5.6570],"Oss":[51.7650,5.5180],"Bergen op Zoom":[51.4949,4.2911],"Roosendaal":[51.5308,4.4653],"Amsterdam":[52.3676,4.9041],"Utrecht":[52.0907,5.1214],"Rotterdam":[51.9244,4.4777],"Den Haag":[52.0705,4.3007],"Nijmegen":[51.8126,5.8372],"Arnhem":[51.9851,5.8987],"Zwolle":[52.5168,6.0830],"Groningen":[53.2194,6.5665],"Maastricht":[50.8514,5.6910],"Venlo":[51.3704,6.1724]};
function km(a,b,c,d){const R=6371,x=(c-a)*Math.PI/180,y=(d-b)*Math.PI/180;const h=Math.sin(x/2)**2+Math.cos(a*Math.PI/180)*Math.cos(c*Math.PI/180)*Math.sin(y/2)**2;return 2*R*Math.asin(Math.sqrt(h))}
function travel(vid){const v=V[vid], h=S.homeXY; if(v.lat==null) return {car:null,ov:null,k:null}; const k=km(h[0],h[1],v.lat,v.lon);
  if(k<3) return {car:Math.round(k*4+5),ov:Math.round(k*6+8),k};
  return {car:Math.round(k*1.2/90*60+10), ov:Math.round(k*1.35/65*60+20), k}}

/* ---------- STATE ---------- */
const store={get(k,f){try{const v=localStorage.getItem(k);return v?JSON.parse(v):f}catch{return f}},set(k,v){try{localStorage.setItem(k,JSON.stringify(v))}catch{}}};
const S={type:"pop",view:"list",day:-1,month:"",q:"",sort:"date",regio:new Set(),venue:"",genre:new Set(),time:"",maxTravel:0,onlyFav:false,
  fav:new Set(store.get("pr_fav2",[])), favV:new Set(store.get("pr_favv",[])), onlyFree:false, vmode:store.get("pr_vmode","list")==="map"?"map":"list", alarms:store.get("pr_alarms",[]), home:store.get("pr_home","Tilburg"), homeXY:null,
  // Uitgevinkte steden en podia (blijven bewaard): niets van tonen
  hideC:new Set(store.get("pr_hideC",[])), hideV:new Set(store.get("pr_hideV",[]))};
const saveHidden=()=>{store.set("pr_hideC",[...S.hideC]);store.set("pr_hideV",[...S.hideV])};
const hiddenLoc=vid=>{const v=V[vid];return S.hideV.has(vid)||(v&&S.hideC.has(cityKey(v.city)))};
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
// Maanden: sleutel "2026-11", als dagnummers (t.o.v. vandaag) [eerste, laatste dag]
const MONL=["januari","februari","maart","april","mei","juni","juli","augustus","september","oktober","november","december"];
const mKey=x=>x.getFullYear()+"-"+String(x.getMonth()+1).padStart(2,"0");
const mRange=k=>{const [y,m]=k.split("-").map(Number);return [Math.round((new Date(y,m-1,1)-today)/864e5),Math.round((new Date(y,m,0)-today)/864e5)]};
const inMonth=(e,r)=>e.d<=r[1]&&(e.endD??e.d)>=r[0];
const monthLabel=k=>{const [y,m]=k.split("-").map(Number);return MONL[m-1]+(y!==today.getFullYear()?" "+y:"")};
const cap=t=>t.charAt(0).toUpperCase()+t.slice(1);
const nf=n=>n.toLocaleString("nl-NL");
const short=e=>WD[e.date.getDay()]+" "+e.date.getDate()+" "+MON[e.date.getMonth()];
const dm=x=>x.getDate()+" "+MON[x.getMonth()]+(x.getFullYear()!==today.getFullYear()?" "+x.getFullYear():"");
// Periode-tekst voor tentoonstellingen en meerdaagse festivals
const range=e=>!e.endDate?null:e.started?"t/m "+dm(e.endDate):dm(e.date)+" – "+dm(e.endDate);
const onDay=(e,day)=>e.endD!=null?e.d<=day&&day<=e.endD:e.d===day;
function toast(t){const el=$("#toast");el.textContent=t;el.classList.add("on");clearTimeout(toast.h);toast.h=setTimeout(()=>el.classList.remove("on"),2200)}
const isFav=e=>S.fav.has(e.ak)||e.support.some(s=>S.fav.has(artistKey(s)));
function toggleFav(ak,name){ if(S.fav.has(ak)){S.fav.delete(ak);toast(name+" niet meer gevolgd")} else {S.fav.add(ak);toast("Je volgt nu "+name)}
  store.set("pr_fav2",[...S.fav]); store.set("pr_favnames",Object.assign(store.get("pr_favnames",{}),{[ak]:name})); render(); }
/* Podia volgen: sleutel = VG-key (naam|stad) */
function toggleFavV(key,name){ if(S.favV.has(key)){S.favV.delete(key);toast(name+" niet meer gevolgd")} else {S.favV.add(key);toast("Je volgt nu "+name)}
  store.set("pr_favv",[...S.favV]); render(); }
const isFavV=e=>S.favV.has(vgOf(e.v));
const priceTxt=p=>p==null?"":p===0?"Gratis":"€ "+(Number.isInteger(p)?String(p):p.toFixed(2).replace(".",","));
const KIND={pop:"Concert",thea:"Theater",film:"Film",expo:"Museum",fest:"Festival"};
const favName=ak=>store.get("pr_favnames",{})[ak]||(EV.find(e=>e.ak===ak)||{}).artist||ak;
// Films tussen muziek/theater/festivals zijn standaard verborgen ("Toon films" in de filters); het tabblad Film toont ze altijd
const inTab=e=>S.type==="kids"?e.kids:e.type===S.type;
const alarmHit=e=>S.alarms.find(a=>(e.title+" "+V[e.v].name+" "+V[e.v].city).toLowerCase().includes(a.toLowerCase()));

/* timetable: bron geeft één tijd; de rest is een schatting */
function slots(e){
  // Echte settijden van het podium: die gebruiken, niets schatten
  if(e.times){
    const T=e.times, fi=T.findIndex(x=>artistKey(x.a)===e.ak), main=fi<0?T.length-1:fi;
    const out=e.doors!=null&&e.doors<T[0].s?[{k:"door",l:"Deuren open",s:e.doors,e:Math.min(e.doors+30,T[0].s),est:false}]:[];
    T.forEach((x,i)=>{const nx=T[i+1]; const end=nx?Math.max(x.s+15,nx.s-5):x.s+(i===main?90:45);
      out.push({k:i===main?"main":"sup",l:i===main?"Hoofdact":i<main?"Voorprogramma":"Daarna",a:x.a,s:x.s,e:i===main&&!nx?x.s+90:Math.min(end,x.s+(i===main?120:75)),est:false})});
    return out;
  }
  if(e.time==null) return [];
  const t=e.start??e.time;
  if(e.type==="film") return [{k:"main",l:"Film",a:e.artist,s:t,e:t+(e.dur||120),est:!e.dur}];
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

function filtered(ignoreDay,ignoreMonth){
  const q=S.q.trim().toLowerCase(), mr=!ignoreDay&&!ignoreMonth&&S.day<0&&S.month?mRange(S.month):null;
  let list=EV.filter(e=>{
    if(!inTab(e)) return false;
    const v=V[e.v];
    if(!ignoreDay&&S.day>=0&&!onDay(e,S.day)) return false;
    if(mr&&!inMonth(e,mr)) return false;
    if(S.regio.size&&!S.regio.has(v.prov)) return false;
    if(S.venue&&e.v!==S.venue) return false;
    if(e.v!==S.venue&&hiddenLoc(e.v)) return false;
    if(S.genre.size&&!S.genre.has(e.genre)) return false;
    if(S.time){ if(e.time==null) return false;
      if(S.time==="mid"&&!(e.time<18*60)) return false;
      if(S.time==="eve"&&!(e.time>=18*60&&e.time<22*60)) return false;
      if(S.time==="late"&&!(e.time>=22*60)) return false; }
    if(S.maxTravel){const c=travel(e.v).car; if(c==null||c>S.maxTravel) return false;}
    if(S.onlyFav&&!isFav(e)&&!isFavV(e)) return false;
    if(S.onlyFree&&e.price!==0) return false;
    if(q&&![e.title,v.name,v.city,e.genre].join(" ").toLowerCase().includes(q)) return false;
    return true;
  });
  const tm=e=>e.time==null?20*60:e.time;
  // Eigen stad altijd bovenaan (per dag bij sorteren op datum)
  const own=(a,b)=>inCity(b.v)-inCity(a.v);
  const cmp={date:(a,b)=>(b.started-a.started)||a.d-b.d||own(a,b)||tm(a)-tm(b),
    az:(a,b)=>own(a,b)||a.artist.localeCompare(b.artist,"nl")||a.d-b.d,
    venue:(a,b)=>own(a,b)||V[a.v].name.localeCompare(V[b.v].name,"nl")||a.d-b.d,
    near:(a,b)=>(travel(a.v).car??999)-(travel(b.v).car??999)||a.d-b.d}[S.sort];
  return list.sort(cmp);
}
// Ligt deze locatie in de gekozen stad? Op naam van de plaats; bij "Mijn locatie" binnen 5 km.
const CITY_ALIAS={"den bosch":"s hertogenbosch","s hertogenbosch":"s hertogenbosch","den haag":"s gravenhage","s gravenhage":"s gravenhage"};
const cityKey=c=>{const k=String(c||"").toLowerCase().normalize("NFD").replace(/[̀-ͯ]/g,"").replace(/[^a-z]+/g," ").trim();return CITY_ALIAS[k]||k};
const inCity=vid=>{const v=V[vid]; if(!v) return false; if(S.home==="__geo"){const k=travel(vid).k; return k!=null&&k<5}
  return cityKey(v.city)===cityKey(S.home)};
function similar(e,n=4){
  if(["Overig","Feest"].includes(e.genre)) return [];
  const seenA=new Set([e.ak]);
  return EV.filter(x=>x.type===e.type&&x.genre===e.genre&&!seenA.has(x.ak)&&(seenA.add(x.ak),true))
    .sort((a,b)=>(travel(a.v).car??999)-(travel(b.v).car??999)||a.d-b.d).slice(0,n);
}

/* ---------- RENDER ---------- */
function renderDates(){
  const ds=[...new Set(EV.filter(e=>inTab(e)).map(e=>e.d))].sort((a,b)=>a-b).slice(0,70);
  if(S.view==="grid"&&(S.day<0||!ds.includes(S.day))){S.day=ds[0]??0;S.month=""}
  let h=S.view!=="grid"?`<button class="day all" data-d="-1" aria-pressed="${S.day<0}">Alle data</button>`:"";
  let pm=ds.length?dateOf(ds[0]).getMonth():null;
  ds.forEach(d=>{const x=dateOf(d),we=x.getDay()===5||x.getDay()===6;
    if(x.getMonth()!==pm){pm=x.getMonth();h+=`<span class="mlab" aria-hidden="true">${MON[pm]}</span>`}
    h+=`<button class="day${we?" we":""}" data-d="${d}" aria-pressed="${S.day===d}" aria-label="${dayLabel(d)}"><small>${d===0?"vand.":WD[x.getDay()]}</small><strong>${x.getDate()}</strong><small>${MON[x.getMonth()]}</small></button>`});
  $("#dates").innerHTML=h;
}
const fcount=()=>S.regio.size+S.genre.size+(S.venue?1:0)+(S.time?1:0)+(S.onlyFav?1:0)+(S.onlyFree?1:0)+(S.maxTravel?1:0);
const hidNote=()=>{const n=S.hideC.size+S.hideV.size; if(!n) return "";
  const parts=[S.hideC.size?`${S.hideC.size} ${S.hideC.size===1?"stad":"steden"}`:"",S.hideV.size?`${S.hideV.size} ${S.hideV.size===1?"podium":"podia"}`:""].filter(Boolean);
  return ` · <button id="showHidden">${parts.join(" en ")} verborgen, toon</button>`};

function evRow(e,o={}){
  const v=V[e.v], tr=travel(e.v);
  const flag=(NEW.has(e.id)||recent(e))?'<span class="new">Nieuw</span>':"";
  // o.kind: kleur en label per soort (lijsten over alle tabbladen heen)
  const kind=o.kind&&KIND[e.type]?` style="--acc:var(--${e.type});--acc-soft:var(--${e.type}-soft)"`:"";
  return `<div class="ev" role="button" tabindex="0" data-ev="${e.id}"${kind}>
    ${e.endDate?`<div class="t" style="font-size:13px;line-height:1.2">${e.started?"nu":short(e)}<small>t/m ${dm(e.endDate)}</small></div>`
      :`<div class="t">${e.time==null?"—":hm(e.time)}<small>${o.showDate?short(e):(e.time==null?"tijd volgt":"aanvang")}</small></div>`}
    <div><div class="a">${esc(e.artist)}${flag}</div>
      ${e.support.length?`<div class="s">met ${esc(e.support.join(", "))}</div>`:(e.title!==e.artist&&!e.title.startsWith(e.artist+" +")?`<div class="s">${esc(e.title.slice(e.artist.length).replace(/^\s*-\s*/,""))}</div>`:"")}
      <div class="v">${esc(v.name)}, ${esc(v.city)}</div>
      <div class="tt">${tr.car==null?"reistijd onbekend":"± "+tr.car+" min met de auto"}</div>
      ${kind?`<span class="tag kind">${KIND[e.type]}</span>`:""}${kind&&e.genre===KIND[e.type]?"":`<span class="tag">${esc(e.genre)}</span>`}${e.price!=null?`<span class="tag price${e.price===0?" free":""}">${priceTxt(e.price)}</span>`:""}${e.status==="sold"?'<span class="tag sold">Uitverkocht</span>':""}${o.reason?`<div class="s" style="margin-top:4px">${esc(o.reason)}</div>`:""}</div>
    <button class="star" data-fav="${e.ak}" data-name="${esc(e.artist)}" aria-pressed="${S.fav.has(e.ak)}" aria-label="Volg ${esc(e.artist)}">★</button>
  </div>`;
}
function emptyState(){
  if(S.onlyFree&&!EV.some(e=>e.price===0&&inTab(e))) return `<div class="empty"><strong>Nog geen gratis ${LBL[S.type][1]} bekend</strong>Prijzen komen rechtstreeks van de sites van de podia en staan nog niet bij elk item. Zet 'Alleen gratis' uit om alles te zien.<br><button class="btn ghost" id="freeOff" style="display:inline-flex;flex:0">Toon ook betaald</button></div>`;
  return `<div class="empty"><strong>Niets gevonden</strong>Geen ${LBL[S.type][0]} dat bij deze filters past. Kies een andere datum of haal een filter weg.<br><button class="btn ghost" id="clearAll2" style="display:inline-flex;flex:0">Filters wissen</button></div>`}
const srcNote=()=>`<p class="note">Rechtstreeks van de sites van ${Object.keys(V).length} podia, theaters, musea en festivals, bijgewerkt op ${SNAPSHOT}. ${EV.length} items in totaal. Elke nacht komt er nieuwe data bij. Tijden met ~ zijn geschat. De site van het podium is altijd leidend. <a href="over.html">Over Podiumradar, privacy en contact</a></p>`;

/* Lijst met kopjes per dag (en per maand); wat vóór `from` begon of al loopt staat bovenaan onder één kopje */
function dayRows(list,n,o){
  let h="",cur=null,curM=null;
  if(o.month){curM=o.month;h+=`<h2 class="mh">${cap(monthLabel(o.month))}</h2>`}
  list.slice(0,n).forEach(e=>{const door=e.started||e.d<o.from, k=door?"door":e.d;
    if(k!==cur){cur=k;
      if(!door&&o.months){const m=mKey(e.date); if(m!==curM){curM=m;h+=`<h2 class="mh">${cap(monthLabel(m))}</h2>`}}
      h+=`<h2 class="dh">${door?o.door:dayLabel(e.d)}</h2>`}
    h+=evRow(e)});
  return h;
}
// Aantal per maand (alleen bij Alle data): [["2026-10",812],...]
function monthCounts(all){
  const last=all.reduce((m,e)=>Math.max(m,e.endD??e.d),0), out=[];
  for(let i=0;i<18;i++){const x=new Date(today.getFullYear(),today.getMonth()+i,1); if(i&&(x-today)/864e5>last) break;
    const k=mKey(x), r=mRange(k), n=all.filter(e=>inMonth(e,r)).length; if(n||k===S.month) out.push([k,n])}
  if(S.month&&!out.some(([k])=>k===S.month)) out.push([S.month,0]);
  return out;
}
function monthBar(mc){
  if(S.day>=0||(mc.length<2&&!S.month)) return "";
  const lab=k=>{const [y,m]=k.split("-").map(Number);return MON[m-1]+(y!==today.getFullYear()?" ’"+String(y).slice(2):"")};
  return `<div class="months" role="group" aria-label="Maand"><button class="chip" data-month="" aria-pressed="${!S.month}">Alle maanden</button>${mc.map(([k,n])=>`<button class="chip" data-month="${k}" aria-pressed="${S.month===k}" aria-label="${monthLabel(k)}, ${n}">${lab(k)}<small>${nf(n)}</small></button>`).join("")}</div>`;
}
// Hoeveel kaarten de lijst toont; begint opnieuw bij 300 zodra datum, maand, zoekterm of filters veranderen
const LIM={n:300,sig:""};
function viewList(){
  const list=filtered(false), month=S.day<0&&S.month?S.month:"", mr=month?mRange(month):null;
  const mc=S.day<0?monthCounts(month?filtered(false,true):list):[];
  const sig=[S.type,S.day,month,S.q,S.sort,S.venue,S.time,S.maxTravel,S.onlyFav,S.onlyFree,[...S.genre],[...S.regio],S.hideC.size,S.hideV.size].join("|");
  if(sig!==LIM.sig){LIM.sig=sig;LIM.n=300}
  const n=LIM.n;
  let h=tonightCta()+monthBar(mc)+`<div class="meta"><span>${nf(list.length)} ${LBL[S.type][list.length===1?0:1]}${month?" in "+monthLabel(month):""}${hidNote()}</span>${fcount()||S.q?'<button id="clearAll">Alles wissen</button>':""}</div>`;
  if(!list.length){const alt=month&&mc.find(([k,c])=>c&&k!==month);
    return h+(alt?`<div class="empty"><strong>Niets in ${monthLabel(month)}</strong>Wel in andere maanden, bijvoorbeeld ${monthLabel(alt[0])} (${nf(alt[1])}).<br><button class="btn ghost" data-month="${alt[0]}" style="display:inline-flex;flex:0">Toon ${monthLabel(alt[0])}</button> <button class="btn ghost" data-month="" style="display:inline-flex;flex:0">Alle maanden</button></div>`:emptyState())+srcNote()}
  if(S.sort==="date"){
    const from=S.day>=0?S.day:mr?Math.max(0,mr[0]):0;
    h+=dayRows(list,n,{from,months:S.day<0,month,door:from===0?"Nu te zien":S.day>=0?"Loopt al, ook te zien op deze dag":"Al begonnen, loopt nog"});
  }
  else list.slice(0,n).forEach(e=>h+=evRow(e,{showDate:true}));
  if(list.length>n) h+=`<button class="btn ghost more" id="moreBtn">Toon meer <small>nog ${nf(list.length-n)}</small></button>`;
  else if(month){const i=mc.findIndex(([k])=>k===month), nx=mc.slice(i+1).find(([,c])=>c); if(nx) h+=`<button class="btn ghost more" data-month="${nx[0]}" data-month-top>Verder in ${monthLabel(nx[0])} ›</button>`}
  return h+srcNote();
}
/* ---------- VANAVOND IN DE BUURT (alle soorten samen) ---------- */
const TN={when:"today",max:[15,30,45].includes(store.get("pr_tnmax",30))?store.get("pr_tnmax",30):30,kinds:new Set(Object.keys(KIND))};
const nowMin=()=>{const n=new Date();return n.getHours()*60+n.getMinutes()};
// Dit weekend: vrijdag t/m zondag; is het al vr/za/zo, dan vanaf vandaag
const weekend=()=>{const wd=today.getDay(); return wd===0?[0,0]:wd>=5?[0,7-wd]:[5-wd,7-wd]};
function tonightList(when=TN.when){
  const [a,b]=when==="today"?[0,0]:weekend(), nm=nowMin(), q=S.q.trim().toLowerCase();
  const timed=[], period=[];
  EV.forEach(e=>{
    if(!TN.kinds.has(e.type)||hiddenLoc(e.v)) return;
    if(e.endD!=null){ if(e.d>b||e.endD<a) return; }
    else { if(e.d<a||e.d>b) return;
      // vandaag: alleen wat nog moet beginnen of nog bezig is
      if(e.d===0&&e.time!=null&&(endOf(e)??e.time+120)<=nm) return; }
    const c=travel(e.v).car; if(c==null||c>TN.max) return;
    if(q&&![e.title,V[e.v].name,V[e.v].city,e.genre].join(" ").toLowerCase().includes(q)) return;
    (e.endD!=null?period:timed).push(e);
  });
  timed.sort((x,y)=>x.d-y.d||(x.time??1e4)-(y.time??1e4)||(travel(x.v).car??999)-(travel(y.v).car??999));
  period.sort((x,y)=>(travel(x.v).car??999)-(travel(y.v).car??999)||x.d-y.d);
  return {timed,period};
}
function viewTonight(){
  const {timed,period}=tonightList(), nm=nowMin(), wk=TN.when!=="today";
  const home=S.home==="__geo"?"je locatie":S.home;
  const chip=(attr,val,on,lab,style="")=>`<button class="chip" ${attr}="${val}" aria-pressed="${on}"${style}>${lab}</button>`;
  let h=`<div class="meta"><button data-view-go="list">‹ Agenda</button></div>
    <div class="vhead"><h1>${wk?"Dit weekend":"Vanavond"} in de buurt</h1><div class="s">Alles binnen ${TN.max} min rijden vanaf ${esc(home)}, over alle soorten heen${wk?"":", vanaf nu"}.</div></div>
    <div class="tnbar"><div class="chips">${chip("data-tn-when","today",!wk,"Vandaag")+chip("data-tn-when","weekend",wk,"Dit weekend")}</div>
    <div class="chips">${[15,30,45].map(m=>chip("data-tn-max",m,TN.max===m,m+" min")).join("")}</div></div>
    <div class="chips tnkinds">${Object.entries(KIND).map(([k,l])=>chip("data-tn-kind",k,TN.kinds.has(k),l,` style="--acc:var(--${k})"`)).join("")}</div>
    <div class="meta"><span>${timed.length} met een tijd${period.length?`, ${period.length} doorlopend`:""}${hidNote()}</span></div>`;
  if(!timed.length&&!period.length) return h+`<div class="empty"><strong>Niets gevonden</strong>Niets meer binnen ${TN.max} min ${wk?"dit weekend":"vandaag"}. Kies een grotere afstand${wk?"":" of Dit weekend"}.</div>`;
  let cur=null;
  timed.slice(0,250).forEach(e=>{ if(wk&&e.d!==cur){cur=e.d;h+=`<h2 class="dh">${dayLabel(e.d)}</h2>`}
    const busy=e.d===0&&e.time!=null&&e.time<=nm;
    h+=evRow(e,{kind:true,reason:busy?"Al begonnen, nog bezig":""}) });
  if(timed.length>250) h+=`<p class="note">De eerste 250 van ${timed.length} getoond. Kies een kleinere afstand of zet soorten uit.</p>`;
  if(period.length) h+=`<details class="tnper"${timed.length?"":" open"}><summary>Tentoonstellingen en festivals die nu lopen <small>${period.length}</small></summary><p class="s">Check de openingstijden op de site; musea zijn 's avonds meestal dicht.</p>${period.slice(0,150).map(e=>evRow(e,{kind:true})).join("")}</details>`;
  return h;
}
function tonightCta(){
  if(S.day>0) return "";
  const {timed}=tonightList("today");
  return `<button class="tncta" data-view-go="tonight"><svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><path d="M20 14.5A8 8 0 1 1 9.5 4a6.5 6.5 0 0 0 10.5 10.5z"/></svg><span><b>Vanavond in de buurt</b><small>${timed.length} ${timed.length===1?"ding":"dingen"} binnen ${TN.max} min, alle soorten samen</small></span><i aria-hidden="true">›</i></button>`;
}
function viewGrid(){
  const all=filtered(false), list=all.filter(e=>e.time!=null), unk=all.filter(e=>e.time==null);
  let h=`<div class="meta"><span>${dayLabel(S.day)}: ${all.length} ${LBL[S.type][all.length===1?0:1]}${hidNote()}</span></div>`;
  if(!all.length) return h+emptyState();
  if(list.length){
    const from=Math.floor(Math.min(...list.map(e=>e.time-(e.type==="thea"?30:0)))/60)*60;
    const to=Math.ceil(Math.max(...list.map(endOf))/60)*60, hours=Math.max(3,(to-from)/60), px=96/60;
    const byV={}; list.forEach(e=>(byV[e.v]=byV[e.v]||[]).push(e));
    const vids=Object.keys(byV).sort((a,b)=>S.sort==="near"?(travel(a).car??999)-(travel(b).car??999):inCity(b)-inCity(a)||Math.min(...byV[a].map(e=>e.time))-Math.min(...byV[b].map(e=>e.time))||V[a].name.localeCompare(V[b].name));
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
  const newList=EV.filter(e=>NEW.has(e.id)&&inTab(e));
  const newHits=newList.filter(e=>isFav(e)||alarmHit(e));
  // nieuw bij gevolgde podia staat hieronder per podium (alle tabbladen), niet nog eens in deze lijst
  const newV=S.favV.size?EV.filter(e=>NEW.has(e.id)&&isFavV(e)).length:0;
  if(NEW.size){ h+=`<div class="banner"><strong>${NEW.size} nieuwe shows sinds je laatste bezoek</strong>${newHits.length?`${newHits.length} daarvan passen bij je favorieten of alarmen.`:"Geen daarvan past bij je favoriete artiesten of alarmen."}${newV?` ${newV} nieuw bij podia die je volgt (zie hieronder).`:""}<div style="margin-top:8px"><button class="btn ghost" id="markSeen" style="display:inline-flex;flex:0">Markeer als gezien</button></div></div>`;
    h+=newHits.map(e=>evRow(e,{showDate:true,reason:isFav(e)?"Nieuw van een artiest die je volgt":"Nieuw voor alarm: "+alarmHit(e)})).join(""); }
  // alarmen
  h+=`<h2 class="dh" style="margin-top:18px">Seintjes</h2><p class="s" style="margin:0">Volg artiesten met de ster, of zet een alarm op een naam, podium of stad. Nieuwe shows krijgen hier een melding zodra de agenda is bijgewerkt.</p>
  <div class="alarmrow"><input id="alarmIn" placeholder="Bijv. Froukje, Mezz of Nijmegen" aria-label="Nieuw alarm"><button class="btn" id="alarmAdd">Toevoegen</button></div>
  <div class="favhead">${S.alarms.map((a,i)=>`<span class="favchip">🔔 ${esc(a)}<button data-alarm="${i}" aria-label="Verwijder alarm ${esc(a)}">✕</button></span>`).join("")}</div>`;
  const hits=S.alarms.length?EV.filter(e=>inTab(e)&&alarmHit(e)).sort((a,b)=>a.d-b.d):[];
  if(hits.length) h+=`<h2 class="dh">Gevonden voor je alarmen <small>${hits.length}</small></h2>`+hits.slice(0,15).map(e=>evRow(e,{showDate:true,reason:"Alarm: "+alarmHit(e)})).join("");
  // gevolgde podia: eerstvolgende items en wat nieuw is sinds je laatste bezoek (alle tabbladen samen)
  h+=`<h2 class="dh">Podia die je volgt${S.favV.size?` <small>${S.favV.size}</small>`:""}</h2>`;
  const fv=VG.filter(g=>S.favV.has(g.key)).sort((a,b)=>a.name.localeCompare(b.name,"nl"));
  if(!fv.length) h+=`<p class="s" style="margin:0">Tik op de ster bij een podium (onder Podia) om het te volgen. Je ziet dan hier wat er binnenkort is en wat er nieuw bij is gekomen.</p>`;
  fv.forEach(g=>{
    const all=EV.filter(e=>g.ids.has(e.v)).sort((a,b)=>(b.started-a.started)||a.d-b.d||(a.time??1440)-(b.time??1440));
    const nw=all.filter(e=>NEW.has(e.id)), next=all.filter(e=>!NEW.has(e.id)).slice(0,3);
    h+=`<div class="vfav"><div class="vfavh"><button class="linkbtn" data-openvenue="${esc(g.key)}">${esc(g.name)}</button><span class="s">${esc(g.city)} · ${all.length} op de agenda${nw.length?` · <b class="newtxt">${nw.length} nieuw</b>`:""}</span>${vStar(g)}</div>`+
      nw.slice(0,5).map(e=>evRow(e,{showDate:true,reason:"Nieuw sinds je laatste bezoek"})).join("")+
      (nw.length>5?`<p class="s"><button class="linkbtn" data-openvenue="${esc(g.key)}">Nog ${nw.length-5} nieuw, bekijk alles</button></p>`:"")+
      next.map(e=>evRow(e,{showDate:true})).join("")+(all.length?"":`<p class="s">Nu niets op de agenda.</p>`)+`</div>`});
  // favorieten
  const favs=[...S.fav];
  h+=`<h2 class="dh">Artiesten die je volgt</h2>`;
  if(!favs.length) return h+`<div class="empty"><strong>Nog niemand gevolgd</strong>Tik op de ster bij een ${S.type==="pop"?"artiest":LBL[S.type][0]}. Daarna zie je hier hun shows en tips.</div>`;
  h+=`<div class="favhead">${favs.map(ak=>`<span class="favchip">${esc(favName(ak))}<button data-fav="${ak}" data-name="${esc(favName(ak))}" aria-label="Ontvolg">✕</button></span>`).join("")}</div>`;
  const own=EV.filter(e=>inTab(e)&&isFav(e)).sort((a,b)=>a.d-b.d||(a.time??0)-(b.time??0));
  h+=`<h2 class="dh">Waar ze spelen <small>${own.length}</small></h2>`+(own.length?own.map(e=>evRow(e,{showDate:true})).join(""):`<p class="s">Geen shows in de huidige agenda.</p>`);
  // genre-tips
  const favGenres={}; EV.filter(isFav).forEach(e=>{if(!["Overig","Feest"].includes(e.genre)) favGenres[e.genre]=e.artist});
  const seenA=new Set(favs);
  const recs=EV.filter(e=>inTab(e)&&favGenres[e.genre]&&!seenA.has(e.ak)&&(seenA.add(e.ak),true)).sort((a,b)=>(travel(a.v).car??999)-(travel(b.v).car??999)||a.d-b.d).slice(0,6);
  h+=`<h2 class="dh">Zelfde genre, dichtbij</h2>`+(recs.length?recs.map(e=>evRow(e,{showDate:true,reason:e.genre+", net als "+favGenres[e.genre]})).join(""):`<p class="s">Volg nog iemand om tips te krijgen.</p>`);
  h+=meldBox();
  h+=`<div class="ai" id="aiBox"><strong>Persoonlijk advies van Claude</strong><p>Claude kent de artiesten en kijkt naar wie je volgt. Daarna kiest het uit de hele agenda wat echt bij je past, met uitleg.</p><button class="btn" id="askAI">Vraag advies</button><div id="aiOut"></div></div>`;
  return h;
}
/* ---------- PODIA ---------- */
// Eén regel per podium; zelfde naam en stad (bv. podium + eigen filmzaal) samen
const VKIND={pop:"Poppodium",concert:"Concertzaal",arena:"Arena",cafe:"Café",thea:"Theater",film:"Bioscoop / filmhuis",museum:"Museum",festival:"Festival"};
const VGROUPS=[{k:"",l:"Alles"},{k:"muz",l:"Muziek",t:["pop","concert","arena","cafe"]},{k:"thea",l:"Theater",t:["thea"]},{k:"film",l:"Film",t:["film"]},{k:"museum",l:"Musea",t:["museum"]},{k:"festival",l:"Festivals",t:["festival"]}];
const VG=(()=>{const m={}; EV.forEach(e=>{const v=V[e.v]; const k=(v.name+"|"+v.city).toLowerCase();
  const g=m[k]||(m[k]={key:k,name:v.name,city:v.city,type:v.type,ids:new Set(),n:0,next:null}); g.ids.add(e.v); g.n++;
  if(!g.next||e.d<g.next.d) g.next=e}); return Object.values(m)})();
const vgOf=vid=>{const v=V[vid]; return (v.name+"|"+v.city).toLowerCase()};
const VCOL={pop:"pop",concert:"pop",arena:"pop",cafe:"pop",thea:"thea",film:"film",museum:"expo",festival:"fest"};
const vStar=(g,big)=>`<button class="star${big?" big":""}" data-favv="${esc(g.key)}" data-name="${esc(g.name)}" aria-pressed="${S.favV.has(g.key)}" aria-label="Volg podium ${esc(g.name)}">★</button>`;
function venueList(){
  const q=S.q.trim().toLowerCase(), grp=VGROUPS.find(x=>x.k===S.vkind)||VGROUPS[0];
  return VG.filter(g=>(!grp.t||grp.t.includes(g.type))&&(!q||(g.name+" "+g.city).toLowerCase().includes(q)))
    .sort((a,b)=>(travel([...a.ids][0]).car??9999)-(travel([...b.ids][0]).car??9999)||a.name.localeCompare(b.name,"nl"));
}
function viewVenues(){
  if(S.venuePage){
    const g=VG.find(x=>x.key===S.venuePage); if(!g){S.venuePage=null;return viewVenues()}
    const tr=travel([...g.ids][0]);
    const list=EV.filter(e=>g.ids.has(e.v)).sort((a,b)=>(b.started-a.started)||a.d-b.d||(a.time??1440)-(b.time??1440));
    let h=`<div class="meta"><button data-vback>‹ Alle podia</button></div>
      <div class="vhead"><div class="dhead"><h1>${esc(g.name)}</h1>${vStar(g,true)}</div><div class="s">${esc(g.city)} · ${esc(VKIND[g.type]||"")}${tr.car!=null?` · ± ${tr.car} min met de auto`:""}</div>
      <div class="s">${list.length} op de agenda${S.favV.has(g.key)?" · je volgt dit podium":""}</div></div>`;
    return h+dayRows(list,400,{from:0,months:true,door:"Nu te zien"});
  }
  const list=venueList(), map=S.vmode==="map";
  let h=`<div class="vbar"><div class="chips vkinds">${VGROUPS.map(x=>`<button class="chip" data-vkind="${x.k}" aria-pressed="${x.k===(S.vkind||"")}">${x.l}</button>`).join("")}</div>
    <div class="seg vmode" role="group" aria-label="Weergave podia"><button data-vmode="list" aria-pressed="${!map}">Lijst</button><button data-vmode="map" aria-pressed="${map}">Kaart</button></div></div>
    <div class="meta"><span>${list.length} ${list.length===1?"podium":"podia"}${map?"":", dichtstbij eerst"}</span></div>`;
  if(!list.length) return h+`<div class="empty"><strong>Geen podium gevonden</strong>Zoek op een andere naam of stad.</div>`;
  if(map) return h+`<div class="mapbox" id="mapbox"><p class="s" style="padding:16px">Kaart laden…</p></div>`;
  list.slice(0,300).forEach(g=>{const tr=travel([...g.ids][0]);
    h+=`<div class="ev venue" role="button" tabindex="0" data-venue="${esc(g.key)}" style="--acc:var(--${VCOL[g.type]||"pop"});--acc-soft:var(--${VCOL[g.type]||"pop"}-soft)"><div class="t" style="font-size:15px">${g.n}<small>op agenda</small></div>
      <div><div class="a">${esc(g.name)}</div><div class="v">${esc(g.city)} · ${esc(VKIND[g.type]||"")}</div>
      <div class="tt">${tr.car==null?"reistijd onbekend":"± "+tr.car+" min met de auto"}${g.next?` · eerstvolgend ${g.next.started?"nu":short(g.next)}: ${esc(g.next.artist)}`:""}</div></div>${vStar(g)}</div>`});
  return h;
}

/* ---------- KAART (eigen SVG, geen kaarttegels van buiten) ---------- */
let NL=null, nlLoad=null;
const MAPV={vb:null};
const proj=(lat,lon)=>[(lon-NL.lon0)*NL.cos*NL.k,(NL.lat0-lat)*NL.k];
function drawMap(){
  const box=$("#mapbox"); if(!box) return;
  if(!NL){
    if(!nlLoad) nlLoad=fetch("nl.json").then(r=>{if(!r.ok) throw new Error("kaart"); return r.json()}).then(j=>{NL=j}).catch(()=>{nlLoad=null});
    const p=nlLoad; p.then(()=>{ if(NL) drawMap(); else { const b=$("#mapbox"); if(b) b.innerHTML='<p class="s" style="padding:16px">De kaart kon niet laden. Probeer het opnieuw of kies Lijst.</p>' } });
    return; }
  if(!MAPV.vb) MAPV.vb=[0,0,NL.w,NL.h];
  const list=venueList().filter(g=>V[[...g.ids][0]].lat!=null).sort((a,b)=>b.n-a.n);
  const pts=list.map(g=>{const v=V[[...g.ids][0]]; const [x,y]=proj(v.lat,v.lon); return {g,x,y,r:Math.min(13,3+Math.sqrt(g.n)*0.8)}});
  // Podia op (bijna) hetzelfde punt (vaak het stadscentrum) een klein beetje uit elkaar zetten, zodat ze bij inzoomen los te tikken zijn
  const same={}; pts.forEach(p=>{const k=Math.round(p.x/1.5)+"|"+Math.round(p.y/1.5); const i=same[k]=(same[k]||0)+1;
    if(i>1){const a=i*2.39996, d=1.6*Math.sqrt(i-1); p.x+=Math.cos(a)*d; p.y+=Math.sin(a)*d}});
  const [hx,hy]=proj(S.homeXY[0],S.homeXY[1]);
  const homeName=S.home==="__geo"?"Mijn locatie":S.home, f1=x=>x.toFixed(1);
  box.innerHTML=`<svg id="nlmap" viewBox="${MAPV.vb.join(" ")}" preserveAspectRatio="xMidYMid meet" role="img" aria-label="Kaart van Nederland met ${pts.length} podia">
    <rect x="-3000" y="-3000" width="7000" height="7000" class="m-sea"/>
    <path d="${NL.nb}" class="m-nb"/>
    ${NL.prov.map(p=>`<path d="${p.d}" class="m-land"/>`).join("")}
    <path d="${NL.inner}" class="m-prov"/>
    <g id="mdots">${pts.map(p=>`<circle cx="${f1(p.x)}" cy="${f1(p.y)}" data-r="${f1(p.r)}" data-venue="${esc(p.g.key)}" class="m-dot${S.favV.has(p.g.key)?" fav":""}" style="fill:var(--${VCOL[p.g.type]||"pop"})"><title>${esc(p.g.name)}, ${esc(p.g.city)}: ${p.g.n} op de agenda</title></circle>`).join("")}</g>
    <g id="mlabels">${pts.map(p=>`<text x="${f1(p.x)}" y="${f1(p.y)}" data-r="${f1(p.r)}" class="m-lbl">${esc(p.g.name)}</text>`).join("")}</g>
    <g class="m-home"><circle cx="${f1(hx)}" cy="${f1(hy)}" id="mhome"/><text x="${f1(hx)}" y="${f1(hy)}" id="mhomeT">${esc(homeName)}</text></g>
  </svg>
  <div class="mapbtns"><button data-zoom="in" aria-label="Inzoomen">+</button><button data-zoom="out" aria-label="Uitzoomen">−</button><button data-zoom="home" aria-label="Naar je vertrekpunt">◎</button><button data-zoom="all" aria-label="Heel Nederland">NL</button></div>`;
  if(!$("#maplegend")) box.insertAdjacentHTML("afterend",`<div class="legend" id="maplegend"><span><i class="dot" style="background:var(--pop)"></i>Muziek</span><span><i class="dot" style="background:var(--thea)"></i>Theater</span><span><i class="dot" style="background:var(--film)"></i>Film</span><span><i class="dot" style="background:var(--expo)"></i>Musea</span><span><i class="dot" style="background:var(--fest)"></i>Festivals</span><span><i class="dot home"></i>Vertrekpunt</span></div><p class="note">Grotere stip = meer op de agenda. Tik op een stip voor het programma; zoom met de knoppen, knijpen of het scrollwiel. Kaart: Natural Earth (publiek domein), op je eigen toestel getekend: er gaat niets naar een kaartdienst.</p>`);
  setupMap();
}
function mapGeom(){const r=$("#nlmap").getBoundingClientRect(), vb=MAPV.vb, upp=Math.max(vb[2]/r.width,vb[3]/r.height);
  return {r,upp,ox:(r.width-vb[2]/upp)/2,oy:(r.height-vb[3]/upp)/2}}
function toMap(cx,cy){const {r,upp,ox,oy}=mapGeom(), vb=MAPV.vb; return [vb[0]+(cx-r.left-ox)*upp, vb[1]+(cy-r.top-oy)*upp]}
// Nieuwe grootte w,h zó dat kaartpunt A onder schermpunt (cx,cy) blijft
function setView(w,h,A,cx,cy){
  const min=30, max=NL.w*1.3; if(w<min){h*=min/w;w=min} if(w>max){h*=max/w;w=max}
  const vb=MAPV.vb; vb[2]=w; vb[3]=h;
  if(A){const {r,upp,ox,oy}=mapGeom(); vb[0]=A[0]-(cx-r.left-ox)*upp; vb[1]=A[1]-(cy-r.top-oy)*upp}
  // niet helemaal van de kaart af schuiven
  vb[0]=Math.min(Math.max(vb[0],-w*0.7),NL.w-w*0.3); vb[1]=Math.min(Math.max(vb[1],-h*0.7),NL.h-h*0.3);
  applyView();
}
function applyView(){
  const svg=$("#nlmap"); if(!svg) return; svg.setAttribute("viewBox",MAPV.vb.map(x=>x.toFixed(1)).join(" "));
  const {upp}=mapGeom(), z=NL.w/MAPV.vb[2];
  // stippen houden op het scherm ongeveer dezelfde grootte (iets groter bij inzoomen)
  const f=upp*Math.min(1.7,0.9+z*0.1);
  svg.querySelectorAll("#mdots circle").forEach(c=>{c.setAttribute("r",(+c.dataset.r*f).toFixed(2));c.style.strokeWidth=(1.2*upp).toFixed(2)});
  const showL=z>=3; svg.querySelector("#mlabels").style.display=showL?"":"none";
  if(showL){
    // namen alleen waar ze niet over een andere naam vallen (grootste podia eerst)
    const placed=[], vb=MAPV.vb;
    svg.querySelectorAll("#mlabels text").forEach(t=>{
      const x=+t.getAttribute("x")+(+t.dataset.r*f+3*upp), y=+t.getAttribute("y"), w=t.textContent.length*7*upp, h=14*upp;
      const inView=x<vb[0]+vb[2]&&x+w>vb[0]&&y>vb[1]&&y<vb[1]+vb[3];
      const free=inView&&!placed.some(b=>x<b[0]+b[2]&&x+w>b[0]&&y-h/2<b[1]+b[3]&&y+h/2>b[1]);
      t.style.display=free?"":"none"; if(!free) return; placed.push([x,y-h/2,w,h]);
      t.setAttribute("font-size",(12*upp).toFixed(2));t.setAttribute("dx",(+t.dataset.r*f+3*upp).toFixed(2));t.setAttribute("dy",(4*upp).toFixed(2));t.style.strokeWidth=(3*upp).toFixed(2)});
  }
  const hc=$("#mhome"); hc.setAttribute("r",(7*upp).toFixed(2)); hc.style.strokeWidth=(3*upp).toFixed(2);
  const ht=$("#mhomeT"); ht.setAttribute("font-size",(12*upp).toFixed(2)); ht.setAttribute("dx",(10*upp).toFixed(2)); ht.setAttribute("dy",(-9*upp).toFixed(2)); ht.style.strokeWidth=(3*upp).toFixed(2);
  svg.querySelectorAll(".m-prov,.m-land,.m-nb").forEach(p=>p.style.strokeWidth=(p.classList.contains("m-prov")?0.8:1)*upp);
}
function zoomBy(f,cx,cy){const r=$("#nlmap").getBoundingClientRect(); if(cx==null){cx=r.left+r.width/2;cy=r.top+r.height/2}
  setView(MAPV.vb[2]*f,MAPV.vb[3]*f,toMap(cx,cy),cx,cy)}
function zoomTo(x,y,w){const h=w*NL.h/NL.w; MAPV.vb=[x-w/2,y-h/2,w,h]; setView(w,h)}
function setupMap(){
  const svg=$("#nlmap"); applyView();
  const P=new Map(); let g=null;
  const start=moved=>{const ps=[...P.values()];
    if(ps.length===1) g={one:true,A:toMap(ps[0].x,ps[0].y),x0:ps[0].x,y0:ps[0].y,moved};
    else if(ps.length>=2){const mx=(ps[0].x+ps[1].x)/2,my=(ps[0].y+ps[1].y)/2; g={one:false,A:toMap(mx,my),d0:Math.hypot(ps[0].x-ps[1].x,ps[0].y-ps[1].y)||1,w0:MAPV.vb[2],h0:MAPV.vb[3],moved:true}}
    else g=null};
  svg.addEventListener("pointerdown",e=>{ if(e.pointerType==="mouse"&&e.button!==0) return; if(e.isPrimary) P.clear(); P.set(e.pointerId,{x:e.clientX,y:e.clientY}); start(!!(g&&g.moved)) });
  svg.addEventListener("pointermove",e=>{ if(!P.has(e.pointerId)||!g) return; P.set(e.pointerId,{x:e.clientX,y:e.clientY}); const ps=[...P.values()];
    if(g.one){ if(!g.moved&&Math.hypot(e.clientX-g.x0,e.clientY-g.y0)<6) return; if(!g.moved) try{svg.setPointerCapture(e.pointerId)}catch{} g.moved=true; svg.classList.add("dragging"); setView(MAPV.vb[2],MAPV.vb[3],g.A,e.clientX,e.clientY) }
    else if(ps.length>=2){const mx=(ps[0].x+ps[1].x)/2,my=(ps[0].y+ps[1].y)/2, d=Math.hypot(ps[0].x-ps[1].x,ps[0].y-ps[1].y)||1; setView(g.w0*g.d0/d,g.h0*g.d0/d,g.A,mx,my)}
    e.preventDefault()});
  const end=e=>{ if(!P.has(e.pointerId)) return;
    // tik met vinger/pen op een stip: meteen openen (niet wachten op een klik die na slepen soms uitblijft)
    if(e.type==="pointerup"&&e.pointerType!=="mouse"&&g&&g.one&&!g.moved&&P.size===1){const t=e.target.closest&&e.target.closest("[data-venue]");
      if(t){P.clear(); g=null; noClickUntil=Date.now()+350; S.venuePage=t.dataset.venue; render(); try{window.scrollTo(0,0)}catch{}; return}}
    P.delete(e.pointerId); svg.classList.remove("dragging");
    if(g&&g.moved) noClickUntil=Date.now()+80; if(P.size) start(true); else g=null };
  svg.addEventListener("pointerup",end); svg.addEventListener("pointercancel",end);
  svg.addEventListener("wheel",e=>{e.preventDefault(); zoomBy(Math.exp(Math.max(-1,Math.min(1,e.deltaY/(e.deltaMode?3:100)))*0.35),e.clientX,e.clientY)},{passive:false});
}

function render(){
  ["thea","film","expo","fest","kids"].forEach(t=>document.body.classList.toggle(t,S.type===t));
  document.querySelectorAll(".seg [data-type]").forEach(b=>b.setAttribute("aria-pressed",b.dataset.type===S.type));
  const navV=S.view==="tonight"?"list":S.view;
  document.querySelectorAll("nav.tabs button").forEach(b=>b.dataset.view===navV?b.setAttribute("aria-current","page"):b.removeAttribute("aria-current"));
  const n=fcount(); $("#fcount").hidden=!n; $("#fcount").textContent=n;
  $("#newDot").hidden=!EV.some(e=>NEW.has(e.id)&&(isFav(e)||alarmHit(e)||isFavV(e)));
  document.body.classList.toggle("venues",S.view==="venues");
  document.body.classList.toggle("tonight",S.view==="tonight");
  $("#dates").style.display=S.view==="fav"||S.view==="venues"||S.view==="tonight"?"none":"flex";
  renderDates();
  $("#main").innerHTML=S.view==="list"?viewList():S.view==="grid"?viewGrid():S.view==="venues"?viewVenues():S.view==="tonight"?viewTonight():viewFav();
  if(S.view==="fav") setupFav();
  if(S.view==="venues"&&!S.venuePage&&S.vmode==="map") drawMap();
  const mb=$(".months"), mo=mb&&mb.querySelector('[aria-pressed="true"]'); if(mo) mb.scrollLeft=mo.offsetLeft-(mb.clientWidth-mo.offsetWidth)/2;
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
  const regios=[...new Set(EV.filter(e=>inTab(e)).map(e=>V[e.v].prov))].sort();
  const genres=[...new Set(EV.filter(e=>inTab(e)).map(e=>e.genre))].sort((a,b)=>a.localeCompare(b,"nl"));
  const chip=(on,val,lab)=>`<button class="chip" data-val="${esc(val)}" aria-pressed="${on}">${esc(lab)}</button>`;
  $("#fSort").innerHTML=[["date","Datum"],["az","Artiest A–Z"],["venue","Podium A–Z"],["near","Dichtstbij"]].map(([k,l])=>chip(S.sort===k,k,l)).join("");
  $("#fTravel").innerHTML=[[0,"Alles"],[30,"30 min"],[45,"45 min"],[60,"1 uur"],[90,"1,5 uur"]].map(([k,l])=>chip(S.maxTravel===k,k,l)).join("");
  $("#fRegio").innerHTML=regios.map(r=>chip(S.regio.has(r),r,r)).join("");
  $("#fGenre").innerHTML=genres.map(g=>chip(S.genre.has(g),g,g)).join("");
  $("#fTime").innerHTML=[["","Alles"],["mid","Middag"],["eve","Avond"],["late","Nacht (na 22:00)"]].map(([k,l])=>chip(S.time===k,k,l)).join("");
  const vs=[...new Set(EV.filter(e=>inTab(e)).map(e=>e.v))].map(id=>V[id]).filter(v=>!S.regio.size||S.regio.has(v.prov)).sort((a,b)=>a.name.localeCompare(b.name,"nl"));
  vs.sort((a,b)=>inCity(b.id)-inCity(a.id)); // eigen stad eerst, daarna A-Z (sort is stabiel)
  $("#fVenue").innerHTML=`<option value="">Alle podia</option>`+vs.map(v=>`<option value="${v.id}"${S.venue===v.id?" selected":""}>${esc(v.name)} (${esc(v.city)})</option>`).join("");
  $("#fOnlyFav").checked=S.onlyFav; $("#fOnlyFree").checked=S.onlyFree;
  buildLocList();
}
function openSheet(id){$("#scrim").classList.add("open");$(id).classList.add("open")}
function closeSheets(){$("#scrim").classList.remove("open");document.querySelectorAll(".sheet").forEach(s=>s.classList.remove("open"));
  if(location.hash) try{history.replaceState(null,"",location.pathname+location.search)}catch{}}
$("#openFilters").onclick=()=>{buildFilters();openSheet("#filterSheet")};
$("#scrim").onclick=closeSheets;
$("#applyF").onclick=()=>{closeSheets();render()};
function resetFilters(){S.regio.clear();S.genre.clear();S.venue="";S.time="";S.onlyFav=false;S.onlyFree=false;S.sort="date";S.maxTravel=0}
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
$("#fOnlyFree").onchange=e=>S.onlyFree=e.target.checked;

/* Steden en podia aan/uit: per stad een vinkje, uitklapbaar naar de losse podia */
function buildLocList(){
  const q=($("#fLocQ").value||"").trim().toLowerCase(), open=new Set([...document.querySelectorAll("#fLoc details[open]")].map(d=>d.dataset.city));
  const cnt={}; EV.forEach(e=>{if(inTab(e)) cnt[e.v]=(cnt[e.v]||0)+1});
  const cities={}; Object.keys(cnt).forEach(id=>{const v=V[id], k=cityKey(v.city); (cities[k]=cities[k]||{name:v.city||"?",vs:[]}).vs.push(v)});
  const home=cityKey(S.home);
  const keys=Object.keys(cities).sort((a,b)=>(b===home)-(a===home)||cities[a].name.localeCompare(cities[b].name,"nl"));
  let h="";
  keys.forEach(k=>{const c=cities[k], vs=c.vs.sort((a,b)=>a.name.localeCompare(b.name,"nl"));
    const hit=!q||c.name.toLowerCase().includes(q)||vs.some(v=>v.name.toLowerCase().includes(q)); if(!hit) return;
    const n=vs.reduce((s,v)=>s+cnt[v.id],0), cityOff=S.hideC.has(k);
    h+=`<details data-city="${esc(k)}"${open.has(k)||(q&&!c.name.toLowerCase().includes(q))?" open":""}><summary><input type="checkbox" data-hidec="${esc(k)}"${cityOff?"":" checked"} aria-label="Toon ${esc(c.name)}"><span${cityOff?' class="off"':""}>${esc(c.name)}</span><span class="cnt">${n}</span></summary>`+
      vs.filter(v=>!q||c.name.toLowerCase().includes(q)||v.name.toLowerCase().includes(q)).map(v=>`<label class="v${cityOff?" off":""}"><input type="checkbox" data-hidev="${v.id}"${S.hideV.has(v.id)?"":" checked"}${cityOff?" disabled":""}>${esc(v.name)} <span class="cnt">${cnt[v.id]}</span></label>`).join("")+`</details>`});
  $("#fLoc").innerHTML=h||`<p class="s" style="padding:10px 12px;margin:0">Niets gevonden.</p>`;
}
$("#fLocQ").oninput=buildLocList;
$("#fLocAll").onclick=()=>{S.hideC.clear();S.hideV.clear();saveHidden();buildLocList()};
$("#fLoc").addEventListener("click",e=>{if(e.target.matches("summary input")) e.stopPropagation()},true);  // vinkje klikken klapt niet open/dicht
$("#fLoc").addEventListener("change",e=>{
  const t=e.target;
  if(t.dataset.hidec){t.checked?S.hideC.delete(t.dataset.hidec):S.hideC.add(t.dataset.hidec)}
  if(t.dataset.hidev){t.checked?S.hideV.delete(t.dataset.hidev):S.hideV.add(t.dataset.hidev)}
  saveHidden(); buildLocList();
});

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
     <div class="dsub">${esc(v.name)}, ${esc(v.city)} · <button class="linkbtn" data-openvenue="${esc(vgOf(e.v))}">Alles bij dit podium</button></div></div>
     <button class="star" data-fav="${e.ak}" data-name="${esc(e.artist)}" aria-pressed="${S.fav.has(e.ak)}" aria-label="Volg ${esc(e.artist)}" style="font-size:30px">★</button></div>
   <div class="facts"><div><small>Genre</small><b>${esc(e.genre)}</b></div>${tr.car!=null?`<div><small>Auto</small><b>± ${tr.car} min</b></div><div><small>OV</small><b>± ${tr.ov} min</b></div>`:""}${e.price!=null?`<div><small>${e.price===0?"Entree":"Prijs vanaf"}</small><b>${priceTxt(e.price)}</b></div>`:""}${e.status==="sold"?`<div><small>Kaarten</small><b style="color:var(--warn)">Uitverkocht</b></div>`:""}</div>
   <div class="timeline">${tl}</div>
   <div class="row2"><a class="btn" href="${esc(e.url)}" target="_blank" rel="noopener noreferrer">Info en kaarten bij ${esc(V[e.v].name)}</a></div>
   <div class="row2" style="margin-top:10px">${e.time!=null?`<button class="btn ghost" id="icsBtn">Zet in agenda</button><a class="btn ghost" id="gcal" target="_blank" rel="noopener">Google Agenda</a>`:`<p class="s">Agenda-knop verschijnt zodra de tijd bekend is.</p>`}</div>
   <div class="row2" style="margin-top:10px"><button class="btn ghost" id="shareBtn" type="button">Delen</button><a class="btn ghost" href="${esc(issueUrl(e))}" target="_blank" rel="noopener noreferrer">Klopt niet?</a></div>
   <p class="note">Gegevens van ${SNAPSHOT}, overgenomen van de site van ${esc(V[e.v].name)}. Tijden, prijzen en beschikbaarheid kunnen veranderen: kijk altijd op die site voordat je gaat of kaarten koopt.</p>
   <h3>Vergelijkbaar en dichtbij</h3>
   <div class="simlist">${sims.length?sims.map(o=>`<div class="ev" role="button" tabindex="0" data-ev="${o.id}"><div><div class="a">${esc(o.artist)}</div><div class="v">${short(o)}, ${esc(V[o.v].name)} ${travel(o.v).car!=null?"(± "+travel(o.v).car+" min)":""}</div></div><button class="star" data-fav="${o.ak}" data-name="${esc(o.artist)}" aria-pressed="${S.fav.has(o.ak)}" aria-label="Volg ${esc(o.artist)}">★</button></div>`).join(""):'<p class="s">Geen genre-match in de huidige agenda.</p>'}</div>
   <div class="ai" id="simAI" hidden><strong>Wie lijkt hierop?</strong><p>Claude noemt vergelijkbare artiesten en checkt of die in de agenda staan.</p><button class="btn" id="askSim">Vraag Claude</button><div id="simOut"></div></div>`;
  if(e.time!=null){ $("#gcal").href=gcalUrl(e); $("#icsBtn").onclick=()=>saveIcs(e); }
  $("#shareBtn").onclick=()=>share(e);
  if(sample){ $("#simAI").hidden=false; $("#askSim").onclick=()=>askSimilar(e); }
  openSheet("#detailSheet"); $("#detailSheet").scrollTop=0;
}
/* Melding "Klopt niet?": vooringevuld GitHub-issue (alles URL-gecodeerd) */
const ISSUES="https://github.com/jjjreinhoudt-wq/podiumradar/issues/new";
const whenTxt=e=>e.endDate?(e.started?"nu":short(e))+" t/m "+dm(e.endDate):short(e)+(e.date.getFullYear()!==today.getFullYear()?" "+e.date.getFullYear():"");
function issueUrl(e){
  const v=V[e.v];
  const title=`Klopt niet: ${e.title} (${v.name}, ${e.rawDate})`;
  const body=[`Datum: ${e.rawDate}${e.endDate?" t/m "+e.endDate.getFullYear()+"-"+String(e.endDate.getMonth()+1).padStart(2,"0")+"-"+String(e.endDate.getDate()).padStart(2,"0"):""} (${whenTxt(e)})`,
    `Tijd: ${e.time!=null?hm(e.time):"onbekend"}`,`Podium: ${v.name}, ${v.city}`,`Bron: ${e.url!=="#"?e.url:"geen link"}`,`Id: ${e.id}`,"","Wat klopt er niet?",""].join("\n");
  return ISSUES+"?labels=melding&title="+encodeURIComponent(title)+"&body="+encodeURIComponent(body);
}
/* Delen: deelmenu van het toestel, anders kopiëren. De link opent de app met dit item (#id). */
const appLink=e=>location.origin+location.pathname+"#"+encodeURIComponent(e.id);
function shareText(e){const v=V[e.v];
  const wd=e.endDate?whenTxt(e):WDL[e.date.getDay()]+" "+dm(e.date)+(e.time!=null?" "+hm(e.time):"");
  return `${e.artist} — ${wd}, ${v.name} ${v.city}`+(e.url!=="#"?"\n"+e.url:"")}
async function share(e){
  const text=shareText(e), url=appLink(e);
  if(navigator.share){ try{ await navigator.share({title:e.artist,text,url}); return }catch(err){ if(err&&err.name==="AbortError") return } }
  const all=text+"\n"+url;
  try{ await navigator.clipboard.writeText(all); toast("Gekopieerd: plak het in een bericht"); return }catch{}
  try{ const ta=document.createElement("textarea"); ta.value=all; ta.setAttribute("readonly",""); ta.style.cssText="position:fixed;opacity:0;top:0"; document.body.appendChild(ta); ta.select();
    const ok=document.execCommand("copy"); ta.remove(); if(ok){toast("Gekopieerd: plak het in een bericht");return} }catch{}
  toast("Delen lukt hier niet. Kopieer de link uit de adresbalk.");
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
/* Pushmeldingen via ntfy: de volglijst staat op dit toestel; met deze knop gaat hij als GitHub-melding naar de
   repository, waar workflow volglijst.yml hem overneemt (alleen van de eigenaar). Zie scraper/meldingen.py. */
function meldBox(){
  const lijst={artiesten:[...S.fav].map(favName),podia:[...S.favV],alarmen:S.alarms};
  const n=lijst.artiesten.length+lijst.podia.length+lijst.alarmen.length;
  const body="Volglijst vanuit de app (niet aanpassen, alleen op 'Submit new issue' tikken).\n\n```json\n"+JSON.stringify(lijst,null,1)+"\n```\n";
  const url="https://github.com/jjjreinhoudt-wq/podiumradar/issues/new?title="+encodeURIComponent("Volglijst Podiumradar")+"&body="+encodeURIComponent(body);
  return `<div class="ai meld"><strong>Meldingen op je telefoon</strong><p>Krijg een melding in de app <b>ntfy</b> zodra er een nieuwe show is van een artiest of podium dat je volgt, of die past bij een alarm. Na het volgen of ontvolgen: stuur je lijst opnieuw.</p>
    ${n?`<a class="btn" href="${esc(url)}" target="_blank" rel="noopener noreferrer">Stuur mijn volglijst (${n})</a>`:`<p class="s">Volg eerst een artiest of podium, of zet een alarm.</p>`}</div>`;
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
    const pool=EV.filter(e=>inTab(e)&&!isFav(e)).slice(0,250).map(e=>({id:e.id,t:e.title,g:e.genre,p:V[e.v].name,dag:short(e),auto_min:travel(e.v).car}));
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
  const fv=e.target.closest("[data-favv]"); if(fv){e.stopPropagation(); toggleFavV(fv.dataset.favv,fv.dataset.name||"Podium"); return}
  const vm=e.target.closest("[data-vmode]"); if(vm){S.vmode=vm.dataset.vmode; store.set("pr_vmode",S.vmode); render(); return}
  const zb=e.target.closest("[data-zoom]"); if(zb&&NL&&$("#nlmap")){const z=zb.dataset.zoom;
    if(z==="in") zoomBy(1/1.6); else if(z==="out") zoomBy(1.6);
    else if(z==="home"){const [x,y]=proj(S.homeXY[0],S.homeXY[1]); zoomTo(x,y,NL.w/4)} else {MAPV.vb=[0,0,NL.w,NL.h]; applyView()}
    return}
  const go=e.target.closest("[data-view-go]"); if(go){S.view=go.dataset.viewGo; render(); try{window.scrollTo(0,0)}catch{}; return}
  const tw=e.target.closest("[data-tn-when]"); if(tw){TN.when=tw.dataset.tnWhen; render(); return}
  const tm=e.target.closest("[data-tn-max]"); if(tm){TN.max=+tm.dataset.tnMax; store.set("pr_tnmax",TN.max); render(); return}
  const tk=e.target.closest("[data-tn-kind]"); if(tk){const k=tk.dataset.tnKind; TN.kinds.has(k)?TN.kinds.delete(k):TN.kinds.add(k); if(!TN.kinds.size) TN.kinds.add(k); render(); return}
  if(e.target.id==="freeOff"){S.onlyFree=false; render(); return}
  const f=e.target.closest("[data-fav]"); if(f){e.stopPropagation(); const ak=f.dataset.fav; toggleFav(ak,f.dataset.name||favName(ak));
    document.querySelectorAll(`#detailSheet [data-fav="${ak}"]`).forEach(b=>b.setAttribute("aria-pressed",S.fav.has(ak))); return}
  const al=e.target.closest("[data-alarm]"); if(al){S.alarms.splice(+al.dataset.alarm,1);store.set("pr_alarms",S.alarms);render();return}
  const ev=e.target.closest("[data-ev]"); if(ev){openDetail(ev.dataset.ev);return}
  // Datum gekozen: naar het begin van de nieuwe lijst; is de kop ingeklapt, dan blijft alleen de datumrij staan (anders zit de volgende tik op de soortknoppen)
  const d=e.target.closest(".day"); if(d){const kb=d.matches(":focus-visible"), hd=$("header"), top=hd.classList.contains("tuck")?$("#dates").offsetTop:0;
    S.day=+d.dataset.d;S.month="";render();
    if(scrollY>top){if(top) hd.dataset.hold="1"; try{window.scrollTo(0,top)}catch{}}
    const c=kb&&document.querySelector(`#dates [data-d="${S.day}"]`); if(c) c.focus({preventScroll:true}); return}
  // Met het toetsenbord gekozen: focus terug op de gekozen maand (bij tikken geen focusrand)
  const mo=e.target.closest("[data-month]"); if(mo){const top=mo.hasAttribute("data-month-top"), kb=mo.matches(":focus-visible"); S.month=mo.dataset.month;S.day=-1;render();if(top){try{window.scrollTo(0,0)}catch{}}
    const c=kb&&(document.querySelector(`.months [data-month="${S.month}"]`)||document.querySelector("#main .ev")); if(c) c.focus({preventScroll:true}); return}
  const mb=e.target.closest("#moreBtn"); if(mb){const kb=mb.matches(":focus-visible"), c=document.querySelectorAll("#main .ev").length; LIM.n+=300; render(); const nx=document.querySelectorAll("#main .ev")[c]; if(nx) nx.focus({preventScroll:true,focusVisible:kb}); return}
  const vk=e.target.closest("[data-vkind]"); if(vk){S.vkind=vk.dataset.vkind;render();return}
  const vb=e.target.closest("[data-vback]"); if(vb){S.venuePage=null;render();try{window.scrollTo(0,0)}catch{};return}
  const ov=e.target.closest("[data-openvenue]"); if(ov){closeSheets();S.view="venues";S.venuePage=ov.dataset.openvenue;S.q="";$("#q").value="";render();try{window.scrollTo(0,0)}catch{};return}
  const vn=e.target.closest("[data-venue]"); if(vn){S.view="venues";S.venuePage=vn.dataset.venue;render();try{window.scrollTo(0,0)}catch{};return}
  const t=e.target.closest("nav.tabs button"); if(t){S.view=t.dataset.view;if(t.dataset.view==="venues")S.venuePage=null;render();try{window.scrollTo(0,0)}catch{};return}
  if(e.target.id==="showHidden"){S.hideC.clear();S.hideV.clear();saveHidden();render();return}
  if(e.target.id==="clearAll"||e.target.id==="clearAll2"){resetFilters();S.q="";$("#q").value="";if(S.view!=="grid"){S.day=-1;S.month=""}render()}
});
/* Slepen met de muis om blokkenschema en datumrij opzij te schuiven (touch scrolt al vanzelf) */
let drag=null;
document.addEventListener("pointerdown",e=>{
  if(e.pointerType!=="mouse"||e.button!==0) return;
  const el=e.target.closest(".grid-wrap,.dates,.months"); if(!el||el.scrollWidth<=el.clientWidth) return;
  drag={el,x:e.clientX,left:el.scrollLeft,moved:false};
  e.preventDefault(); // geen tekstselectie; klikken werkt gewoon
});
// Anders start de browser "tekst/link slepen" en breekt het schuiven af
document.addEventListener("dragstart",e=>{if(e.target.closest&&e.target.closest(".grid-wrap,.dates,.months")) e.preventDefault()});
document.addEventListener("pointercancel",()=>{if(drag){drag.el.classList.remove("dragging");drag=null}});
document.addEventListener("pointermove",e=>{
  if(!drag) return; const dx=e.clientX-drag.x;
  if(!drag.moved&&Math.abs(dx)<5) return;
  drag.moved=true; drag.el.classList.add("dragging"); drag.el.scrollLeft=drag.left-dx; e.preventDefault();
});
document.addEventListener("pointerup",()=>{
  if(!drag) return; drag.el.classList.remove("dragging");
  // Na slepen geen klik laten doorgaan op het blok/de datum waar je losliet
  if(drag.moved) noClickUntil=Date.now()+60;
  drag=null;
});
let noClickUntil=0;
document.addEventListener("click",ev=>{if(Date.now()<noClickUntil){ev.stopPropagation();ev.preventDefault()}},{capture:true});
/* Maandknop met het toetsenbord gekozen: helemaal in beeld schuiven (niet onder de vervaging rechts) */
document.addEventListener("focusin",e=>{const c=e.target.closest&&e.target.closest(".months .chip"); if(c&&c.matches(":focus-visible")) c.scrollIntoView({inline:"nearest",block:"nearest"})});
/* Scrollwiel boven de datumrij schuift die opzij */
document.addEventListener("wheel",e=>{
  const el=e.target.closest(".dates,.months"); if(!el||el.scrollWidth<=el.clientWidth||e.shiftKey||Math.abs(e.deltaX)>Math.abs(e.deltaY)) return;
  // Aan het eind van de rij: gewoon de pagina laten scrollen
  const max=el.scrollWidth-el.clientWidth; if((e.deltaY>0&&el.scrollLeft>=max-1)||(e.deltaY<0&&el.scrollLeft<=0)) return;
  el.scrollLeft+=e.deltaY; e.preventDefault();
},{passive:false});
document.addEventListener("keydown",e=>{if(e.key==="Escape")closeSheets();if(e.key==="Enter"&&e.target.id==="q")e.target.blur();if(e.key==="Enter"&&e.target.matches(".ev[data-ev]"))openDetail(e.target.dataset.ev);if(e.key==="Enter"&&e.target.matches("[data-venue]"))e.target.click()});
document.querySelectorAll(".seg [data-type]").forEach(b=>b.onclick=()=>{S.type=b.dataset.type;S.genre.clear();S.venue="";S.month="";if(S.view!=="grid")S.day=-1;render()});
let qt;$("#q").oninput=e=>{clearTimeout(qt);qt=setTimeout(()=>{S.q=e.target.value;render()},150)};

/* Kop inklappen bij naar beneden scrollen: alleen de datumrij blijft staan (of niets, als die er niet is); een stukje omhoog haalt alles terug */
(()=>{const hd=$("header"), ds=$("#dates"); let lastY=Math.max(0,scrollY), busy=false;
  // Zonder datumrij helemaal weg, inclusief schaduw (procent = eigen hoogte, dus geen afrondingsrandje)
  const setT=()=>hd.style.setProperty("--tuck",ds.style.display==="none"?"calc(100% + 24px)":ds.offsetTop+"px");
  const upd=()=>{busy=false; const y=Math.max(0,scrollY), dy=y-lastY;
    hd.classList.toggle("scrolled",y>2);
    if(hd.dataset.hold){delete hd.dataset.hold;lastY=y;return} // zelf gescrold (datum gekozen): ingeklapt laten
    // Pas inklappen als de lijst direct onder de datumrij zou aansluiten; daarboven altijd helemaal tonen
    if(y<(ds.style.display==="none"?hd.offsetHeight:ds.offsetTop)){hd.classList.remove("tuck");lastY=y;return}
    if(y+innerHeight>=document.documentElement.scrollHeight-2&&dy<0){lastY=y;return} // terugveren onderaan telt niet
    if(dy>6&&!(hd.contains(document.activeElement)&&document.activeElement.matches("input"))){setT();hd.classList.add("tuck")}
    else if(dy<-6) hd.classList.remove("tuck");
    if(Math.abs(dy)>6) lastY=y};
  addEventListener("scroll",()=>{if(!busy){busy=true;requestAnimationFrame(upd)}},{passive:true});
  // Andere hoogte (draaien, datumrij aan/uit) terwijl hij ingeklapt is: opnieuw meten
  if(window.ResizeObserver) new ResizeObserver(()=>{if(hd.classList.contains("tuck")) setT()}).observe(hd);
  // Met het toetsenbord (Tab) of in het zoekveld: kop weer helemaal tonen; een tik op een datum laat hem ingeklapt
  hd.addEventListener("focusin",e=>{if(e.target.matches(":focus-visible,input,select")) hd.classList.remove("tuck")});
  // Tab: eerst zonder animatie uitklappen, anders schuift de browser de pagina naar de (nog verborgen) kop;
  // komt de focus buiten de kop terecht, dan meteen weer inklappen (anders valt de kop over de gekozen kaart)
  let tabOpen=false;
  addEventListener("keydown",e=>{if(e.key==="Tab"&&hd.classList.contains("tuck")){tabOpen=true;hd.style.transition="none";hd.classList.remove("tuck");hd.offsetHeight;requestAnimationFrame(()=>{hd.style.transition="";tabOpen=false})}},true);
  document.addEventListener("focusin",e=>{if(tabOpen&&!hd.contains(e.target)){tabOpen=false;hd.classList.add("tuck")}});
  // Op de telefoon: scrollen in de lijst sluit het toetsenbord van het zoekveld, zodat de kop weer kan inklappen
  $("#main").addEventListener("touchmove",()=>{const a=document.activeElement; if(a&&a.id==="q") a.blur()},{passive:true});
})();

buildHome(); render();
/* Gedeelde link (#id): meteen de details van dat item openen */
function openFromHash(){
  let id=""; try{id=decodeURIComponent(location.hash.slice(1))}catch{} if(!id) return;
  if(EV.some(x=>x.id===id)) openDetail(id);
  else if(/^[a-z][\w-]{3,40}$/i.test(id)) toast("Dit item staat niet (meer) in de agenda");
}
openFromHash(); window.addEventListener("hashchange",openFromHash);
if(window.claude&&claude.use){
  claude.use("sample").then(s=>{sample=s;if(S.view==="fav")render()}).catch(()=>{});
  claude.use("downloads").then(d=>{downloads=d}).catch(()=>{});
}
})();
