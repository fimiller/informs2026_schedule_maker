"""itinerary.md text, conflict explanations and the 'People not yet met' outreach list."""

from collections import defaultdict
from datetime import datetime

from .config import BLOCKS, DAYS, DAY_LONG, FIXED_EVENTS, PRESENT_ROLES
from .names import fold
from .solver import group_reason
from .timefmt import fmt, hm, overlaps, span12, t12


def talk_line(s, o):
    t = s["talks"][o["talk"]] if o["talk"] is not None else None
    if t:
        when = f" {span12(t['time'])}" if t.get("time") else ""
        return f"{o['role']}{when}: \"{t['title']}\""
    return o["role"]


def person_tag(p):
    aff = f", {p['affs'][0]}" if p.get("affs") else ""
    return f"{p['name']} [T{p['tier']}{aff}]"


def explain_conflicts(people, sessions, attend, my_picks, skips):
    """For every presenter whose talk isn't attended, say what won and why."""
    act = [p for p in people if p["status"] == "found"]
    att = [sessions[e] for e in attend]
    lines = []
    for p in sorted(act, key=lambda p: (p["tier"], fold(p["name"]))):
        for e in p["present_evts"]:
            if e in attend:
                continue
            s = sessions[e]
            if e in skips:
                lines.append(f"- {s['id']} ({s['day']} {t12(s['start'])}) {p['name']} [T{p['tier']}]: "
                             "you chose to skip it (my_sessions.txt).")
                continue
            rivals = [a for a in att if overlaps(a, s)]
            if not rivals:
                continue  # shouldn't happen: free slot would be taken
            r = rivals[0]
            winners = [q for q in act if r["evt"] in q["present_evts"]]
            label = f"{s['id']} ({s['day']} {t12(s['start'])}) {p['name']} [T{p['tier']}]"
            if p["seen_at_talk"]:
                other = next(sessions[x]["id"] for x in p["present_evts"] if x in attend)
                lines.append(f"- {label}: skipped, you see them presenting at {other} instead.")
                continue
            if not winners:
                why = "you picked this session in my_sessions.txt" if r["evt"] in my_picks else "it lets you find more people"
                lines.append(f"- {label}: lost to {r['id']} ({why}). -> on your outreach list")
                continue
            best = min(q["tier"] for q in winners)
            names = ", ".join(f"{q['name']} [T{q['tier']}]" for q in winners)
            if best < p["tier"]:
                why = "higher tier"
            else:
                finds = [q["name"] for q in act if r["evt"] in q["find_evts"]]
                loser_finds = [q["name"] for q in act if e in q["find_evts"]]
                if len(winners) > 1:
                    why = f"tie on tier; {r['id']} has {len(winners)} of your presenters"
                elif len(finds) > len(loser_finds):
                    why = f"tie on tier; {r['id']} also lets you find {', '.join(finds)}"
                elif any(len(q["present_evts"]) == 1 for q in winners) and len(p["present_evts"]) > 1:
                    why = f"tie on tier; {p['name']} has another talk"
                else:
                    why = "tie on tier; broken alphabetically by name (swap via my_sessions.txt)"
            lines.append(f"- {label}: lost to {r['id']} with {names} ({why}). -> on your outreach list")
    return lines


