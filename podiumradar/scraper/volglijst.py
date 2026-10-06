"""Leest de volglijst uit een GitHub-melding (workflow volglijst.yml) en schrijft scraper/volgen.json."""
import json, pathlib, re, sys

OUT = pathlib.Path(__file__).resolve().parent / "volgen.json"
event = json.loads(pathlib.Path(sys.argv[1]).read_text(encoding="utf-8"))
body = (event.get("issue") or {}).get("body") or ""
m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", body, re.S)
if not m:
    sys.exit("Geen volglijst (JSON-blok) gevonden in de melding")
raw = json.loads(m.group(1))


def clean(xs, n):
    out = []
    for x in xs if isinstance(xs, list) else []:
        if isinstance(x, str):
            x = re.sub(r"[\x00-\x1f]", "", x).strip()[:80]
            if x and x not in out:
                out.append(x)
    return out[:n]


volg = {"artiesten": clean(raw.get("artiesten"), 300), "podia": clean(raw.get("podia"), 200),
        "alarmen": clean(raw.get("alarmen"), 50)}
OUT.write_text(json.dumps(volg, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
print(f"Volglijst: {len(volg['artiesten'])} artiesten, {len(volg['podia'])} podia, {len(volg['alarmen'])} alarmen")
