"""HTML for the dashboard pages. Plain Python strings, no template engine needed."""

from __future__ import annotations

from datetime import date
from html import escape
from urllib.parse import quote

from .dates import PRESETS, Period, fmt_day

CURRENCY_SIGNS = {"INR": "₹", "USD": "$", "EUR": "€", "GBP": "£", "AUD": "A$",
                  "CAD": "C$", "AED": "AED ", "SGD": "S$"}


# ---------- number formatting ----------
def _group_indian(n: int) -> str:
    s = str(abs(n))
    if len(s) > 3:
        head, tail = s[:-3], s[-3:]
        parts = []
        while len(head) > 2:
            parts.insert(0, head[-2:])
            head = head[:-2]
        if head:
            parts.insert(0, head)
        s = ",".join(parts) + "," + tail
    return ("-" if n < 0 else "") + s


def fmt_int(v, currency: str | None = None) -> str:
    if v is None:
        return "—"
    n = int(round(v))
    return _group_indian(n) if currency == "INR" else f"{n:,}"


def fmt_money(v, currency: str | None, decimals: int | None = None) -> str:
    if v is None:
        return "—"
    sign = CURRENCY_SIGNS.get(currency or "", f"{currency} " if currency else "")
    if decimals is None:
        decimals = 0 if abs(v) >= 1000 else 2
    ip, _, fp = f"{abs(v):.{decimals}f}".partition(".")
    grouped = _group_indian(int(ip)) if currency == "INR" else f"{int(ip):,}"
    frac = f".{fp}" if fp else ""
    return f"{'-' if v < 0 else ''}{sign}{grouped}{frac}"


def fmt_pct(v) -> str:
    return "—" if v is None else f"{v:.2f}%"


def fmt_roas(v) -> str:
    return "—" if not v else f"{v:.2f}x"


def num(v) -> str:
    """Sort value for a table cell. Empty values sort last."""
    return "" if v is None else str(v)