def render(people, sessions, attend, meals, groups, scraped_at, my_picks, skips, busy=(), stats=None,
           dropped=(), mine=frozenset()):
    act = [p for p in people if p["status"] in ("found", "missing")]
    by_evt = defaultdict(list)
    for p in act:
        for o in p["occ"]:
            by_evt[o["evt"]].append((p, o))
    meal_of = {m["id"]: m for m in meals}

    L = []
    L.append("# INFORMS Annual Meeting 2026 - Itinerary")
    L.append("")
    L.append(f"Built {datetime.now().strftime('%Y-%m-%d %H:%M')} from people.txt "
             f"({len(people)} people) and sessions.json (scraped {scraped_at[:16].replace('T', ' ')} UTC).")
    if stats:
        L.append(f"Solved with {stats['solver']} in {stats['solve time (s)']}s "
                 f"({stats['binary variables']} binaries, {stats['constraints']} constraints, {stats['status']}).")
    L.append("Edit people.txt (and optionally my_sessions.txt), then run: .venv/bin/python build.py")
    L.append("Priorities: required items in my_sessions.txt first, then tier 1, tier 2, tier 3.")
    if dropped:
        L.append("")
        L.append("## Required items that didn't fit")
        L.append("")
        L.append("These lines in my_sessions.txt clash with other required items; the one higher in the file wins.")
        for d in dropped:
            L.append(f"- line {d['line']}: {d['item']} ({d['why']})")
    L.append("")
    L.append("Legend: ATTEND = go to this session. [T1] must see, [T2] want to see, [T3] if convenient.")
    L.append("'find at session' = co-author or chair only, so they may not be there.")
    L.append("FREE = no one on your list; open for sessions you want to add.")
    L.append("")

    for day in DAYS:
        rows = []
        for (d, code, s, e) in BLOCKS:
            if d == day:
                rows.append((hm(s), "block", code, hm(e)))
        for e in attend:
            ss = sessions[e]
            if ss["day"] == day and ss["block"] is None:
                rows.append((ss["s"], "extra", e, ss["e"]))
        for ml in meals:
            if ml["day"] == day:
                rows.append((ml["s"], "meal", ml["id"], ml["e"]))
        for (d, s, e, label) in FIXED_EVENTS:
            if d == day:
                rows.append((hm(s), "fixed", label, hm(e)))
        for b in busy:
            if b["day"] == day:
                rows.append((b["s"], "busy", b["title"] + (f" with {b['who']}" if b["who"] else ""), b["e"]))
        if not rows:
            continue
        L.append(f"## {DAY_LONG[day]}")
        L.append("")
        for start, kind, key, end in sorted(rows, key=lambda r: (r[0], r[1] != "fixed")):
            span = f"{fmt(start)}-{fmt(end)}"
            if kind == "fixed":
                L.append(f"- {span}  {key}")
            elif kind == "busy":
                L.append(f"- {span}  BUSY: {key} (my_sessions.txt)")
            elif kind == "meal":
                ml = meal_of[key]
                who = groups.get(key, [])
                note = f" ({ml['note']})" if ml["note"] else ""
                label = ml["kind"].upper()
                if not who:
                    if any(overlaps(b, ml) for b in busy):
                        continue
                    L.append(f"- {span}  {label}: open{note}")
                    continue
                L.append(f"- {span}  {label}: " + ", ".join(person_tag(p) for p in who) + note)
                if len(who) > 1:
                    L.append(f"    grouped because: {group_reason(who[0], who[1], sessions) or ''}"
                             + "".join(f"; {group_reason(who[0], q, sessions)}" for q in who[2:]))
                for p in who:
                    L.append(f"    {p['name']}: {p['need_reason']}" + (f" | {p['note']}" if p["note"] else ""))
            else:
                evts = [e for e in attend if sessions[e]["day"] == day and
                        (sessions[e]["block"] == key if kind == "block" else e == key)]
                head = f"- {span}  {key if kind == 'block' else ''}".rstrip()
                if not evts:
                    blk = {"day": day, "s": start, "e": end}
                    if not any(overlaps(b, blk) for b in busy):
                        L.append(f"{head}  FREE")
                    continue
                for e in evts:
                    s = sessions[e]
                    tag = " (MY SESSION)" if e in mine else " (my pick)" if e in my_picks else ""
                    L.append(f"{head}  ATTEND {s['id']}{tag}: {s['title']}")
                    L.append(f"    Room: {s['room'] or 'TBA'} | {s['track']} | {s['url']}")
                    for p, o in sorted(by_evt[e], key=lambda x: (x[1]["role"] not in PRESENT_ROLES, x[0]["tier"])):
                        tag = "" if o["role"] in PRESENT_ROLES else " - find at session"
                        L.append(f"    {person_tag(p)} {talk_line(s, o)}{tag}")
        L.append("")

    conflicts = explain_conflicts(people, sessions, attend, my_picks, skips)
    if conflicts:
        L.append("## Conflicts")
        L.append("")
        L.extend(conflicts)
        L.append("")

    verify = [p for p in people if p["verify"]]
    if verify:
        L.append("## VERIFY (not scheduled until resolved)")
        L.append("")
        L.append("Fix in the app (Schedule tab > Resolve VERIFY) or add the right affiliation as the")
        L.append("4th field in people.txt, e.g.  Alex Rivera | 2 | | Example University")
        L.append("Use - as the affiliation if none of these is the person you mean.")
        L.append("")
        for p in verify:
            state = "NOT SCHEDULED" if p["status"] == "verify" else "scheduled from confident matches; check these extras"
            L.append(f"- {p['name']} [T{p['tier']}]: {p['verify_reason']} ({state})")
            for o in sorted(p["verify"], key=lambda o: (fold(o["aff"]), sessions[o["evt"]]["id"])):
                s = sessions[o["evt"]]
                extra = f" [{o['why']}]" if o["why"] else ""
                L.append(f"    {o['as']}, {o['aff'] or '(no affiliation listed)'}: {o['role']} in {s['id']} "
                         f"{s['day']} {t12(s['start'])} \"{s['title']}\"{extra}")
        L.append("")

    not_met = not_met_data(people, sessions, attend, meals)
    if not_met:
        L.append("## People not yet met: reach out")
        L.append("")
        L.append("Not seen presenting at a session you're attending and no busy block in my_sessions.txt yet.")
        for n_, nm in enumerate(not_met):
            if nm.get("seen") and not (n_ and not_met[n_ - 1].get("seen")):
                L.append("")
                L.append("Tier 1 you'll see present (a talk may not be enough time; consider inviting too):")
            aff = f", {nm['affiliation']}" if nm["affiliation"] else ""
            L.append(f"- **{nm['name']}** [T{nm['tier']}{aff}]" + (f" | {nm['note']}" if nm["note"] else ""))
            for a in nm["actions"]:
                L.append(f"    - {a}")
        L.append("")

    missing = [p for p in people if p["status"] == "missing"]
    if missing:
        L.append("## Not in the program (email first)")
        L.append("")
        for p in missing:
            where = (f"-> {p['meal']}" if p["meal"] else
                     f"-> already meeting: {p['met']['title']} {p['met']['day']} {fmt(p['met']['s'])}" if p.get("met")
                     else "-> email first, then invite")
            L.append(f"- {person_tag(p)} {where}" + (f" | {p['note']}" if p["note"] else ""))
        L.append("")

    L.append("## Everyone")
    L.append("")
    for p in sorted(people, key=lambda p: (p["tier"], fold(p["name"]))):
        if p["status"] == "verify":
            L.append(f"- {p['name']} [T{p['tier']}]: VERIFY")
            continue
        bits = []
        for e in p.get("present_evts", []):
            s = sessions[e]
            mark = "attending" if e in attend else "skipped"
            bits.append(f"presents {s['id']} {s['day']} {t12(s['start'])} ({mark})")
        for e in p.get("find_evts", []):
            s = sessions[e]
            roles = "/".join(sorted({o["role"] for o in p["occ"] if o["evt"] == e}))
            mark = "attending" if e in attend else "not attending"
            bits.append(f"{roles} {s['id']} {s['day']} {t12(s['start'])} ({mark})")
        if p["status"] == "missing":
            bits.append("not in program")
        if p.get("met"):
            m_ = p["met"]
            bits.append(f"already meeting: {m_['title']} {m_['day']} {fmt(m_['s'])}")
        if p.get("meal"):
            bits.append(f"meal: {p['meal']}")
        elif p.get("needs_meal"):
            bits.append("not yet met: invite")
        L.append(f"- {person_tag(p)}: " + "; ".join(bits) + (f" | {p['note']}" if p["note"] else ""))
        for o in p.get("dropped", []):
            s = sessions[o["evt"]]
            L.append(f"    ignored (affiliation filter): {o['as']}, {o['aff'] or 'no affiliation'} in {s['id']}")
    L.append("")
    return "\n".join(L)


