/* Podiumradar als app: service worker (offline + automatisch bijwerken) en installatiehulp. */
(()=>{
const ls={get(k){try{return localStorage.getItem(k)}catch{return null}},set(k,v){try{localStorage.setItem(k,v)}catch{}}};
const ss={get(k){try{return sessionStorage.getItem(k)}catch{return null}},set(k,v){try{sessionStorage.setItem(k,v)}catch{}},del(k){try{sessionStorage.removeItem(k)}catch{}}};
function say(t){const el=document.getElementById("toast");if(!el)return;el.textContent=t;el.classList.add("on");clearTimeout(say.h);say.h=setTimeout(()=>el.classList.remove("on"),2600)}
let inFrame; try{inFrame=window.self!==window.top}catch{inFrame=true}
const standalone=(window.matchMedia&&matchMedia("(display-mode: standalone)").matches)||navigator.standalone===true;

/* ---------- service worker ---------- */
if("serviceWorker" in navigator && !inFrame && (location.protocol==="https:"||location.hostname==="localhost"||location.hostname==="127.0.0.1")){
  if(ss.get("pr_sw_updated")){ss.del("pr_sw_updated");setTimeout(()=>say("Nieuwe versie geladen"),400)}
  const hadController=!!navigator.serviceWorker.controller;
  let reloading=false;
  navigator.serviceWorker.addEventListener("controllerchange",()=>{
    // Eerste installatie: niets doen. Daarna: één keer herladen (niet vaker dan eens per 30 s).
    if(!hadController||reloading) return;
    const last=+ss.get("pr_sw_reload")||0; if(Date.now()-last<30000) return;
    reloading=true; ss.set("pr_sw_reload",String(Date.now())); ss.set("pr_sw_updated","1");
    say("Nieuwe versie geladen"); setTimeout(()=>location.reload(),600);
  });
  window.addEventListener("load",()=>{
    navigator.serviceWorker.register("sw.js",{scope:"./"}).then(reg=>{
      document.addEventListener("visibilitychange",()=>{if(document.visibilityState==="visible") reg.update().catch(()=>{})});
    }).catch(()=>{});
  });
}

/* ---------- installatiehulp ---------- */
if(standalone||inFrame||ls.get("pr_install_hide")) return;
const ios=/iphone|ipad|ipod/i.test(navigator.userAgent)||(navigator.platform==="MacIntel"&&navigator.maxTouchPoints>1);
function banner(html,onInstall){
  if(document.getElementById("installBar")) return;
  const b=document.createElement("div"); b.id="installBar"; b.className="installbar"; b.setAttribute("role","note");
  b.innerHTML='<div>'+html+'</div>'+(onInstall?'<button class="btn" data-i>Installeer als app</button>':'')+'<button class="x" aria-label="Sluiten">×</button>';
  b.querySelector(".x").onclick=()=>{ls.set("pr_install_hide","1");b.remove()};
  if(onInstall) b.querySelector("[data-i]").onclick=onInstall;
  document.body.appendChild(b);
}
let deferred=null;
window.addEventListener("beforeinstallprompt",e=>{
  e.preventDefault(); deferred=e;
  banner("<strong>Podiumradar als app</strong>Op je beginscherm, werkt ook offline.",async()=>{
    const bar=document.getElementById("installBar"); if(!deferred){bar&&bar.remove();return}
    deferred.prompt(); const r=await deferred.userChoice.catch(()=>null); deferred=null;
    if(bar) bar.remove(); if(r&&r.outcome==="dismissed") ls.set("pr_install_hide","1");
  });
});
window.addEventListener("appinstalled",()=>{const b=document.getElementById("installBar");if(b)b.remove();ls.set("pr_install_hide","1");say("Podiumradar staat op je beginscherm")});
if(ios) setTimeout(()=>banner('<strong>Zet Podiumradar op je beginscherm</strong>Tik op <b>Deel</b> <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true" style="vertical-align:-2px"><path d="M12 3v12M7 8l5-5 5 5M5 12v8h14v-8"/></svg> en kies <b>Zet op beginscherm</b>.'),2500);
})();
