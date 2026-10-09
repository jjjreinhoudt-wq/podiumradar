"""Draait op de eigen computer van de eigenaar (Windows-taak 'Podiumradar lokaal', dagelijks en na inloggen).

Haalt alleen de bronnen met "local_only": true op: sites die datacenters zoals GitHub weigeren (403), maar
vanaf een gewone internetaansluiting gewoon werken (Pathé, Filmhuis Breda, Kriterion, ...).
Het resultaat gaat als scraper/lokaal.json naar GitHub; de nachtelijke run daar neemt het over.

Handmatig:  python scraper/lokaal.py            (ophalen + naar GitHub)
            python scraper/lokaal.py --no-push  (alleen ophalen, om te testen)
"""
import datetime as dt, json, pathlib, subprocess, sys, time

ROOT = pathlib.Path(__file__).resolve().parent.parent          # .../podiumradar/podiumradar
REPO = ROOT.parent                                              # git-map
LOG = ROOT / "scraper/lokaal.log"


def log(msg):
    line = f"{dt.datetime.now():%Y-%m-%d %H:%M:%S} {msg}"
    print(line, flush=True)
    with LOG.open("a", encoding="utf-8") as f:
        f.write(line + "\n")


def git(*args):
    # Altijd de neutrale identiteit van de bot, ook voor de commits die 'git pull --rebase' maakt: nooit het persoonlijke adres van deze pc
    r = subprocess.run(["git", "-C", str(REPO), "-c", "user.name=podiumradar-bot", "-c", "user.email=actions@users.noreply.github.com", *args],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    if r.returncode:
        log(f"git {' '.join(args)}: {r.stderr.strip()[:300]}")
    return r.returncode == 0


def main():
    push = "--no-push" not in sys.argv
    if push:
        git("pull", "--rebase", "--autostash", "-q", "origin", "main")  # nieuwste bronnenlijst
    sys.path.insert(0, str(ROOT / "scraper"))
    import sources
    cfg = json.loads((ROOT / "scraper/config.json").read_text(encoding="utf-8"))
    t0 = time.time()
    results = sources.collect(cfg, log=log, local=True)
    if not results:
        log("geen lokale bronnen in bronnen.json")
        return
    data = {"datum": dt.datetime.now().strftime("%Y-%m-%d %H:%M"),
            "bronnen": {sources.local_key(src): evs for src, evs in results if evs is not None}}
    n = sum(len(v) for v in data["bronnen"].values())
    if n == 0:
        log("niets opgehaald (geen internet?): lokaal.json niet aangepast")
        return
    sources.LOKAAL.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    log(f"{n} items van {len(data['bronnen'])} bronnen in {time.time() - t0:.0f} s")
    if push:
        git("add", "podiumradar/scraper/lokaal.json", "podiumradar/scraper/lokaal_cache.json")
        if git("commit", "-q", "-m", "Lokaal opgehaald (Pathé e.a.)"):
            if not (git("pull", "--rebase", "-X", "theirs", "-q", "origin", "main") and git("push", "-q", "origin", "main")):
                log("naar GitHub sturen mislukt; volgende keer opnieuw")
            else:
                log("naar GitHub gestuurd")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:  # nooit een foutvenster op het scherm van de eigenaar
        log(f"fout: {e.__class__.__name__}: {e}")