def where_line(p, s):
    """'**TE35: Session title**, "Talk title" (Tue 4:15 PM-4:30 PM), Room' for person p in session s."""
    talk = next((s["talks"][o["talk"]] for o in p["occ"] if o["evt"] == s["evt"] and o["talk"] is not None
                 and o["role"] in PRESENT_ROLES), None) or next(
        (s["talks"][o["talk"]] for o in p["occ"] if o["evt"] == s["evt"] and o["talk"] is not None), None)
    when = f"{s['day']} {span12(talk['time'])}" if talk and talk.get("time") else f"{s['day']} {t12(s['start'])}"
    talk_txt = f", talk \"{talk['title']}\"" if talk else ""
    return f"**{s['id']}: {s['title']}**{talk_txt} ({when}), {s['room'] or 'room TBA'}"


def not_met_data(people, sessions, attend, meals):
    """Your outreach list: everyone not seen presenting at a session you attend and with no busy
    block in my_sessions.txt. Actions are markdown with the verb in bold, most important first."""
    meal_of = {m["id"]: m for m in meals}
    out = []
    for p in sorted(people, key=lambda p: (p["tier"], fold(p["name"]))):
        if p["status"] == "verify":
            out.append({"name": p["name"], "tier": p["tier"], "affiliation": "", "note": p["note"],
                        "seen": False, "actions": ["**Resolve VERIFY first** (ambiguous name), then rebuild."]})
            continue
        if p.get("met"):
            continue
        first = p["name"].split()[0]
        example = f"`Coffee - <day> <time> - {p['name']}`"
        if p.get("seen_at_talk"):
            if p["tier"] == 1:  # rule: a talk alone isn't enough time with a tier-1 person
                talk = next(sessions[e] for e in p["present_evts"] if e in attend)
                out.append({"name": p["name"], "tier": 1, "affiliation": ", ".join(p.get("affs", [])[:1]),
                            "note": p["note"], "seen": True, "actions": [
                                f"You'll see {first} present: {where_line(p, talk)}. "
                                f"**Invite** them too if you want real time together ({example})."]})
            continue
        acts = []
        if p["status"] == "missing":
            acts.append(f"**Email first**: not in the program, so ask whether {first} is coming, then invite "
                        f"and add it to my_sessions.txt ({example}).")
        elif p.get("meal"):
            ml = meal_of[p["meal"]]
            acts.append(f"**Invite** to the suggested {ml['kind']}: **{DAY_LONG[ml['day']]} {fmt(ml['s'])}**.")
        else:
            acts.append(f"**Invite** {first} to coffee, lunch or dinner. Once agreed, add it to my_sessions.txt "
                        f"({example}).")
        for e in p.get("present_evts", []):
            s = sessions[e]
            acts.append(f"**Catch them** before or after their talk, which clashes with your schedule: "
                        f"{where_line(p, s)}.")
        for e in sorted(p.get("find_evts", []), key=lambda e: e not in attend):
            s = sessions[e]
            roles = "/".join(sorted({o["role"] for o in p["occ"] if o["evt"] == e}))
            if e in attend:
                acts.append(f"**Look for them** at {where_line(p, s)}, which you're attending. "
                            f"Listed as {roles}, so they may not be there.")
            else:
                acts.append(f"Also listed as {roles} in {where_line(p, s)}; you're not attending.")
        out.append({"name": p["name"], "tier": p["tier"], "affiliation": ", ".join(p.get("affs", [])[:1]),
                    "note": p["note"], "seen": False, "actions": acts})
    return sorted(out, key=lambda x: x.get("seen", False))
