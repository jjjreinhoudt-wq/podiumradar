# Podiumradar – instructies voor Claude Code

Dit project is van Jasper. Hij wil **zo min mogelijk techniek uitgelegd krijgen**: hij zegt wat hij wil, jij bouwt het. Leg alleen iets uit als het misgaat, en dan in gewone taal, in het Nederlands.

## Wat dit is
- `site/` is een statische app (index.html + app.js + data.json) die op GitHub Pages draait.
- `scraper/scrape.py` haalt elke nacht de agenda van alle Nederlandse podia en theaters op via Podiuminfo (provincie- en genrepagina's, plus detailpagina's voor tijden en voorprogramma) en schrijft `site/data.json`.
- `.github/workflows/update.yml` draait de scraper elke nacht en zet de site opnieuw online.

## Als Jasper zegt "zet dit online" (eerste keer)
1. Controleer of `gh` geïnstalleerd en ingelogd is (`gh auth status`). Zo niet: installeer het en laat Jasper inloggen met `gh auth login` (kies GitHub.com, HTTPS, browser). Begeleid hem stap voor stap.
2. **Test eerst de scraper lokaal** voordat je iets online zet:
   `pip install -r scraper/requirements.txt`
   `python scraper/scrape.py --only noord-brabant --max-pages 2 --dry-run --dump /tmp/pr`
   - De parser is geschreven zonder de ruwe HTML te kunnen zien. Controleer in de output of datums, tijden, podium en plaats kloppen (vergelijk met de pagina in `/tmp/pr`).
   - Klopt iets niet (0 shows, geen tijden, geen plaatsen)? Pas `parse_listing()` en/of `detail()` aan op basis van de echte HTML, en test opnieuw.
   - Controleer ook de genre-slugs in `scraper/config.json` (een 404 op een genrepagina betekent een verkeerde slug).
   - Check `robots.txt` van podiuminfo.nl; respecteer die en houd de vertraging van 1,5 sec aan.
3. Maak een **publieke** GitHub-repo `podiumradar` (GitHub Pages is gratis alleen voor publieke repo's; de data is sowieso openbaar) en push alles naar `main`.
4. Zet Pages aan met GitHub Actions als bron:
   `gh api -X POST repos/{owner}/podiumradar/pages -f build_type=workflow`
5. Start de eerste volledige run: `gh workflow run "Agenda bijwerken"` en volg hem met `gh run watch`. Een volledige run duurt ongeveer 30 à 60 minuten.
6. Geef Jasper daarna **alleen** de link (`https://<gebruiker>.github.io/podiumradar/`) en de tip om hem op zijn telefoon aan het beginscherm toe te voegen (Safari: Deel > Zet op beginscherm).

## Onderhoud
- Faalt de nachtelijke run met code 2 of 3, dan is de bronsite waarschijnlijk veranderd. De oude data blijft dan staan. Zoek uit wat er veranderd is in de HTML en pas de parser aan.
- Een podium staat verkeerd als pop/theater: voeg het toe aan `venue_type_overrides` in `scraper/config.json`.
- Nieuwe wensen van Jasper: bouw ze in `site/app.js`, test lokaal met `python -m http.server -d site`, en push.

## Ideeën die nog openstaan (alleen oppakken als Jasper erom vraagt)
- Echte pushmeldingen bij nieuwe shows van gevolgde artiesten (vergt een kleine server of een dienst als ntfy.sh).
- Voorprogramma's en tijden direct van de sites van de grote podia halen (013, Paradiso, Melkweg, TivoliVredenburg…) voor meer precisie.