# ---------- page frame ----------
CSS = """
:root{color-scheme:light;--bg:#f6f6f4;--surface:#fcfcfb;--border:#e3e2dd;--grid:#ecebe7;
--text:#0b0b0b;--text2:#52514e;--muted:#6f6e69;--accent:#2a78d6;--accent-ink:#fff;
--s-spend:#2a78d6;--s-leads:#6250d6;--bad-bg:#fdecec;--bad:#a32626;--warn-bg:#fff5db;--warn:#7a5300;
--row-hover:#f1f0ec}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){color-scheme:dark;--bg:#111110;
--surface:#1a1a19;--border:#2e2e2c;--grid:#262624;--text:#f0efec;--text2:#c3c2b7;--muted:#9b9a92;
--accent:#3987e5;--accent-ink:#fff;--s-spend:#3987e5;--s-leads:#9085e9;--bad-bg:#3a1c1c;--bad:#f2a5a5;
--warn-bg:#352a10;--warn:#f0cf7c;--row-hover:#222221}}
:root[data-theme="dark"]{color-scheme:dark;--bg:#111110;--surface:#1a1a19;--border:#2e2e2c;--grid:#262624;
--text:#f0efec;--text2:#c3c2b7;--muted:#9b9a92;--accent:#3987e5;--accent-ink:#fff;--s-spend:#3987e5;
--s-leads:#9085e9;--bad-bg:#3a1c1c;--bad:#f2a5a5;--warn-bg:#352a10;--warn:#f0cf7c;--row-hover:#222221}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--text);font:15px/1.45 system-ui,-apple-system,"Segoe UI",Roboto,sans-serif}
a{color:var(--accent)}
.wrap{max-width:1180px;margin:0 auto;padding:0 16px 48px}
header.top{display:flex;align-items:center;gap:12px;padding:14px 0;flex-wrap:wrap}
header.top h1{font-size:18px;margin:0;flex:1}
header.top h1 a{color:inherit;text-decoration:none}
.badge{font-size:12px;padding:2px 8px;border-radius:99px;background:var(--warn-bg);color:var(--warn);font-weight:600}
.btn{display:inline-block;border:1px solid var(--border);background:var(--surface);color:var(--text);
padding:7px 12px;border-radius:8px;font:inherit;font-size:14px;cursor:pointer;text-decoration:none}
.btn.primary{background:var(--accent);border-color:var(--accent);color:var(--accent-ink)}
.notice{padding:10px 14px;border-radius:10px;margin:0 0 16px;background:var(--warn-bg);color:var(--warn)}
.notice.bad{background:var(--bad-bg);color:var(--bad)}
.card{background:var(--surface);border:1px solid var(--border);border-radius:12px;padding:16px;margin-bottom:16px}
form.dates{display:flex;gap:8px;flex-wrap:wrap;align-items:end}
form.dates label{display:flex;flex-direction:column;font-size:12px;color:var(--text2);gap:3px}
form.dates select,form.dates input{font:inherit;font-size:14px;padding:6px 8px;border-radius:8px;
border:1px solid var(--border);background:var(--bg);color:var(--text);min-width:0}
.period{color:var(--text2);font-size:14px;margin:4px 0 16px}
.tiles{display:grid;grid-template-columns:repeat(auto-fill,minmax(150px,1fr));gap:12px;margin-bottom:16px}
.tile{background:var(--surface);border:1px solid var(--border);border-radius:12px;padding:12px 14px}
.tile .k{font-size:12px;color:var(--text2);text-transform:uppercase;letter-spacing:.04em}
.tile .v{font-size:24px;font-weight:650;margin-top:2px;font-variant-numeric:tabular-nums}
.tile .s{font-size:12px;color:var(--muted)}
h2{font-size:16px;margin:0 0 10px}
.tablewrap{overflow-x:auto;-webkit-overflow-scrolling:touch}
table{border-collapse:collapse;width:100%;font-variant-numeric:tabular-nums}
th,td{padding:9px 10px;text-align:right;border-bottom:1px solid var(--grid);white-space:nowrap}
th:first-child,td:first-child{text-align:left}
th{font-size:12px;color:var(--text2);font-weight:600;text-transform:uppercase;letter-spacing:.03em;
cursor:pointer;user-select:none;position:sticky;top:0;background:var(--surface)}
th[aria-sort=ascending]::after{content:" ▲";font-size:9px}
th[aria-sort=descending]::after{content:" ▼";font-size:9px}
tbody tr:hover{background:var(--row-hover)}
td.name a{font-weight:600;text-decoration:none;color:var(--text)}
td.name small{display:block;color:var(--muted);font-weight:400}
td.err{color:var(--bad);white-space:normal;text-align:left;font-size:13px}
tfoot td{font-weight:650;border-bottom:none;border-top:2px solid var(--border)}
.charts{display:grid;grid-template-columns:repeat(auto-fit,minmax(320px,1fr));gap:16px}
.chart svg{width:100%;height:auto;display:block;overflow:visible}
.chart .bar{fill:var(--series)}
.chart .hit{fill:transparent}
.chart g.pt:hover .bar,.chart g.pt:focus .bar{opacity:.75}
.chart .gl{stroke:var(--grid);stroke-width:1}
.chart .ax{fill:var(--muted);font-size:11px}
.chart .base{stroke:var(--border);stroke-width:1}
.tip{position:fixed;pointer-events:none;background:var(--text);color:var(--bg);padding:6px 9px;border-radius:8px;
font-size:13px;display:none;z-index:10;white-space:nowrap}
.empty{color:var(--muted);padding:24px 0;text-align:center}
.login{max-width:360px;margin:12vh auto 0}
.login input{width:100%;font:inherit;padding:10px;border-radius:8px;border:1px solid var(--border);
background:var(--bg);color:var(--text);margin:8px 0 12px}
.login .btn{width:100%;padding:10px}
.foot{color:var(--muted);font-size:12px;margin-top:8px}
.crumbs{font-size:14px;margin:0 0 6px}
.sub{color:var(--text2);font-size:13px}
@media (max-width:600px){.tile .v{font-size:20px}header.top h1{font-size:16px}}
"""

