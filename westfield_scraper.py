import json
import json
import re
from urllib.parse import urljoin, urlparse

from playwright.sync_api import sync_playwright

# Configure one or more URLs to scrape. Add more addresses to the list below.
URLS = ["https://www.gallerian.se/butik/", "https://www.nordstan.se/sv/butiker/shoppa",
    "https://www.westfield.com/sv/sweden/mallofscandinavia/butiker",
    # Add more mall/store listing pages here, e.g.:
    # "https://www.westfield.com/sv/sweden/another-mall/butiker",
]


def clean_store_name(raw: str) -> str:
    """Clean raw store text by removing parentheses, status, floor info, dashes and generic words.

    Examples removed: "(Stängt)", "stängt", "plan 0", "- stängt", "Butik: "
    """
    if not raw:
        return ""
    s = raw.strip()
    # remove parenthesis content
    s = re.sub(r"\s*\([^)]*\)", "", s)
    # remove 'plan <num>' or 'Plan <num>'
    s = re.sub(r"\b[Pp]lan\s*\d+\b", "", s)
    # remove common status words (case-insensitive)
    s = re.sub(r"(?i)\b(stäng[ta]?|stänger|stängt|öppet|stängd)\b", "", s)
    # remove trailing dash and any following text (e.g. "Name - stängt")
    s = re.sub(r"[-–—].*$", "", s)
    # remove leading generic 'Butik' or 'Butiker' or 'Shop'
    s = re.sub(r"(?i)^(butik|butiker|shop)[:\s-]+", "", s)
    # collapse whitespace
    s = re.sub(r"\s+", " ", s)
    s = s.strip()
    # remove lone 'Plan' leftovers
    s = re.sub(r"(?i)\bplan\b", "", s).strip()
    # remove pipe-delimited location info (e.g. "Gatuplan | Postgatan")
    s = re.sub(r"\s*\|.*$", "", s)
    # remove common trailing location words like 'Gatuplan', 'Övre', 'Nedre' and following text
    s = re.sub(r"(?i)\b(?:gatuplan|övre|nedre)\b.*$", "", s)
    # remove common street/place suffixes (e.g. 'Postgatan', 'Köpmansgatan', 'Nordstadstorget')
    s = re.sub(r"(?i)\b(?:hamngatan|postgatan|köpmansgatan|spannmålsgatan|nordstadstorget|lilla klädpressaregatan)\b.*$", "", s)
    # remove trailing numbers (addresses)
    s = re.sub(r"[\s,/-]*\d+\s*$", "", s)
    # collapse exact duplicated halves like 'NAME NAME' -> 'NAME'
    m = re.match(r"^(?P<x>.+?)\s+\1$", s, flags=re.IGNORECASE)
    if m:
        s = m.group("x").strip()
    return s


def extract_store_links(page):
    """Extract candidate store names from the page and return cleaned names only."""
    anchors = page.query_selector_all("a")
    names = []
    seen = set()
    heuristics = ["/butik", "/butiker", "/store", "/shop", "/shops"]

    for a in anchors:
        try:
            text = (a.inner_text() or "").strip()
            href = a.get_attribute("href") or ""
        except Exception:
            continue
        if not text or len(text) < 2:
            continue
        lower_href = href.lower()
        lower_text = text.lower()
        if any(k in lower_href for k in heuristics) or any(k in lower_text for k in ["butik", "store", "shop"]):
            cleaned = clean_store_name(text)
            if cleaned and cleaned not in seen:
                names.append(cleaned)
                seen.add(cleaned)

    # Fallback: look for elements with store-like class names
    if not names:
        candidates = page.query_selector_all("[class*='store'], [class*='butik'], [class*='shop']")
        for el in candidates:
            try:
                text = (el.inner_text() or "").strip()
            except Exception:
                continue
            cleaned = clean_store_name(text)
            if cleaned and cleaned not in seen:
                names.append(cleaned)
                seen.add(cleaned)

    return names


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context()
        page = context.new_page()

        all_names = []
        merged_display = []
        for url in URLS:
            page.goto(url, wait_until="networkidle")
            # small wait to let dynamic content render
            page.wait_for_timeout(1000)
            names = extract_store_links(page)

            # Deduplicate per-URL while preserving order
            per_seen = set()
            per_unique = []
            for n in names:
                if n not in per_seen:
                    per_unique.append(n)
                    per_seen.add(n)
            # Remove generic header entries (e.g. 'butik', 'butiker') that are not real stores
            stop_headers = {"butik", "butiker"}
            per_unique = [x for x in per_unique if x and x.strip().lower() not in stop_headers]
            # Save per-URL file using a slugified filename
            parsed = urlparse(url)
            slug_base = (parsed.netloc + parsed.path).lower()
            slug = re.sub(r"[^a-z0-9]+", "_", slug_base).strip("_")
            per_filename = f"westfield_stores_{slug}.json"
            with open(per_filename, "w", encoding="utf-8") as pf:
                json.dump(per_unique, pf, ensure_ascii=False, indent=2)

            # Add a header row for this site using the page title (fallback to netloc)
            try:
                site_title = page.title().strip()
            except Exception:
                site_title = parsed.netloc
            if not site_title:
                site_title = parsed.netloc

            merged_display.append(f"== {site_title} ==")
            # Number stores per-site (1..n)
            for i, nm in enumerate(per_unique, start=1):
                merged_display.append(f"{i}. {nm}")
            # keep full list as before if needed
            all_names.extend(per_unique)

        # Previously we deduplicated across sites; now we produce a grouped, numbered
        # merged output that clearly separates stores per source URL.
        print(f"Found data for {len(URLS)} site(s). Writing grouped output with per-site numbering.")
        with open("westfield_stores.json", "w", encoding="utf-8") as f:
            json.dump(merged_display, f, ensure_ascii=False, indent=2)

        browser.close()


if __name__ == "__main__":
    main()

