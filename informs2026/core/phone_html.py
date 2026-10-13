"""Self-contained, phone-friendly itinerary page (itinerary.html).

One HTML file with inline CSS and a tiny inline script (theme switch), no external assets,
so it works offline: AirDrop/email it to your phone and open it in the browser. Built from
build_itinerary()'s `sched` dict.
"""
import html
import re
from datetime import datetime

from .config import DAY_LONG, DAYS
from .timefmt import fmt as _fmt, span12 as _span


def _md(text):
    """Escape, then render the little markdown the outreach actions use (**bold**, `code`)."""
    t = html.escape(text)
    t = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", t)
    return re.sub(r"`(.+?)`", r"<code>\1</code>", t)


def _session_card(ev):
    e = html.escape
    talks, other = {}, []
    for p in ev["people"]:
        if p.get("talk"):
            talks.setdefault((p.get("talk_time", ""), p["talk"]), []).append(p)
        else:
            other.append(p)
    name = lambda p: (f'<span class="t{p["tier"]}">{e(p["name"])}</span>'
                      + ("" if p["presenting"] else ' <span class="find">find</span>'))
    rows = "".join(
        f'<li><span class="tm">{e(_span(tm))}</span> {", ".join(name(p) for p in ps)}'
        f'<div class="talk">{e(title)}</div></li>' for (tm, title), ps in sorted(talks.items()))
    rows += "".join(f'<li>{name(p)} <span class="tm">{e(p["role"].split(",")[0])}</span></li>' for p in other)
    cls = "card mine" if ev.get("mine") else "card"
    tag = '<span class="badge">MY SESSION</span>' if ev.get("mine") else ""
    return (f'<div class="{cls}"><div class="when">{_fmt(ev["s"])} - {_fmt(ev["e"])} {tag}</div>'
            f'<div class="title"><b>{e(ev["id"])}</b> {e(ev["title"])}</div>'
            f'<div class="room">{e(ev["room"] or "Room TBA")}</div>'
            + (f"<ul>{rows}</ul>" if rows else "")
            + f'<a class="link" href="{e(ev["url"])}">Session page</a></div>')


