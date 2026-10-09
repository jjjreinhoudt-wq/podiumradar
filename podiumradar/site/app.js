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
const TABNAME={pop:"Concerten",thea:"Theater",film:"Film",expo:"Musea",fest:"Festivals",kids:"Kids"};
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
Object.entries(DATA.venues||{}).forEach(([id,v])=>{ if(/^[\w-]{1,80}$/.test(id)&&v&&typeof v==="object"&&typeof v.name==="string"&&typeof v.city==="string") V[id]={id,...v} });
const filmSeen=new Set();
let BAD=0;
(DATA.events||[]).forEach(r=>{ try{
  if(!/^[\w-]{1,40}$/.test(r.id)||!/^[\w-]{1,80}$/.test(r.v)) throw 0;
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
  const support=Array.isArray(r.support)&&r.support.length?r.support.map(String):acts.slice(1);
  EV.push({id:r.id,title:r.title,artist:acts[0],support,v:r.v,genre:r.genre,type,date,d,
    time:toMin(r.time)??toMin(r.start)??toMin(r.doors), doors:toMin(r.doors), start:toMin(r.start),
    // alleen echte webadressen als link (geen javascript:-links uit een bron)
    url:/^https?:\/\/[^\s<>"]+$/i.test(String(r.url||"").trim().replace(/ /g,"%20"))?String(r.url).trim().replace(/ /g,"%20"):"#",isFest:r.id[0]==="f"||type==="fest",status:r.status||null,firstSeen:r.first_seen,
    dur:r.dur||null,kids:!!r.kids||isKids(r.title,r.genre),endD,endDate:r.end?new Date(...r.end.split("-").map((x,i)=>i===1?x-1:+x)):null,started,
    rawDate:r.date, price:priceOf(r.price), times:timesOf(r.times)});
}catch(err){BAD++} });   // een rij die niet te lezen is wordt overgeslagen
const SNAPSHOT=(()=>{try{const [dpart,t]=DATA.updated.split(" ");const [y,m,d]=dpart.split("-").map(Number);return d+" "+["januari","februari","maart","april","mei","juni","juli","augustus","september","oktober","november","december"][m-1]+" om "+t}catch{return "onbekend"}})();
// Hoe oud is de agenda? (data.json: "JJJJ-MM-DD UU:MM", Nederlandse tijd) Na 36 uur staat er een waarschuwing boven de lijst
const AGE_H=(()=>{const m=String(DATA.updated).match(/^(\d{4})-(\d\d)-(\d\d) (\d\d):(\d\d)/);return m?(Date.now()-new Date(+m[1],m[2]-1,+m[3],+m[4],+m[5]))/36e5:0})();
const staleBanner=()=>AGE_H>36?`<div class="stale" role="status"><strong>De agenda is niet bijgewerkt sinds ${SNAPSHOT}.</strong> Tijden kunnen verouderd zijn: kijk voor de zekerheid bij het podium.</div>`:"";
const recent=e=>e.firstSeen&&(today-new Date(e.firstSeen))/864e5<=3;
// Zoeken: zonder hoofdletters/accenten, alle woorden moeten voorkomen ("amity 013" vindt The Amity Affliction bij 013)
const FOLD={"ø":"o","đ":"d","ł":"l","ı":"i","æ":"ae","œ":"oe","ß":"ss","ð":"d","þ":"th"};
const norm=s=>String(s).toLowerCase().normalize("NFD").replace(/[\u0300-\u036f\u00ad\u200b-\u200d\ufeff]/g,"").replace(/[øđłıæœßðþ]/g,c=>FOLD[c]).replace(/[\u2018\u2019\u02bc`\u00b4]/g,"'").replace(/[\u201c\u201d\u201e]/g,'"');
// Zoeken op de bekende schrijfwijze van een plaats ("den bosch" vindt 's-Hertogenbosch)
const CITY_AKA=c=>/hertogenbosch/i.test(c)?"den bosch":/^den haag$/i.test(c)?"s-gravenhage 's-gravenhage":"";
const artistKey=n=>n.toLowerCase().normalize("NFD").replace(/[\u0300-\u036f]/g,"").replace(/[^a-z0-9]/g,"");
EV.forEach(e=>{e.ak=artistKey(e.artist); if(e.time==null&&e.times) e.time=e.times[0].s;
  const v=V[e.v]; e.hay=norm([e.title,v.name,v.city,CITY_AKA(v.city),e.genre,e.support.join(" ")].join(" "));
  e.age=e.firstSeen?Math.max(0,-dayNr(e.firstSeen)):999});   // dagen sinds het item voor het eerst op de agenda kwam
const BYID=new Map(EV.map(e=>[e.id,e]));

/* ---------- PLACES ---------- */
const HOMES={"Tilburg":[51.5555,5.0913],"Breda":[51.5719,4.7683],"Eindhoven":[51.4416,5.4697],"Den Bosch":[51.6978,5.3037],"Helmond":[51.4793,5.6570],"Oss":[51.7650,5.5180],"Bergen op Zoom":[51.4949,4.2911],"Roosendaal":[51.5308,4.4653],"Amsterdam":[52.3676,4.9041],"Utrecht":[52.0907,5.1214],"Rotterdam":[51.9244,4.4777],"Den Haag":[52.0705,4.3007],"Nijmegen":[51.8126,5.8372],"Arnhem":[51.9851,5.8987],"Zwolle":[52.5168,6.0830],"Groningen":[53.2194,6.5665],"Maastricht":[50.8514,5.6910],"Venlo":[51.3704,6.1724]};
function km(a,b,c,d){const R=6371,x=(c-a)*Math.PI/180,y=(d-b)*Math.PI/180;const h=Math.sin(x/2)**2+Math.cos(a*Math.PI/180)*Math.cos(c*Math.PI/180)*Math.sin(y/2)**2;return 2*R*Math.asin(Math.sqrt(h))}
// Schatting uit de afstand hemelsbreed, geen echte route: auto = 1,2 x omweg met 90 km/u + 10 min parkeren, OV = 1,2 x omweg met 70 km/u + 15 min lopen en overstappen
// (ijkpunten vanuit Tilburg: Breda ±40, Eindhoven ±55, Utrecht ±70, Amsterdam ±105 min). Google Maps rekent vanaf je echte locatie met verkeer en dienstregeling.
function travel(vid){const v=V[vid], h=S.homeXY; if(v.lat==null) return {car:null,ov:null,k:null}; const k=km(h[0],h[1],v.lat,v.lon);
  if(k<3) return {car:Math.round(k*4+5),ov:Math.round(k*6+8),k};
  return {car:Math.round(k*1.2/90*60+10), ov:Math.round(k*1.2/70*60+15), k}}

/* ---------- STATE ---------- */
const store={get(k,f){try{const v=localStorage.getItem(k);if(!v) return f;const p=JSON.parse(v);return p===null||typeof p!==typeof f||Array.isArray(p)!==Array.isArray(f)?f:p}catch{return f}},set(k,v){try{localStorage.setItem(k,JSON.stringify(v))}catch{}}};
const S={type:"pop",view:"list",day:-1,month:"",calMonth:"",q:"",qAll:true,sort:"date",regio:new Set(),venue:"",genre:new Set(),time:"",maxTravel:0,onlyFav:false,
  fav:new Set(store.get("pr_fav2",[])), favV:new Set(store.get("pr_favv",[])), onlyFree:false, vmode:store.get("pr_vmode","list")==="map"?"map":"list", alarms:store.get("pr_alarms",[]), home:store.get("pr_home","Tilburg"), homeXY:null,
  // Uitgevinkte steden en podia (blijven bewaard): niets van tonen
  hideC:new Set(store.get("pr_hideC",[])), hideV:new Set(store.get("pr_hideV",[]))};
/* Mijn plannen ('Ik ga'): id -> kleine momentopname, zodat een plan zichtbaar blijft als het item uit de agenda verdwijnt */
const GO=(()=>{const o=store.get("pr_going",{}); return o&&typeof o==="object"&&!Array.isArray(o)?o:{}})();
const ymd=x=>x.getFullYear()+"-"+String(x.getMonth()+1).padStart(2,"0")+"-"+String(x.getDate()).padStart(2,"0");
function pruneGo(){let ch=false; Object.keys(GO).forEach(id=>{const g=GO[id]; if(!g||typeof g.d!=="string"||!/^\d{4}-\d{2}-\d{2}$/.test(g.d)||dayNr(typeof g.x==="string"&&g.x?g.x:g.d)<0){delete GO[id];ch=true}}); if(ch) store.set("pr_going",GO)}
pruneGo();
// Verplaatst of hernoemd item (nieuw id): het plan koppelt aan hetzelfde item op dezelfde dag en hetzelfde podium
function migrateGo(){let ch=false; Object.keys(GO).forEach(id=>{const g=GO[id]; if(BYID.has(id)) return;
  const c=EV.filter(e=>e.rawDate===g.d&&V[e.v].name+", "+V[e.v].city===g.v&&norm(e.artist)===norm(g.t||"")&&!GO[e.id]);
  const near=x=>g.tm==null||x.time==null||Math.abs(x.time-g.tm)<=30;
  const e=c.find(x=>x.time===g.tm)||(c.length===1&&near(c[0])?c[0]:null);   // films: zelfde titel en dag, dus liefst dezelfde tijd
  if(e){g.t=e.artist; g.tm=e.time; GO[e.id]=g; delete GO[id]; ch=true}}); if(ch) store.set("pr_going",GO)}
migrateGo();
function toggleGoing(e){
  if(GO[e.id]){delete GO[e.id]; toast("Uit je plannen gehaald")}
  else{GO[e.id]={t:e.artist,d:e.rawDate,tm:e.time,v:V[e.v].name+", "+V[e.v].city}; if(e.endDate) GO[e.id].x=ymd(e.endDate); toast("Staat in je plannen")}
  store.set("pr_going",GO); requestAnimationFrame(()=>setTimeout(render));   // eerst de knop, dan pas de lijst erachter
}
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

const qTokens=()=>norm(S.q.trim()).split(/\s+/).filter(Boolean);
const matchQ=(e,toks)=>toks.every(t=>e.hay.includes(t));
function filtered(ignoreDay,ignoreMonth,allTypes,noSort){
  const toks=qTokens(), mr=!ignoreDay&&!ignoreMonth&&S.day<0&&S.month?mRange(S.month):null;
  let list=EV.filter(e=>{
    if(!allTypes&&!inTab(e)) return false;
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
    if(toks.length&&!matchQ(e,toks)) return false;
    return true;
  });
  const tm=e=>e.time==null?20*60:e.time;
  // Eigen stad altijd bovenaan (per dag bij sorteren op datum)
  const own=(a,b)=>inCity(b.v)-inCity(a.v);
  const cmp={date:(a,b)=>(b.started-a.started)||a.d-b.d||own(a,b)||tm(a)-tm(b),
    az:(a,b)=>own(a,b)||a.artist.localeCompare(b.artist,"nl")||a.d-b.d,
    venue:(a,b)=>own(a,b)||V[a.v].name.localeCompare(V[b.v].name,"nl")||a.d-b.d,
    near:(a,b)=>(travel(a.v).car??999)-(travel(b.v).car??999)||a.d-b.d}[S.sort];
  return noSort?list:list.sort(cmp);
}
// Ligt deze locatie in de gekozen stad? Op naam van de plaats; bij "Mijn locatie" binnen 5 km.
const CITY_ALIAS={"den bosch":"s hertogenbosch","s hertogenbosch":"s hertogenbosch","den haag":"s gravenhage","s gravenhage":"s gravenhage"};
const CKC=new Map();
const cityKey=c=>{c=String(c||""); let r=CKC.get(c); if(r===undefined){const k=c.toLowerCase().normalize("NFD").replace(/[\u0300-\u036f]/g,"").replace(/[^a-z]+/g," ").trim(); r=CITY_ALIAS[k]||k; CKC.set(c,r)} return r};
const inCity=vid=>{const v=V[vid]; if(!v) return false; if(S.home==="__geo"){const k=travel(vid).k; return k!=null&&k<5}
  return cityKey(v.city)===cityKey(S.home)};
function similar(e,n=4){
  if(["Overig","Feest"].includes(e.genre)) return [];
  const seenA=new Set([e.ak]);
  return EV.filter(x=>x.type===e.type&&x.genre===e.genre&&!seenA.has(x.ak)&&(seenA.add(x.ak),true))
    .sort((a,b)=>(travel(a.v).car??999)-(travel(b.v).car??999)||a.d-b.d).slice(0,n);
}

/* ---------- RENDER ---------- */
// Gemarkeerde datum in het midden van de rij zetten (na wisselen van weergave of kiezen in de Kalender)
const showDay=()=>{const dp=$('#dates .day[aria-pressed="true"]:not(.all)'), dd=$("#dates"); if(dp&&dd.offsetParent){const a=dp.getBoundingClientRect(), b=dd.getBoundingClientRect(); if(a.left<b.left||a.right>b.right) dd.scrollLeft+=a.left-b.left-(dd.clientWidth-dp.offsetWidth)/2}};
let dayHold=null;   // Blokkenschema: dag die een zoekopdracht even wegdrukte
function renderDates(){
  const toks=qTokens(), all=S.view==="list"&&S.q.trim()&&S.qAll;
  const inScope=e=>(all||inTab(e))&&(!toks.length||matchQ(e,toks));
  const ds=[...new Set(EV.filter(inScope).map(e=>e.d))].sort((a,b)=>a-b).slice(0,70);
  // De gekozen dag blijft in de rij staan: in de Agenda ook zonder treffer, in het Blokkenschema alleen als er iets te zien is
  if(S.day>=0&&!ds.includes(S.day)&&(S.view!=="grid"||EV.some(e=>inScope(e)&&onDay(e,S.day)))){ds.push(S.day);ds.sort((a,b)=>a-b)}
  if(S.view!=="grid") dayHold=null;
  else{   // valt de dag door een zoekopdracht weg, dan naar de eerste dag met een treffer; wissen zet de oude dag terug
    const q=S.q.trim();
    if(dayHold!=null&&(!q||ds.includes(dayHold))){ if(ds.includes(dayHold)) S.day=dayHold; dayHold=null }
    if(S.day<0||!ds.includes(S.day)){ if(q&&S.day>=0&&dayHold==null) dayHold=S.day; S.day=ds[0]??0; S.month="" }
  }
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
      ${kind?`<span class="tag kind">${KIND[e.type]}</span>`:""}${kind&&e.genre===KIND[e.type]?"":`<span class="tag">${esc(e.genre)}</span>`}${e.price!=null?`<span class="tag price${e.price===0?" free":""}">${priceTxt(e.price)}</span>`:""}${GO[e.id]?'<span class="tag going">✓ Ik ga</span>':""}${e.status==="sold"?'<span class="tag sold">Uitverkocht</span>':""}${o.reason?`<div class="s${o.warn?" warn":""}" style="margin-top:4px">${esc(o.reason)}</div>`:""}</div>
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
/* Snelle acties onder 'Vanavond in de buurt' */
function quickRow(){
  const n=filtered(true,false,false,true).reduce((c,e)=>c+(e.age<=7?1:0),0);
  return `<div class="qrow"><button class="qpill" data-surprise type="button">${ICO.dice}Verras me</button><button class="qpill" data-view-go="cal" type="button">${ICO.cal}Kalender</button>${n?`<button class="qpill" data-view-go="new" type="button">${ICO.spark}Nieuw <small>${nf(n)}</small></button>`:""}</div>`;
}
/* Verras me: willekeurig iets in de buurt, vanavond; anders dit weekend; anders de komende twee weken */
const SURP={seen:new Set(),last:null};
function surprise(again){
  const nm=nowMin(), toks=qTokens(), usable=e=>e.time!=null&&e.status!=="sold"&&e.status!=="cancelled"&&!(e.d===0&&e.time<=nm);
  let when="vanavond", pool=tonightList("today").timed.filter(usable);
  if(!pool.length){when="dit weekend"; pool=tonightList("weekend").timed.filter(usable)}
  if(!pool.length){when="de komende dagen"; pool=EV.filter(e=>e.endD==null&&e.d>=0&&e.d<=14&&usable(e)&&TN.kinds.has(e.type)&&!hiddenLoc(e.v)&&(travel(e.v).car??999)<=TN.max&&(!toks.length||matchQ(e,toks)))}
  if(!pool.length){toast(toks.length?"Niets in de buurt gevonden voor ‘"+S.q.trim()+"’. Wis de zoekterm voor een verrassing.":"Niets in de buurt gevonden. Kies een grotere afstand bij ‘Vanavond in de buurt’."); return}
  // Eerst een soort kiezen, dan een titel: anders wint film met zijn vele speeltijden bijna altijd
  const key=e=>e.type+"|"+e.ak+"|"+e.v, pick=a=>a[Math.floor(Math.random()*a.length)];
  if(again&&new Set(pool.map(key)).size===1&&SURP.last===key(pool[0])){toast("Dit is het enige in de buurt voor nu."); return}
  let fresh=pool.filter(e=>!SURP.seen.has(key(e)));
  if(!fresh.length){SURP.seen.clear(); fresh=pool.filter(e=>key(e)!==SURP.last); if(!fresh.length) fresh=pool}
  const k=pick([...new Set(fresh.map(e=>e.type))]), kk=pick([...new Set(fresh.filter(e=>e.type===k).map(key))]);
  const e=pick(fresh.filter(e=>key(e)===kk)); SURP.seen.add(key(e)); SURP.last=key(e);
  openDetail(e.id,{surprise:when==="vanavond"&&e.time<17*60?"vandaag":when});
}
/* Kalender: maandrooster met per dag hoeveel er te doen is (huidig tabblad en filters) */
function viewCal(){
  const list=filtered(true,false,false,true), cur=mKey(today);
  let h=`<div class="meta"><button data-view-go="list">‹ Agenda</button>${fcount()||S.q.trim()?'<button id="clearAll">Alles wissen</button>':""}</div><div class="vhead"><h1>Kalender</h1><div class="s">Tik op een dag voor de lijst. Hoe donkerder, hoe meer er te doen is (${TABNAME[S.type]}).</div></div>`;
  if(!list.length) return h+emptyState();
  // Zelfde horizon als de maandknoppen (18 maanden): lange tentoonstellingen rekken de kalender niet tot 2032 uit
  const capKey=mKey(new Date(today.getFullYear(),today.getMonth()+17,1)), endKey=mKey(dateOf(list.reduce((m,e)=>Math.max(m,e.endD??e.d),0))), lastKey=endKey<capKey?endKey:capKey;
  let k=S.calMonth||S.month||cur; if(k<cur) k=cur; if(lastKey>=cur&&k>lastKey) k=lastKey; S.calMonth=k;
  const [y,m]=k.split("-").map(Number), r=mRange(k), nd=r[1]-r[0]+1, counts=new Array(nd).fill(0);
  list.forEach(e=>{const a=Math.max(e.d,r[0]), z=Math.min(e.endD??e.d,r[1]); for(let d=a;d<=z;d++) counts[d-r[0]]++});
  const max=Math.max(1,...counts), off=(new Date(y,m-1,1).getDay()+6)%7, total=list.filter(e=>inMonth(e,r)).length, title=cap(monthLabel(k));
  let cells=off?`<span class="calpad" style="grid-column:span ${off}" aria-hidden="true"></span>`:"";
  for(let i=0;i<nd;i++){const d=r[0]+i, c=counts[i], hb=c?1+Math.min(3,Math.floor(c*4/(max+.0001))):0;
    cells+=`<button class="calday h${hb}${d===0?" today":""}" data-calday="${d}" ${d<0||!c?"disabled":""} aria-label="${dayLabel(d)}: ${c} ${LBL[S.type][c===1?0:1]}"><span>${i+1}</span><small>${c||""}</small></button>`}
  return h+`<div class="calnav"><button data-calnav="-1" aria-label="Vorige maand" ${k<=cur?"disabled":""}>‹</button><h2>${title}</h2><button data-calnav="1" aria-label="Volgende maand" ${k>=lastKey?"disabled":""}>›</button></div>
    <div class="calgrid" role="group" aria-label="${title}">${["ma","di","wo","do","vr","za","zo"].map(w=>`<span class="calwd">${w}</span>`).join("")}${cells}</div>
    <div class="meta" style="margin-top:2px"><span>${nf(total)} ${LBL[S.type][total===1?0:1]} in ${monthLabel(k)}${hidNote()}</span></div>`;
}
/* Net toegevoegd: wat de afgelopen 7 dagen voor het eerst op de agenda kwam, per dag */
function viewNew(){
  const list=filtered(true,false,false,true).filter(e=>e.age<=7).sort((a,b)=>a.age-b.age||a.d-b.d||(a.time??0)-(b.time??0));
  const sig="new|"+S.type+"|"+S.q+"|"+fcount(); if(sig!==LIM.sig){LIM.sig=sig;LIM.n=100}
  const n=LIM.n, cnt={}; list.forEach(e=>cnt[e.age]=(cnt[e.age]||0)+1);
  let h=`<div class="meta"><button data-view-go="list">‹ Agenda</button>${fcount()||S.q.trim()?'<button id="clearAll">Alles wissen</button>':""}</div><div class="vhead"><h1>Net toegevoegd</h1><div class="s">Wat de afgelopen 7 dagen nieuw op de agenda is gekomen (${TABNAME[S.type]}).</div></div><div class="meta"><span>${nf(list.length)} ${LBL[S.type][list.length===1?0:1]}${hidNote()}</span></div>`;
  if(!list.length) return h+`<div class="empty"><strong>Niets nieuws</strong>De afgelopen 7 dagen is er niets bijgekomen dat bij deze filters past.</div>`;
  let cur=null;
  list.slice(0,n).forEach(e=>{ if(e.age!==cur){cur=e.age;
      const fd=e.firstSeen.split("-").map(Number), x=new Date(fd[0],fd[1]-1,fd[2]);
      h+=`<h2 class="dh">${e.age===0?"Vandaag toegevoegd":e.age===1?"Gisteren toegevoegd":"Toegevoegd op "+WDL[x.getDay()]+" "+x.getDate()+" "+MON[x.getMonth()]} <small>${nf(cnt[e.age])}</small></h2>`+(cnt[e.age]>1500?`<p class="s" style="margin:0 0 8px">Veel op één dag: meestal komt dat doordat er een nieuw podium aan de agenda is toegevoegd.</p>`:"")}
    h+=evRow(e,{showDate:true})});
  if(list.length>n) h+=`<button class="btn ghost more" id="moreBtn">Toon meer <small>nog ${nf(list.length-n)}</small></button>`;
  return h+srcNote();
}
// Zoekopdracht: kiezen tussen alle soorten of alleen het huidige tabblad
function scopeChips(){
  if(!S.q.trim()) return "";
  return `<div class="chips scope" role="group" aria-label="Zoeken in"><button class="chip" data-qall="1" aria-pressed="${S.qAll}">Alle soorten</button><button class="chip" data-qall="0" aria-pressed="${!S.qAll}">Alleen ${TABNAME[S.type]}</button></div>`;
}
// Zoeken over alle tabbladen: per soort een kopje met de eerste treffers
const SEARCH_CAP=12;
function viewSearch(){
  const list=filtered(false,false,true), month=S.day<0&&S.month?S.month:"";
  const mc=S.day<0?monthCounts(month?filtered(false,true,true):list):[];
  let h=scopeChips()+monthBar(mc)+`<div class="meta"><span>${nf(list.length)} ${list.length===1?"resultaat":"resultaten"} voor “${esc(S.q.trim())}”${month?" in "+monthLabel(month):""}${hidNote()}</span><button id="clearAll">Alles wissen</button></div>`;
  if(!list.length) return h+`<div class="empty"><strong>Niets gevonden</strong>Geen resultaat voor “${esc(S.q.trim())}” in alle soorten. Probeer een andere naam, kies een andere datum of haal een filter weg.<br><button class="btn ghost" id="clearAll2" style="display:inline-flex;flex:0">Filters wissen</button></div>`+srcNote();
  const by={}; list.forEach(e=>(by[e.type]=by[e.type]||[]).push(e));
  const order=["pop","thea","film","expo","fest"]; if(order.includes(S.type)) order.unshift(...order.splice(order.indexOf(S.type),1));
  order.forEach(t=>{const a=by[t]; if(!a) return;
    h+=`<h2 class="dh" style="--acc:var(--${t})">${TABNAME[t]} <small>${nf(a.length)}</small></h2>`+a.slice(0,SEARCH_CAP).map(e=>evRow(e,{showDate:true,kind:true})).join("");
    if(a.length>SEARCH_CAP) h+=`<button class="btn ghost more" data-qtab="${t}" style="--acc:var(--${t})">Toon alle ${nf(a.length)} bij ${TABNAME[t]} ›</button>`});
  return h+srcNote();
}
function viewList(){
  if(S.q.trim()&&S.qAll) return viewSearch();
  const list=filtered(false), month=S.day<0&&S.month?S.month:"", mr=month?mRange(month):null;
  const mc=S.day<0?monthCounts(month?filtered(false,true):list):[];
  const sig=[S.type,S.day,month,S.q,S.sort,S.venue,S.time,S.maxTravel,S.onlyFav,S.onlyFree,[...S.genre],[...S.regio],S.hideC.size,S.hideV.size].join("|");
  if(sig!==LIM.sig){LIM.sig=sig;LIM.n=300}
  const n=LIM.n;
  let h=scopeChips()+tonightCta()+quickRow()+monthBar(mc)+`<div class="meta"><span>${nf(list.length)} ${LBL[S.type][list.length===1?0:1]}${month?" in "+monthLabel(month):""}${hidNote()}</span>${fcount()||S.q?'<button id="clearAll">Alles wissen</button>':""}</div>`;
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
function tonightList(when=TN.when,ignoreQ){
  const [a,b]=when==="today"?[0,0]:weekend(), nm=nowMin(), toks=ignoreQ?[]:qTokens();
  const timed=[], period=[];
  EV.forEach(e=>{
    if(!TN.kinds.has(e.type)||hiddenLoc(e.v)) return;
    if(e.endD!=null){ if(e.d>b||e.endD<a) return; }
    else { if(e.d<a||e.d>b) return;
      // vandaag: alleen wat nog moet beginnen of nog bezig is
      if(e.d===0&&e.time!=null&&(endOf(e)??e.time+120)<=nm) return; }
    const c=travel(e.v).car; if(c==null||c>TN.max) return;
    if(toks.length&&!matchQ(e,toks)) return;
    (e.endD!=null?period:timed).push(e);
  });
  timed.sort((x,y)=>x.d-y.d||(x.time??1e4)-(y.time??1e4)||(travel(x.v).car??999)-(travel(y.v).car??999));
  period.sort((x,y)=>(travel(x.v).car??999)-(travel(y.v).car??999)||x.d-y.d);
  return {timed,period};
}
function viewTonight(){
  const {timed,period}=tonightList(), nm=nowMin(), wk=TN.when!=="today", qs=S.q.trim();
  const home=S.home==="__geo"?"je locatie":S.home;
  const chip=(attr,val,on,lab,style="")=>`<button class="chip" ${attr}="${val}" aria-pressed="${on}"${style}>${lab}</button>`;
  let h=`<div class="meta"><button data-view-go="list">‹ Agenda</button></div>
    <div class="vhead"><h1>${wk?"Dit weekend":"Vanavond"} in de buurt</h1><div class="s">Alles binnen ${TN.max} min rijden vanaf ${esc(home)}, over alle soorten heen${wk?"":", vanaf nu"}.</div></div>
    <div class="tnbar"><div class="chips">${chip("data-tn-when","today",!wk,"Vandaag")+chip("data-tn-when","weekend",wk,"Dit weekend")}</div>
    <div class="chips">${[15,30,45].map(m=>chip("data-tn-max",m,TN.max===m,m+" min")).join("")}</div></div>
    <div class="chips tnkinds">${Object.entries(KIND).map(([k,l])=>chip("data-tn-kind",k,TN.kinds.has(k),l,` style="--acc:var(--${k})"`)).join("")}</div>
    <div class="meta"><span>${timed.length} met een tijd${period.length?`, ${period.length} doorlopend`:""}${hidNote()}${qs?` voor “${esc(qs)}”`:""}</span>${qs?'<button id="tnClearQ">Zoekterm wissen</button>':""}</div>`;
  if(!timed.length&&!period.length) return h+`<div class="empty"><strong>Niets gevonden</strong>Niets meer binnen ${TN.max} min ${wk?"dit weekend":"vandaag"}${qs?` voor “${esc(qs)}”`:""}. ${qs?"Wis de zoekterm of kies":"Kies"} een grotere afstand${wk?"":" of Dit weekend"}.${qs?'<br><button class="btn ghost" id="tnClearQ" style="display:inline-flex;flex:0">Zoekterm wissen</button>':""}</div>`;
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
  return `<button class="tncta" data-view-go="tonight"><svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><path d="M20 14.5A8 8 0 1 1 9.5 4a6.5 6.5 0 0 0 10.5 10.5z"/></svg><span><b>Vanavond in de buurt</b><small>${timed.length} ${timed.length===1?"ding":"dingen"} binnen ${TN.max} min, ${S.q.trim()?"voor “"+esc(S.q.trim())+"”":"alle soorten samen"}</small></span><i aria-hidden="true">›</i></button>`;
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
function plansBlock(){
  pruneGo();
  const ids=Object.keys(GO);
  let h=`<h2 class="dh" style="margin-top:6px">Mijn plannen${ids.length?` <small>${ids.length}</small>`:""}</h2>`;
  if(!ids.length) return h+`<p class="s" style="margin:0">Tik in een event op ‘Ik ga’. Je plannen staan dan hier, met een waarschuwing als twee plannen overlappen. Alles in één keer in je agenda zetten kan ook.</p>`;
  const have=ids.map(id=>BYID.get(id)).filter(Boolean).sort((a,b)=>a.d-b.d||(a.time??0)-(b.time??0));
  const timed=have.filter(e=>e.time!=null&&e.endD==null);
  // Overlap in absolute minuten, dus ook als een avond na middernacht doorloopt
  const span=x=>[x.d*1440+x.time, x.d*1440+(endOf(x)??x.time+120)];
  const clash=e=>{ if(e.time==null||e.endD!=null) return ""; const [a,z]=span(e); const o=timed.find(x=>{ if(x===e) return false; const [b,y]=span(x); return a<y&&b<z }); return o?"⚠ Overlapt met "+o.artist:"" };
  h+=have.map(e=>evRow(e,{showDate:true,reason:clash(e),warn:true})).join("");
  ids.filter(id=>!BYID.has(id)).forEach(id=>{const g=GO[id], dd=g.d.split("-").map(Number), x=new Date(dd[0],dd[1]-1,dd[2]);
    h+=`<div class="ev gone"><div class="t">${x.getDate()} ${MON[x.getMonth()]}<small>weg</small></div><div><div class="a">${esc(g.t||"Onbekend")}</div>${g.v?`<div class="v">${esc(g.v)}</div>`:""}<div class="s">Niet meer gevonden in de agenda</div></div><button class="star" data-go-del="${esc(id)}" aria-label="Haal ${esc(g.t||"dit plan")} uit je plannen">✕</button></div>`});
  if(timed.length) h+=`<button class="btn ghost more" id="icsAll" type="button">Alles in agenda zetten <small>${timed.length}</small></button>`;
  const skip=have.length-timed.length; if(timed.length&&skip>0) h+=`<p class="s" style="margin:6px 0 0">${skip} ${skip===1?"plan":"plannen"} zonder vaste starttijd ${skip===1?"staat":"staan"} er niet in.</p>`;
  return h;
}
function viewFav(){
  let h=plansBlock();
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
  return h;
}
/* ---------- PODIA ---------- */
// Eén regel per podium; zelfde naam en stad (bv. podium + eigen filmzaal) samen
const VKIND={pop:"Poppodium",concert:"Concertzaal",arena:"Arena",cafe:"Café",thea:"Theater",film:"Bioscoop / filmhuis",museum:"Museum",festival:"Festival"};
const VGROUPS=[{k:"",l:"Alles"},{k:"muz",l:"Muziek",t:["pop","concert","arena","cafe"]},{k:"thea",l:"Theater",t:["thea"]},{k:"film",l:"Film",t:["film"]},{k:"museum",l:"Musea",t:["museum"]},{k:"festival",l:"Festivals",t:["festival"]}];
const VG=(()=>{const m={}; EV.forEach(e=>{const v=V[e.v]; const k=(v.name+"|"+v.city).toLowerCase();
  const g=m[k]||(m[k]={key:k,name:v.name,city:v.city,type:v.type,ids:new Set(),n:0,next:null,hay:norm(v.name+" "+v.city+" "+CITY_AKA(v.city))}); g.ids.add(e.v); g.n++;
  if(!g.next||e.d<g.next.d) g.next=e}); return Object.values(m)})();
const vgOf=vid=>{const v=V[vid]; return (v.name+"|"+v.city).toLowerCase()};
const VCOL={pop:"pop",concert:"pop",arena:"pop",cafe:"pop",thea:"thea",film:"film",museum:"expo",festival:"fest"};
const vStar=(g,big)=>`<button class="star${big?" big":""}" data-favv="${esc(g.key)}" data-name="${esc(g.name)}" aria-pressed="${S.favV.has(g.key)}" aria-label="Volg podium ${esc(g.name)}">★</button>`;
function venueList(){
  const toks=qTokens(), grp=VGROUPS.find(x=>x.k===S.vkind)||VGROUPS[0];
  return VG.filter(g=>(!grp.t||grp.t.includes(g.type))&&(!toks.length||toks.every(t=>g.hay.includes(t))))
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
  if(!S.q.trim()) S.qAll=true;
  ["thea","film","expo","fest","kids"].forEach(t=>document.body.classList.toggle(t,S.type===t));
  document.querySelectorAll(".seg [data-type]").forEach(b=>b.setAttribute("aria-pressed",b.dataset.type===S.type));
  const navV=["tonight","cal","new"].includes(S.view)?"list":S.view;
  document.querySelectorAll("nav.tabs button").forEach(b=>b.dataset.view===navV?b.setAttribute("aria-current","page"):b.removeAttribute("aria-current"));
  const n=fcount(); $("#fcount").hidden=!n; $("#fcount").textContent=n;
  $("#newDot").hidden=!EV.some(e=>NEW.has(e.id)&&(isFav(e)||alarmHit(e)||isFavV(e)));
  document.body.classList.toggle("venues",S.view==="venues");
  document.body.classList.toggle("tonight",S.view==="tonight");
  document.body.classList.toggle("favview",S.view==="fav");
  $("#dates").style.display=["fav","venues","tonight","cal","new"].includes(S.view)?"none":"flex";
  renderDates();
  $("#main").innerHTML=staleBanner()+(S.view==="list"?viewList():S.view==="grid"?viewGrid():S.view==="venues"?viewVenues():S.view==="tonight"?viewTonight():S.view==="cal"?viewCal():S.view==="new"?viewNew():viewFav());
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
/* Eén geschiedenisstap per open scherm: de terugknop (of veegbeweging) van de telefoon sluit dan het scherm in plaats van de app */
let sheetPushed=false, backing=false;
function openSheet(id){$("#scrim").classList.add("open");$(id).classList.add("open");
  if(!sheetPushed){try{history.pushState({prSheet:1},"");sheetPushed=true}catch{}}}
function closeSheets(fromPop){$("#scrim").classList.remove("open");document.querySelectorAll(".sheet").forEach(s=>s.classList.remove("open"));
  if(sheetPushed){sheetPushed=false; if(fromPop!==true){backing=true; setTimeout(()=>backing=false,1500); try{history.back()}catch{backing=false}}}
  stripHash()}
function stripHash(){if(location.hash) try{history.replaceState(null,"",location.pathname+location.search)}catch{}}
// Alleen opruimen na een terugstap die wij zelf deden of die het scherm sloot; een #-link in een open app moet gewoon het item openen
window.addEventListener("popstate",()=>{ if(sheetPushed) closeSheets(true); else if(backing){backing=false; stripHash()} });
document.addEventListener("click",e=>{if(e.target.closest("[data-close]")) closeSheets()});
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
/* Route (Google Maps, op het podium zelf) en luisteren (zoeklink; er gaat niets vanuit de app naar die diensten) */
const ICO={pin:'<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><path d="M12 21s-7-6.2-7-11.5A7 7 0 0 1 19 9.5C19 14.8 12 21 12 21z"/><circle cx="12" cy="9.5" r="2.5"/></svg>',
  play:'<svg viewBox="0 0 24 24" width="16" height="16" fill="currentColor" aria-hidden="true"><path d="M8 5v14l11-7z"/></svg>',
  dice:'<svg viewBox="0 0 24 24" width="17" height="17" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><rect x="4" y="4" width="16" height="16" rx="3"/><circle cx="9" cy="9" r="1" fill="currentColor"/><circle cx="15" cy="15" r="1" fill="currentColor"/><circle cx="15" cy="9" r="1" fill="currentColor"/><circle cx="9" cy="15" r="1" fill="currentColor"/></svg>',
  cal:'<svg viewBox="0 0 24 24" width="17" height="17" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><rect x="3.5" y="5" width="17" height="15" rx="2.5"/><path d="M3.5 10h17M8 3v4M16 3v4"/></svg>',
  spark:'<svg viewBox="0 0 24 24" width="17" height="17" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><path d="M12 3l1.9 5.1L19 10l-5.1 1.9L12 17l-1.9-5.1L5 10l5.1-1.9zM18 16l.8 2.2L21 19l-2.2.8L18 22l-.8-2.2L15 19l2.2-.8z"/></svg>'};
/* Logo's van de diensten waar de knoppen naartoe linken (Simple Icons, CC0); kleuren staan in de CSS (.b-spotify, .b-youtube, .b-maps) */
const LOGO={
  spotify:'<svg viewBox="0 0 24 24" width="20" height="20" fill="currentColor" aria-hidden="true"><path d="M12 0C5.4 0 0 5.4 0 12s5.4 12 12 12 12-5.4 12-12S18.66 0 12 0zm5.521 17.34c-.24.359-.66.48-1.021.24-2.82-1.74-6.36-2.101-10.561-1.141-.418.122-.779-.179-.899-.539-.12-.421.18-.78.54-.9 4.56-1.021 8.52-.6 11.64 1.32.42.18.479.659.301 1.02zm1.44-3.3c-.301.42-.841.6-1.262.3-3.239-1.98-8.159-2.58-11.939-1.38-.479.12-1.02-.12-1.14-.6-.12-.48.12-1.021.6-1.141C9.6 9.9 15 10.561 18.72 12.84c.361.181.54.78.241 1.2zm.12-3.36C15.24 8.4 8.82 8.16 5.16 9.301c-.6.179-1.2-.181-1.38-.721-.18-.601.18-1.2.72-1.381 4.26-1.26 11.28-1.02 15.721 1.621.539.3.719 1.02.419 1.56-.299.421-1.02.599-1.559.3z"/></svg>',
  youtube:'<svg viewBox="0 0 24 24" width="22" height="22" fill="currentColor" aria-hidden="true"><path d="M23.498 6.186a3.016 3.016 0 0 0-2.122-2.136C19.505 3.545 12 3.545 12 3.545s-7.505 0-9.377.505A3.017 3.017 0 0 0 .502 6.186C0 8.07 0 12 0 12s0 3.93.502 5.814a3.016 3.016 0 0 0 2.122 2.136c1.871.505 9.376.505 9.376.505s7.505 0 9.377-.505a3.015 3.015 0 0 0 2.122-2.136C24 15.93 24 12 24 12s0-3.93-.502-5.814zM9.545 15.568V8.432L15.818 12l-6.273 3.568z"/></svg>',
  maps:'<svg viewBox="0 0 24 24" width="20" height="20" aria-hidden="true"><path fill="#FBBC04" d="M19.527 4.799c1.212 2.608.937 5.678-.405 8.173-1.101 2.047-2.744 3.74-4.098 5.614-.619.858-1.244 1.75-1.669 2.727-.141.325-.263.658-.383.992-.121.333-.224.673-.34 1.008-.109.314-.236.684-.627.687h-.007c-.466-.001-.579-.53-.695-.887-.284-.874-.581-1.713-1.019-2.525-.51-.944-1.145-1.817-1.79-2.671L19.527 4.799z"/><path fill="#34A853" d="M8.545 7.705l-3.959 4.707c.724 1.54 1.821 2.863 2.871 4.18.247.31.494.622.737.936l4.984-5.925-.029.01c-1.741.601-3.691-.291-4.392-1.987a3.377 3.377 0 0 1-.209-.716c-.063-.437-.077-.761-.004-1.198l.001-.007z"/><path fill="#1A73E8" d="M5.492 3.149l-.003.004c-1.947 2.466-2.281 5.88-1.117 8.77l4.785-5.689-.058-.05-3.607-3.035z"/><path fill="#4285F4" d="M14.661.436l-3.838 4.563a.295.295 0 0 1 .027-.01c1.6-.551 3.403.15 4.22 1.626.176.319.323.683.377 1.045.068.446.085.773.012 1.22l-.003.016 3.836-4.561A8.382 8.382 0 0 0 14.67.439l-.009-.003z"/><path fill="#EA4335" d="M9.466 5.868L14.162.285l-.047-.012A8.31 8.31 0 0 0 11.986 0a8.439 8.439 0 0 0-6.169 2.766l-.016.018 3.665 3.084z"/></svg>'};
const mapUrl=v=>v.lat!=null&&v.lon!=null?`https://www.google.com/maps/dir/?api=1&destination=${v.lat},${v.lon}`:"https://www.google.com/maps/search/?api=1&query="+encodeURIComponent(v.name+", "+v.city);
const NOT_MUSIC=/workshop|lezing|cursus|quiz|bingo|borrel|lunch|diner|rondleiding|open dag|proefles|clinic|filmavond|tentoonstelling|expositie|vergadering|netwerk|markt|\wbeurs\b|yoga|game night|jam ?sessi(e|on)|open (mic|podium|stage)|proeverij|proefavond|springkussen|boekenclub|(hedon|nacht) academy|publieke tribune|masterclass|^(ajax|vitesse)\s+-\s|social dance|spelletjes|vaccinatie|science caf|subsidie|boekpresentatie|podcast|business club|\bmeeting\b|protestborden|woonprotest|stadssafari|crafternoon|design week|\bddw\b|cultuurnacht|museumnacht/i;
/* Spotify: scraper/spotify.py zoekt 's nachts per artiest op of die op Spotify staat (site/spotify.json:
   found = id, none = niet gevonden, skip = handmatig verborgen). Per event dus:
   link = direct naar de artiest, none = grijze knop, search = zoeklink, skip = geen Spotify-knop.
   Zonder bestand (nog geen sleutels ingesteld) blijft het een zoeklink. De regels hieronder zijn dezelfde als basis() en
   eligible() in scraper/spotify.py (NOT_MUSIC, SERIE en de genres staan op twee plaatsen!). */
// Titel 'Voorstelling - Artiest' (klassiek, cabaret, comedy, tribute): het deel voor het streepje is meestal de voorstelling, dus geen artiest
const showFirst=e=>/ - /.test(e.title)&&["Klassiek","Cabaret","Comedy","Tribute"].includes(e.genre);
const SERIE=/comedy|cabaret|stand-?up|try-?out|conferen|caf[eé]\b|\bclub\b|night|train\b|kwis/i;   // reeksen en avonden, geen artiest (alleen bij cabaret/comedy)
const isCab=e=>e.genre==="Cabaret"||e.genre==="Comedy";
const spotBase=e=>!!e.artist&&!e.isFest&&e.type!=="film"&&e.type!=="expo"&&e.type!=="fest"&&!NOT_MUSIC.test(e.title)&&(isCab(e)||(e.type==="pop"&&e.genre!=="Feest"&&e.genre!=="Lezing"));
let SPOT=null, lastDetail=null;
const SPOT_ID=/^[A-Za-z0-9]{22}$/;
// Zoeknaam voor de links: zonder 'datum ✦ zaal'-ruis en backslashes; bij 'Voorstelling - Artiest' de hele titel
const linkName=e=>String(showFirst(e)?e.title:e.artist).split(" ✦ ")[0].replace(/\\/g,"").trim();
const linkRow=e=>`<a class="btn brand b-maps" href="${esc(mapUrl(V[e.v]))}" target="_blank" rel="noopener noreferrer">${LOGO.maps}Route</a>${spotBtn(e)}${ytBtn(e)}`;
fetch("spotify.json",{cache:"no-cache"}).then(r=>r.ok?r.json():null).then(j=>{
  if(!j||j.v!==1||!j.found||typeof j.found!=="object") return;
  SPOT={found:new Map(Object.entries(j.found).filter(([,v])=>typeof v==="string"&&SPOT_ID.test(v))),none:new Set(Array.isArray(j.none)?j.none:[]),skip:new Set(Array.isArray(j.skip)?j.skip:[])};
  // Detailscherm stond al open: alleen de knoppenrij bijwerken (scrollstand en focus blijven)
  const d=lastDetail&&BYID.get(lastDetail.id), r=$("#linkRow");
  if(d&&r&&$("#detailSheet").classList.contains("open")){const h=linkRow(d); if(h!==lastDetail.row){r.innerHTML=h; lastDetail.row=h}}
}).catch(()=>{});
function spotState(e){
  if(!spotBase(e)) return {k:"skip"};
  if(showFirst(e)) return {k:"search"};                       // de titel is de voorstelling: geen artiest opzoeken
  if(isCab(e)&&SERIE.test(e.artist)) return {k:"skip"};       // reeks of avond, geen artiest
  if(!SPOT) return {k:"search"};
  if(SPOT.skip.has(e.ak)) return {k:"skip"};
  const id=SPOT.found.get(e.ak);
  if(id) return {k:"link",id};
  return SPOT.none.has(e.ak)?{k:"none"}:{k:"search"};   // nog niet opgezocht of niet in het bestand: gewone zoeklink
}
function spotBtn(e){
  const st=spotState(e);
  if(st.k==="skip") return "";
  if(st.k==="link") return `<a class="btn brand b-spotify" href="https://open.spotify.com/artist/${st.id}" target="_blank" rel="noopener noreferrer">${LOGO.spotify}Spotify</a>`;
  if(st.k==="none") return `<button class="btn ghost" type="button" disabled aria-label="Spotify: ${esc(e.artist)} is niet gevonden op Spotify">${LOGO.spotify}<span>Spotify<small>niet gevonden</small></span></button>`;
  return `<a class="btn brand b-spotify" href="https://open.spotify.com/search/${encodeURIComponent(linkName(e))}" target="_blank" rel="noopener noreferrer">${LOGO.spotify}Spotify</a>`;
}
// YouTube kan niet vooraf gecontroleerd worden: altijd een zoeklink (bij films: de trailer)
function ytBtn(e){
  if(e.type==="film") return `<a class="btn brand b-youtube" href="https://www.youtube.com/results?search_query=${encodeURIComponent(e.title+" trailer")}" target="_blank" rel="noopener noreferrer">${LOGO.youtube}Trailer</a>`;
  if(spotState(e).k==="skip") return "";
  return `<a class="btn brand b-youtube" href="https://www.youtube.com/results?search_query=${encodeURIComponent(linkName(e))}" target="_blank" rel="noopener noreferrer">${LOGO.youtube}YouTube</a>`;
}
function openDetail(id,o={}){
  lastDetail={id,o};
  const e=BYID.get(id), v=V[e.v], tr=travel(e.v), going=!!GO[e.id];
  const sl=slots(e);
  const tl=sl.length?sl.map(s=>`<div class="slot${s.k==="main"?" key":""}"><time>${hm(s.s)}</time>${s.a?`<strong>${esc(s.a)}</strong> <span class="s">${s.l.toLowerCase()}</span>`:esc(s.l)} ${s.est?'<span class="est">geschat</span>':""}</div>`).join("")
    :`<p class="s">De tijden zijn nog niet bekend bij de bron. Check de pagina van het podium.</p>`;
  const sims=similar(e);
  $("#detailSheet").innerHTML=`<div class="sheetbar"><button class="sheetx" type="button" data-close><svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" aria-hidden="true"><path d="M6 6l12 12M18 6 6 18"/></svg>Sluiten</button><div class="grab"></div></div>
   ${o.surprise?`<div class="surp" style="--acc:var(--${e.type});--acc-soft:var(--${e.type}-soft)">🎲 Verrassing voor ${o.surprise}, in de buurt</div>`:""}
   <div class="dhead"><div><div class="dsub">${range(e)?(e.started?"Nu te zien, ":"")+range(e):dayLabel(e.d)}</div><div class="dtitle">${esc(e.artist)}</div>
     ${e.title!==e.artist?`<div class="dsub">${esc(e.title)}</div>`:""}
     <div class="dsub">${esc(v.name)}, ${esc(v.city)} · <button class="linkbtn" data-openvenue="${esc(vgOf(e.v))}">Alles bij dit podium</button></div></div>
     <button class="star" data-fav="${e.ak}" data-name="${esc(e.artist)}" aria-pressed="${S.fav.has(e.ak)}" aria-label="Volg ${esc(e.artist)}" style="font-size:30px">★</button></div>
   <div class="facts"><div><small>Genre</small><b>${esc(e.genre)}</b></div>${tr.car!=null?`<div><small>Auto</small><b>± ${tr.car} min</b></div><div><small>OV</small><b>± ${tr.ov} min</b></div>`:""}${e.price!=null?`<div><small>${e.price===0?"Entree":"Prijs vanaf"}</small><b>${priceTxt(e.price)}</b></div>`:""}${e.status==="sold"?`<div><small>Kaarten</small><b style="color:var(--warn)">Uitverkocht</b></div>`:""}</div>
   ${tr.car!=null?`<p class="s travnote">Reistijd is een schatting vanaf ${S.home==="__geo"?"je opgeslagen locatie":esc(S.home)} (afstand hemelsbreed). Google Maps rekent vanaf waar je nu bent, met verkeer en dienstregeling.</p>`:""}
   <div class="timeline">${tl}</div>
   <div class="row2"><a class="btn" href="${esc(e.url)}" target="_blank" rel="noopener noreferrer">Info en kaarten bij ${esc(V[e.v].name)}</a></div>
   <div class="row2" style="margin-top:10px"><button class="btn ghost go" id="goBtn" type="button" aria-pressed="${going}">${going?"✓ Ik ga":"Ik ga"}</button>${o.surprise?`<button class="btn ghost" id="surpBtn" type="button">${ICO.dice}Nog een verrassing</button>`:""}</div>
   <div class="row2 wrapr" id="linkRow" style="margin-top:10px">${linkRow(e)}</div>
   <div class="row2" style="margin-top:10px">${e.time!=null?`<button class="btn ghost" id="icsBtn">Zet in agenda</button><a class="btn ghost" id="gcal" target="_blank" rel="noopener">Google Agenda</a>`:`<p class="s">Agenda-knop verschijnt zodra de tijd bekend is.</p>`}</div>
   <div class="row2" style="margin-top:10px"><button class="btn ghost" id="shareBtn" type="button">Delen</button><button class="btn ghost" id="wrongBtn" type="button">Klopt niet?</button></div>
   <p class="note">Gegevens van ${SNAPSHOT}, overgenomen van de site van ${esc(V[e.v].name)}. Tijden, prijzen en beschikbaarheid kunnen veranderen: kijk altijd op die site voordat je gaat of kaarten koopt.${DATA.verouderd&&/^\d{4}-\d\d-\d\d$/.test(DATA.verouderd[e.v]||"")?` <strong>Let op: de site van dit podium was de laatste dagen niet uit te lezen; deze gegevens zijn van ${dm(new Date(DATA.verouderd[e.v]+"T12:00"))} of eerder.</strong>`:""}</p>
   <h3>Vergelijkbaar en dichtbij</h3>
   <div class="simlist">${sims.length?sims.map(o=>`<div class="ev" role="button" tabindex="0" data-ev="${o.id}"><div><div class="a">${esc(o.artist)}</div><div class="v">${short(o)}, ${esc(V[o.v].name)} ${travel(o.v).car!=null?"(± "+travel(o.v).car+" min)":""}</div></div><button class="star" data-fav="${o.ak}" data-name="${esc(o.artist)}" aria-pressed="${S.fav.has(o.ak)}" aria-label="Volg ${esc(o.artist)}">★</button></div>`).join(""):'<p class="s">Geen genre-match in de huidige agenda.</p>'}</div>`;
  if(e.time!=null){ $("#gcal").href=gcalUrl(e); $("#icsBtn").onclick=()=>saveIcs(e); }
  lastDetail.row=linkRow(e);
  $("#shareBtn").onclick=()=>share(e);
  $("#wrongBtn").onclick=()=>reportWrong(e);
  $("#goBtn").onclick=ev=>{toggleGoing(e); const on=!!GO[e.id], b=ev.currentTarget; b.setAttribute("aria-pressed",on); b.textContent=on?"✓ Ik ga":"Ik ga"};
  if(o.surprise) $("#surpBtn").onclick=()=>surprise(true);
  openSheet("#detailSheet"); $("#detailSheet").scrollTop=0;
}
/* "Klopt niet?": een kant-en-klaar bericht (deelmenu of kopiëren) voor degene die je de link gaf; er wordt niets gepubliceerd */
const whenTxt=e=>e.endDate?(e.started?"nu":short(e))+" t/m "+dm(e.endDate):short(e)+(e.date.getFullYear()!==today.getFullYear()?" "+e.date.getFullYear():"");
function reportText(e){
  const v=V[e.v];
  return ["Klopt niet in Podiumradar: "+e.title+" ("+v.name+", "+e.rawDate+")",
    "Datum: "+e.rawDate+(e.endDate?" t/m "+e.endDate.getFullYear()+"-"+String(e.endDate.getMonth()+1).padStart(2,"0")+"-"+String(e.endDate.getDate()).padStart(2,"0"):"")+" ("+whenTxt(e)+")",
    "Tijd: "+(e.time!=null?hm(e.time):"onbekend"),"Podium: "+v.name+", "+v.city,"Bron: "+(e.url!=="#"?e.url:"geen link"),"","Wat klopt er niet? "].join("\n");
}
/* Delen: deelmenu van het toestel, anders kopiëren. De link opent de app met dit item (#id). */
const appLink=e=>location.origin+location.pathname+"#"+encodeURIComponent(e.id);
function shareText(e){const v=V[e.v];
  const wd=e.endDate?whenTxt(e):WDL[e.date.getDay()]+" "+dm(e.date)+(e.time!=null?" "+hm(e.time):"");
  return `${e.artist} — ${wd}, ${v.name} ${v.city}`+(e.url!=="#"?"\n"+e.url:"")}
async function sendOut(title,text,url,okMsg){
  if(navigator.share){ try{ await navigator.share({title,text,url}); return }catch(err){ if(err&&err.name==="AbortError") return } }
  const all=text+"\n"+url;
  try{ await navigator.clipboard.writeText(all); toast(okMsg); return }catch{}
  try{ const ta=document.createElement("textarea"); ta.value=all; ta.setAttribute("readonly",""); ta.style.cssText="position:fixed;opacity:0;top:0"; document.body.appendChild(ta); ta.select();
    const ok=document.execCommand("copy"); ta.remove(); if(ok){toast(okMsg);return} }catch{}
  toast("Delen lukt hier niet. Kopieer de link uit de adresbalk.");
}
const share=e=>sendOut(e.artist,shareText(e),appLink(e),"Gekopieerd: plak het in een bericht");
const reportWrong=e=>sendOut("Klopt niet",reportText(e),appLink(e),"Gekopieerd: plak het in een bericht aan degene die je de link gaf");
function dt(e,min){const x=new Date(e.date);x.setMinutes(min);return x}
const utc=x=>x.toISOString().replace(/[-:]/g,"").replace(/\.\d{3}/,"");
const descr=e=>slots(e).map(s=>hm(s.s)+" "+(s.a||s.l)+(s.est?" (geschat)":"")).join("\n")+"\n\n"+e.url;
function gcalUrl(e){const v=V[e.v];return "https://calendar.google.com/calendar/render?action=TEMPLATE&text="+encodeURIComponent(e.artist+" @ "+v.name)+"&dates="+utc(dt(e,e.time))+"/"+utc(dt(e,endOf(e)))+"&location="+encodeURIComponent(v.name+", "+v.city)+"&details="+encodeURIComponent(descr(e))}
const icsEsc=t=>String(t).replace(/\\/g,"\\\\").replace(/[;,]/g,"\\$&").replace(/\n/g,"\\n");
function vevent(e){const v=V[e.v], tr=travel(e.v);
  return ["BEGIN:VEVENT","UID:"+e.id+"@podiumradar","DTSTAMP:"+utc(new Date()),"DTSTART:"+utc(dt(e,e.time)),"DTEND:"+utc(dt(e,endOf(e))),
    "SUMMARY:"+icsEsc(e.artist+" @ "+v.name),"LOCATION:"+icsEsc(v.name+", "+v.city),...(e.url!=="#"?["URL:"+e.url]:[]),"DESCRIPTION:"+icsEsc(descr(e)),
    "BEGIN:VALARM","TRIGGER:-PT"+((tr.car||30)+30)+"M","ACTION:DISPLAY","DESCRIPTION:"+icsEsc("Vertrekken naar "+e.artist),"END:VALARM","END:VEVENT"]}
const icsDoc=evs=>["BEGIN:VCALENDAR","VERSION:2.0","PRODID:-//Podiumradar//NL",...evs.flatMap(vevent),"END:VCALENDAR"].join("\r\n");
// Bestand aanbieden als gewone download; geeft true als het is aangeboden
async function deliverIcs(ics,name,msgDownloaded){
  const url=URL.createObjectURL(new Blob([ics],{type:"text/calendar"})), a=document.createElement("a");a.href=url;a.download=name;document.body.appendChild(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(url),4000);toast(msgDownloaded);return true;
}
async function saveIcs(e){
  const ok=await deliverIcs(icsDoc([e]),e.artist.replace(/[^\w\- ]/g,"")+".ics","Agendabestand gedownload, met vertrekherinnering");
  if(ok===false) window.open(gcalUrl(e),"_blank","noopener");
}
async function saveIcsAll(list){
  if(!list.length){toast("Geen plannen met een tijd om in je agenda te zetten");return}
  const pl=list.length+(list.length===1?" plan":" plannen");
  const ok=await deliverIcs(icsDoc(list),"Podiumradar-plannen.ics",pl+" als agendabestand gedownload, met vertrekherinnering",pl+" klaar als agendabestand");
  if(ok===false) toast("Downloaden lukt hier niet. Zet ze één voor één in je agenda.");
}

function setupFav(){
  const add=()=>{const v=$("#alarmIn").value.trim(); if(!v) return; if(!S.alarms.includes(v)) S.alarms.push(v); store.set("pr_alarms",S.alarms); toast("Alarm gezet voor "+v); render();};
  $("#alarmAdd").onclick=add; $("#alarmIn").onkeydown=e=>{if(e.key==="Enter") add()};
  const ms=$("#markSeen"); if(ms) ms.onclick=markSeen;
  const ia=$("#icsAll"); if(ia) ia.onclick=()=>saveIcsAll(Object.keys(GO).map(id=>BYID.get(id)).filter(e=>e&&e.time!=null&&e.endD==null).sort((a,b)=>a.d-b.d||a.time-b.time));
}

/* ---------- EVENTS ---------- */
document.addEventListener("click",e=>{
  const fv=e.target.closest("[data-favv]"); if(fv){e.stopPropagation(); toggleFavV(fv.dataset.favv,fv.dataset.name||"Podium"); return}
  const vm=e.target.closest("[data-vmode]"); if(vm){S.vmode=vm.dataset.vmode; store.set("pr_vmode",S.vmode); render(); return}
  const zb=e.target.closest("[data-zoom]"); if(zb&&NL&&$("#nlmap")){const z=zb.dataset.zoom;
    if(z==="in") zoomBy(1/1.6); else if(z==="out") zoomBy(1.6);
    else if(z==="home"){const [x,y]=proj(S.homeXY[0],S.homeXY[1]); zoomTo(x,y,NL.w/4)} else {MAPV.vb=[0,0,NL.w,NL.h]; applyView()}
    return}
  const go=e.target.closest("[data-view-go]"); if(go){if(go.classList.contains("tncta")) TN.when="today"; if(go.dataset.viewGo==="cal"){ if(S.month) S.calMonth=S.month; else if(S.day>=0) S.calMonth=mKey(dateOf(S.day)) } S.view=go.dataset.viewGo; render(); try{window.scrollTo(0,0)}catch{} showDay(); return}
  const tw=e.target.closest("[data-tn-when]"); if(tw){TN.when=tw.dataset.tnWhen; render(); return}
  const tm=e.target.closest("[data-tn-max]"); if(tm){TN.max=+tm.dataset.tnMax; store.set("pr_tnmax",TN.max); render(); return}
  const tk=e.target.closest("[data-tn-kind]"); if(tk){const k=tk.dataset.tnKind; TN.kinds.has(k)?TN.kinds.delete(k):TN.kinds.add(k); if(!TN.kinds.size) TN.kinds.add(k); render(); return}
  if(e.target.id==="freeOff"){S.onlyFree=false; render(); return}
  const f=e.target.closest("[data-fav]"); if(f){e.stopPropagation(); const ak=f.dataset.fav; toggleFav(ak,f.dataset.name||favName(ak));
    document.querySelectorAll(`#detailSheet [data-fav="${ak}"]`).forEach(b=>b.setAttribute("aria-pressed",S.fav.has(ak))); return}
  const al=e.target.closest("[data-alarm]"); if(al){S.alarms.splice(+al.dataset.alarm,1);store.set("pr_alarms",S.alarms);render();return}
  const ev=e.target.closest("[data-ev]"); if(ev){openDetail(ev.dataset.ev);return}
  // Datum gekozen: naar het begin van de nieuwe lijst; is de kop ingeklapt, dan blijft alleen de datumrij staan (anders zit de volgende tik op de soortknoppen)
  const d=e.target.closest(".day"); if(d){dayHold=null;const kb=d.matches(":focus-visible"), hd=$("header"), top=hd.classList.contains("tuck")?$("#dates").offsetTop:0;
    S.day=+d.dataset.d;S.month="";render();
    if(scrollY>top){if(top) hd.dataset.hold="1"; try{window.scrollTo(0,top)}catch{}}
    const c=kb&&document.querySelector(`#dates [data-d="${S.day}"]`); if(c) c.focus({preventScroll:true}); return}
  // Met het toetsenbord gekozen: focus terug op de gekozen maand (bij tikken geen focusrand)
  if(e.target.closest("[data-surprise]")){surprise(); return}
  const gd=e.target.closest("[data-go-del]"); if(gd){delete GO[gd.dataset.goDel]; store.set("pr_going",GO); render(); return}
  const cn=e.target.closest("[data-calnav]"); if(cn){const kb=cn.matches(":focus-visible"), dir=cn.dataset.calnav, [cy,cm]=(S.calMonth||mKey(today)).split("-").map(Number); S.calMonth=mKey(new Date(cy,cm-1+(+dir),1)); render();
    if(kb){const c=document.querySelector(`[data-calnav="${dir}"]:not([disabled])`)||document.querySelector("[data-calnav]:not([disabled])"); if(c) c.focus({preventScroll:true})} return}
  const cd=e.target.closest("[data-calday]"); if(cd){S.day=+cd.dataset.calday;S.month="";S.view="list";if(S.q.trim())S.qAll=false;render();try{window.scrollTo(0,0)}catch{}
    showDay(); return}
  const qa=e.target.closest("[data-qall]"); if(qa){const kb=qa.matches(":focus-visible"), v=qa.dataset.qall; S.qAll=v==="1"; render(); if(kb){const c=document.querySelector(`.scope [data-qall="${v}"]`); if(c) c.focus({preventScroll:true})} return}
  const qb=e.target.closest("[data-qtab]"); if(qb){S.type=qb.dataset.qtab;S.qAll=false;render();try{window.scrollTo(0,0)}catch{};return}
  const mo=e.target.closest("[data-month]"); if(mo){const top=mo.hasAttribute("data-month-top"), kb=mo.matches(":focus-visible"); S.month=mo.dataset.month;S.day=-1;render();if(top){try{window.scrollTo(0,0)}catch{}}
    const c=kb&&(document.querySelector(`.months [data-month="${S.month}"]`)||document.querySelector("#main .ev")); if(c) c.focus({preventScroll:true}); return}
  const mb=e.target.closest("#moreBtn"); if(mb){const kb=mb.matches(":focus-visible"), c=document.querySelectorAll("#main .ev").length; LIM.n+=300; render(); const nx=document.querySelectorAll("#main .ev")[c]; if(nx) nx.focus({preventScroll:true,focusVisible:kb}); return}
  const vk=e.target.closest("[data-vkind]"); if(vk){S.vkind=vk.dataset.vkind;render();return}
  const vb=e.target.closest("[data-vback]"); if(vb){S.venuePage=null;render();try{window.scrollTo(0,0)}catch{};return}
  const ov=e.target.closest("[data-openvenue]"); if(ov){closeSheets();S.view="venues";S.venuePage=ov.dataset.openvenue;S.q="";$("#q").value="";render();try{window.scrollTo(0,0)}catch{};return}
  const vn=e.target.closest("[data-venue]"); if(vn){S.view="venues";S.venuePage=vn.dataset.venue;render();try{window.scrollTo(0,0)}catch{};return}
  const t=e.target.closest("nav.tabs button"); if(t){S.view=t.dataset.view;if(t.dataset.view==="venues")S.venuePage=null;render();try{window.scrollTo(0,0)}catch{} showDay();return}
  if(e.target.id==="tnClearQ"){S.q="";$("#q").value="";render();return}
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
document.querySelectorAll(".seg [data-type]").forEach(b=>b.onclick=()=>{S.type=b.dataset.type;S.genre.clear();S.venue="";S.month="";if(S.q.trim())S.qAll=false;if(S.view!=="grid")S.day=-1;render()});
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
    // Niet tijdens typen in het zoekveld; 'Vanaf' en andere knoppen die wegschuiven verliezen hun focus (anders veranderen pijltjes onzichtbaar de stad)
    const a=document.activeElement;
    if(dy>6&&!(hd.contains(a)&&a.matches("input"))){if(hd.contains(a)&&!ds.contains(a)) a.blur(); setT();hd.classList.add("tuck")}
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
  // Toetsenbordfocus in de lijst die onder de kop of de tabbalk valt (Shift+Tab): net genoeg bijschuiven, kop blijft zoals hij is
  const nav=$("nav.tabs");
  document.addEventListener("focusin",e=>{const t=e.target; if(!t.closest||!t.closest("#main")||!t.matches(":focus-visible")) return;
    requestAnimationFrame(()=>{const r=t.getBoundingClientRect(), hb=hd.getBoundingClientRect().bottom, nt=nav.getBoundingClientRect().top;
      const by=r.top<hb?r.top-hb-8:r.bottom>nt?r.bottom-nt+8:0; if(by){hd.dataset.hold="1";scrollBy(0,by)}})});
  // Op de telefoon: scrollen in de lijst sluit het toetsenbord van het zoekveld, zodat de kop weer kan inklappen
  $("#main").addEventListener("touchmove",()=>{const a=document.activeElement; if(a&&a.id==="q") a.blur()},{passive:true});
})();

/* Snelkoppelingen van het app-icoon (manifest.json): ?snel=vanavond / weekend / plannen */
(()=>{let q=""; try{q=new URLSearchParams(location.search).get("snel")||""}catch{}
  if(!q) return;
  if(q==="vanavond"||q==="weekend"){S.view="tonight";TN.when=q==="weekend"?"weekend":"today"}
  else if(q==="plannen") S.view="fav";
  try{history.replaceState(null,"",location.pathname+location.hash)}catch{}
})();

buildHome(); render();
/* Gedeelde link (#id): meteen de details van dat item openen */
function openFromHash(){
  let id=""; try{id=decodeURIComponent(location.hash.slice(1))}catch{} if(!id) return;
  if(EV.some(x=>x.id===id)) openDetail(id);
  else if(/^[a-z][\w-]{3,40}$/i.test(id)) toast("Dit item staat niet (meer) in de agenda");
}
openFromHash(); window.addEventListener("hashchange",openFromHash);
// Na middernacht opnieuw laden: een scherm van gisteren zou anders nog "Vandaag" van gisteren tonen
document.addEventListener("visibilitychange",()=>{ if(!document.hidden&&new Date().getDate()!==today.getDate()) location.reload() });
})().catch(()=>{ const m=document.querySelector("#main"); if(m&&!m.children.length) m.innerHTML='<div class="empty"><strong>De app kon niet starten</strong>Ververs de pagina. Blijft het misgaan, laat het weten aan degene die je de link gaf.</div>'; });
