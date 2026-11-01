# GLAMSHUB

An automatically updated record of damage to and destruction of **G**alleries, **L**ibraries, **A**rchives and **M**useums worldwide, whether from war, conflict, fire, flood or neglect.

Live site: https://akhileshksy.github.io/glamshubs/

It is a static site (plain HTML, CSS and JavaScript, no build tools). A scheduled GitHub Action collects news, writes it to `data/incidents.json`, rebuilds the CSV, RSS feed and sitemap, and redeploys the site to GitHub Pages.

```
News sources ─► scripts/collect.py ─► data/incidents.json ─► GitHub Pages
 (Google News,   filter, de-duplicate,   (+ CSV, feed.xml,
  GDELT, RSS)    classify, geolocate     sitemap.xml)
```

## Deploy in 6 steps

1. **Create the repository.** On GitHub, create a public repository named `glamshubs` under the `akhileshksy` account. Leave it empty.
2. **Upload the files.** Upload the *contents* of this folder (not the folder itself) so that `index.html` sits at the top level of the repo. Include the hidden `.github` and `.nojekyll` entries. With Git:
   ```bash
   cd glamshubs
   git init -b main
   git add .
   git commit -m "Initial GLAMSHUB site"
   git remote add origin https://github.com/akhileshksy/glamshubs.git
   git push -u origin main
   ```
3. **Turn on Pages.** Repository → *Settings* → *Pages* → *Build and deployment* → **Source: GitHub Actions**.
4. **Allow the bot to commit.** *Settings* → *Actions* → *General* → *Workflow permissions* → choose **Read and write permissions** → Save.
5. **Run it once.** *Actions* tab → *Update data and deploy site* → *Run workflow*. After a couple of minutes the site is live at https://akhileshksy.github.io/glamshubs/. From then on it refreshes every six hours.
6. **(Optional) Better classification.** Add a repository secret `ANTHROPIC_API_KEY` (*Settings* → *Secrets and variables* → *Actions*). The collector then uses a small Claude model to extract institution, place, cause and a one-line summary from each headline. Without it, simpler keyword rules are used. Set the repository variable `GLAMSHUB_MODEL` to override the default model.

## Preview locally

```bash
python -m http.server 8000      # then open http://localhost:8000
python scripts/collect.py --dry-run   # see what the collector would add
python scripts/build_outputs.py       # regenerate CSV, RSS, sitemap
```

Opening `index.html` directly from disk will not load the data, because browsers block `fetch()` on `file://` URLs; use the local server.

## Folder layout

```
index.html, incidents.html, map.html,
stats.html, incident.html, report.html,
about.html, methodology.html, 404.html   site pages
assets/css/style.css                     styling (light and dark)
assets/js/app.js                         all front-end logic
assets/img/favicon.svg
data/incidents.json                      the dataset (source of truth)
data/incidents.csv                       generated
data/seen.json, data/geocache.json      collector memory (generated)
feed.xml, sitemap.xml, robots.txt        generated / SEO
scripts/collect.py                       the collector
scripts/build_outputs.py                 CSV, RSS and sitemap builder
scripts/sources.json                     queries, languages, filter words
scripts/gazetteer.json                   countries and conflict-zone cities
.github/workflows/update.yml             schedule, commit, deploy, failure alert
.github/ISSUE_TEMPLATE/                  incident-report and correction forms
```

## How records are curated

The collector appends records with `"verification": "auto"` and never edits records a person has touched, except to attach extra source links to duplicates. To review a record, edit `data/incidents.json` on GitHub: fix the fields, add a better `sourceUrl`, and set `verification` to `reported` or `verified`. To remove a bad record, delete it from the file. Incident reports arrive as GitHub issues (`needs-review` label); add accepted ones to the JSON by hand.

Record fields: `id, title, date (YYYY, YYYY-MM or YYYY-MM-DD), institution, institutionType, country, countryCode, city, lat, lng, geoPrecision, cause, status, summary, sourceName, sourceUrl, extraSources, verification`. Allowed values for type, cause, status and verification are listed at the top of `assets/js/app.js`.

The 12 records included at first are well-known historical incidents so the site is not empty on day one. Their source links are background searches; replace them with primary sources as you review them.

## Tuning what is collected

Edit `scripts/sources.json`:

- `google_news.queries` and `extra_languages`: search phrases per language.
- `gdelt.queries`: GDELT query strings.
- `rss_feeds`: add the RSS feeds of organisations you follow (UNESCO, ICOM, IFLA, national libraries and so on). Check each URL yourself before adding it.
- `rules`: the institution words, damage words and exclusion words used by the filter. If you see irrelevant records, add words to `exclude_terms`.

## Custom domain (later)

1. Buy a domain and add DNS records as described in GitHub's *Configuring a custom domain for GitHub Pages* guide (A records for the apex domain, and a CNAME for `www` pointing to `akhileshksy.github.io`).
2. Put the domain on a single line in a file named `CNAME` at the top of the repo, and set it under *Settings → Pages* with *Enforce HTTPS* ticked.
3. Update the absolute URLs: `index.html` and the `<link rel="canonical">` / `og:url` tags in each page, `robots.txt`, and `SITE.baseUrl` in `assets/js/app.js`. For the feed and sitemap, set the repository variable or edit the default in `scripts/build_outputs.py` (`GLAMSHUB_BASE_URL`).

## Things to know

- **Scheduled workflows pause** on public repositories after about 60 days without repository activity. The bot's data commits normally count, and a failed run opens an issue labelled `automation-failure`, but check the Actions tab now and then.
- **Automated data is imperfect.** Headline-only classification will occasionally be wrong or duplicate an event. That is why records are labelled and why curation matters.
- **Copyright.** The collector stores only a headline, date, publisher, a link and (optionally) a short model-written restatement. Do not paste article text into the dataset.
- **Map tiles** come from OpenStreetMap's public tile server, which is fine for a small site; switch to a commercial tile provider if traffic grows.
- **Be considerate of sources.** The collector sleeps between requests (GDELT asks for about one every five seconds). Do not shorten these delays.

## Licence

Code: MIT. Dataset: CC BY 4.0. See `LICENSE`.