JS = """
(function(){
  // sortable tables
  document.querySelectorAll('table.sortable').forEach(function(t){
    var heads=t.tHead.rows[0].cells;
    Array.prototype.forEach.call(heads,function(th,i){
      th.addEventListener('click',function(){
        var desc=th.getAttribute('aria-sort')!=='descending';
        Array.prototype.forEach.call(heads,function(h){h.removeAttribute('aria-sort')});
        th.setAttribute('aria-sort',desc?'descending':'ascending');
        var rows=Array.prototype.slice.call(t.tBodies[0].rows);
        rows.sort(function(a,b){
          var x=a.cells[i].dataset.v,y=b.cells[i].dataset.v;
          if(x===''&&y!=='')return 1; if(y===''&&x!=='')return -1;
          var nx=parseFloat(x),ny=parseFloat(y),r;
          r=(!isNaN(nx)&&!isNaN(ny))?nx-ny:String(x).localeCompare(String(y));
          return desc?-r:r;
        });
        rows.forEach(function(r){t.tBodies[0].appendChild(r)});
      });
    });
  });
  // chart tooltips
  var tip=document.createElement('div');tip.className='tip';document.body.appendChild(tip);
  function show(e,el){tip.textContent=el.getAttribute('data-tip');tip.style.display='block';
    var x=(e.touches?e.touches[0].clientX:e.clientX)||el.getBoundingClientRect().left,
        y=(e.touches?e.touches[0].clientY:e.clientY)||el.getBoundingClientRect().top;
    var w=tip.offsetWidth;tip.style.left=Math.max(8,Math.min(window.innerWidth-w-8,x-w/2))+'px';
    tip.style.top=(y-44)+'px';}
  document.querySelectorAll('[data-tip]').forEach(function(el){
    el.addEventListener('mousemove',function(e){show(e,el)});
    el.addEventListener('touchstart',function(e){show(e,el)},{passive:true});
    el.addEventListener('focus',function(e){show(e,el)});
    el.addEventListener('mouseleave',function(){tip.style.display='none'});
    el.addEventListener('blur',function(){tip.style.display='none'});
  });
  // date picker: choosing a preset clears custom dates
  var f=document.querySelector('form.dates');
  if(f){var sel=f.querySelector('select');sel.addEventListener('change',function(){
    if(sel.value){f.querySelectorAll('input[type=date]').forEach(function(i){i.value=''});f.submit();}});}
})();
"""


def page(title: str, body: str, *, demo: bool = False, logged_in: bool = False) -> str:
    badge = '<span class="badge">DEMO DATA</span>' if demo else ""
    logout = ('<form method="post" action="/dashboard/logout" style="margin:0">'
              '<button class="btn" type="submit">Log out</button></form>') if logged_in else ""
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="robots" content="noindex,nofollow">
<title>{escape(title)}</title>
<style>{CSS}</style></head>
<body><div class="wrap">
<header class="top"><h1><a href="/dashboard">Ads Dashboard</a></h1>{badge}{logout}</header>
{body}
</div><script>{JS}</script></body></html>"""


def demo_notice() -> str:
    return ('<div class="notice"><b>Demo mode.</b> These numbers are fake. '
            'Add <code>META_ACCESS_TOKEN</code> (and remove <code>DASHBOARD_DEMO</code>) '
            'to see real data from Meta.</div>')


def login_page(error: str | None = None, demo: bool = False) -> str:
    err = f'<div class="notice bad">{escape(error)}</div>' if error else ""
    body = f"""<div class="login card"><h2>Log in</h2>{err}
<form method="post" action="/dashboard/login">
<label for="pw" class="sub">Password</label>
<input id="pw" type="password" name="password" autocomplete="current-password" autofocus required>
<button class="btn primary" type="submit">Log in</button></form></div>"""
    return page("Log in · Ads Dashboard", body, demo=demo)


def message_page(title: str, text: str, demo: bool = False, logged_in: bool = False) -> str:
    return page(title, f'<div class="card"><h2>{escape(title)}</h2><p>{text}</p></div>',
                demo=demo, logged_in=logged_in)


def date_picker(period: Period, action: str) -> str:
    opts = ['<option value="">Custom dates</option>'] + [
        f'<option value="{k}"{" selected" if period.preset == k else ""}>{escape(v)}</option>'
        for k, v in PRESETS]
    s = "" if period.preset else period.since.isoformat()
    u = "" if period.preset else period.until.isoformat()
    today = date.today().isoformat()
    return f"""<form class="dates card" method="get" action="{escape(action)}">
