/* GLAMSHUB front-end. Plain JavaScript, no build step.
   All links are relative so the site works under /glamshubs/ and on a custom domain. */
(function () {
  'use strict';

  var SITE = {
    name: 'GLAMSHUB',
    repo: 'akhileshksy/glamshubs',
    baseUrl: 'https://akhileshksy.github.io/glamshubs/'
  };
  var DATA_URL = 'data/incidents.json';
  var PAGE_SIZE = 24;

  var LABELS = {
    cause: {
      'war-conflict': 'War / armed conflict', 'looting': 'Looting / theft', 'deliberate': 'Deliberate destruction',
      'fire': 'Fire', 'flood': 'Flood / water damage', 'earthquake': 'Earthquake',
      'collapse': 'Structural collapse', 'neglect': 'Neglect / decay', 'other': 'Other / unknown'
    },
    type: {
      library: 'Library', museum: 'Museum', archive: 'Archive', gallery: 'Gallery',
      multiple: 'Multiple / GLAM', other: 'Other'
    },
    status: { destroyed: 'Destroyed', damaged: 'Damaged', looted: 'Looted', 'at-risk': 'At risk' },
    verification: { verified: 'Verified', reported: 'Reported', auto: 'Automated, unverified' }
  };
  var STATUS_COLORS = { destroyed: '#b3261e', damaged: '#a86a06', looted: '#6f4aa0', 'at-risk': '#1f6f6b' };

  /* ---------- helpers ---------- */
  function esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }
  function safeUrl(u) {
    try {
      var x = new URL(u, location.href);
      return (x.protocol === 'http:' || x.protocol === 'https:') ? x.href : '#';
    } catch (e) { return '#'; }
  }
  function $(sel, root) { return (root || document).querySelector(sel); }
  function label(group, key) { return (LABELS[group] && LABELS[group][key]) || key || ''; }
  function uniq(arr) { return arr.filter(function (v, i) { return arr.indexOf(v) === i; }); }
  function place(i) { return [i.city, i.country].filter(Boolean).join(', ') || 'Location unknown'; }
  function yearOf(d) { return parseInt(String(d || '').slice(0, 4), 10) || 0; }
  function sortKey(d) {
    d = String(d || '');
    if (d.length === 4) return d + '-12-31';
    if (d.length === 7) return d + '-28';
    return d;
  }
  function fmtDate(d) {
    d = String(d || '');
    if (!d) return 'Date unknown';
    var y = parseInt(d.slice(0, 4), 10), m = parseInt(d.slice(5, 7), 10), day = parseInt(d.slice(8, 10), 10);
    if (isNaN(y)) return d;
    if (d.length === 4) return String(y);
    var dt = new Date(Date.UTC(y, (m || 1) - 1, day || 1));
    var opts = d.length === 7 ? { month: 'short', year: 'numeric' } : { day: 'numeric', month: 'short', year: 'numeric' };
    opts.timeZone = 'UTC';
    return dt.toLocaleDateString('en-GB', opts);
  }
  function countBy(list, fn) {
    var o = {};
    list.forEach(function (i) { var k = fn(i); if (k) o[k] = (o[k] || 0) + 1; });
    return Object.keys(o).map(function (k) { return [k, o[k]]; }).sort(function (a, b) { return b[1] - a[1] || a[0].localeCompare(b[0]); });
  }

  /* ---------- page chrome ---------- */
  var NAV = [
    ['index.html', 'Home', 'home'], ['incidents.html', 'Incidents', 'incidents'], ['map.html', 'Map', 'map'],
    ['stats.html', 'Statistics', 'stats'], ['methodology.html', 'Methodology', 'methodology'], ['about.html', 'About', 'about']
  ];
  function renderChrome(page) {
    var nav = NAV.map(function (n) {
      return '<a href="' + n[0] + '"' + (n[2] === page ? ' aria-current="page"' : '') + '>' + n[1] + '</a>';
    }).join('') + '<a class="cta" href="report.html"' + (page === 'report' ? ' aria-current="page"' : '') + '>Report an incident</a>' +
      '<button class="theme-btn" type="button" id="theme-btn" aria-label="Toggle dark mode">Theme</button>';
    var header = '<a class="skip" href="#main">Skip to content</a><header class="site-header"><div class="container header-row">' +
      '<a class="brand" href="index.html" aria-label="GLAMSHUB home"><b>GLAMS<span>HUB</span></b>' +
      '<small>Galleries · Libraries · Archives · Museums</small></a><nav class="nav" aria-label="Main">' + nav + '</nav></div></header>';
    var footer = '<footer class="site-footer"><div class="container"><div class="footer-grid">' +
      '<div><h2>GLAMSHUB</h2><p>An open, automatically updated record of damage to and destruction of galleries, libraries, archives and museums worldwide, in war, conflict and disaster.</p></div>' +
      '<div><h2>Explore</h2><ul><li><a href="incidents.html">All incidents</a></li><li><a href="map.html">Map</a></li><li><a href="stats.html">Statistics</a></li><li><a href="feed.xml">RSS feed</a></li><li><a href="data/incidents.csv">Download CSV</a></li><li><a href="data/incidents.json">Download JSON</a></li></ul></div>' +
      '<div><h2>Project</h2><ul><li><a href="methodology.html">Methodology &amp; corrections</a></li><li><a href="report.html">Report an incident</a></li><li><a href="https://github.com/' + SITE.repo + '" rel="noopener">Source on GitHub</a></li></ul></div></div>' +
      '<p class="fine">Data: headline, date, location and a link to the original report; summaries are written in our own words. Dataset released under CC BY 4.0, code under the MIT licence. Records marked “Automated, unverified” have not yet been checked by a person.</p></div></footer>';
    var h = $('#site-header'), f = $('#site-footer');
    if (h) h.innerHTML = header;
    if (f) f.innerHTML = footer;
    var btn = $('#theme-btn');
    if (btn) btn.addEventListener('click', function () {
      var cur = document.documentElement.dataset.theme;
      var dark = cur ? cur === 'dark' : window.matchMedia('(prefers-color-scheme: dark)').matches;
      var next = dark ? 'light' : 'dark';
      document.documentElement.dataset.theme = next;
      try { localStorage.setItem('glamshub-theme', next); } catch (e) { /* ignore */ }
    });
  }

  /* ---------- data ---------- */
  function loadData() {
    return fetch(DATA_URL, { cache: 'no-cache' }).then(function (r) {
      if (!r.ok) throw new Error('HTTP ' + r.status);
      return r.json();
    }).then(function (j) {
      j.incidents = (j.incidents || []).slice().sort(function (a, b) {
        return sortKey(b.date).localeCompare(sortKey(a.date));
      });
      return j;
    });
  }

  /* ---------- components ---------- */
  function card(i) {
    return '<article class="card status-' + esc(i.status) + '" id="' + esc(i.id) + '">' +
      '<div class="card-top"><time datetime="' + esc(i.date) + '">' + esc(fmtDate(i.date)) + '</time>' +
      '<span class="badge st-' + esc(i.status) + '">' + esc(label('status', i.status)) + '</span></div>' +
      '<h3><a href="incident.html?id=' + encodeURIComponent(i.id) + '">' + esc(i.title) + '</a></h3>' +
      '<p class="meta">' + esc(place(i)) + ' · ' + esc(label('type', i.institutionType)) + ' · ' + esc(label('cause', i.cause)) + '</p>' +
      (i.summary ? '<p class="summary">' + esc(i.summary) + '</p>' : '') +
      '<p class="source">Source: <a href="' + esc(safeUrl(i.sourceUrl)) + '" rel="noopener nofollow" target="_blank">' + esc(i.sourceName || 'link') + '</a>' +
      '<span class="ver v-' + esc(i.verification) + '">' + esc(label('verification', i.verification)) + '</span></p></article>';
  }
  function bars(el, entries, opts) {
    opts = opts || {};
    if (!entries.length) { el.innerHTML = '<p class="empty">No data yet.</p>'; return; }
    var max = Math.max.apply(null, entries.map(function (e) { return e[1]; }));
    el.innerHTML = '<ul class="bars">' + entries.map(function (e) {
      var style = 'width:' + Math.max(2, Math.round(e[1] / max * 100)) + '%' +
        (opts.colors && opts.colors[e[0]] ? ';background:' + opts.colors[e[0]] : '');
      return '<li><span>' + esc(opts.labelGroup ? label(opts.labelGroup, e[0]) : e[0]) + '</span>' +
        '<span class="track"><span class="fill" style="' + style + '"></span></span>' +
        '<span class="num">' + e[1] + '</span></li>';
    }).join('') + '</ul>';
  }
  function popupHtml(i) {
    return '<strong><a href="incident.html?id=' + encodeURIComponent(i.id) + '">' + esc(i.title) + '</a></strong><br>' +
      esc(fmtDate(i.date)) + ' · ' + esc(place(i)) + '<br>' + esc(label('status', i.status)) + ' · ' + esc(label('type', i.institutionType));
  }
  function legendHtml() {
    return '<div class="legend">' + Object.keys(STATUS_COLORS).map(function (k) {
      return '<span><i style="background:' + STATUS_COLORS[k] + '"></i>' + label('status', k) + '</span>';
    }).join('') + '</div>';
  }
  function makeMap(el, items, opts) {
    opts = opts || {};
    if (!window.L) { el.innerHTML = '<p class="empty">The map library could not be loaded. Check your connection and reload.</p>'; return null; }
    var map = L.map(el, { scrollWheelZoom: !!opts.scroll, worldCopyJump: true }).setView(opts.center || [25, 15], opts.zoom || 2);
    L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {
      maxZoom: 18,
      attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
    }).addTo(map);
    var layer = L.layerGroup().addTo(map);
    function draw(list) {
      layer.clearLayers();
      var seen = {}, pts = [];
      list.forEach(function (i) {
        if (typeof i.lat !== 'number' || typeof i.lng !== 'number') return;
        var key = i.lat.toFixed(2) + ',' + i.lng.toFixed(2);
        var n = seen[key] = (seen[key] || 0) + 1;
        var ang = n * 2.4, rad = (n - 1) * 0.012;
        var lat = i.lat + Math.sin(ang) * rad, lng = i.lng + Math.cos(ang) * rad;
        L.circleMarker([lat, lng], {
          radius: 7, weight: 1.5, color: '#ffffff', fillColor: STATUS_COLORS[i.status] || '#555555', fillOpacity: 0.92
        }).bindPopup(popupHtml(i)).addTo(layer);
        pts.push([lat, lng]);
      });
      if (pts.length && !opts.noFit) map.fitBounds(pts, { padding: [30, 30], maxZoom: opts.maxZoom || 6 });
    }
    draw(items);
    return { map: map, draw: draw };
  }
  function showError(el, err) {
    if (!el) return;
    el.innerHTML = '<p class="empty">Could not load the incident data (' + esc(err && err.message) + '). If you are viewing the files locally, serve the folder with <code>python -m http.server</code> instead of opening the file directly.</p>';
  }

  /* ---------- pages ---------- */
  function initHome(data) {
    var list = data.incidents;
    var countries = uniq(list.map(function (i) { return i.country; }).filter(function (c) { return c && c !== 'Unknown'; }));
    var cutoff = Date.now() - 30 * 864e5;
    var recent = list.filter(function (i) { return new Date(sortKey(i.date)).getTime() >= cutoff; }).length;
    var destroyed = list.filter(function (i) { return i.status === 'destroyed'; }).length;
    var meta = data.meta || {};
    var set = function (id, v) { var e = $('#' + id); if (e) e.textContent = v; };
    set('l-total', list.length);
    set('l-countries', countries.length);
    set('l-destroyed', destroyed);
    set('l-recent', recent);
    set('l-updated', meta.updated ? new Date(meta.updated).toISOString().slice(0, 16).replace('T', ' ') + ' UTC' : 'n/a');
    var latest = $('#latest');
    latest.innerHTML = list.slice(0, 9).map(card).join('') || '<p class="empty">No incidents recorded yet.</p>';
    bars($('#hotspots'), countBy(list, function (i) { return i.country && i.country !== 'Unknown' ? i.country : null; }).slice(0, 8));
    bars($('#causes'), countBy(list, function (i) { return i.cause; }), { labelGroup: 'cause' });
    var m = $('#home-map');
    if (m) makeMap(m, list);
    var form = $('#hero-search');
    if (form) form.addEventListener('submit', function (e) {
      e.preventDefault();
      location.href = 'incidents.html?q=' + encodeURIComponent($('#hero-q').value.trim());
    });
  }

  function fillSelect(sel, values, group) {
    var cur = sel.value;
    sel.innerHTML = '<option value="">All</option>' + values.map(function (v) {
      return '<option value="' + esc(v) + '">' + esc(group ? label(group, v) : v) + '</option>';
    }).join('');
    sel.value = cur;
  }
  function wireFilters(list, onChange) {
    var ids = ['q', 'country', 'type', 'cause', 'status', 'verification', 'year', 'sort'];
    var el = {};
    ids.forEach(function (k) { el[k] = $('#f-' + k); });
    fillSelect(el.country, uniq(list.map(function (i) { return i.country; }).filter(Boolean)).sort());
    fillSelect(el.type, uniq(list.map(function (i) { return i.institutionType; }).filter(Boolean)).sort(), 'type');
    fillSelect(el.cause, uniq(list.map(function (i) { return i.cause; }).filter(Boolean)).sort(), 'cause');
    fillSelect(el.status, uniq(list.map(function (i) { return i.status; }).filter(Boolean)).sort(), 'status');
    fillSelect(el.verification, uniq(list.map(function (i) { return i.verification; }).filter(Boolean)).sort(), 'verification');
    fillSelect(el.year, uniq(list.map(function (i) { return String(yearOf(i.date)); }).filter(function (y) { return y !== '0'; })).sort().reverse());
    var params = new URLSearchParams(location.search);
    ids.forEach(function (k) { if (params.get(k) && el[k]) el[k].value = params.get(k); });
    function state() {
      var s = {};
      ids.forEach(function (k) { s[k] = el[k] ? el[k].value : ''; });
      return s;
    }
    function apply() {
      var s = state();
      var p = new URLSearchParams();
      ids.forEach(function (k) { if (s[k] && !(k === 'sort' && s[k] === 'new')) p.set(k, s[k]); });
      try { history.replaceState(null, '', location.pathname + (p.toString() ? '?' + p.toString() : '')); } catch (e) { /* ignore */ }
      var tokens = s.q.toLowerCase().split(/\s+/).filter(Boolean);
      var out = list.filter(function (i) {
        if (s.country && i.country !== s.country) return false;
        if (s.type && i.institutionType !== s.type) return false;
        if (s.cause && i.cause !== s.cause) return false;
        if (s.status && i.status !== s.status) return false;
        if (s.verification && i.verification !== s.verification) return false;
        if (s.year && String(yearOf(i.date)) !== s.year) return false;
        if (tokens.length) {
          var hay = [i.title, i.institution, i.city, i.country, i.summary, i.sourceName].join(' ').toLowerCase();
          for (var t = 0; t < tokens.length; t++) if (hay.indexOf(tokens[t]) === -1) return false;
        }
        return true;
      });
      if (s.sort === 'old') out.reverse();
      onChange(out);
    }
    ids.forEach(function (k) {
      if (!el[k]) return;
      el[k].addEventListener(k === 'q' ? 'input' : 'change', apply);
    });
    var reset = $('#f-reset');
    if (reset) reset.addEventListener('click', function () {
      ids.forEach(function (k) { if (el[k]) el[k].value = k === 'sort' ? 'new' : ''; });
      apply();
    });
    apply();
  }

  function initIncidents(data) {
    var shown = PAGE_SIZE, current = [];
    var out = $('#results'), count = $('#count'), more = $('#more');
    function render() {
      count.textContent = 'Showing ' + Math.min(shown, current.length) + ' of ' + current.length + ' records';
      out.innerHTML = current.slice(0, shown).map(card).join('') || '<p class="empty">No incidents match these filters.</p>';
      more.hidden = shown >= current.length;
    }
    more.querySelector('button').addEventListener('click', function () { shown += PAGE_SIZE; render(); });
    wireFilters(data.incidents, function (list) { current = list; shown = PAGE_SIZE; render(); });
  }

  function initMap(data) {
    var m = makeMap($('#big-map'), data.incidents, { scroll: true });
    var count = $('#count');
    wireFilters(data.incidents, function (list) {
      count.textContent = list.filter(function (i) { return typeof i.lat === 'number'; }).length + ' mapped of ' + list.length + ' matching records';
      if (m) m.draw(list);
    });
  }

  function initStats(data) {
    var list = data.incidents;
    var set = function (id, v) { var e = $('#' + id); if (e) e.textContent = v; };
    var countries = uniq(list.map(function (i) { return i.country; }).filter(function (c) { return c && c !== 'Unknown'; }));
    set('s-total', list.length);
    set('s-countries', countries.length);
    set('s-destroyed', list.filter(function (i) { return i.status === 'destroyed'; }).length);
    set('s-auto', list.filter(function (i) { return i.verification === 'auto'; }).length);
    bars($('#by-status'), countBy(list, function (i) { return i.status; }), { labelGroup: 'status', colors: STATUS_COLORS });
    bars($('#by-cause'), countBy(list, function (i) { return i.cause; }), { labelGroup: 'cause' });
    bars($('#by-type'), countBy(list, function (i) { return i.institutionType; }), { labelGroup: 'type' });
    bars($('#by-country'), countBy(list, function (i) { return i.country && i.country !== 'Unknown' ? i.country : null; }).slice(0, 15));
    var years = list.map(function (i) { return yearOf(i.date); }).filter(Boolean);
    var el = $('#by-year');
    if (!years.length) { el.innerHTML = '<p class="empty">No data yet.</p>'; return; }
    var min = Math.min.apply(null, years), max = Math.max.apply(null, years);
    var counts = {};
    years.forEach(function (y) { counts[y] = (counts[y] || 0) + 1; });
    var peak = Math.max.apply(null, Object.keys(counts).map(function (k) { return counts[k]; }));
    var html = '<div class="years" role="img" aria-label="Incidents per year, ' + min + ' to ' + max + '">';
    for (var y = min; y <= max; y++) {
      var c = counts[y] || 0;
      html += '<div class="col" title="' + y + ': ' + c + '" style="height:' + (c ? Math.max(4, Math.round(c / peak * 100)) : 0) + '%"></div>';
    }
    html += '</div><div class="year-axis"><span>' + min + '</span><span>peak: ' + peak + ' in one year</span><span>' + max + '</span></div>';
    el.innerHTML = html;
  }

  function initIncident(data) {
    var id = new URLSearchParams(location.search).get('id');
    var i = data.incidents.filter(function (x) { return x.id === id; })[0];
    var out = $('#detail');
    if (!i) { out.innerHTML = '<p class="empty">Incident not found. <a href="incidents.html">Browse all incidents</a>.</p>'; return; }
    document.title = i.title + ' · GLAMSHUB';
    var correction = 'https://github.com/' + SITE.repo + '/issues/new?template=correction.yml&title=' +
      encodeURIComponent('[Correction] ' + i.title) + '&record_id=' + encodeURIComponent(i.id);
    var extra = (i.extraSources || []).map(function (s) {
      return '<li><a href="' + esc(safeUrl(s.url)) + '" rel="noopener nofollow" target="_blank">' + esc(s.name || s.url) + '</a></li>';
    }).join('');
    out.innerHTML = '<div class="detail"><div>' +
      '<span class="badge st-' + esc(i.status) + '">' + esc(label('status', i.status)) + '</span>' +
      '<span class="ver v-' + esc(i.verification) + '">' + esc(label('verification', i.verification)) + '</span>' +
      '<h1 style="margin-top:1rem;font-size:clamp(1.7rem,4vw,2.6rem)">' + esc(i.title) + '</h1>' +
      (i.summary ? '<p class="lead">' + esc(i.summary) + '</p>' : '') +
      '<dl class="facts">' +
      '<dt>Date</dt><dd>' + esc(fmtDate(i.date)) + '</dd>' +
      '<dt>Institution</dt><dd>' + esc(i.institution || 'Not specified') + '</dd>' +
      '<dt>Type</dt><dd>' + esc(label('type', i.institutionType)) + '</dd>' +
      '<dt>Location</dt><dd>' + esc(place(i)) + (i.geoPrecision ? ' <span class="muted">(map position: ' + esc(i.geoPrecision) + ' level)</span>' : '') + '</dd>' +
      '<dt>Cause</dt><dd>' + esc(label('cause', i.cause)) + '</dd>' +
      '<dt>Source</dt><dd><a href="' + esc(safeUrl(i.sourceUrl)) + '" rel="noopener nofollow" target="_blank">' + esc(i.sourceName || i.sourceUrl) + '</a></dd>' +
      '</dl>' + (extra ? '<h2>Other reports</h2><ul>' + extra + '</ul>' : '') +
      '<p><a class="btn ghost" href="' + esc(correction) + '" rel="noopener">Suggest a correction</a> <a class="btn ghost" href="incidents.html">All incidents</a></p>' +
      '</div><div>' + (typeof i.lat === 'number' ? '<div id="mini-map" class="map"></div>' : '<p class="empty">No map position recorded.</p>') + '</div></div>';
    if (typeof i.lat === 'number') makeMap($('#mini-map'), [i], { scroll: false, maxZoom: 6, center: [i.lat, i.lng], zoom: 5 });
  }

  function initReport() {
    var form = $('#report-form');
    form.addEventListener('submit', function (e) {
      e.preventDefault();
      var v = function (id) { return ($('#r-' + id).value || '').trim(); };
      var p = new URLSearchParams();
      p.set('template', 'report-incident.yml');
      p.set('title', '[Incident] ' + (v('institution') || 'New report'));
      ['institution', 'location', 'date', 'institution_type', 'cause', 'status', 'source', 'details'].forEach(function (k) {
        if (v(k)) p.set(k, v(k));
      });
      window.open('https://github.com/' + SITE.repo + '/issues/new?' + p.toString(), '_blank', 'noopener');
    });
  }

  /* ---------- boot ---------- */
  document.addEventListener('DOMContentLoaded', function () {
    var page = document.body.getAttribute('data-page');
    renderChrome(page);
    var inits = { home: initHome, incidents: initIncidents, map: initMap, stats: initStats, incident: initIncident };
    if (page === 'report') { initReport(); return; }
    if (!inits[page]) return;
    loadData().then(inits[page]).catch(function (err) {
      showError($('#latest') || $('#results') || $('#big-map') || $('#by-status') || $('#detail'), err);
    });
  });
})();
