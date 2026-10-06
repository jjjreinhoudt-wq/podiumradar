"""Wekelijkse controle: zoekt in site/data.json en scraper/rapport.json naar bronnen die stuk lijken.

Vergelijkt met de stand van ongeveer een week geleden (uit de git-geschiedenis) en schrijft een kort
Markdown-rapport. De workflow .github/workflows/controle.yml zet dat elke maandag in één vast GitHub-issue.

Gebruik:  python scraper/controle.py              (rapport naar het scherm)
          python scraper/controle.py --uit r.md   (rapport naar een bestand)
Lokaal draaien kan gewoon; er wordt niets opgehaald of veranderd.
"""
import argparse, collections, datetime as dt, json, pathlib, re, subprocess

ROOT = pathlib.Path(__file__).resolve().parent.parent
DATA, RAPPORT = "site/data.json", "scraper/rapport.json"
TODAY = dt.date.today()
PODIA = ("pop", "concert", "arena", "cafe", "thea")
NACHT_GENRES = ("Dance", "Feest")              # clubnachten mogen na middernacht beginnen
KOPJE_WOORDEN = r"(agenda|programma|program|tickets?|kaarten|overzicht|totaal|alle|voorstellingen|concerten|evenementen|events?|home|nieuws|archief)"
KOPJE_RE = re.compile(r"^(" + KOPJE_WOORDEN + r"\W*)+$|^" + KOPJE_WOORDEN + r"\s*[:|–—-]|cookie", re.I)
MAX_VOORBEELDEN = 3
MAX_REGELS = 15                                # per onderdeel; de rest als "en nog N"


def git(*args):
    r = subprocess.run(["git", "-C", str(ROOT), *args], capture_output=True, text=True)
    return r.stdout.strip() if r.returncode == 0 else ""


def vorige(path, dagen=6):
    """Versie van een bestand van minstens `dagen` geleden (of de oudste die er is). Geeft (datum, inhoud) of (None, None)."""
    sha = git("log", "-1", "--format=%H", f"--before={(dt.datetime.now() - dt.timedelta(days=dagen)).isoformat()}",
              "--", path)
    if not sha:  # nog geen week geschiedenis (of een ondiepe checkout): de oudste versie die er is
        shas = git("log", "--format=%H", "--", path).split()
        sha = shas[-1] if len(shas) > 1 else ""
    if not sha:
        return None, None
    try:
        return git("log", "-1", "--format=%cs", sha), json.loads(git("show", f"{sha}:./{path}") or "null")
    except ValueError:
        return None, None


def norm(t):
    return re.sub(r"[^a-z0-9]", "", (t or "").lower())


def voorbeeld(e):
    return f"{e['date']}{' ' + e['time'] if e.get('time') else ''} “{e['title'][:60]}”"