<label>Date range<select name="preset">{''.join(opts)}</select></label>
<label>From<input type="date" name="since" value="{s}" max="{today}"></label>
<label>To<input type="date" name="until" value="{u}" max="{today}"></label>
<button class="btn primary" type="submit">Show</button>
<a class="btn" href="{escape(action)}?{period.query()}&amp;refresh=1" title="Get fresh numbers from Meta">Refresh</a>
</form>"""


def tile(label: str, value: str, sub: str = "") -> str:
    s = f'<div class="s">{escape(sub)}</div>' if sub else ""
    return f'<div class="tile"><div class="k">{escape(label)}</div><div class="v">{escape(value)}</div>{s}</div>'


def _cells(t: dict, cur: str | None, roas_col: bool, msg_col: bool) -> str:
    cells = [
        (t["spend"], fmt_money(t["spend"], cur)),
        (t["leads"], fmt_int(t["leads"], cur)),
        (t["cpl"], fmt_money(t["cpl"], cur, 2)),
    ]
    if msg_col:
        cells.append((t.get("messages_started"), fmt_int(t.get("messages_started"), cur)))
    cells += [
        (t["clicks"], fmt_int(t["clicks"], cur)),
        (t["cpc"], fmt_money(t["cpc"], cur, 2)),
        (t.get("ctr_percent"), fmt_pct(t.get("ctr_percent"))),
        (t["impressions"], fmt_int(t["impressions"], cur)),
    ]
    if roas_col:
        cells.append((t.get("roas"), fmt_roas(t.get("roas"))))
    return "".join(f'<td data-v="{num(v)}">{escape(s)}</td>' for v, s in cells)


def _heads(first: str, roas_col: bool, msg_col: bool) -> str:
    cols = [first, "Spend", "Leads", "CPL"] + (["Messages"] if msg_col else []) + \
        ["Clicks", "CPC", "CTR", "Impressions"] + (["ROAS"] if roas_col else [])
    return "".join(f"<th>{c}</th>" for c in cols)


def overview_page(data: dict, period: Period, *, demo: bool, logged_in: bool,
                  cache_minutes: int) -> str:
    rows, totals = data["rows"], data["totals"]
    parts = [demo_notice() if demo else "", date_picker(period, "/dashboard"),
             f'<p class="period">Showing <b>{escape(period.label())}</b> · {len(rows)} clients</p>']

    if not rows:
        parts.append('<div class="card empty">No clients yet. Add them to '
                     '<code>clients.json</code> or <code>CLIENTS_JSON</code>.</div>')
        return page("Ads Dashboard", "".join(parts), demo=demo, logged_in=logged_in)

    for cur, t in totals.items():
        label = "All clients" + (f" ({cur})" if len(totals) > 1 else "")
        parts.append(f'<h2>{escape(label)}</h2><div class="tiles">'
                     + tile("Total spend", fmt_money(t["spend"], cur))
                     + tile("Total leads", fmt_int(t["leads"], cur))
                     + tile("Average CPL", fmt_money(t["cpl"], cur, 2), "Cost per lead")
                     + tile("Clicks", fmt_int(t["clicks"], cur))
                     + tile("Average CPC", fmt_money(t["cpc"], cur, 2), "Cost per click")
                     + (tile("ROAS", fmt_roas(t["roas"]), "Sales value ÷ spend") if t.get("roas") else "")
                     + "</div>")

    roas_col = any((r["total"] or {}).get("roas") for r in rows)
    msg_col = any((r["total"] or {}).get("messages_started") for r in rows)
    ncols = 8 + roas_col + msg_col
    body_rows = []
    q = period.query()
    for r in rows:
        c = r["client"]
        link = f'/dashboard/client/{quote(c.key)}?{q}'
        name = (f'<td class="name" data-v="{escape(c.name.lower())}"><a href="{escape(link)}">'
                f'{escape(c.name)}</a><small>{escape(c.ad_account_id)}</small></td>')
        if r["error"]:
            body_rows.append(f'<tr>{name}<td class="err" colspan="{ncols - 1}" data-v="">'
                             f'Could not load: {escape(r["error"])}</td></tr>')
        else:
            body_rows.append(f'<tr>{name}{_cells(r["total"], r["currency"], roas_col, msg_col)}</tr>')
    foot = ""
    if len(totals) == 1:
        cur, t = next(iter(totals.items()))
        foot = f'<tfoot><tr><td>Total</td>{_cells(t, cur, roas_col, msg_col)}</tr></tfoot>'
    parts.append(f"""<div class="card"><h2>Clients</h2><div class="tablewrap">
