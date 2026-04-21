#!/usr/bin/env python3
"""Generate a styled HTML listings page from Supabase → index.html"""

import json
import os
from datetime import date, datetime
from itertools import groupby

from dotenv import load_dotenv

load_dotenv()

OUTPUT_PATH = os.path.join(os.path.dirname(__file__), "index.html")
SUPABASE_DB_URL = os.getenv("SUPABASE_DB_URL")

_FORMAT_COLORS = {
    "LP": "#6a5acd",
    "CD": "#2e8b57",
    '7"': "#cc6600",
    '10"': "#cc6600",
    '12"': "#cc6600",
    "cassette": "#8b4513",
}


def get_listings() -> list[dict]:
    import psycopg
    from psycopg.rows import dict_row

    if not SUPABASE_DB_URL:
        raise RuntimeError("SUPABASE_DB_URL environment variable is not set.")

    conn = psycopg.connect(SUPABASE_DB_URL, row_factory=dict_row)
    cur = conn.execute(
        """
        SELECT hash, shop, artist, title, format, signed_by, signature_location,
               price, url, image_url, first_seen::date AS date_added,
               first_seen
        FROM listings
        ORDER BY first_seen DESC
        """
    )
    rows = cur.fetchall()
    conn.close()

    result = []
    for row in rows:
        result.append({
            "hash":               row["hash"] or "",
            "shop":               row["shop"] or "",
            "artist":             row["artist"] or "",
            "title":              row["title"] or "",
            "format":             row["format"] or "unknown",
            "signed_by":          row["signed_by"] or "unknown",
            "signature_location": row["signature_location"] or "unknown",
            "price":              row["price"] or "",
            "url":                row["url"] or "",
            "image_url":          row["image_url"] or "",
            "date_added":         str(row["date_added"]) if row["date_added"] else "",
        })
    return result


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


