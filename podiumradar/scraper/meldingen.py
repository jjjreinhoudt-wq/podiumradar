"""Pushmeldingen via ntfy (https://ntfy.sh) bij nieuwe shows van gevolgde artiesten, podia en alarmen.

Draait na de nachtelijke ophaalronde (update.yml). Het kanaal (topic) is geheim en staat als GitHub-secret
NTFY_TOPIC; zonder secret doet dit script niets. De volglijst staat in scraper/volgen.json en wordt vanuit de
app bijgewerkt via een GitHub-melding (workflow volglijst.yml). Al verstuurde items: scraper/meldingen_verstuurd.json.

Test zonder te versturen:  python scraper/meldingen.py --droog
"""
import datetime as dt, json, os, pathlib, re, sys, unicodedata
import requests

ROOT = pathlib.Path(__file__).resolve().parent.parent
DATA = ROOT / "site/data.json"
VOLGEN = ROOT / "scraper/volgen.json"
SENT = ROOT / "scraper/meldingen_verstuurd.json"
APP = "https://jjjreinhoudt-wq.github.io/agenda-nefmp54/"
MAX_LOS = 8          # meer nieuwe treffers dan dit: één samenvattende melding
DROOG = "--droog" in sys.argv


def key(s):
    """Zelfde sleutel als artistKey() in app.js: kleine letters, zonder accenten en leestekens."""
    s = unicodedata.normalize("NFD", (s or "").lower())
    return re.sub(r"[^a-z0-9]", "", re.sub(r"[̀-ͯ]", "", s))


def acts(e):
    head = re.sub(r"\s*\((festival|festival, dag \d)\)$", "", e["title"], flags=re.I).split(" - ")[0].strip()
    names = [a.strip() for a in re.sub(r"^Popronde:\s*", "", head).split(" + ")]
    m = re.search(r"Instore:\s*(.+)$", e["title"])
    if m:
        names = [m.group(1)]
    return names + list(e.get("support") or [])


def main():
    topic = os.environ.get("NTFY_TOPIC", "").strip()
    if not topic and not DROOG:
        print("Meldingen: geen NTFY_TOPIC ingesteld, overgeslagen")
        return
    volg = json.loads(VOLGEN.read_text(encoding="utf-8")) if VOLGEN.exists() else {}
    artiesten = {key(a): a for a in volg.get("artiesten", []) if len(key(a)) >= 2}
    podia = {p.lower() for p in volg.get("podia", [])}
    alarmen = [a.lower() for a in volg.get("alarmen", []) if len(a.strip()) >= 3]
    if not (artiesten or podia or alarmen):
        print("Meldingen: volglijst is leeg")
        return
    data = json.loads(DATA.read_text(encoding="utf-8"))
    V = data["venues"]
    today = dt.date.today().isoformat()
    sent = json.loads(SENT.read_text(encoding="utf-8")) if SENT.exists() else {}

    hits = []
    for e in data["events"]:
        if e.get("first_seen") != today or e["id"] in sent or e["date"] < today:
            continue
        v = V.get(e["v"], {})
        waarom = None
        ks = [key(a) for a in acts(e)]
        tk = key(e["title"])
        for k, naam in artiesten.items():
            if k in ks or (len(k) >= 6 and k in tk):
                waarom = naam
                break
        if not waarom and f"{v.get('name', '')}|{v.get('city', '')}".lower() in podia:
            waarom = v.get("name")
        if not waarom:
            hay = f"{e['title']} {v.get('name', '')} {v.get('city', '')}".lower()
            waarom = next((a for a in alarmen if a in hay), None)
        if waarom:
            hits.append((e, v, waarom))

    hits.sort(key=lambda h: (h[0]["date"], h[0].get("time") or ""))
    print(f"Meldingen: {len(hits)} nieuwe treffers")
    berichten = []
    for e, v, waarom in hits[:MAX_LOS] if len(hits) <= MAX_LOS else []:
        d = dt.date.fromisoformat(e["date"])
        wanneer = f"{['ma','di','wo','do','vr','za','zo'][d.weekday()]} {d.day}-{d.month}" + (f" {e['time']}" if e.get("time") else "")
        berichten.append({"title": f"Nieuw: {e['title'][:80]}", "message": f"{wanneer}, {v.get('name')} ({v.get('city')})\nOmdat je {waarom} volgt",
                          "click": APP + "#" + e["id"], "tags": "musical_note"})
    if len(hits) > MAX_LOS:
        lijst = "\n".join(f"• {e['title'][:50]} – {v.get('name')}, {e['date'][8:]}-{e['date'][5:7]}" for e, v, _ in hits[:15])
        berichten.append({"title": f"{len(hits)} nieuwe shows voor jou", "message": lijst + ("\n…" if len(hits) > 15 else ""),
                          "click": APP, "tags": "musical_note"})
    for b in berichten:
        if DROOG:
            print("  (droog)", b["title"], "|", b["message"].replace("\n", " / "))
            continue
        try:
            r = requests.post(f"https://ntfy.sh/{topic}", data=b["message"].encode("utf-8"), timeout=20,
                              headers={"Title": b["title"].encode("utf-8"), "Click": b["click"], "Tags": b["tags"]})
            r.raise_for_status()
        except requests.RequestException as err:
            print("Meldingen: versturen mislukt:", err)
            return  # niets als verstuurd markeren; ntfy was onbereikbaar
    if not DROOG:
        for e, _, _ in hits:
            sent[e["id"]] = today
        grens = (dt.date.today() - dt.timedelta(days=60)).isoformat()
        SENT.write_text(json.dumps({k: d for k, d in sent.items() if d >= grens}, indent=0), encoding="utf-8")


if __name__ == "__main__":
    main()
