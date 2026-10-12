"""Reading and writing people.txt and my_sessions.txt, and loading sessions.json."""

import json
import re
from pathlib import Path

from .config import BLOCKS, SESSIONS
from .names import match_name
from .timefmt import hm, t12


def load_people(text):
    people = []
    for ln, raw in enumerate(text.splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        parts = [p.strip() for p in line.split("|")]
        name = parts[0]
        tier = 2
        if len(parts) > 1 and parts[1]:
            try:
                tier = int(parts[1])
            except ValueError:
                tier = None
            if tier not in (1, 2, 3):
                raise ValueError(f"people.txt line {ln}: tier must be 1, 2 or 3: {raw!r}")
        people.append({"name": name, "tier": tier,
                       "note": parts[2] if len(parts) > 2 else "",
                       "pin": parts[3] if len(parts) > 3 else ""})
    return people


def load_sessions(path=None):
    data = json.loads(Path(path or SESSIONS).read_text())
    sessions = {}
    for s in data["sessions"]:
        if not s.get("day") or not s.get("start"):
            continue
        s = dict(s)
        s["day"] = s["day"][:3]
        s["s"], s["e"] = hm(s["start"]), hm(s["end"])
        s["block"] = next((b[1] for b in BLOCKS if b[0] == s["day"]
                           and hm(b[2]) < s["e"] and s["s"] < hm(b[3])), None)
        s["id"] = s["code"] or f"evt{s['evt']}"
        sessions[s["evt"]] = s
    return data["scraped_at"], sessions

DAY_WORDS = {"sat": "Sat", "saturday": "Sat", "sun": "Sun", "sunday": "Sun", "mon": "Mon", "monday": "Mon",
             "tue": "Tue", "tues": "Tue", "tuesday": "Tue", "wed": "Wed", "weds": "Wed", "wednesday": "Wed"}

BUSY_MINUTES = {"coffee": 30, "breakfast": 60, "lunch": 60, "dinner": 120, "drinks": 90}

_T = r"(\d{1,2})(?::(\d{2}))?\s*(am|pm|a|p)?"


def _clock(h, m, ap, ref_ap=None):
    h, m = int(h), int(m or 0)
    ap = (ap or ref_ap or "").lower()[:1]
    if ap == "p" and h < 12:
        h += 12
    elif ap == "a" and h == 12:
        h = 0
    elif not ap and 1 <= h < 7:  # bare "3" means 3pm at a conference
        h += 12
    return h * 60 + m


def parse_busy(line):
    """'Coffee - Tue 10am - Jane Smith' -> {title, who, day, s, e}; None if no day word in the line."""
    parts = [x.strip() for x in re.split(r"\s+[-–—|]\s+", line) if x.strip()]
    day = when = None
    # Prefer the part with a day word AND a digit, so "Coffee with Sun Wei - Tue 10am" works.
    for need_digit in (True, False):
        for i, part in enumerate(parts):
            d = next((DAY_WORDS[w] for w in re.findall(r"[a-z]+", part.lower()) if w in DAY_WORDS), None)
            if d and (not need_digit or re.search(r"\d", part)):
                day, when = d, i
                break
        if day:
            break
    if day is None:
        return None
    text = parts[when].lower()
    rng = re.search(_T + r"\s*(?:-|–|to)\s*" + _T, text)
    one = re.search(_T, text)
    rest = [x for i, x in enumerate(parts) if i != when]
    title = rest[0] if rest else "Busy"
    who = " - ".join(rest[1:])
    if rng:
        g = rng.groups()
        start, end = _clock(g[0], g[1], g[2], g[5]), _clock(g[3], g[4], g[5])
    elif one:
        start = _clock(*one.groups())
        end = start + next((v for k, v in BUSY_MINUTES.items() if k in title.lower()), 60)
    else:
        raise ValueError(f"my_sessions.txt: no time found in {line!r} (try 'Coffee - Tue 10am - Name')")
    return {"title": title, "who": who, "day": day, "s": start, "e": max(end, start + 15), "raw": line}


def load_my_sessions(text, sessions, log):
    """Parse my_sessions.txt (everything after # is a comment).

      TC27            attend (required)
      TC27 mine       attend; it's your own session (highlighted)
      -TC27           never attend
      Coffee - Tue 10am - Name    busy block (required)

    Returns (picks, skips, busy, meta): picks in file order; meta = {"line": {evt: line_no},
    "mine": {evt, ...}}. Overlapping required items are left for the solver to arbitrate.
    """
    by_code = {s["id"].upper(): s["evt"] for s in sessions.values()}
    picks, skips, busy, meta = [], set(), [], {"line": {}, "mine": set()}
    for ln, raw in enumerate((text or "").splitlines(), 1):
        line = raw.split("#")[0].strip()
        if not line:
            continue
        toks = line.split()
        code = toks[0].upper()
        skip = code.startswith("-")
        code = code.lstrip("-")
        if code not in by_code:
            try:
                b = parse_busy(line)
            except ValueError as e:
                log(f"warning: {e}")
                continue
            if b:
                b["line"] = ln
                busy.append(b)
            else:
                log(f"warning: my_sessions.txt line {ln}: unknown session code {code}")
            continue
        evt = by_code[code]
        if skip:
            skips.add(evt)
            continue
        if evt not in meta["line"]:
            picks.append(evt)
            meta["line"][evt] = ln
        if "mine" in (t.lower() for t in toks[1:]):
            meta["mine"].add(evt)
    return picks, skips, busy, meta


def annotate_my_sessions(text, sessions, people):
    """Add a '# why' comment to my_sessions.txt lines that don't have one. Existing comments are kept."""
    by_code = {s["id"].upper(): s for s in sessions.values()}
    out = []
    for raw in (text or "").splitlines():
        body, hashmark, _ = raw.partition("#")
        if hashmark or not body.strip():
            out.append(raw)
            continue
        toks = body.split()
        code = toks[0].upper().lstrip("-")
        if code in by_code:
            s = by_code[code]
            who = []
            for p in people:
                roles = sorted({(o["role"], (t12(s["talks"][o["talk"]].get("time", "")[:5]) if o["talk"] is not None else ""))
                                for o in p.get("occ", []) if o["evt"] == s["evt"]})
                if roles:
                    who.append(f"{p['name']} [T{p['tier']}] " + ", ".join(f"{r} {tm}".strip() for r, tm in roles))
            if toks[0].startswith("-"):
                note = f"skip: {s['title']}"
            elif "mine" in (t.lower() for t in toks[1:]):
                note = f"my session: {s['title']}" + (f" ({'; '.join(who)})" if who else "")
            else:
                note = f"{s['title']}: " + ("; ".join(who) if who else "no one from people.txt")
        else:
            try:
                b = parse_busy(body.strip())
            except ValueError:
                b = None
            if not b:
                out.append(raw)
                continue
            p = next((p for p in people if b["who"] and match_name(p["name"], b["who"])), None)
            if p:
                state = {"missing": "not in the program", "found": "in the program",
                         "verify": "needs VERIFY"}[p["status"]]
                note = f"meeting {p['name']} [T{p['tier']}] ({state}); counts as their meal"
            else:
                note = f"busy: {b['title']}" + (f" with {b['who']}" if b["who"] else "") + " (not in people.txt)"
        out.append(f"{body.rstrip():<23} # {note}")
    return "\n".join(out) + ("\n" if out else "")


def set_affiliation(people_text, name, affiliation):
    """Rewrite the people.txt line for `name` with a new 4th field. -> (text, line_no, old, new)."""
    lines = people_text.splitlines()
    for n, raw in enumerate(lines):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        parts = [x.strip() for x in line.split("|")]
        if parts[0] == name:
            parts += [""] * (4 - len(parts))
            parts[3] = affiliation
            new = " | ".join(parts[:4])
            lines[n] = new
            return "\n".join(lines) + "\n", n + 1, raw, new
    raise ValueError(f"{name} not found in people.txt")
