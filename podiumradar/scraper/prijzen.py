"""Prijs van een voorstelling: laagste prijs in euro's (0 = gratis), of None als het niet zeker is.

Conservatief: liever geen prijs dan een verkeerde. Gebruikt door sources.py (from_jsonld en from_text).
Test: python scraper/test_prijzen.py
"""
import re

MIN, MAX = 1, 500  # bedragen daarbuiten zijn geen kaartprijs (fooi, servicekosten, arrangement, typefout)
# Offers/bedragen die geen toegangskaart zijn
NIET_KAART = re.compile(r"servicekosten|service ?fee|transactie|administratie|reserveringskosten|garderobe|parkeer|parking|"
                        r"consumptie|munt|drank|diner|menu|arrangement|hotel|toeslag|cadeau|gift|lidmaatschap|merch|"
                        r"programmaboekje|korting van|bespaar|donatie|fooi", re.I)


def bedrag(x):
    """24.5 / "24,50" / "€ 24,50" / "24,-" / "1.250,00" -> float; anders None."""
    if isinstance(x, bool):
        return None
    if isinstance(x, (int, float)):
        return float(x)
    if not isinstance(x, str):
        return None
    s = re.sub(r"\s|€|eur(o|os)?\b", "", x.strip(), flags=re.I)
    m = re.fullmatch(r"(\d{1,3}(?:\.\d{3})+|\d+)(?:[,.](\d{1,2}|-{1,2}))?", s)
    if not m:
        return None
    heel = int(m.group(1).replace(".", ""))
    dec = m.group(2) if m.group(2) and m.group(2)[0] != "-" else "0"
    return round(heel + int(dec.ljust(2, "0")) / 100, 2)


def _rond(p):
    return int(p) if p == int(p) else p


def from_offers(event):
    """Laagste prijs uit JSON-LD: offers (dict of lijst, ook AggregateOffer met lowPrice) of isAccessibleForFree."""
    if event.get("isAccessibleForFree") in (True, "true", "True", "https://schema.org/True"):
        return 0
    prijzen, nul = [], False

    def walk(o):
        nonlocal nul
        if isinstance(o, list):
            for x in o:
                walk(x)
            return
        if not isinstance(o, dict):
            return
        cur = str(o.get("priceCurrency") or "EUR").upper()
        tekst = " ".join(str(o.get(k) or "") for k in ("name", "description", "category"))
        if cur == "EUR" and not NIET_KAART.search(tekst):
            for k in ("lowPrice", "price"):
                p = bedrag(o.get(k))
                if p is None:
                    continue
                if p == 0:
                    # Veel sites zetten 0 als 'onbekend': alleen gratis als het er ook staat
                    nul = nul or bool(re.search(r"gratis|free|vrij", tekst, re.I))
                elif MIN <= p <= MAX:
                    prijzen.append(p)
                break  # lowPrice gaat voor price
        walk(o.get("offers"))
        walk(o.get("priceSpecification"))

    walk(event.get("offers"))
    if prijzen:
        return _rond(min(prijzen))
    return 0 if nul else None


# "Entree: gratis", "Gratis toegang", "vrij entree", "Toegang vrij", "free entrance"
GRATIS_RE = re.compile(r"\b(?:(?:entree|entr[ée]e|toegang|toegangsprijs|entreeprijs|prijs|kaarten|tickets?)\s*:?\s*(?:is\s+)?"
                       r"(?:gratis|vrij|free)\b(?!\s+(?:voor|met|bij|tot|t/m|onder|vanaf|na)\b)"
                       r"|(?:gratis|vrije?)\s+(?:entree|entr[ée]e|toegang)\b(?!\s+(?:voor|met|bij|tot|t/m|onder|vanaf|na)\b)"
                       r"|free\s+(?:entry|entrance|admission)\b)", re.I)
# Bedrag met een woord ervoor dat zegt dat het de kaartprijs is: "Entree € 24,50", "Tickets: vanaf €19,-", "Prijs 15 euro"
EURO = r"(?:€\s*(\d{1,3}(?:[.,]\d{2}|,-{1,2})?)(?![\d.,]*\d)|(\d{1,3}(?:[.,]\d{2})?)\s*(?:euro|eur)\b)"
LABEL_RE = re.compile(r"\b(?:entree|entr[ée]e|toegang|toegangsprijs|entreeprijs|prijs|prijzen|kaarten|kaartprijs|tickets?|"
                      r"ticketprijs|voorverkoop|kassa|regulier|normaal|vanaf|v\.a\.)\b[^\n€\d]{0,15}?" + EURO, re.I)
LOS_RE = re.compile(EURO, re.I)


def from_text(txt):
    """Prijs uit de tekst van een voorstellingspagina (blokken met andere voorstellingen zijn al verwijderd)."""
    # "€ 19,- excl. servicekosten" gaat wél over de kaartprijs
    txt = re.sub(r"\b(?:excl|incl|exclusief|inclusief|ex|plus)\.?\s*(?:\w+\s+){0,2}(?:servicekosten|service ?fee|"
                 r"transactiekosten|reserveringskosten|administratiekosten)", "", txt, flags=re.I)
    gelabeld, los = [], set()
    for m in LABEL_RE.finditer(txt):
        if not NIET_KAART.search(txt[max(0, m.start() - 30):m.end() + 20]):
            p = bedrag(m.group(1) or m.group(2))
            if p is not None and MIN <= p <= MAX:
                gelabeld.append(p)
    alle = list(LOS_RE.finditer(txt))
    for m in alle:
        p = bedrag(m.group(1) or m.group(2))
        if p is not None and MIN <= p <= MAX and not NIET_KAART.search(txt[max(0, m.start() - 30):m.end() + 20]):
            los.add(p)
    if gelabeld:
        return _rond(min(gelabeld))
    # Zonder woord ervoor ("€ 24,50" in het kaartjesblok): alleen als dat het enige bedrag op de pagina is
    if len(los) == 1 and len(alle) <= 2:
        return _rond(los.pop())
    # Alleen 'gratis' als er nergens een bedrag staat ("Entree € 15, kinderen gratis" is niet gratis)
    if not alle and GRATIS_RE.search(txt):
        return 0
    return None
