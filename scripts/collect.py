#!/usr/bin/env python3
"""GLAMSHUB collector.

Fetches news about damage to galleries, libraries, archives and museums, filters
and de-duplicates it, classifies each item, and appends new records to
data/incidents.json with verification = "auto".

Standard library only. Optional: set ANTHROPIC_API_KEY to let a small Claude
model classify headlines more accurately (env GLAMSHUB_MODEL overrides the model).

Usage:
    python scripts/collect.py              # normal run
    python scripts/collect.py --dry-run    # print what would be added, write nothing
    python scripts/collect.py --skip-gdelt --skip-google --offline-file items.json
"""
from __future__ import annotations

import argparse
import datetime as dt
import difflib
import hashlib
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_FILE = ROOT / "data" / "incidents.json"
SEEN_FILE = ROOT / "data" / "seen.json"
GEOCACHE_FILE = ROOT / "data" / "geocache.json"
SOURCES_FILE = ROOT / "scripts" / "sources.json"
GAZ_FILE = ROOT / "scripts" / "gazetteer.json"

UA = "GLAMSHUB-collector/1.0 (+https://akhileshksy.github.io/glamshubs/)"
NOW = dt.datetime.now(dt.timezone.utc)
MAX_NEW_PER_RUN = 120
SEEN_DAYS = 60
DUP_RATIO = 0.85

CAUSES = ["war-conflict", "looting", "deliberate", "fire", "flood", "earthquake", "collapse", "neglect", "other"]
TYPES = ["library", "museum", "archive", "gallery", "multiple", "other"]
STATUSES = ["destroyed", "damaged", "looted", "at-risk"]


def log(*a):
    print(*a, file=sys.stderr, flush=True)