def generate_html(listings: list[dict]) -> str:
    today_iso = date.today().isoformat()
    generated_at = datetime.now().strftime("%B %d, %Y at %I:%M %p")
    total = len(listings)
    listings_json = json.dumps(listings, ensure_ascii=False)

    # Pre-render date sections (for no-JS fallback and initial paint)
    date_sections_html = ""
    for date_key, group in groupby(listings, key=lambda x: x["date_added"]):
        group_list = list(group)
        date_label = _format_date_label(date_key)
        today_badge = '<span class="today-badge">Today</span>' if date_key == today_iso else ""

        rows_html = ""
        for lst in group_list:
            fmt = lst["format"]
            fmt_color = _FORMAT_COLORS.get(fmt, "")
            fmt_badge = (
                f'<span class="format-badge" style="background:{fmt_color}">{_esc(fmt)}</span>'
                if fmt_color and fmt != "unknown"
                else ""
            )

            img_html = (
                f'<img src="{_esc(lst["image_url"])}" alt="" class="thumb">'
                if lst["image_url"]
                else '<div class="thumb-placeholder"></div>'
            )

            meta_parts = []
            if lst["signed_by"] != "unknown":
                meta_parts.append(f"signed by: {lst['signed_by']}")
            if lst["signature_location"] != "unknown":
                meta_parts.append(f"location: {lst['signature_location']}")
            meta_html = (
                f'<div class="td-meta">{_esc("  ·  ".join(meta_parts))}</div>'
                if meta_parts
                else ""
            )

            link_html = (
                f'<a class="buy-link" href="{_esc(lst["url"])}" target="_blank" rel="noopener">Buy</a>'
                if lst["url"]
                else ""
            )

            rows_html += f"""<tr data-hash="{_esc(lst['hash'])}">
        <td class="td-thumb">{img_html}</td>
        <td class="td-title">
          <div class="title-line">{_esc(lst['title'])}{fmt_badge}</div>
          <div class="td-artist">{_esc(lst['artist'])}</div>
          {meta_html}
        </td>
        <td class="td-shop">{_esc(lst['shop'])}</td>
        <td class="td-price">{_esc(lst['price'])}</td>
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
          <th>Title / Artist</th>
          <th>Shop</th>
          <th>Price</th>
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
<title>Signed Records</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Bebas+Neue&family=DM+Sans:ital,opsz,wght@0,9..40,300;0,9..40,400;0,9..40,500;0,9..40,600&family=DM+Mono:wght@400;500&display=swap" rel="stylesheet">
<style>
  :root {{
    --navy:       #1a1a2e;
    --navy-deep:  #12122a;
    --navy-mid:   #232340;
    --navy-card:  #1e1e38;
    --coral:      #e94560;
    --coral-dim:  #b8304a;
    --white:      #f2f0ee;
    --gray:       #9494aa;
    --gray-dim:   #5c5c78;
    --border:     rgba(255,255,255,0.07);
    --font-display: 'Bebas Neue', sans-serif;
    --font-body:    'DM Sans', sans-serif;
    --font-mono:    'DM Mono', monospace;
  }}

  *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
  html {{ scroll-behavior: smooth; }}

  body {{
    background-color: var(--navy-deep);
    color: var(--white);
    font-family: var(--font-body);
    min-height: 100vh;
    background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='300' height='300'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.75' numOctaves='4' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='300' height='300' filter='url(%23n)' opacity='0.035'/%3E%3C/svg%3E");
  }}

  /* ─── Header ─── */
  .site-header {{
    position: sticky; top: 0; z-index: 100;
    background: var(--navy-deep);
    border-bottom: 1px solid var(--border);
    backdrop-filter: blur(12px);
  }}
  .header-inner {{
    max-width: 1200px; margin: 0 auto; padding: 0 24px;
    display: flex; align-items: center; gap: 20px; height: 64px;
  }}
  .site-title {{
    font-family: var(--font-display);
    font-size: 2rem; letter-spacing: 0.06em;
    color: var(--white); line-height: 1; flex-shrink: 0;
  }}
  .site-title span {{ color: var(--coral); }}
  .header-meta {{
    font-family: var(--font-mono); font-size: 0.68rem;
    color: var(--gray-dim); letter-spacing: 0.08em;
    text-transform: uppercase; padding-bottom: 2px;
  }}
  .header-count {{
    font-family: var(--font-mono); font-size: 0.72rem;
    color: var(--gray); flex-shrink: 0;
  }}

  /* ─── Search ─── */
  .search-wrap {{
    width: 260px; margin-left: auto; margin-right: 0;
    position: relative; display: flex; align-items: center; flex-shrink: 0;
  }}
  .search-input {{
    width: 100%; background: var(--navy-mid);
    border: 1px solid var(--border); border-radius: 20px;
    padding: 7px 30px 7px 14px;
    font-family: var(--font-body); font-size: 0.8rem;
    color: var(--white); outline: none;
    transition: border-color 0.18s, background 0.18s;
    -webkit-appearance: none;
  }}
  .search-input::placeholder {{ color: var(--gray-dim); }}
  .search-input:focus {{ border-color: var(--gray-dim); background: var(--navy-card); }}
  .search-input::-webkit-search-cancel-button {{ display: none; }}
  .search-clear {{
    position: absolute; right: 10px;
    background: none; border: none; color: var(--gray-dim);
    cursor: pointer; font-size: 0.68rem; line-height: 1;
    padding: 2px 4px; display: none; transition: color 0.15s;
  }}
  .search-clear:hover {{ color: var(--white); }}
  .search-clear.visible {{ display: block; }}

  /* ─── Main ─── */
  .main {{
    max-width: 1200px; margin: 0 auto; padding: 32px 24px 80px;
  }}

  /* ─── Date Section ─── */
  .date-section {{ margin-bottom: 48px; }}
  .date-section.hidden {{ display: none; }}
  .date-heading {{
    display: flex; align-items: baseline; gap: 14px;
    margin-bottom: 4px; padding-bottom: 10px;
    border-bottom: 2px solid var(--coral);
  }}
  .date-label {{
    font-family: var(--font-display); font-size: 1.65rem;
    letter-spacing: 0.05em; color: var(--white); line-height: 1;
  }}
  .date-count {{
    font-family: var(--font-mono); font-size: 0.7rem;
    color: var(--gray); letter-spacing: 0.08em;
  }}
  .today-badge {{
    display: inline-block; background: var(--coral); color: #fff;
    font-family: var(--font-mono); font-size: 0.6rem; font-weight: 500;
    letter-spacing: 0.08em; text-transform: uppercase;
    padding: 2px 6px; border-radius: 3px; margin-left: 10px;
    vertical-align: middle; position: relative; top: -3px;
  }}

  /* ─── Table ─── */
  .listings-table {{ width: 100%; border-collapse: collapse; margin-top: 2px; }}
  .listings-table thead th {{
    font-family: var(--font-mono); font-size: 0.62rem;
    letter-spacing: 0.12em; text-transform: uppercase;
    color: var(--gray-dim); padding: 10px 12px 8px; text-align: left;
    border-bottom: 1px solid var(--border); font-weight: 400;
  }}
  .listings-table thead th:last-child {{ text-align: right; }}
  .th-thumb {{ width: 68px; }}
  .listings-table tbody tr {{
    border-bottom: 1px solid var(--border);
    transition: background 0.14s;
  }}
  .listings-table tbody tr:hover {{ background: rgba(255,255,255,0.03); }}
  .listings-table tbody tr.hidden {{ display: none; }}
  .listings-table td {{ padding: 10px 12px; vertical-align: middle; }}

  /* ─── Thumbnail ─── */
  .td-thumb {{ width: 68px; padding: 8px 12px 8px 0 !important; }}
  .thumb {{
    width: 52px; height: 52px; object-fit: cover;
    border-radius: 4px; display: block;
  }}
  .thumb-placeholder {{
    width: 52px; height: 52px; border-radius: 4px;
    background: var(--navy-mid);
  }}

  /* ─── Title / Artist ─── */
  .td-title {{ max-width: 360px; }}
  .title-line {{
    font-size: 0.95rem; font-weight: 500; color: var(--white);
    display: flex; align-items: center; gap: 6px; flex-wrap: wrap;
  }}
  .format-badge {{
    display: inline-block; color: #fff;
    font-family: var(--font-mono); font-size: 0.62rem;
    letter-spacing: 0.08em; text-transform: uppercase;
    padding: 2px 6px; border-radius: 3px; flex-shrink: 0;
  }}
  .td-artist {{
    font-family: var(--font-mono); font-size: 0.75rem;
    color: var(--gray); margin-top: 3px;
  }}
  .td-meta {{
    font-family: var(--font-mono); font-size: 0.68rem;
    color: var(--gray-dim); margin-top: 3px;
  }}

  /* ─── Shop / Price ─── */
  .td-shop {{
    font-family: var(--font-mono); font-size: 0.72rem;
    color: var(--gray); white-space: nowrap;
  }}
  .td-price {{
    font-family: var(--font-mono); font-size: 0.72rem;
    color: var(--gray); white-space: nowrap;
  }}

  /* ─── Buy link ─── */
  .td-link {{ text-align: right; width: 90px; }}
  .buy-link {{
    display: inline-block; font-family: var(--font-mono);
    font-size: 0.65rem; letter-spacing: 0.08em; text-transform: uppercase;
    color: var(--coral); text-decoration: none;
    border: 1px solid var(--coral-dim); padding: 4px 10px;
    border-radius: 3px; transition: background 0.15s, color 0.15s;
    white-space: nowrap;
  }}
  .buy-link:hover {{ background: var(--coral); color: #fff; border-color: var(--coral); }}

  /* ─── Empty / Search empty ─── */
  .empty-state, .search-empty {{
    padding: 60px 0; text-align: center;
    color: var(--gray-dim); font-family: var(--font-mono);
    font-size: 0.8rem; letter-spacing: 0.08em;
  }}

  /* ─── Footer ─── */
  .site-footer {{
    text-align: center; padding: 40px 24px;
    font-family: var(--font-mono); font-size: 0.65rem;
    letter-spacing: 0.1em; color: var(--gray-dim);
    border-top: 1px solid var(--border); text-transform: uppercase;
  }}

  /* ─── Responsive ─── */
  @media (max-width: 720px) {{
    .td-shop, .td-price {{ display: none; }}
    .site-title {{ font-size: 1.5rem; }}
    .header-count {{ display: none; }}
    .search-wrap {{ width: 170px; }}
    .date-label {{ font-size: 1.3rem; }}
  }}
</style>
</head>
<body>

<header class="site-header">
  <div class="header-inner">
    <div class="site-title">Signed<span>&nbsp;Records</span></div>
    <div class="header-meta">Autographed vinyl &amp; CDs</div>
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
  const sections = Array.from(document.querySelectorAll('.date-section'));
  const total = {total};

  function escHtml(s) {{
    return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
  }}

  function doSearch(query) {{
    const q = query.trim().toLowerCase();
    searchClear.classList.toggle('visible', query.length > 0);

    if (!q) {{
      sections.forEach(s => {{
        s.classList.remove('hidden');
        s.querySelectorAll('tbody tr').forEach(r => r.classList.remove('hidden'));
      }});
      headerCount.textContent = total + ' listings';
      searchEmpty.style.display = 'none';
      return;
    }}

    let matchCount = 0;
    sections.forEach(s => {{
      let hits = 0;
      s.querySelectorAll('tbody tr').forEach(r => {{
        const titleEl = r.querySelector('.title-line');
        const artistEl = r.querySelector('.td-artist');
        const text = ((titleEl ? titleEl.textContent : '') + ' ' + (artistEl ? artistEl.textContent : '')).toLowerCase();
        const match = text.includes(q);
        r.classList.toggle('hidden', !match);
        if (match) hits++;
      }});
      matchCount += hits;
      s.classList.toggle('hidden', hits === 0);
    }});

    headerCount.textContent = matchCount + (matchCount === 1 ? ' match' : ' matches');
    searchEmpty.style.display = matchCount === 0 ? 'block' : 'none';
    if (matchCount === 0) {{
      searchEmpty.innerHTML = 'No results for &ldquo;' + escHtml(query) + '&rdquo;';
    }}
  }}

  searchInput.addEventListener('input', e => doSearch(e.target.value));
  searchClear.addEventListener('click', () => {{ searchInput.value = ''; doSearch(''); searchInput.focus(); }});
  searchInput.addEventListener('keydown', e => {{
    if (e.key === 'Escape') {{ searchInput.value = ''; doSearch(''); searchInput.blur(); }}
  }});
}})();
</script>
</body>
</html>
"""


def main():
    print("Reading listings from Supabase…")
    listings = get_listings()
    print(f"Found {len(listings)} listings.")

    html = generate_html(listings)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"Written → {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
