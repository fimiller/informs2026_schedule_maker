"""Calendar export (.ics) for Outlook and phones, with VTIMEZONE and two alarms per event."""

import io
import re
import zipfile
from datetime import datetime
from datetime import timezone

from .config import DAYS, ICS_DIR, ICS_OUT
from .timefmt import fmt24, span12

DATES = {"Sat": "20261031", "Sun": "20261101", "Mon": "20261102", "Tue": "20261103", "Wed": "20261104"}

VENUE = "Moscone Center, San Francisco"

VTIMEZONE = """BEGIN:VTIMEZONE
TZID:America/Los_Angeles
BEGIN:DAYLIGHT
TZOFFSETFROM:-0800
TZOFFSETTO:-0700
TZNAME:PDT
DTSTART:19700308T020000
RRULE:FREQ=YEARLY;BYMONTH=3;BYDAY=2SU
END:DAYLIGHT
BEGIN:STANDARD
TZOFFSETFROM:-0700
TZOFFSETTO:-0800
TZNAME:PST
DTSTART:19701101T020000
RRULE:FREQ=YEARLY;BYMONTH=11;BYDAY=1SU
END:STANDARD
END:VTIMEZONE"""


def _ics_text(s):
    return (s or "").replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")


def _ics_fold(line):
    """Fold to 75-octet lines as RFC 5545 requires (Outlook is picky)."""
    out, cur = [], b""
    for ch in line:
        b = ch.encode("utf-8")
        if len(cur) + len(b) > (75 if not out else 74):
            out.append(cur.decode("utf-8"))
            cur = b""
        cur += b
    out.append(cur.decode("utf-8"))
    return "\r\n ".join(out)


def ics_events(sched, include_fixed=False):
    """-> [(filename, VEVENT text)] for attended sessions, busy blocks, suggested meals (if enabled) and optionally fixed events."""
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out = []
    for ev in sorted(sched["events"], key=lambda e: (DAYS.index(e["day"]), e["s"])):
        if ev["kind"] == "session" and ev["chosen"]:
            summary = ("MY SESSION " if ev.get("mine") else "") + f"{ev['id']}: {ev['title']}"
            loc = f"{ev['room']}, {VENUE}" if ev["room"] else VENUE
            desc = "\n".join([f"Session: {ev['title']}", f"Room: {ev['room'] or 'TBA'}", ""]
                             + [f"{p['name']} [T{p['tier']}] {p['role']}"
                                + (f" {span12(p['talk_time'])}" if p.get("talk_time") else "")
                                + (f": \"{p['talk']}\"" if p.get("talk") else "") for p in ev["people"]]
                             + ["", ev["url"]])
            start, end, busy = fmt24(ev["s"]), fmt24(ev["e"]), "BUSY"
        elif ev["kind"] == "meal":
            names = ", ".join(p["name"] for p in ev["people"])
            summary = f"{ev['title']}: {names}"
            loc = "TBD"
            start, end = fmt24(ev["s"]), fmt24(ev["e"])
            desc = "\n".join([f"{p['name']} [T{p['tier']}]: {p['role']}" for p in ev["people"]]
                             + ([f"Note: {ev['note']}"] if ev.get("note") else []))
            busy = "TENTATIVE"
        elif ev["kind"] == "busy":
            summary = ev["title"] + (f": {ev['who']}" if ev.get("who") else "")
            loc, desc = "TBD", "From my_sessions.txt"
            start, end, busy = fmt24(ev["s"]), fmt24(ev["e"]), "BUSY"
        elif ev["kind"] == "fixed" and include_fixed:
            summary, loc, desc = f"INFORMS: {ev['title']}", VENUE, ""
            start, end, busy = fmt24(ev["s"]), fmt24(ev["e"]), "FREE"
        else:
            continue
        d = DATES[ev["day"]]
        uid = re.sub(r"[^A-Za-z0-9-]", "", f"{ev['kind']}-{ev['id']}-{d}") + "@informs2026-itinerary"
        lines = ["BEGIN:VEVENT", f"UID:{uid}", f"DTSTAMP:{stamp}",
                 f"DTSTART;TZID=America/Los_Angeles:{d}T{start.replace(':', '')}00",
                 f"DTEND;TZID=America/Los_Angeles:{d}T{end.replace(':', '')}00",
                 f"SUMMARY:{_ics_text(summary)}", f"LOCATION:{_ics_text(loc)}",
                 f"DESCRIPTION:{_ics_text(desc)}",
                 f"X-MICROSOFT-CDO-BUSYSTATUS:{busy}", "TRANSP:" + ("TRANSPARENT" if busy == "FREE" else "OPAQUE")]
        if busy == "TENTATIVE":
            lines.append("STATUS:TENTATIVE")
        if ev["kind"] == "session":
            lines.append(f"URL:{ev['url']}")
        if busy != "FREE":
            # Two alarms: 15 min before, and at the start. Outlook keeps only one reminder per
            # event and uses the first (15 min); Apple/Google Calendar use both.
            for trig, when in (("-PT15M", "in 15 minutes"), ("PT0M", "now")):
                lines += ["BEGIN:VALARM", "ACTION:DISPLAY", f"TRIGGER:{trig}",
                          f"DESCRIPTION:{_ics_text(summary + ' starts ' + when)}", "END:VALARM"]
        lines.append("END:VEVENT")
        fname = f"{ev['day']}_{start.replace(':', '')}_{re.sub(r'[^A-Za-z0-9-]+', '-', ev['id'])}.ics"
        out.append((fname, "\r\n".join(_ics_fold(x) for x in lines)))
    return out


def ics_calendar(vevents):
    body = "\r\n".join(v for _, v in vevents)
    head = "BEGIN:VCALENDAR\r\nVERSION:2.0\r\nPRODID:-//informs2026-itinerary//EN\r\nCALSCALE:GREGORIAN\r\nMETHOD:PUBLISH\r\n"
    return head + VTIMEZONE.replace("\n", "\r\n") + "\r\n" + (body + "\r\n" if body else "") + "END:VCALENDAR\r\n"


def ics_zip(vevents):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for fname, v in vevents:
            z.writestr(fname, ics_calendar([(fname, v)]))
    return buf.getvalue()


def write_calendar_files(sched, include_fixed=False):
    vevents = ics_events(sched, include_fixed)
    ICS_OUT.write_text(ics_calendar(vevents), newline="")
    ICS_DIR.mkdir(exist_ok=True)
    for old in ICS_DIR.glob("*.ics"):
        old.unlink()
    for fname, v in vevents:
        (ICS_DIR / fname).write_text(ics_calendar([(fname, v)]), newline="")
    return len(vevents)