def load_json(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def save_json(path: Path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def http_get(url: str, timeout: int = 30, retries: int = 2, headers: dict | None = None) -> bytes:
    h = {"User-Agent": UA, **(headers or {})}
    last = None
    for attempt in range(retries + 1):
        try:
            req = urllib.request.Request(url, headers=h)
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read()
        except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
            last = e
            time.sleep(2 * (attempt + 1))
    raise RuntimeError(f"GET failed for {url[:110]}: {last}")


# ----------------------------------------------------------------- fetching

def _iso_date(value: str | None) -> str:
    """Return YYYY-MM-DD from RFC 822, ISO 8601 or GDELT timestamps."""
    if not value:
        return NOW.date().isoformat()
    value = value.strip()
    try:
        return parsedate_to_datetime(value).astimezone(dt.timezone.utc).date().isoformat()
    except (TypeError, ValueError):
        pass
    m = re.match(r"(\d{4})-?(\d{2})-?(\d{2})", value)
    if m:
        return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
    return NOW.date().isoformat()


def parse_feed(raw: bytes, origin: str, lang: str) -> list[dict]:
    """Parse RSS 2.0 or Atom into plain dicts."""
    items: list[dict] = []
    try:
        root = ET.fromstring(raw)
    except ET.ParseError as e:
        log(f"  feed parse error: {e}")
        return items
    for it in root.iter("item"):
        title = (it.findtext("title") or "").strip()
        link = (it.findtext("link") or "").strip()
        src_el = it.find("source")
        source = (src_el.text or "").strip() if src_el is not None and src_el.text else ""
        if title and link:
            items.append({"title": title, "url": link, "source": source,
                          "published": _iso_date(it.findtext("pubDate")), "lang": lang, "origin": origin})
    ns = "{http://www.w3.org/2005/Atom}"
    for en in root.iter(ns + "entry"):
        title = (en.findtext(ns + "title") or "").strip()
        link_el = en.find(ns + "link")
        link = (link_el.get("href") if link_el is not None else "") or ""
        if title and link:
            items.append({"title": title, "url": link.strip(), "source": "",
                          "published": _iso_date(en.findtext(ns + "updated") or en.findtext(ns + "published")),
                          "lang": lang, "origin": origin})
    return items


def clean_google_title(title: str, source: str) -> str:
    # Google News appends " - Publisher" to every headline.
    if source and title.endswith(" - " + source):
        return title[: -len(source) - 3].strip()
    m = re.match(r"^(.*\S)\s+-\s+[^-]{2,60}$", title)
    return m.group(1).strip() if m else title


def fetch_google_news(cfg: dict) -> tuple[list[dict], int]:
    items, ok = [], 0
    groups = [{**e, "queries": cfg.get("queries", [])} for e in cfg.get("editions", [])] + cfg.get("extra_languages", [])
    for g in groups:
        for q in g["queries"]:
            full_q = f'{q} when:{cfg.get("when", "2d")}'
            url = "https://news.google.com/rss/search?" + urllib.parse.urlencode(
                {"q": full_q, "hl": g["hl"], "gl": g["gl"], "ceid": g["ceid"]})
            try:
                raw = http_get(url)
            except RuntimeError as e:
                log(" ", e)
                continue
            ok += 1
            for it in parse_feed(raw, "google-news", g["hl"].split("-")[0]):
                it["title"] = clean_google_title(it["title"], it["source"])
                items.append(it)
            time.sleep(1)
    return items, ok


def fetch_gdelt(cfg: dict) -> tuple[list[dict], int]:
    items, ok = [], 0
    for q in cfg.get("queries", []):
        params = {"query": q, "mode": "artlist", "format": "json", "sort": "datedesc",
                  "maxrecords": str(cfg.get("maxrecords", 60)), "timespan": cfg.get("timespan", "1d")}
        url = "https://api.gdeltproject.org/api/v2/doc/doc?" + urllib.parse.urlencode(params)
        try:
            raw = http_get(url, timeout=45)
            data = json.loads(raw.decode("utf-8", "replace"))
        except (RuntimeError, json.JSONDecodeError) as e:
            log("  GDELT:", str(e)[:140])
            time.sleep(6)
            continue
        ok += 1
        for a in data.get("articles", []):
            if a.get("title") and a.get("url"):
                items.append({"title": a["title"].strip(), "url": a["url"], "source": a.get("domain", ""),
                              "published": _iso_date(a.get("seendate")),
                              "lang": (a.get("language") or "")[:2].lower(), "origin": "gdelt"})
        time.sleep(6)  # GDELT asks for roughly one request per 5 seconds
    return items, ok


def fetch_rss_feeds(urls: list[str]) -> tuple[list[dict], int]:
    items, ok = [], 0
    for u in urls:
        try:
            raw = http_get(u)
        except RuntimeError as e:
            log(" ", e)
            continue
        ok += 1
        items += parse_feed(raw, "rss", "")
    return items, ok


# ---------------------------------------------------------------- filtering

def is_relevant(title: str, rules: dict) -> bool:
    t = title.lower()
    if any(x in t for x in rules.get("exclude_terms", [])):
        return False
    return (any(x in t for x in rules.get("institution_terms", []))
            and any(x in t for x in rules.get("damage_terms", [])))


def norm_title(t: str) -> str:
    t = re.sub(r"[^\w\s]", " ", t.lower())
    return re.sub(r"\s+", " ", t).strip()


def _stems(t: str) -> set[str]:
    # Crude stems (first 5 letters of words longer than 2) so "damages"/"damaged" match.
    return {w[:5] for w in t.split() if len(w) > 2}


def similar(a: str, b: str) -> bool:
    """True when two normalised headlines most likely describe the same story."""
    if not a or not b:
        return False
    sm = difflib.SequenceMatcher(None, a, b)
    if sm.real_quick_ratio() >= DUP_RATIO and sm.quick_ratio() >= DUP_RATIO and sm.ratio() >= DUP_RATIO:
        return True
    sa, sb = _stems(a), _stems(b)
    shared = len(sa & sb)
    # Same words in a different order; require 4+ shared stems so a changed place name keeps stories apart.
    return shared >= 4 and shared / len(sa | sb) >= 0.7


def url_key(u: str) -> str:
    return hashlib.sha1(u.encode("utf-8")).hexdigest()[:16]


# ----------------------------------------------------------- classification

RE_TYPE = {
    "library": r"librar|bibliothè|biblioteca|مكتبة|бібліотек|библиотек",
    "archive": r"archiv|أرشيف|архів|архив",
    "museum": r"museum|musée|museo|متحف|музей|музеї",
    "gallery": r"galler|galerie|galería|معرض|галере",
}
RE_CAUSE = [
    ("looting", r"loot|pillag|plunder|stolen|theft|ransack|نهب|pillé|saque|разграб|розграб"),
    ("war-conflict", r"\bwar\b|conflict|shell|bomb|airstrike|air strike|missile|drone|rocket|invasion|offensive|militia|rebel|bombard|قصف|обстріл|обстрел|ракет"),
    ("deliberate", r"demolish|razed|bulldoz|blown up|blew up|deliberate|iconoclas|arson|set on fire|set fire"),
    ("earthquake", r"earthquake|quake|séisme|terremoto|زلزال|землетрус|землетряс"),
    ("flood", r"flood|inundat|water damage|inondation|inundaci|فيضان|повен|наводнен"),
    ("collapse", r"collaps|cave-in|effondr|derrumb|انهيار"),
    ("fire", r"\bfire\b|blaze|burn|incendi|حريق|пожеж|пожар"),
    ("neglect", r"neglect|decay|disrepair|abandon"),
]
RE_STATUS = [
    ("destroyed", r"destroy|razed|ruined|obliterat|burn(?:ed|t) down|gutted|flatten|détrui|destruid|تدمير|دمر|знищ|зруйнов|разруш|уничтож"),
    ("looted", r"loot|stolen|ransack|plunder|pillag|نهب|pillé|saque"),
    ("at-risk", r"at risk|threat|endanger|in danger|under threat"),
    ("damaged", r"damag|hit|struck|shelled|partly|partially|endommag|dañad|ضرر|пошкодж"),
]


def rule_classify(title: str) -> dict:
    t = title.lower()
    found = [(m.start(), k) for k, rx in RE_TYPE.items() for m in [re.search(rx, t)] if m]
    found.sort()
    kinds = [k for _, k in found]
    itype = "multiple" if len(kinds) > 1 else (kinds[0] if kinds else "other")
    cause = next((k for k, rx in RE_CAUSE if re.search(rx, t)), "other")
    status = next((k for k, rx in RE_STATUS if re.search(rx, t)), "damaged")
    if cause == "looting" and status == "damaged":
        status = "looted"
    return {"institutionType": itype, "cause": cause, "status": status}


def build_gazetteer(gaz: list[dict]):
    entries = []
    for g in gaz:
        for a in g.get("aliases", []):
            a = a.lower()
            entries.append((a, g, bool(re.match(r"^[a-z0-9 .'()\-]+$", a))))
    entries.sort(key=lambda e: -len(e[0]))
    by_name = {g["name"].lower(): g for g in gaz}
    return entries, by_name


def find_place(text: str, gaz_index):
    entries, by_name = gaz_index
    t = text.lower()
    city = country = None
    for alias, g, latin in entries:
        hit = re.search(r"(?<![a-z])" + re.escape(alias) + r"(?![a-z])", t) if latin else (alias in t)
        if not hit:
            continue
        if g["type"] == "city" and city is None:
            city = g
        elif g["type"] == "country" and country is None:
            country = g
        if city and country:
            break
    if city and not country:
        country = by_name.get(city["country"].lower())
    return city, country


def lookup_country(name: str | None, gaz_index):
    if not name:
        return None
    entries, by_name = gaz_index
    g = by_name.get(name.lower())
    if g:
        return g
    low = name.lower()
    for alias, g2, _ in entries:
        if g2["type"] == "country" and alias == low:
            return g2
    return None


def geocode(query: str, cache: dict, budget: list[int]):
    """Nominatim lookup with a persistent cache. budget is a one-element list (remaining calls)."""
    if query in cache:
        return cache[query]
    if budget[0] <= 0:
        return None
    budget[0] -= 1
    url = "https://nominatim.openstreetmap.org/search?" + urllib.parse.urlencode({"q": query, "format": "json", "limit": "1"})
    try:
        data = json.loads(http_get(url, timeout=20, retries=1).decode("utf-8"))
    except (RuntimeError, json.JSONDecodeError):
        return None
    finally:
        time.sleep(1.2)  # Nominatim usage policy: max 1 request per second
    res = {"lat": round(float(data[0]["lat"]), 4), "lng": round(float(data[0]["lon"]), 4)} if data else None
    cache[query] = res
    return res


LLM_SYSTEM = (
    "You classify news headlines for a database of damage to GLAM institutions "
    "(galleries, libraries, archives, museums). Use ONLY what the headline states; never invent facts. "
    "Reply with one JSON object and nothing else."
)
LLM_PROMPT = """Headline: {title}
Publisher: {source}
Published: {date}

Return JSON with these keys:
- "relevant": true only if the headline reports damage, destruction, looting or loss of a gallery, library, archive or museum (or its collections), or a credible threat to one. Otherwise false.
- "institution": name of the institution, or null
- "institutionType": one of {types}
- "country": English country name, or null
- "city": English city or town, or null
- "cause": one of {causes}
- "status": one of {statuses}
- "summary": one neutral sentence of at most 25 words restating the headline in your own words, or null"""


def llm_classify(item: dict, api_key: str, model: str):
    body = {
        "model": model, "max_tokens": 400, "system": LLM_SYSTEM,
        "messages": [{"role": "user", "content": LLM_PROMPT.format(
            title=item["title"], source=item.get("source", ""), date=item["published"],
            types=TYPES, causes=CAUSES, statuses=STATUSES)}],
    }
    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages", data=json.dumps(body).encode("utf-8"),
        headers={"x-api-key": api_key, "anthropic-version": "2023-06-01", "content-type": "application/json", "User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            payload = json.loads(r.read().decode("utf-8"))
        text = "".join(b.get("text", "") for b in payload.get("content", []) if b.get("type") == "text")
        m = re.search(r"\{.*\}", text, re.S)
        out = json.loads(m.group(0)) if m else None
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, KeyError) as e:
        log("  LLM error:", str(e)[:120])
        return None
    if not isinstance(out, dict):
        return None
    if out.get("institutionType") not in TYPES:
        out["institutionType"] = None
    if out.get("cause") not in CAUSES:
        out["cause"] = None
    if out.get("status") not in STATUSES:
        out["status"] = None
    return out


# ------------------------------------------------------------------- main

def make_record(item, cls, gaz_index, geo_cache, geo_budget):
    title = item["title"]
    city_g, country_g = find_place(title, gaz_index)
    llm = cls.get("llm") or {}
    if llm.get("country"):
        country_g = lookup_country(llm["country"], gaz_index) or country_g
    country_name = (country_g or {}).get("name") or llm.get("country") or "Unknown"
    city_name = llm.get("city") or (city_g or {}).get("name")
    lat = lng = None
    precision = None
    if city_g and (not llm.get("city") or llm["city"].lower() == city_g["name"].lower()):
        lat, lng, precision = city_g["lat"], city_g["lng"], "city"
    elif llm.get("city") and country_g:
        g = geocode(f'{llm["city"]}, {country_g["name"]}', geo_cache, geo_budget)
        if g:
            lat, lng, precision = g["lat"], g["lng"], "city"
    if lat is None and country_g:
        lat, lng, precision = country_g["lat"], country_g["lng"], "country"
        city_name = city_name if city_g or llm.get("city") else None
    return {
        "id": "auto-" + url_key(item["url"]),
        "title": title,
        "date": item["published"],
        "institution": llm.get("institution") or "",
        "institutionType": llm.get("institutionType") or cls["institutionType"],
        "country": country_name,
        "countryCode": (country_g or {}).get("code", ""),
        "city": city_name or "",
        "lat": lat, "lng": lng, "geoPrecision": precision,
        "cause": llm.get("cause") or cls["cause"],
        "status": llm.get("status") or cls["status"],
        "summary": (llm.get("summary") or "").strip(),
        "sourceName": item.get("source") or urllib.parse.urlparse(item["url"]).netloc,
        "sourceUrl": item["url"],
        "extraSources": [],
        "language": item.get("lang", ""),
        "verification": "auto",
        "addedAt": NOW.strftime("%Y-%m-%dT%H:%M:%SZ"),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dry-run", action="store_true", help="do everything except write files")
    ap.add_argument("--skip-google", action="store_true")
    ap.add_argument("--skip-gdelt", action="store_true")
    ap.add_argument("--skip-geocode", action="store_true")
    ap.add_argument("--max-llm", type=int, default=40, help="max headlines sent to the language model per run")
    ap.add_argument("--offline-file", help="JSON list of items (title,url,source,published) to use instead of the network; for testing")
    args = ap.parse_args()

    sources = load_json(SOURCES_FILE, {})
    rules = sources.get("rules", {})
    gaz_index = build_gazetteer(load_json(GAZ_FILE, []))
    db = load_json(DATA_FILE, {"meta": {}, "incidents": []})
    incidents: list[dict] = db.get("incidents", [])
    seen: dict = load_json(SEEN_FILE, {})
    geo_cache: dict = load_json(GEOCACHE_FILE, {})
    api_key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    model = os.environ.get("GLAMSHUB_MODEL", "").strip() or "claude-haiku-5-5"

    # 1. fetch ----------------------------------------------------------------
    raw_items: list[dict] = []
    ok_sources = attempted = 0
    if args.offline_file:
        raw_items = json.loads(Path(args.offline_file).read_text(encoding="utf-8"))
        ok_sources = attempted = 1
    else:
        gn, gd = sources.get("google_news", {}), sources.get("gdelt", {})
        if gn.get("enabled") and not args.skip_google:
            log("Fetching Google News …")
            items, ok = fetch_google_news(gn)
            raw_items += items
            ok_sources += 1 if ok else 0
            attempted += 1
        if gd.get("enabled") and not args.skip_gdelt:
            log("Fetching GDELT …")
            items, ok = fetch_gdelt(gd)
            raw_items += items
            ok_sources += 1 if ok else 0
            attempted += 1
        if sources.get("rss_feeds"):
            log("Fetching extra RSS feeds …")
            items, ok = fetch_rss_feeds(sources["rss_feeds"])
            raw_items += items
            ok_sources += 1 if ok else 0
            attempted += 1
    log(f"Fetched {len(raw_items)} items from {ok_sources}/{attempted} source groups.")
    if attempted and ok_sources == 0:
        log("ERROR: every source failed; failing the run so the workflow alerts the maintainer.")
        return 2

    # 2. filter + dedupe ---------------------------------------------------------
    known_urls = set()
    recent_titles: list[tuple[str, dict]] = []
    cutoff = (NOW - dt.timedelta(days=45)).date().isoformat()
    for rec in incidents:
        known_urls.add(rec.get("sourceUrl", ""))
        known_urls.update(s.get("url", "") for s in rec.get("extraSources", []))
        if str(rec.get("date", "")) >= cutoff or str(rec.get("addedAt", ""))[:10] >= cutoff:
            recent_titles.append((norm_title(rec.get("title", "")), rec))

    candidates: list[dict] = []
    stats = {"irrelevant": 0, "seen": 0, "merged": 0}
    batch_titles: list[tuple[str, dict]] = []
    for it in raw_items:
        k = url_key(it["url"])
        if it["url"] in known_urls or k in seen:
            stats["seen"] += 1
            continue
        seen[k] = NOW.date().isoformat()
        if not is_relevant(it["title"], rules):
            stats["irrelevant"] += 1
            continue
        nt = norm_title(it["title"])
        target = next((r for t, r in recent_titles if similar(nt, t)), None)
        if target is not None:
            extras = target.setdefault("extraSources", [])
            if len(extras) < 5 and it["url"] not in {e["url"] for e in extras}:
                extras.append({"name": it.get("source") or urllib.parse.urlparse(it["url"]).netloc, "url": it["url"]})
            stats["merged"] += 1
            continue
        if any(similar(nt, t) for t, _ in batch_titles):
            stats["merged"] += 1
            continue
        batch_titles.append((nt, it))
        candidates.append(it)
    log(f"Candidates: {len(candidates)} (skipped {stats['seen']} seen, {stats['irrelevant']} irrelevant, {stats['merged']} merged as duplicates)")

    # 3. classify + build records ----------------------------------------------
    candidates.sort(key=lambda i: i["published"], reverse=True)
    candidates = candidates[:MAX_NEW_PER_RUN]
    geo_budget = [0 if args.skip_geocode or args.offline_file else 20]
    new_records, llm_used, llm_calls = [], 0, 0
    for it in candidates:
        cls = rule_classify(it["title"])
        if api_key and llm_calls < args.max_llm:
            llm_calls += 1
            out = llm_classify(it, api_key, model)
            if out is not None:
                if out.get("relevant") is False:
                    continue  # model says this is not about a GLAM institution
                cls["llm"] = out
                llm_used += 1
        new_records.append(make_record(it, cls, gaz_index, geo_cache, geo_budget))
    log(f"Built {len(new_records)} new records ({llm_used} classified by the language model).")

    # 4. write ------------------------------------------------------------------
    cutoff_seen = (NOW - dt.timedelta(days=SEEN_DAYS)).date().isoformat()
    seen = {k: v for k, v in seen.items() if v >= cutoff_seen}
    incidents.extend(new_records)
    incidents.sort(key=lambda r: (str(r.get("date", "")), r.get("id", "")), reverse=True)
    db["incidents"] = incidents
    db["meta"] = {
        **db.get("meta", {}),
        "updated": NOW.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "count": len(incidents),
        "autoCount": sum(1 for r in incidents if r.get("verification") == "auto"),
        "lastRun": {"fetched": len(raw_items), "added": len(new_records), "merged": stats["merged"], "llm": bool(api_key)},
    }
    if args.dry_run:
        for r in new_records:
            print(f'+ {r["date"]} [{r["country"]}] {r["institutionType"]}/{r["cause"]}/{r["status"]}: {r["title"]}')
        log("Dry run: nothing written.")
        return 0
    save_json(DATA_FILE, db)
    save_json(SEEN_FILE, seen)
    if not args.skip_geocode:
        save_json(GEOCACHE_FILE, geo_cache)
    log("Wrote", DATA_FILE.relative_to(ROOT))
    return 0


if __name__ == "__main__":
    sys.exit(main())
