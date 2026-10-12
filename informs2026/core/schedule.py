"""Structured schedule (events + overlap groups) for the app's calendar and exports."""

from collections import defaultdict


from .config import BLOCKS, DAYS, FIXED_EVENTS, PRESENT_ROLES
from .timefmt import fmt24, hm, overlaps


def schedule_data(people, sessions, attend, meals, groups, cand, my_picks, skips, busy=()):
    """Structured schedule for the app's calendar: events plus choice groups.

    A choice group is every candidate session (someone on the list presents, co-authors
    or chairs) in the same conference block, or, outside blocks, a run of overlapping ones.
    """
    act = [p for p in people if p["status"] in ("found", "missing")]
    who = defaultdict(list)
    for p in act:
        for o in p["occ"]:
            role = o["role"] if o["role"] in PRESENT_ROLES else f"{o['role']}, find at session"
            talk = sessions[o["evt"]]["talks"][o["talk"]] if o["talk"] is not None else {}
            who[o["evt"]].append((p["name"], p["tier"], role, o["role"] in PRESENT_ROLES,
                                  talk.get("title", ""), talk.get("time", "")))
    events = []
    for e in cand:
        s = sessions[e]
        ppl = sorted(set(who[e]), key=lambda w: (not w[3], w[1], w[5], w[0]))
        events.append({
            "kind": "session", "evt": e, "id": s["id"], "day": s["day"], "s": s["s"], "e": s["e"],
            "title": s["title"], "room": s["room"], "url": s["url"], "block": s["block"],
            "people": [{"name": n, "tier": t, "role": r, "presenting": pr, "talk": tt, "talk_time": tm}
                       for n, t, r, pr, tt, tm in ppl],
            "chosen": e in attend, "pinned": e in my_picks, "skipped": e in skips,
        })
    for ml in meals:
        if groups.get(ml["id"]):
            events.append({
                "kind": "meal", "id": ml["id"], "day": ml["day"], "s": ml["s"], "e": ml["e"],
                "title": ml["kind"].capitalize(), "note": ml["note"], "chosen": True,
                "people": [{"name": p["name"], "tier": p["tier"], "role": p["need_reason"],
                            "presenting": False} for p in groups[ml["id"]]],
            })
    for d, st, en, label in FIXED_EVENTS:
        events.append({"kind": "fixed", "id": label, "day": d, "s": hm(st), "e": hm(en),
                       "title": label, "chosen": True, "people": []})
    for b in busy:
        events.append({"kind": "busy", "id": f"busy-{b['day']}-{fmt24(b['s'])}", "day": b["day"], "s": b["s"],
                       "e": b["e"], "title": b["title"], "who": b["who"], "chosen": True,
                       "people": [{"name": b["who"], "tier": 0, "role": "", "presenting": False}] if b["who"] else []})
    taken = [ev for ev in events if (ev["kind"] == "session" and ev["chosen"]) or ev["kind"] == "busy"]
    for d, code, st, en in BLOCKS:
        slot = {"day": d, "s": hm(st), "e": hm(en)}
        if not any(overlaps(slot, b) for b in taken):
            events.append({"kind": "free", "id": code, "day": d, "s": hm(st), "e": hm(en),
                           "title": f"{code} free", "chosen": True, "people": []})

    sess = sorted((ev for ev in events if ev["kind"] == "session"), key=lambda ev: (DAYS.index(ev["day"]), ev["s"]))
    groups_out, by_key = [], {}
    for ev in sess:
        key = ev["block"]
        if key is None:  # outside the standard blocks: chain overlapping sessions
            prev = next((g for g in reversed(groups_out) if g["day"] == ev["day"] and g["block"] is None
                         and any(overlaps(ev, o) for o in g["options"])), None)
            key = prev["key"] if prev else f"{ev['day']}-{fmt24(ev['s'])}"
        if key not in by_key:
            by_key[key] = {"key": key, "day": ev["day"], "block": ev["block"], "s": ev["s"], "e": ev["e"],
                           "options": []}
            groups_out.append(by_key[key])
        g = by_key[key]
        g["options"].append(ev)
        g["s"], g["e"] = min(g["s"], ev["s"]), max(g["e"], ev["e"])
    return {"events": events, "groups": groups_out}
