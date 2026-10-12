"""Week calendar rendered as HTML (sessions side by side when they overlap)."""

import html


from core import config, timefmt


DAY_START, DAY_END, PX = 7 * 60, 22 * 60 + 30, 1.7


def lanes(evts):
    """Assign side-by-side lanes to overlapping events; returns [(ev, lane, n_lanes)]."""
    evts = sorted(evts, key=lambda e: (e["s"], -e["e"]))
    out, cluster, end = [], [], -1

    def flush():
        lane_end = []
        placed = []
        for ev in cluster:
            for i, le in enumerate(lane_end):
                if le <= ev["s"]:
                    lane_end[i] = ev["e"]
                    placed.append((ev, i))
                    break
            else:
                lane_end.append(ev["e"])
                placed.append((ev, len(lane_end) - 1))
        out.extend((ev, i, len(lane_end)) for ev, i in placed)

    for ev in evts:
        if cluster and ev["s"] >= end:
            flush()
            cluster, end = [], -1
        cluster.append(ev)
        end = max(end, ev["e"])
    if cluster:
        flush()
    return out


def session_tip(ev):
    lines = [f'{ev["id"]}: {ev["title"]}', ev["room"] or "Room TBA"]
    for p in ev["people"]:
        lines.append(f'{p["name"]} [T{p["tier"]}] {p["role"]}' + (f' {timefmt.span12(p["talk_time"])}' if p.get("talk_time") else ""))
        if p.get("talk"):
            lines.append(f'    "{p["talk"]}"')
    return "\n".join(lines)


def talks_html(ppl):
    """One line per talk (time, your people on it, title); chairs etc. without a talk listed after."""
    esc = html.escape
    talks, other = {}, []
    for p in ppl:
        if p.get("talk"):
            talks.setdefault((p.get("talk_time", ""), p["talk"]), []).append(p)
        else:
            other.append(p)
    name = lambda p: (f'<span class="t{p["tier"]}">{esc(p["name"])}</span>'
                      + ("" if p["presenting"] else " <i>(find)</i>"))
    out = []
    for (tm, title), ps in sorted(talks.items()):
        out.append(f'<div class="pp"><span class="tm">{esc(timefmt.span12(tm))}</span> {", ".join(name(p) for p in ps)}'
                   f'<div class="tk">{esc(title)}</div></div>')
    for p in other:
        out.append(f'<div class="pp">{name(p)} <span class="tm">{esc(p["role"].split(",")[0])}</span></div>')
    return "".join(out)