def itinerary_html(sched, scraped_at=""):
    e = html.escape
    evs = sched["events"]
    body = []
    for d in sched.get("dropped", []):
        body.append(f'<div class="warn">Required item didn\'t fit: line {d["line"]}: {e(d["item"])} ({e(d["why"])})</div>')
    days_used = [d for d in DAYS if any(ev["day"] == d and ev["kind"] in ("session", "busy", "fixed")
                                        and ev.get("chosen", True) for ev in evs)]
    for d in days_used:
        items = sorted((ev for ev in evs if ev["day"] == d and ev.get("chosen", True)
                        and ev["kind"] in ("session", "busy", "fixed", "meal", "free")),
                       key=lambda ev: (ev["s"], ev["kind"] != "fixed"))
        parts = []
        for ev in items:
            if ev["kind"] == "session":
                parts.append(_session_card(ev))
            elif ev["kind"] == "busy":
                who = f" with {e(ev['who'])}" if ev.get("who") else ""
                parts.append(f'<div class="card busy"><div class="when">{_fmt(ev["s"])} - {_fmt(ev["e"])}</div>'
                             f'<div class="title"><b>{e(ev["title"])}</b>{who}</div></div>')
            elif ev["kind"] == "meal":
                names = ", ".join(e(p["name"]) for p in ev["people"])
                parts.append(f'<div class="card busy"><div class="when">{_fmt(ev["s"])} - {_fmt(ev["e"])}</div>'
                             f'<div class="title"><b>{e(ev["title"])}</b> (suggested): {names}</div></div>')
            elif ev["kind"] == "fixed":
                parts.append(f'<div class="fixed">{_fmt(ev["s"])} - {_fmt(ev["e"])} &middot; {e(ev["title"])}</div>')
            else:
                parts.append(f'<div class="free">{_fmt(ev["s"])} - {_fmt(ev["e"])} &middot; {e(ev["id"])} free</div>')
        body.append(f'<section id="{d}"><h2>{e(DAY_LONG[d])}</h2>{"".join(parts)}</section>')

    nm = sched.get("not_met", [])
    if nm:
        cards = []
        for i, x in enumerate(nm):
            if x.get("seen") and not (i and nm[i - 1].get("seen")):
                cards.append('<p class="sub">Tier 1 you\'ll see present (a talk may not be enough time):</p>')
            aff = f", {e(x['affiliation'])}" if x["affiliation"] else ""
            note = f'<div class="note">{e(x["note"])}</div>' if x["note"] else ""
            acts = "".join(f"<li>{_md(a)}</li>" for a in x["actions"])
            cards.append(f'<details class="card person"{" open" if not x.get("seen") else ""}>'
                         f'<summary><b>{e(x["name"])}</b> <span class="tier">T{x["tier"]}{aff}</span></summary>'
                         f"{note}<ul>{acts}</ul></details>")
        n_todo = sum(not x.get("seen") for x in nm)
        body.append(f'<section id="reach"><h2>People not yet met: reach out ({n_todo})</h2>{"".join(cards)}</section>')

    v = sched.get("verify", [])
    if v:
        body.append('<section id="verify"><h2>VERIFY</h2>' + "".join(
            f'<div class="card"><b>{e(x["name"])}</b>: {e(x["reason"])}</div>' for x in v) + "</section>")

    nav = "".join(f'<a href="#{d}">{d}</a>' for d in days_used) + ('<a href="#reach">Reach out</a>' if nm else "")
    built = datetime.now().strftime("%b %d, %I:%M %p").replace(" 0", " ")
    DARK = ("--bg:#0f1115; --card:#1a1d23; --ink:#e6e8eb; --mute:#9aa1ab; --line:#2a2f37; --accent:#6ea8fe; "
            "--mine:#3a2d0b; --mineb:#f59e0b; --busy:#3a1f0b; --busyb:#fb923c; --code:#252a33; color-scheme: dark;")
    LIGHT = ("--bg:#f7f7f8; --card:#fff; --ink:#1f2328; --mute:#6b7280; --line:#e5e7eb; --accent:#2563eb; "
             "--mine:#fef3c7; --mineb:#d97706; --busy:#ffedd5; --busyb:#ea580c; --code:#f1f5f9; color-scheme: light;")
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>INFORMS 2026</title>
<style>
:root {{ {LIGHT} }}
@media (prefers-color-scheme: dark) {{ :root:not([data-theme="light"]) {{ {DARK} }} }}
:root[data-theme="dark"] {{ {DARK} }}
* {{ box-sizing:border-box; }}
body {{ margin:0; background:var(--bg); color:var(--ink); font:16px/1.4 -apple-system, system-ui, sans-serif;
        padding: env(safe-area-inset-top) 14px calc(24px + env(safe-area-inset-bottom)); }}
header {{ padding:14px 0 6px; }}
h1 {{ font-size:20px; margin:0; }}
.meta {{ color:var(--mute); font-size:12px; }}
nav {{ position:sticky; top:0; z-index:5; background:var(--bg); display:flex; gap:6px; overflow-x:auto;
       padding:8px 0; border-bottom:1px solid var(--line); }}
nav a {{ flex:none; text-decoration:none; color:var(--accent); border:1px solid var(--line); border-radius:999px;
         padding:4px 12px; font-size:14px; background:var(--card); }}
h2 {{ font-size:17px; margin:18px 0 8px; scroll-margin-top:52px; }}
section {{ scroll-margin-top:52px; }}
.card {{ background:var(--card); border:1px solid var(--line); border-left:4px solid var(--accent);
         border-radius:10px; padding:10px 12px; margin:8px 0; }}
