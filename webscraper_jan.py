#!/usr/bin/env python3
"""
webscraper_jan.py

Usage:
  python webscraper_jan.py [URL [URL ...]]
  python webscraper_jan.py --file urls.txt

This script scrapes multiple shopping-centre pages and writes a single output
file (default: webscraper_output.txt). Each site's extracted store names are
written as plain text lines. Between sites a header line with the shopping
centre name is added to make it easy to separate blocks.
"""
from __future__ import annotations

import argparse
import re
from typing import List, Optional

from playwright.sync_api import sync_playwright


URL_DEFAULT = "https://www.westfield.com/sv/sweden/mallofscandinavia/butiker"
OUTPUT_DEFAULT = "webscraper_output.txt"


def clean_store_name(raw: str) -> str:
    if not raw:
        return ""
    s = raw.strip()
    s = re.sub(r"\s*\([^)]*\)", "", s)
    s = re.sub(r"\b[Pp]lan\s*\d+\b", "", s)
    s = re.sub(r"(?i)\b(stäng[ta]?|stänger|stängt|öppet|stängd)\b", "", s)
    s = re.sub(r"[-–—].*$", "", s)
    s = re.sub(r"(?i)^(butik|butiker|shop)[:\s-]+", "", s)
    s = re.sub(r"\s+", " ", s).strip()
    s = re.sub(r"(?i)\bplan\b", "", s).strip()
    m = re.match(r"^(?P<x>.+?)\s+\1$", s, flags=re.IGNORECASE)
    if m:
        s = m.group("x").strip()
    return s


def extract_store_names_from_page(page) -> List[str]:
    anchors = page.query_selector_all("a")
    names: List[str] = []
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

    # fallback: elements with store-like class names
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


def extract_mall_name(page) -> Optional[str]:
    # Try common patterns for a mall or page title
    try:
        h1 = page.query_selector("h1")
        if h1:
            t = (h1.inner_text() or "").strip()
            if t:
                return t
    except Exception:
        pass
    # fallback to the title
    try:
        t = page.title() or ""
        return t.strip() if t else None
    except Exception:
        return None


def scrape_urls(urls: List[str]) -> List[dict]:
    results = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context()
        for url in urls:
            page = context.new_page()
            page.goto(url, wait_until="networkidle")
            page.wait_for_timeout(800)
            mall_name = extract_mall_name(page) or url
            names = extract_store_names_from_page(page)
            results.append({"url": url, "mall": mall_name, "stores": names})
            page.close()
        browser.close()
    return results


def write_output_text(results: List[dict], out_path: str):
    # We will write blocks separated by a blank line and a header with mall name
    with open(out_path, "w", encoding="utf-8") as f:
        first = True
        for r in results:
            if not first:
                # place a blank line and the mall name between websites (as requested)
                f.write("\n")
                f.write(f"{r['mall']}\n")
                f.write("\n")
            # write store names (one per line)
            for s in r.get("stores", []):
                f.write(s + "\n")
            first = False


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("urls", nargs="*", help="URLs to scrape")
    p.add_argument("--file", "-f", help="Path to file that contains URLs (one per line)")
    p.add_argument("--output", "-o", default=OUTPUT_DEFAULT, help="Output text file")
    return p.parse_args()


def main():
    args = parse_args()
    urls: List[str] = []
    if args.file:
        with open(args.file, "r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line:
                    urls.append(line)
    if args.urls:
        urls.extend(args.urls)
    if not urls:
        urls = [URL_DEFAULT]

    results = scrape_urls(urls)
    write_output_text(results, args.output)
    print(f"Wrote output for {len(results)} sites to {args.output}")


if __name__ == "__main__":
    main()