def controleer(data, rap, oud_data, oud_rap):
    """Geeft (samenvatting-regels, {onderdeel: [regels]}) terug."""
    V, E = data["venues"], data["events"]
    per = collections.defaultdict(list)
    for e in E:
        per[e["v"]].append(e)
    naam = lambda v: f"{V.get(v, {}).get('name', v)} ({V.get(v, {}).get('city') or '?'})"
    soort = lambda v: V.get(v, {}).get("type", "pop")
    P = collections.OrderedDict((k, []) for k in (
        "Bronnen zonder items", "Sterke daling", "Niet op tijd klaar", "Geweigerd of niet gevonden (403/404)",
        "Bijna alles uitverkocht", "Veel items op dezelfde dag en tijd", "Titels die op een kopje lijken",
        "Titel is de naam van het podium", "Datum ver weg (meer dan 400 dagen)", "Periode langer dan een maand bij een podium",
        "Vreemde tijden (00:00-08:59)", "Dubbele items", "Podia zonder plek op de kaart"))

    # --- per bron, uit rapport.json
    oud_items = {b["name"]: b["items"] for b in (oud_rap or {}).get("bronnen", []) if not b.get("niet_op_tijd")}
    for b in rap.get("bronnen", []):
        n, codes = b["items"], b.get("antwoorden", {})
        if b.get("niet_op_tijd"):
            P["Niet op tijd klaar"].append(f"{b['name']} ({b['site']}): vorige gegevens blijven staan")
        elif n == 0:
            hoe = ", ".join(f"{k}× {c}" for c, k in codes.items()) or ("lokaal opgehaald" if b.get("lokaal") else "geen antwoord")
            P["Bronnen zonder items"].append(f"{b['name']} ({b['type']}, {b['site']}): antwoorden {hoe}")
        elif b["name"] in oud_items and oud_items[b["name"]] >= 6 and n < oud_items[b["name"]] * 0.5:
            P["Sterke daling"].append(f"{b['name']}: {oud_items[b['name']]} → {n} items")
        slecht = {c: k for c, k in codes.items() if c in ("403", "404")}
        if slecht:
            P["Geweigerd of niet gevonden (403/404)"].append(
                f"{b['name']} ({b['site']}): " + ", ".join(f"{k}× {c}" for c, k in slecht.items())
                + f" van {sum(codes.values())} verzoeken")

    # --- per podium, uit data.json
    alle_keys = collections.Counter()
    for v, evs in per.items():
        typ = soort(v)
        sold = [e for e in evs if e.get("status") == "sold"]
        if len(evs) >= 5 and len(sold) > 0.6 * len(evs):
            P["Bijna alles uitverkocht"].append(f"{naam(v)}: {len(sold)} van {len(evs)} uitverkocht")
        if typ not in ("film", "festival"):
            slot = collections.defaultdict(list)
            for e in evs:
                if e.get("time"):
                    slot[(e["date"], e["time"])].append(e)
            for (d, t), xs in sorted(slot.items()):
                if len(xs) > 3:
                    P["Veel items op dezelfde dag en tijd"].append(
                        f"{naam(v)}: {len(xs)} items op {d} {t}, bv. " + "; ".join(f"“{x['title'][:40]}”" for x in xs[:MAX_VOORBEELDEN]))
        vn = norm(V.get(v, {}).get("name"))
        groepen = {
            "Titels die op een kopje lijken": [e for e in evs if KOPJE_RE.search(e["title"].strip())],
            "Titel is de naam van het podium": [e for e in evs if typ != "festival" and vn and norm(e["title"]) == vn],
            "Datum ver weg (meer dan 400 dagen)": [e for e in evs if e["date"] > (TODAY + dt.timedelta(days=400)).isoformat()],
            "Periode langer dan een maand bij een podium": [
                e for e in evs if typ in PODIA and e.get("end") and e.get("genre") != "Tentoonstelling"
                and (dt.date.fromisoformat(e["end"]) - dt.date.fromisoformat(e["date"])).days > 31],
            "Vreemde tijden (00:00-08:59)": [
                e for e in evs if typ not in ("film", "festival") and e.get("time") and e["time"] < "09:00"
                and e.get("genre") not in NACHT_GENRES],
        }
        for k, xs in groepen.items():
            if xs:
                P[k].append(f"{naam(v)}: {len(xs)}×, bv. " + "; ".join(voorbeeld(x) for x in xs[:MAX_VOORBEELDEN]))
        keys = collections.Counter((e["date"], e.get("time"), norm(e["title"])) for e in evs)
        dubbel = [k for k, c in keys.items() if c > 1]
        if dubbel:
            d, t, _ = dubbel[0]
            x = next(e for e in evs if (e["date"], e.get("time")) == (d, t))
            P["Dubbele items"].append(f"{naam(v)}: {len(dubbel)}× dubbel, bv. {voorbeeld(x)}")
    for v, info in sorted(V.items()):
        if info.get("lat") is None or info.get("lon") is None:
            P["Podia zonder plek op de kaart"].append(f"{naam(v)} ({info.get('type')})")

    # --- samenvatting
    n_oud = len((oud_data or {}).get("events", []))
    sam = [f"- **{len(E)} items** bij {len(per)} locaties"
           + (f" (een week eerder: {n_oud}, {len(E) - n_oud:+d})" if n_oud else ""),
           f"- **{rap.get('werkt', '?')} van de {rap.get('totaal', '?')} bronnen** leveren items "
           f"(rapport van {rap.get('datum', '?')}, agenda van {data.get('updated', '?')})"]
    top = sorted(((k, len(v)) for k, v in P.items() if v), key=lambda x: -x[1])
    if top:
        sam.append("- Meeste meldingen: " + ", ".join(f"{k.lower()} ({n})" for k, n in top[:4]))
    else:
        sam.append("- Geen bijzonderheden gevonden.")
    return sam, P


def markdown(sam, P, vergeleken):
    out = [f"## Wekelijkse controle {TODAY.isoformat()}", "", *sam,
           f"- Vergeleken met de stand van {vergeleken}" if vergeleken else "- Nog geen eerdere stand om mee te vergelijken", ""]
    uitleg = {
        "Bronnen zonder items": "Site levert niets op. Vaak laadt de agenda met JavaScript of is de site veranderd.",
        "Sterke daling": "Minder dan de helft van een week eerder.",
        "Niet op tijd klaar": "Bron was te traag; de app toont de items van de keer ervoor.",
        "Geweigerd of niet gevonden (403/404)": "403 = site weigert ons, 404 = link bestaat niet meer.",
        "Veel items op dezelfde dag en tijd": "Vaak een tijd uit een blok 'meer concerten' op de pagina.",
    }
    for k, regels in P.items():
        if not regels:
            continue
        out += [f"### {k} ({len(regels)})"] + ([f"_{uitleg[k]}_", ""] if k in uitleg else [])
        out += [f"- {r}" for r in regels[:MAX_REGELS]]
        if len(regels) > MAX_REGELS:
            out.append(f"- … en nog {len(regels) - MAX_REGELS}")
        out.append("")
    out.append("_Gemaakt door `scraper/controle.py`. Een melding is een aanwijzing, geen zekerheid: kijk even op de site van het podium._")
    return "\n".join(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--uit", help="bestand voor het rapport (anders naar het scherm)")
    args = ap.parse_args()
    data = json.loads((ROOT / DATA).read_text(encoding="utf-8"))
    rap = json.loads((ROOT / RAPPORT).read_text(encoding="utf-8")) if (ROOT / RAPPORT).exists() else {}
    d1, oud_data = vorige(DATA)
    d2, oud_rap = vorige(RAPPORT)
    sam, P = controleer(data, rap, oud_data, oud_rap)
    md = markdown(sam, P, d1 or d2)
    if len(md) > 60000:  # GitHub-issues kunnen hooguit 65536 tekens aan
        md = md[:60000] + "\n\n… (afgekapt)"
    if args.uit:
        pathlib.Path(args.uit).write_text(md + "\n", encoding="utf-8")
    else:
        print(md)


if __name__ == "__main__":
    main()