def calendar_html(sched):
    days = [d for d in config.DAYS if any(e["day"] == d for e in sched["events"] if e["kind"] != "fixed")]
    height = (DAY_END - DAY_START) * PX
    esc = html.escape
    cols = []
    for d in days:
        evs = [e for e in sched["events"] if e["day"] == d]
        boxes = []
        for ev in [e for e in evs if e["kind"] == "free"]:
            top, h = (ev["s"] - DAY_START) * PX, (ev["e"] - ev["s"]) * PX
            boxes.append(f'<div class="ev free" style="top:{top}px;height:{h}px;left:0;width:100%">'
                         f'{esc(ev["title"])}</div>')
        # Collapse several unchosen options in one block into a single box so lanes stay readable.
        alts = {}
        for ev in evs:
            if ev["kind"] == "session" and not ev["chosen"]:
                alts.setdefault(ev["block"] or (ev["s"], ev["e"]), []).append(ev)
        merged = []
        for grp in alts.values():
            if len(grp) == 1:
                continue
            merged.append({
                "kind": "session", "chosen": False, "id": f"{len(grp)} options", "pinned": False,
                "s": min(e["s"] for e in grp), "e": max(e["e"] for e in grp), "room": "",
                "title": "; ".join(e["id"] for e in grp),
                "people": [p for e in grp for p in e["people"]],
                "tip": "\n\n".join(session_tip(e) for e in grp), "merged": grp,
            })
            evs = [e for e in evs if e not in grp]
        evs = evs + merged
        for ev, lane, n in lanes([e for e in evs if e["kind"] != "free"]):
            top = (max(ev["s"], DAY_START) - DAY_START) * PX
            h = max((min(ev["e"], DAY_END) - max(ev["s"], DAY_START)) * PX, 14)
            cls = ev["kind"]
            if ev["kind"] == "session":
                cls += (" mine" if ev.get("mine") else " chosen") if ev["chosen"] else " alt"
            ppl = ev["people"]
            if ev.get("merged"):
                head = ev["id"]
                body = "".join(
                    f'<div class="pp"><b>{esc(o["id"])}</b> {esc(o["room"])}: '
                    + ", ".join(f'<span class="t{p["tier"]}">{esc(p["name"])}</span>' for p in o["people"])
                    + "</div>" for o in ev["merged"])
                tip = ev["tip"]
            elif ev["kind"] == "session":
                head = ev["id"] + (" MY SESSION" if ev.get("mine") else " (your pick)" if ev.get("pinned") else "") + (
                    "" if ev["chosen"] else " - option")
                body = (f'<div class="st">{esc(ev["title"])}</div>'
                        f'<div class="rm">&#128205; {esc(ev["room"] or "Room TBA")}</div>'
                        + talks_html(ppl))
                tip = session_tip(ev)
            elif ev["kind"] == "meal":
                head = ev["title"]
                body = ", ".join(f'<span class="t{p["tier"]}">{esc(p["name"])}</span>' for p in ppl)
                tip = ev["title"] + (f' ({ev["note"]})' if ev.get("note") else "") + "\n" + "\n".join(
                    f'{p["name"]} [T{p["tier"]}]: {p["role"]}' for p in ppl)
            elif ev["kind"] == "busy":
                head = ev["title"]
                body = f'<br>{esc(ev["who"])}' if ev.get("who") else ""
                tip = ev["title"] + (f' with {ev["who"]}' if ev.get("who") else "") + "\n(from my_sessions.txt)"
            else:
                head, body, tip = ev["title"], "", ev["title"]
            span = f'{timefmt.fmt(ev["s"])}-{timefmt.fmt(ev["e"])}'
            boxes.append(
                f'<div class="ev {cls}" title="{esc(tip)}" style="top:{top}px;height:{h}px;'
                f'left:calc({100 * lane / n}% + 1px);width:calc({100 / n}% - 3px)">'
                f'<b>{esc(head)}</b> <span class="tm">{span}</span>{body if ev["kind"] != "meal" else "<br>" + body}</div>')
        cols.append(f'<div class="col"><div class="dh">{esc(config.DAY_LONG[d])}</div>'
                    f'<div class="dc" style="height:{height}px">{"".join(boxes)}</div></div>')
    hours = "".join(f'<div class="hr" style="top:{(h * 60 - DAY_START) * PX}px">{timefmt.fmt(h * 60).replace(":00", "")}</div>'
                    for h in range(DAY_START // 60, DAY_END // 60 + 1))
    return f"""
<style>
  body {{ margin:0; font:12px -apple-system, system-ui, sans-serif; color:#1f2328; background:#fff; }}
  .cal {{ display:flex; gap:6px; min-width:1200px; }}
  .axis {{ position:relative; width:42px; margin-top:24px; height:{height}px; flex:none; }}
  .hr {{ position:absolute; font-size:10px; color:#8b949e; transform:translateY(-6px); }}
  .col {{ flex:1; min-width:230px; }}
  .ev:hover {{ height:auto !important; min-height:60px; min-width:260px; z-index:20;
              box-shadow:0 4px 14px rgba(0,0,0,.18); overflow:visible; }}
  .col:last-child .ev:hover {{ right:0; left:auto !important; }}
  .st {{ font-style:italic; margin-top:1px; }}
  .rm {{ font-size:10px; opacity:.8; margin-bottom:2px; }}
  .pp {{ margin-top:2px; }}
  .tk {{ font-size:10px; opacity:.85; line-height:1.2; }}
  .dh {{ height:24px; font-weight:600; text-align:center; }}
  .dc {{ position:relative; border-left:1px solid #e5e7eb;
        background:repeating-linear-gradient(#fff 0 {60 * PX - 1}px, #eef0f2 {60 * PX - 1}px {60 * PX}px); }}
  .ev {{ position:absolute; box-sizing:border-box; padding:2px 4px; border-radius:4px; overflow:hidden;
        line-height:1.25; font-size:11px; }}
  .ev .tm {{ color:inherit; opacity:.7; font-size:10px; }}
  .chosen {{ background:#dbeafe; border:1.5px solid #2563eb; z-index:2; }}
  .alt {{ background:#fff; border:1.5px dashed #9ca3af; color:#4b5563; z-index:2; }}
  .meal {{ background:#dcfce7; border:1.5px solid #16a34a; z-index:2; }}
  .fixed {{ background:#f3e8ff; border:1px solid #c4b5fd; color:#5b21b6; z-index:1; }}
  .busy {{ background:#ffedd5; border:1.5px solid #ea580c; color:#7c2d12; z-index:2; }}
  .mine {{ background:#fef3c7; border:2.5px solid #d97706; color:#78350f; z-index:3; }}
  .free {{ background:transparent; border:1px dashed #d1d5db; color:#9ca3af; z-index:0; }}
  .t1 {{ font-weight:700; }} .t3 {{ opacity:.75; }}
  .legend span {{ display:inline-block; padding:1px 6px; margin-right:6px; border-radius:4px; }}
</style>
<div class="legend" style="margin-bottom:6px">
  <span class="mine">my session</span><span class="chosen">attending</span><span class="alt">overlapping option</span>
  <span class="meal">meal</span><span class="busy">busy (my_sessions.txt)</span><span class="fixed">conference event</span><span class="free">free block</span>
  <b>bold</b> = tier 1 &nbsp; (find) = co-author/chair only &nbsp; hover a box for details
</div>
<div style="overflow-x:auto"><div class="cal"><div class="axis">{hours}</div>{"".join(cols)}</div></div>
"""
