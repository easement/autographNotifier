import json
from datetime import date, datetime
from itertools import groupby

from render_models import WebListingViewModel

_FORMAT_COLORS = {
    "LP": "#6a5acd",
    "CD": "#2e8b57",
    '7"': "#cc6600",
    '10"': "#cc6600",
    '12"': "#cc6600",
    "cassette": "#8b4513",
}


def _esc(s: str) -> str:
    return (
        str(s)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _format_date_label(iso: str) -> str:
    if not iso:
        return "Unknown Date"
    try:
        y, m, d_ = iso.split("-")
        d_obj = date(int(y), int(m), int(d_))
        js_days = ["Mon", "Tue", "Wed", "Thurs", "Fri", "Sat", "Sun"]
        months = [
            "January", "February", "March", "April", "May", "June",
            "July", "August", "September", "October", "November", "December",
        ]
        dow = js_days[d_obj.weekday()]
        return f"({dow}) {months[d_obj.month - 1]} {d_obj.day}"
    except (ValueError, AttributeError):
        return iso


def generate_html(listings: list[WebListingViewModel]) -> str:
    today_iso = date.today().isoformat()
    generated_at = datetime.now().strftime("%B %d, %Y at %I:%M %p")
    total = len(listings)
    listings_json = json.dumps([vars(item) for item in listings], ensure_ascii=False)

    # Pre-render date sections (for no-JS fallback and initial paint)
    date_sections_html = ""
    for date_key, group in groupby(listings, key=lambda x: x.date_added):
        group_list = list(group)
        date_label = _format_date_label(date_key)
        today_badge = '<span class="today-badge">Today</span>' if date_key == today_iso else ""

        rows_html = ""
        for lst in group_list:
            fmt = lst.format
            fmt_color = _FORMAT_COLORS.get(fmt, "")
            fmt_badge = (
                f'<span class="format-badge" style="background:{fmt_color}">{_esc(fmt)}</span>'
                if fmt_color and fmt != "unknown"
                else ""
            )

            img_html = (
                f'<img src="{_esc(lst.image_url)}" alt="" class="thumb">'
                if lst.image_url
                else '<div class="thumb-placeholder"></div>'
            )

            meta_parts = []
            if lst.signed_by != "unknown":
                meta_parts.append(f"signed by: {lst.signed_by}")
            if lst.signature_location != "unknown":
                meta_parts.append(f"location: {lst.signature_location}")
            meta_html = (
                f'<div class="td-meta">{_esc("  ·  ".join(meta_parts))}</div>'
                if meta_parts
                else ""
            )

            link_html = (
                f'<a class="buy-link" href="{_esc(lst.url)}" target="_blank" rel="noopener">Buy</a>'
                if lst.url
                else ""
            )

            rows_html += f"""<tr data-hash="{_esc(lst.hash)}">
        <td class="td-thumb">{img_html}</td>
        <td class="td-title">
          <div class="title-line">{_esc(lst.title)}{fmt_badge}</div>
          <div class="td-artist">{_esc(lst.artist)}</div>
          {meta_html}
        </td>
        <td class="td-shop">{_esc(lst.shop)}</td>
        <td class="td-price">{_esc(lst.price)}</td>
        <td class="td-link">{link_html}</td>
      </tr>"""

        date_sections_html += f"""
  <div class="date-section" data-date="{date_key}">
    <div class="date-heading">
      <div class="date-label">{date_label}{today_badge}</div>
      <div class="date-count">{len(group_list)} listing{"s" if len(group_list) != 1 else ""}</div>
    </div>
    <table class="listings-table">
      <thead>
        <tr>
          <th class="th-thumb"></th>
          <th class="th-sort" data-sort="title">Title / Artist</th>
          <th class="th-sort" data-sort="shop">Shop</th>
          <th class="th-sort" data-sort="price">Price</th>
          <th></th>
        </tr>
      </thead>
      <tbody>{rows_html}</tbody>
    </table>
  </div>"""

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Dispatches — Autograph Notifier</title>
<link rel="icon" type="image/svg+xml" href="favicon.svg">
<script async src="https://www.googletagmanager.com/gtag/js?id=G-TBYS6FEB3R"></script>
<script>
  window.dataLayer = window.dataLayer || [];
  function gtag(){{dataLayer.push(arguments);}}
  gtag('js', new Date());
  gtag('config', 'G-TBYS6FEB3R');
</script>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Oswald:wght@400;500;600;700&family=Source+Serif+4:ital,opsz,wght@0,8..60,400;0,8..60,600;1,8..60,400;1,8..60,600&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
<style>
  /* ── Par Avion palette overlay ── */
  :root {{
    --paper:       #F2E8D5;
    --paper-2:     #EADFC7;
    --surface:     #FAF3E1;
    --ink:         #121212;
    --ink-2:       #2B2623;
    --ink-3:       #6B6358;
    --ink-4:       #9B9180;
    --red:         #B91C1C;
    --red-deep:    #8F1414;
    --blue:        #1E3A8A;
    --border:      #C9B994;
    --border-soft: #DDD0B3;

    --font-display: 'Oswald', 'Arial Narrow', Impact, sans-serif;
    --font-body:    'Source Serif 4', 'Iowan Old Style', Georgia, serif;
    --font-mono:    'JetBrains Mono', ui-monospace, monospace;
  }}

  *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
  html {{ scroll-behavior: smooth; }}

  body {{
    background-color: var(--paper);
    color: var(--ink);
    font-family: var(--font-body);
    min-height: 100vh;
  }}

  /* ── Header ── */
  .site-header {{
    position: sticky; top: 0; z-index: 100;
    background: var(--paper);
    border-bottom: 1px solid var(--ink);
  }}
  .header-inner {{
    max-width: 1200px; margin: 0 auto; padding: 0 24px;
    display: flex; align-items: center; gap: 20px; height: 64px;
  }}
  .site-title {{
    font-family: var(--font-display);
    font-size: 1.7rem; letter-spacing: 0.14em; font-weight: 600;
    text-transform: uppercase;
    color: var(--ink); line-height: 1; flex-shrink: 0;
  }}
  .site-title span {{ color: var(--red); }}
  .header-meta {{
    font-family: var(--font-mono); font-size: 0.68rem;
    color: var(--ink-3); letter-spacing: 0.14em;
    text-transform: uppercase; padding-bottom: 2px;
  }}
  .header-count {{
    font-family: var(--font-mono); font-size: 0.72rem;
    color: var(--ink-3); flex-shrink: 0; letter-spacing: 0.08em;
  }}

  /* ── Search ── */
  .search-wrap {{
    width: 260px; margin-left: auto; margin-right: 0;
    position: relative; display: flex; align-items: center; flex-shrink: 0;
  }}
  .search-input {{
    width: 100%; background: var(--surface);
    border: 1px solid var(--border); border-radius: 0;
    padding: 7px 30px 7px 14px;
    font-family: var(--font-body); font-size: 0.85rem;
    color: var(--ink); outline: none;
    transition: border-color 0.18s, background 0.18s;
    -webkit-appearance: none;
  }}
  .search-input::placeholder {{ color: var(--ink-4); font-style: italic; }}
  .search-input:focus {{ border-color: var(--ink); }}
  .search-input::-webkit-search-cancel-button {{ display: none; }}
  .search-clear {{
    position: absolute; right: 10px;
    background: none; border: none; color: var(--ink-3);
    cursor: pointer; font-size: 0.68rem; line-height: 1;
    padding: 2px 4px; display: none; transition: color 0.15s;
  }}
  .search-clear:hover {{ color: var(--ink); }}
  .search-clear.visible {{ display: block; }}

  /* ── Main ── */
  .main {{
    max-width: 1200px; margin: 0 auto; padding: 32px 24px 80px;
  }}

  /* ── Date Section ── */
  .date-section {{ margin-bottom: 48px; }}
  .date-section.hidden {{ display: none; }}
  .date-heading {{
    display: flex; align-items: baseline; gap: 14px;
    margin-bottom: 4px; padding-bottom: 10px;
    border-bottom: 1.5px solid var(--red);
  }}
  .date-label {{
    font-family: var(--font-display); font-size: 1.65rem;
    letter-spacing: 0.05em; color: var(--ink); line-height: 1;
    font-weight: 600; text-transform: uppercase;
  }}
  .date-count {{
    font-family: var(--font-mono); font-size: 0.72rem;
    color: var(--ink-3); letter-spacing: 0.08em;
  }}
  .today-badge {{
    display: inline-block; background: var(--paper); color: var(--red);
    border: 1.5px solid var(--red);
    font-family: var(--font-display); font-size: 0.62rem; font-weight: 600;
    letter-spacing: 0.18em; text-transform: uppercase;
    padding: 2px 7px; border-radius: 0; margin-left: 10px;
    vertical-align: middle; position: relative; top: -3px;
    transform: rotate(-2deg);
  }}

  /* ── Table ── */
  .listings-table {{ width: 100%; border-collapse: collapse; margin-top: 2px; }}
  .listings-table thead th {{
    font-family: var(--font-mono); font-size: 0.62rem;
    letter-spacing: 0.18em; text-transform: uppercase;
    color: var(--ink-3); padding: 10px 12px 8px; text-align: left;
    border-bottom: 1px solid var(--border); font-weight: 500;
  }}
  .listings-table thead th:last-child {{ text-align: right; }}
  .th-thumb {{ width: 68px; }}
  .listings-table tbody tr {{
    border-bottom: 1px solid var(--border-soft);
    transition: background 0.14s;
  }}
  .listings-table tbody tr:hover {{ background: var(--paper-2); }}
  .listings-table tbody tr.hidden {{ display: none; }}
  .listings-table td {{ padding: 10px 12px; vertical-align: middle; }}

  /* ── Thumbnail ── */
  .td-thumb {{ width: 68px; padding: 8px 12px 8px 0 !important; }}
  .thumb {{
    width: 52px; height: 52px; object-fit: cover;
    border-radius: 0; display: block;
    border: 1px solid var(--ink);
  }}
  .thumb-placeholder {{
    width: 52px; height: 52px;
    background: var(--paper-2);
    border: 1px solid var(--border);
  }}

  /* ── Title / Artist ── */
  .td-title {{ max-width: 360px; }}
  .title-line {{
    font-size: 0.98rem; font-weight: 400;
    font-family: var(--font-body);
    color: var(--ink);
    display: flex; align-items: center; gap: 8px; flex-wrap: wrap;
    line-height: 1.35;
  }}
  /* Override all inline background colors on format badges */
  .format-badge {{
    display: inline-block !important;
    color: var(--paper) !important;
    background: var(--red) !important;
    font-family: var(--font-display);
    font-size: 0.6rem;
    letter-spacing: 0.18em; text-transform: uppercase; font-weight: 600;
    padding: 2px 7px; border-radius: 0 !important;
    flex-shrink: 0;
  }}
  /* CD badges: format-badge set to background:#2e8b57 in markup — neutralize with attribute selector */
  .format-badge[style*="2e8b57"] {{
    background: var(--blue) !important;
  }}
  .td-artist {{
    font-family: var(--font-mono); font-size: 0.72rem;
    color: var(--ink-3); margin-top: 3px; letter-spacing: 0.02em;
  }}
  .td-meta {{
    font-family: var(--font-mono); font-size: 0.68rem;
    color: var(--ink-4); margin-top: 3px;
  }}

  /* ── Shop / Price ── */
  .td-shop {{
    font-family: var(--font-mono); font-size: 0.72rem;
    color: var(--ink-3); white-space: nowrap;
  }}
  .td-price {{
    font-family: var(--font-display); font-size: 0.95rem;
    color: var(--ink); white-space: nowrap;
    font-variant-numeric: tabular-nums; font-weight: 600;
    letter-spacing: -0.01em;
  }}

  /* ── Buy link ── */
  .td-link {{ text-align: right; width: 90px; }}
  .buy-link {{
    display: inline-block; font-family: var(--font-display);
    font-size: 0.68rem; letter-spacing: 0.18em; text-transform: uppercase; font-weight: 600;
    color: var(--red); text-decoration: none;
    border: 1.5px solid var(--red); padding: 4px 12px;
    border-radius: 0; transition: background 0.15s, color 0.15s;
    white-space: nowrap;
    background: var(--paper);
  }}
  .buy-link:hover {{ background: var(--red); color: var(--paper); }}

  /* ── Empty ── */
  .empty-state, .search-empty {{
    padding: 60px 0; text-align: center;
    color: var(--ink-3); font-family: var(--font-body); font-style: italic;
    font-size: 0.95rem;
  }}

  /* ── Footer ── */
  .site-footer {{
    text-align: center; padding: 40px 24px;
    font-family: var(--font-mono); font-size: 0.65rem;
    letter-spacing: 0.18em; color: var(--ink-3);
    border-top: 1px solid var(--border); text-transform: uppercase;
  }}

  /* ── Sort ── */
  .th-sort {{ cursor: pointer; user-select: none; white-space: nowrap; }}
  .th-sort:hover {{ color: var(--ink); background: var(--paper-2); }}
  .th-sort::after {{ content: ' ⇅'; opacity: 0.28; font-size: 0.72em; }}
  .th-sort.sort-asc::after  {{ content: ' ▲'; opacity: 1; color: var(--red); }}
  .th-sort.sort-desc::after {{ content: ' ▼'; opacity: 1; color: var(--red); }}

  /* ── Responsive ── */
  @media (max-width: 720px) {{
    .td-shop, .td-price {{ display: none; }}
    .site-title {{ font-size: 1.3rem; }}
    .header-count {{ display: none; }}
    .search-wrap {{ width: 170px; }}
    .date-label {{ font-size: 1.3rem; }}
  }}
</style>
</head>
<body>

<header class="site-header">
  <div class="header-inner">
    <div class="site-title">Autograph<span>&nbsp;Notifier</span></div>
    <div class="header-meta">Signed · Sealed · Delivered</div>
    <div class="search-wrap">
      <input type="search" id="eventSearch" class="search-input"
             placeholder="Search titles, artists…" autocomplete="off"
             spellcheck="false" aria-label="Search listings">
      <button type="button" id="searchClear" class="search-clear" aria-label="Clear">✕</button>
    </div>
    <div class="header-count" id="headerCount">{total} listings</div>
  </div>
</header>

<main class="main" id="mainContent">
{date_sections_html if date_sections_html else '<div class="empty-state">No listings found.</div>'}
  <div id="flatView" style="display:none">
    <table class="listings-table">
      <thead>
        <tr>
          <th class="th-thumb"></th>
          <th class="th-sort" data-sort="title">Title / Artist</th>
          <th class="th-sort" data-sort="shop">Shop</th>
          <th class="th-sort" data-sort="price">Price</th>
          <th></th>
        </tr>
      </thead>
      <tbody id="flatBody"></tbody>
    </table>
  </div>
  <div id="searchEmpty" class="search-empty" style="display:none"></div>
</main>

<footer class="site-footer">
  Autograph Notifier &nbsp;·&nbsp; Generated {generated_at}
</footer>

<script>
(function () {{
  const LISTINGS = {listings_json};
  const searchInput = document.getElementById('eventSearch');
  const searchClear = document.getElementById('searchClear');
  const headerCount = document.getElementById('headerCount');
  const searchEmpty = document.getElementById('searchEmpty');
  const flatView = document.getElementById('flatView');
  const flatBody = document.getElementById('flatBody');
  const sections = Array.from(document.querySelectorAll('.date-section'));
  const total = {total};

  function escHtml(s) {{
    return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
  }}

  function rowText(r) {{
    const t = r.querySelector('.title-line');
    const a = r.querySelector('.td-artist');
    return ((t ? t.textContent : '') + ' ' + (a ? a.textContent : '')).toLowerCase();
  }}

  function setCount(count, q) {{
    if (!q) {{
      headerCount.textContent = total + ' listings';
      searchEmpty.style.display = 'none';
    }} else {{
      headerCount.textContent = count + (count === 1 ? ' match' : ' matches');
      searchEmpty.style.display = count === 0 ? 'block' : 'none';
      if (count === 0) searchEmpty.innerHTML = 'No results for &ldquo;' + escHtml(q) + '&rdquo;';
    }}
  }}

  // ── Search ──
  function doSearch(query) {{
    const q = query.trim().toLowerCase();
    searchClear.classList.toggle('visible', query.length > 0);

    if (sortKey) {{
      let count = 0;
      flatBody.querySelectorAll('tr').forEach(r => {{
        const match = !q || rowText(r).includes(q);
        r.classList.toggle('hidden', !match);
        if (match) count++;
      }});
      setCount(count, q);
      return;
    }}

    let count = 0;
    sections.forEach(s => {{
      let hits = 0;
      s.querySelectorAll('tbody tr').forEach(r => {{
        const match = !q || rowText(r).includes(q);
        r.classList.toggle('hidden', !match);
        if (match) hits++;
      }});
      count += hits;
      if (!q) s.classList.remove('hidden');
      else s.classList.toggle('hidden', hits === 0);
    }});
    setCount(count, q);
  }}

  searchInput.addEventListener('input', e => doSearch(e.target.value));
  searchClear.addEventListener('click', () => {{ searchInput.value = ''; doSearch(''); searchInput.focus(); }});
  searchInput.addEventListener('keydown', e => {{
    if (e.key === 'Escape') {{ searchInput.value = ''; doSearch(''); searchInput.blur(); }}
  }});

  // ── Sort ──
  const byHash = Object.fromEntries(LISTINGS.map(l => [l.hash, l]));
  const rowOrigins = new Map();
  document.querySelectorAll('.listings-table tbody tr').forEach(r => {{
    rowOrigins.set(r, r.parentNode);
  }});
  let sortKey = null;
  let sortDir = 'asc';

  function sortVal(row, key) {{
    const l = byHash[row.dataset.hash];
    if (!l) return '';
    if (key === 'price') return parseFloat(String(l.price).replace(/[^0-9.]/g, '')) || 0;
    if (key === 'title') return (String(l.title) + ' ' + String(l.artist)).toLowerCase();
    return String(l[key] || '').toLowerCase();
  }}

  function updateSortHeaders() {{
    document.querySelectorAll('.th-sort').forEach(th => {{
      th.classList.remove('sort-asc', 'sort-desc');
      if (sortKey && th.dataset.sort === sortKey)
        th.classList.add(sortDir === 'asc' ? 'sort-asc' : 'sort-desc');
    }});
  }}

  function renderSort() {{
    const allRows = Array.from(rowOrigins.keys());
    allRows.sort((a, b) => {{
      const va = sortVal(a, sortKey), vb = sortVal(b, sortKey);
      if (typeof va === 'number') return sortDir === 'asc' ? va - vb : vb - va;
      return sortDir === 'asc' ? va.localeCompare(vb) : vb.localeCompare(va);
    }});
    allRows.forEach(r => flatBody.appendChild(r));
    sections.forEach(s => {{ s.style.display = 'none'; }});
    flatView.style.display = '';
    updateSortHeaders();
    doSearch(searchInput.value);
  }}

  function clearSort() {{
    sortKey = null;
    sortDir = 'asc';
    rowOrigins.forEach((parent, r) => parent.appendChild(r));
    flatView.style.display = 'none';
    sections.forEach(s => {{ s.style.display = ''; }});
    updateSortHeaders();
    doSearch(searchInput.value);
  }}

  document.querySelectorAll('.th-sort').forEach(th => {{
    th.addEventListener('click', () => {{
      const key = th.dataset.sort;
      if (sortKey === key) {{
        if (sortDir === 'asc') {{ sortDir = 'desc'; renderSort(); }}
        else clearSort();
      }} else {{
        sortKey = key;
        sortDir = 'asc';
        renderSort();
      }}
    }});
  }});
}})();
</script>
</body>
</html>
"""