.card.mine {{ background:var(--mine); border-left-color:var(--mineb); }}
.card.busy {{ background:var(--busy); border-left-color:var(--busyb); }}
.card.person {{ border-left-color:var(--busyb); }}
.when {{ font-size:13px; color:var(--mute); font-weight:600; }}
.badge {{ background:var(--mineb); color:#fff; border-radius:4px; padding:0 6px; font-size:11px; margin-left:6px; }}
.title {{ margin-top:2px; }}
.room {{ font-size:14px; color:var(--mute); }}
ul {{ margin:6px 0 0; padding-left:18px; }}
li {{ margin:4px 0; }}
.tm {{ font-size:12px; color:var(--mute); }}
.talk {{ font-size:13px; color:var(--mute); }}
.t1 {{ font-weight:700; }}
.find {{ font-size:11px; border:1px solid var(--line); border-radius:4px; padding:0 4px; color:var(--mute); }}
.fixed, .free {{ font-size:13px; color:var(--mute); padding:4px 2px; }}
.free {{ opacity:.7; }}
.link {{ display:inline-block; margin-top:6px; font-size:13px; color:var(--accent); }}
summary {{ cursor:pointer; }}
.tier {{ color:var(--mute); font-size:13px; }}
.note {{ font-size:13px; font-style:italic; color:var(--mute); margin-top:4px; }}
.sub {{ color:var(--mute); font-size:14px; margin:14px 0 4px; }}
.warn {{ background:var(--busy); border:1px solid var(--busyb); border-radius:8px; padding:8px 10px; margin:8px 0; font-size:14px; }}
code {{ background:var(--code); border-radius:4px; padding:0 4px; font-size:13px; word-break:break-word; }}
.top {{ display:flex; align-items:center; justify-content:space-between; gap:8px; flex-wrap:wrap; }}
.theme {{ display:flex; border:1px solid var(--line); border-radius:999px; overflow:hidden; background:var(--card); }}
.theme button {{ border:0; background:none; color:var(--mute); font:inherit; font-size:13px; padding:4px 10px; }}
.theme button[aria-pressed="true"] {{ background:var(--accent); color:#fff; }}
@media print {{ /* always light; drop the on-screen controls; keep cards whole */
  :root, :root[data-theme], :root:not([data-theme="light"]) {{ {LIGHT} --bg:#fff; }}
  body {{ padding:0; font-size:12px; }}
  nav, .theme {{ display:none; }}
  h2 {{ break-after:avoid; }}
  .card, .warn {{ break-inside:avoid; }}
}}
</style>
<script>/* apply the saved theme before first paint */
try {{ var t = localStorage.getItem("informs2026-theme"); if (t === "light" || t === "dark") document.documentElement.setAttribute("data-theme", t); }} catch (e) {{}}
</script></head><body>
<header><div class="top"><h1>INFORMS 2026 itinerary</h1>
<div class="theme" role="group" aria-label="Theme"><button data-t="auto">Auto</button><button data-t="light">Light</button><button data-t="dark">Dark</button></div></div>
<div class="meta">Built {e(built)} &middot; program scraped {e(scraped_at[:10])} &middot; San Francisco time</div></header>
<nav>{nav}</nav>
{"".join(body)}
<script>
(function () {{
  var KEY = "informs2026-theme", root = document.documentElement;
  var buttons = document.querySelectorAll(".theme button");
  function apply(t) {{
    if (t === "light" || t === "dark") root.setAttribute("data-theme", t); else root.removeAttribute("data-theme");
    try {{ localStorage.setItem(KEY, t); }} catch (e) {{}}
    buttons.forEach(function (b) {{ b.setAttribute("aria-pressed", String(b.dataset.t === t)); }});
  }}
  var saved = "auto";
  try {{ saved = localStorage.getItem(KEY) || "auto"; }} catch (e) {{}}
  apply(saved);
  buttons.forEach(function (b) {{ b.addEventListener("click", function () {{ apply(b.dataset.t); }}); }});
}})();
</script>
</body></html>
"""
