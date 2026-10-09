"""Controle op persoonlijke gegevens (draait in tests.yml; lokaal: python tests/check_identiteit.py).

Zoekt in alle bestanden die in git staan (behalve de grote gegevensbestanden en plaatjes) naar:
  - e-mailadressen, behalve noreply-adressen
  - links naar claude.ai-sessies en 'Claude-Session'-regels
  - Windows-gebruikerspaden (C:\\Users\\...)
  - extra verboden woorden uit de omgevingsvariabele VERBODEN (komma's), bijvoorbeeld een voornaam of achternaam, zodat die
    zelf niet in de repo hoeven te staan
En kijkt of het laatste commitbericht en de auteur/committer daarvan schoon zijn. Afsluiten met een fout als er iets gevonden is.
"""
import os, pathlib, re, subprocess, sys

root = pathlib.Path(subprocess.run(["git", "rev-parse", "--show-toplevel"], capture_output=True, text=True, check=True).stdout.strip())
SKIP = {"podiumradar/site/data.json", "podiumradar/site/nl.json", "podiumradar/scraper/detail_cache.json", "podiumradar/scraper/lokaal.json",
        "podiumradar/scraper/lokaal_cache.json", "podiumradar/scraper/rapport.json", "podiumradar/scraper/venues_cache.json",
        "podiumradar/scraper/spotify_cache.json"}
BINAIR = {".png", ".woff2", ".woff", ".ico", ".jpg", ".jpeg", ".gif", ".webp"}
EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)*\.[A-Za-z]{2,}\b")   # een versie als playwright@1.56.1 is geen adres
TOEGESTAAN = re.compile(r"(?:users\.noreply\.github\.com|noreply@anthropic\.com|noreply@github\.com)$", re.I)
SESSIE = re.compile(r"claude\.ai/code/session|Claude-Session", re.I)
PAD = re.compile(r"[A-Za-z]:\\+Users\\+[^\\\s]+", re.I)
verboden = [w.strip() for w in os.environ.get("VERBODEN", "").split(",") if w.strip()]

fouten = []
def meld(waar, wat): fouten.append(f"{waar}: {wat}")

for naam in subprocess.run(["git", "ls-files"], cwd=root, capture_output=True, text=True, check=True).stdout.splitlines():
    if naam in SKIP or pathlib.Path(naam).suffix.lower() in BINAIR:
        continue
    try:
        tekst = (root / naam).read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        continue
    for i, regel in enumerate(tekst.splitlines(), 1):
        for m in EMAIL.finditer(regel):
            if not TOEGESTAAN.search(m.group(0)):
                meld(f"{naam}:{i}", f"e-mailadres {m.group(0)}")
        if SESSIE.search(regel) and not naam.endswith("check_identiteit.py") and not naam.endswith("CLAUDE.md"):
            meld(f"{naam}:{i}", "link of regel van een Claude-sessie")
        if PAD.search(regel) and not naam.endswith("check_identiteit.py"):
            meld(f"{naam}:{i}", "Windows-gebruikerspad")
        for w in verboden:
            if re.search(r"\b" + re.escape(w) + r"\b", regel, re.I):
                meld(f"{naam}:{i}", "verboden woord uit VERBODEN")

kop = subprocess.run(["git", "log", "-1", "--format=%ae%n%ce%n%B"], cwd=root, capture_output=True, text=True).stdout
for adres in EMAIL.findall(kop):
    if not TOEGESTAAN.search(adres):
        meld("laatste commit", f"persoonlijk adres {adres}")
if SESSIE.search(kop):
    meld("laatste commit", "bericht bevat een Claude-Session-regel of sessielink")
for w in verboden:
    if re.search(r"\b" + re.escape(w) + r"\b", kop, re.I):
        meld("laatste commit", "verboden woord uit VERBODEN")

if fouten:
    print("Persoonlijke gegevens gevonden:"); [print("  " + f) for f in fouten]; sys.exit(1)
print("ALLES GOED: geen persoonlijke gegevens gevonden")
