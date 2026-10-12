#!/usr/bin/env python3
"""Build the itinerary: people.txt + my_sessions.txt + sessions.json -> itinerary files.

Pipeline (build_itinerary): load inputs -> match people to the program (core.matching)
-> solve the lexicographic MIP (core.solver) -> write itinerary.md (core.report), the
calendar data (core.schedule), .ics files (core.ics) and the phone page (core.phone_html).

Usage:
  python build.py                  # re-scrapes first if sessions.json is > 7 days old
  python build.py --no-scrape      # never touch the network
  python build.py --solver highs   # use HiGHS instead of Gurobi
"""
import argparse
import subprocess
import sys
from collections import defaultdict
from datetime import datetime

from core.config import HERE, HTML_OUT, ICS_DIR, ICS_OUT, MY_SESSIONS, OUT, PEOPLE
from core.ics import write_calendar_files
from core.inputs import annotate_my_sessions, load_my_sessions, load_people, load_sessions
from core.matching import resolve, verify_data
from core.mip import SOLVERS
from core.phone_html import itinerary_html
from core.report import not_met_data, render
from core.schedule import schedule_data
from core.solver import solve
from core.timefmt import fmt


def log_stderr(msg):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", file=sys.stderr, flush=True)


def build_itinerary(people_text, my_sessions_text="", sessions_path=None, log=log_stderr, solver="gurobi"):
    """Return (itinerary markdown, people, sched). Used by main() and app.py."""
    log("loading sessions.json...")
    scraped_at, sessions = load_sessions(sessions_path)
    log(f"  {len(sessions)} sessions, {sum(len(s['talks']) for s in sessions.values())} talks "
        f"(scraped {scraped_at[:16].replace('T', ' ')} UTC)")
    people = load_people(people_text)
    my_picks, skips, busy, meta = load_my_sessions(my_sessions_text, sessions, log)
    for b in busy:
        log(f"  busy: {b['day']} {fmt(b['s'])}-{fmt(b['e'])} {b['title']}" + (f" with {b['who']}" if b["who"] else ""))
    log(f"matching {len(people)} people against the program...")
    for p in people:
        resolve(p, sessions)
        roles = defaultdict(int)
        for o in p["occ"]:
            roles[o["role"]] += 1
        detail = {"found": ", ".join(f"{n} {r}" for r, n in sorted(roles.items())),
                  "missing": "not in program",
                  "verify": f"VERIFY ({p.get('verify_reason', '')})"}[p["status"]]
        log(f"  {p['name']} [T{p['tier']}]: {detail}")
    log(f"solving schedule with {SOLVERS[solver]}...")
    attend, meals, groups, stats, cand, extra = solve(people, sessions, my_picks, skips, solver, busy, meta)
    log(f"  {stats['binary variables']} binaries, {stats['constraints']} constraints, "
        f"{stats['stages']} priority stages, solved in {stats['solve time (s)']}s")
    log(f"  required items kept: {stats['required kept']}")
    for d in extra["dropped"]:
        log(f"  DROPPED required line {d['line']}: {d['item']} ({d['why']})")
    busy = extra["kept_busy"]
    log(f"  attend {len(attend)} sessions, {len(groups)} meals booked")
    md = render(people, sessions, attend, meals, groups, scraped_at, my_picks, skips, busy, stats,
                extra["dropped"], meta["mine"])
    sched = schedule_data(people, sessions, attend, meals, groups, cand, my_picks, skips, busy)
    for ev in sched["events"]:
        ev["mine"] = ev.get("evt") in meta["mine"]
    sched["stats"] = stats
    sched["dropped"] = extra["dropped"]
    sched["not_met"] = not_met_data(people, sessions, attend, meals)
    sched["my_sessions_annotated"] = annotate_my_sessions(my_sessions_text, sessions, people)
    sched["verify"] = verify_data(people, sessions)
    sched["scraped_at"] = scraped_at
    sched["html"] = itinerary_html(sched, scraped_at)
    return md, people, sched


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-scrape", action="store_true", help="don't refresh a stale sessions.json")
    ap.add_argument("--solver", choices=list(SOLVERS), default="gurobi", help="MIP solver (default gurobi)")
    args = ap.parse_args()
    if not args.no_scrape:
        log_stderr("checking whether sessions.json needs a refresh...")
        subprocess.run([sys.executable, str(HERE / "scrape.py")], check=True)
    my_text = MY_SESSIONS.read_text() if MY_SESSIONS.exists() else ""
    try:
        md, people, sched = build_itinerary(PEOPLE.read_text(), my_text, solver=args.solver)
    except (ValueError, RuntimeError) as e:
        sys.exit(str(e))
    if sched["my_sessions_annotated"] != my_text:
        MY_SESSIONS.write_text(sched["my_sessions_annotated"])
        log_stderr(f"added '# why' comments to {MY_SESSIONS.name}")
    OUT.write_text(md)
    n_ics = write_calendar_files(sched)
    HTML_OUT.write_text(sched["html"])
    log_stderr(f"wrote {HTML_OUT.name} (phone-friendly; AirDrop or email it to your phone)")
    log_stderr(f"wrote {ICS_OUT.name} and {n_ics} single-event files in {ICS_DIR.name}/ "
               "(import into Outlook, or drag files onto your calendar)")
    counts = defaultdict(int)
    for p in people:
        counts[p["status"]] += 1
    log_stderr(f"wrote {OUT.name}: {counts['found']} found, {counts['verify']} to verify, "
               f"{counts['missing']} not in program")


if __name__ == "__main__":
    main()
