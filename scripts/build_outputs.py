#!/usr/bin/env python3
"""Build data/incidents.csv, feed.xml and sitemap.xml from data/incidents.json.

Standard library only. Set GLAMSHUB_BASE_URL if the site moves (for example to a
custom domain); it must end with a slash.
"""
from __future__ import annotations

import csv
import datetime as dt
import json
import os
from email.utils import format_datetime
from pathlib import Path
from urllib.parse import quote
from xml.sax.saxutils import escape

ROOT = Path(__file__).resolve().parent.parent
BASE = os.environ.get("GLAMSHUB_BASE_URL", "https://akhileshksy.github.io/glamshubs/")
if not BASE.endswith("/"):
    BASE += "/"

PAGES = ["", "incidents.html", "map.html", "stats.html", "methodology.html", "about.html", "report.html"]
COLUMNS = ["id", "date", "title", "institution", "institutionType", "country", "countryCode", "city",
           "lat", "lng", "geoPrecision", "cause", "status", "verification", "sourceName", "sourceUrl", "summary"]


def sort_key(d: str) -> str:
    d = str(d or "")
    return d + "-12-31" if len(d) == 4 else d + "-28" if len(d) == 7 else d


def to_datetime(d: str) -> dt.datetime:
    try:
        return dt.datetime.fromisoformat(sort_key(d)).replace(tzinfo=dt.timezone.utc)
    except ValueError:
        return dt.datetime.now(dt.timezone.utc)


def main() -> None:
    db = json.loads((ROOT / "data" / "incidents.json").read_text(encoding="utf-8"))
    incidents = sorted(db.get("incidents", []), key=lambda r: sort_key(r.get("date")), reverse=True)
    updated = db.get("meta", {}).get("updated") or dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    # CSV --------------------------------------------------------------------
    with open(ROOT / "data" / "incidents.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(COLUMNS)
        for r in incidents:
            w.writerow(["" if r.get(c) is None else r.get(c) for c in COLUMNS])

    # RSS --------------------------------------------------------------------
    items = []
    for r in incidents[:50]:
        link = f"{BASE}incident.html?id={quote(r['id'])}"
        desc = r.get("summary") or f"Reported by {r.get('sourceName', 'unknown source')}."
        meta = " · ".join(x for x in [r.get("city"), r.get("country"), r.get("status")] if x)
        items.append(
            "    <item>\n"
            f"      <title>{escape(r['title'])}</title>\n"
            f"      <link>{escape(link)}</link>\n"
            f"      <guid isPermaLink=\"false\">{escape(r['id'])}</guid>\n"
            f"      <pubDate>{format_datetime(to_datetime(r.get('date')))}</pubDate>\n"
            f"      <description>{escape(desc + (' (' + meta + ')' if meta else ''))}</description>\n"
            "    </item>")
    feed = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<rss version="2.0">\n  <channel>\n'
        "    <title>GLAMSHUB: GLAM institutions damaged or destroyed</title>\n"
        f"    <link>{escape(BASE)}</link>\n"
        "    <description>Reports of damage to galleries, libraries, archives and museums worldwide.</description>\n"
        "    <language>en</language>\n"
        f"    <lastBuildDate>{format_datetime(dt.datetime.now(dt.timezone.utc))}</lastBuildDate>\n"
        + "\n".join(items) + "\n  </channel>\n</rss>\n")
    (ROOT / "feed.xml").write_text(feed, encoding="utf-8")

    # Sitemap ----------------------------------------------------------------
    lastmod = updated[:10]
    urls = "\n".join(f"  <url><loc>{escape(BASE + p)}</loc><lastmod>{lastmod}</lastmod></url>" for p in PAGES)
    (ROOT / "sitemap.xml").write_text(
        '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n' + urls + "\n</urlset>\n",
        encoding="utf-8")
    print(f"Wrote incidents.csv ({len(incidents)} rows), feed.xml and sitemap.xml")


if __name__ == "__main__":
    main()