<table class="sortable"><thead><tr>{_heads("Client", roas_col, msg_col)}</tr></thead>
<tbody>{''.join(body_rows)}</tbody>{foot}</table></div>
<p class="foot">Click a column name to sort. Click a client to see details.
Numbers are saved for {cache_minutes} min; press Refresh for fresh numbers.</p></div>""")
    return page("Ads Dashboard", "".join(parts), demo=demo, logged_in=logged_in)


def _bar_path(x: float, y: float, w: float, h: float) -> str:
    r = min(4.0, w / 2, h)
    if h <= 0:
        return ""
    return (f"M{x:.1f},{y + h:.1f}V{y + r:.1f}Q{x:.1f},{y:.1f} {x + r:.1f},{y:.1f}"
            f"H{x + w - r:.1f}Q{x + w:.1f},{y:.1f} {x + w:.1f},{y + r:.1f}V{y + h:.1f}Z")


def _nice_max(v: float) -> float:
    if v <= 0:
        return 1
    import math
    p = 10 ** math.floor(math.log10(v))
    for m in (1, 2, 2.5, 5, 10):
        if v <= m * p:
            return m * p
    return 10 * p


def bar_chart(title: str, points: list[tuple[str, float, str]], series_var: str,
              axis_fmt) -> str:
    """points = [(x label, value, tooltip text)]. One series, one axis."""
    if not points or not any(v for _, v, _ in points):
        return f'<div class="card chart"><h2>{escape(title)}</h2><div class="empty">No data in this period</div></div>'
    W, H, L, R, T, B = 640, 220, 56, 8, 8, 26
    pw, ph = W - L - R, H - T - B
    top = _nice_max(max(v for _, v, _ in points))
    n = len(points)
    slot = pw / n
    gap = 2 if slot > 4 else 0
    bw = max(1.0, slot - gap)
    out = []
    for i in range(5):
        val = top * i / 4
        y = T + ph - ph * i / 4
        if i:
            out.append(f'<line class="gl" x1="{L}" x2="{W - R}" y1="{y:.1f}" y2="{y:.1f}"/>')
        out.append(f'<text class="ax" x="{L - 6}" y="{y + 4:.1f}" text-anchor="end">{escape(axis_fmt(val))}</text>')
    out.append(f'<line class="base" x1="{L}" x2="{W - R}" y1="{T + ph}" y2="{T + ph}"/>')
    label_every = max(1, round(n / 6))
    for i, (lab, v, tip) in enumerate(points):
        x = L + i * slot + gap / 2
        h = ph * (v / top) if top else 0
        y = T + ph - h
        out.append(f'<g class="pt" tabindex="0" data-tip="{escape(tip)}">'
                   f'<rect class="hit" x="{L + i * slot:.1f}" y="{T}" width="{slot:.1f}" height="{ph}"/>'
                   f'<path class="bar" d="{_bar_path(x, y, bw, h)}"/></g>')
        if i % label_every == 0 or i == n - 1 and n <= 12:
            out.append(f'<text class="ax" x="{x + bw / 2:.1f}" y="{H - 8}" text-anchor="middle">{escape(lab)}</text>')
    return (f'<div class="card chart" style="--series:var({series_var})"><h2>{escape(title)}</h2>'
            f'<svg viewBox="0 0 {W} {H}" role="img" aria-label="{escape(title)}">{"".join(out)}</svg></div>')


def _short(v: float, cur: str | None) -> str:
    sign = CURRENCY_SIGNS.get(cur or "", "")
    if cur == "INR":
        if v >= 1e7:
            return f"{sign}{v / 1e7:g}Cr"
        if v >= 1e5:
            return f"{sign}{v / 1e5:g}L"
    if v >= 1e6:
        return f"{sign}{v / 1e6:g}M"
    if v >= 1e3:
        return f"{sign}{v / 1e3:g}K"
    return f"{sign}{v:g}"


def client_page(c, d: dict, period: Period, *, demo: bool, logged_in: bool) -> str:
    cur = d["currency"]
    act = c.ad_account_id.replace("act_", "")
    head = (f'<p class="crumbs"><a href="/dashboard?{period.query()}">← All clients</a></p>'
            f'<h2 style="font-size:22px;margin:0">{escape(c.name)}</h2>'
            f'<p class="sub">Ad account {escape(c.ad_account_id)}'
            + (f' · Page {escape(c.page_id)}' if c.page_id else "")
            + f' · <a href="https://adsmanager.facebook.com/adsmanager/manage/campaigns?act={quote(act)}" '
              f'target="_blank" rel="noopener">Open in Ads Manager</a></p>')
    parts = [demo_notice() if demo else "", head,
             date_picker(period, f"/dashboard/client/{quote(c.key)}"),
             f'<p class="period">Showing <b>{escape(period.label())}</b></p>']
    if d["error"]:
        parts.append(f'<div class="notice bad">Could not load data from Meta: {escape(d["error"])}</div>')
        return page(f"{c.name} · Ads Dashboard", "".join(parts), demo=demo, logged_in=logged_in)

    t = d["total"]
    parts.append('<div class="tiles">'
                 + tile("Spend", fmt_money(t["spend"], cur))
                 + tile("Leads", fmt_int(t["leads"], cur))
                 + tile("CPL", fmt_money(t["cpl"], cur, 2), "Cost per lead")
                 + tile("Clicks", fmt_int(t["clicks"], cur))
                 + tile("CPC", fmt_money(t["cpc"], cur, 2), "Cost per click")
                 + tile("CTR", fmt_pct(t.get("ctr_percent")), "Clicks ÷ impressions")
                 + tile("Impressions", fmt_int(t["impressions"], cur))
                 + (tile("Messages", fmt_int(t["messages_started"], cur)) if t.get("messages_started") else "")
                 + (tile("Purchases", fmt_int(t["purchases"], cur)) if t.get("purchases") else "")
                 + (tile("ROAS", fmt_roas(t["roas"]), "Sales value ÷ spend") if t.get("roas") else "")
                 + "</div>")

    monthly = d["step"] == "monthly"
    spend_pts, lead_pts = [], []
    for r in d["daily"]:
        try:
            day = date.fromisoformat(r["date_start"])
        except (KeyError, ValueError):
            continue
        lab = day.strftime("%b %y") if monthly else f"{day.day} {day.strftime('%b')}"
        when = day.strftime("%B %Y") if monthly else fmt_day(day)
        spend_pts.append((lab, r["spend"], f"{when}: {fmt_money(r['spend'], cur)}"))
        cpl = f" · CPL {fmt_money(r['cpl'], cur, 2)}" if r.get("cpl") else ""
        lead_pts.append((lab, r["leads"], f"{when}: {fmt_int(r['leads'], cur)} leads{cpl}"))
    per = "month" if monthly else "day"
    parts.append('<div class="charts">'
                 + bar_chart(f"Spend per {per}", spend_pts, "--s-spend", lambda v: _short(v, cur))
                 + bar_chart(f"Leads per {per}", lead_pts, "--s-leads", lambda v: f"{v:g}")
                 + "</div>")

    camps = d["campaigns"]
    if camps:
        roas_col = any(r.get("roas") for r in camps)
        msg_col = any(r.get("messages_started") for r in camps)
        rows = "".join(
            f'<tr><td class="name" data-v="{escape((r.get("campaign_name") or "").lower())}">'
            f'{escape(r.get("campaign_name") or r.get("campaign_id") or "?")}'
            f'<small>{escape(r.get("campaign_id") or "")}</small></td>'
            f'{_cells(r, cur, roas_col, msg_col)}</tr>' for r in camps)
        parts.append(f"""<div class="card"><h2>Campaigns</h2><div class="tablewrap">
<table class="sortable"><thead><tr>{_heads("Campaign", roas_col, msg_col)}</tr></thead>
<tbody>{rows}</tbody></table></div>
<p class="foot">Only campaigns that spent money in this period are shown.</p></div>""")
    else:
        parts.append('<div class="card empty">No campaign spent money in this period.</div>')
    return page(f"{c.name} · Ads Dashboard", "".join(parts), demo=demo, logged_in=logged_in)
