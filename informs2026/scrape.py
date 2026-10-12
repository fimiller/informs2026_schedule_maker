#!/usr/bin/env python3
"""Scrape the INFORMS Annual Meeting 2026 program into sessions.json.

Flow (see CLAUDE.md for details):
  1. Playwright/Chromium loads EventsAAG.aspx to pass the JS gate (cookie + redirect).
  2. The grid page lists every session: evt id, code, title, track, room, time.
  3. EventDetail.aspx?evt=N (needs a Referer header) gives date, chairs and talks;
     talk author lists there are truncated with "...", presenter is in <b>.
  4. PresentationDetail.aspx?evdid=N gives the full title + author/affiliation list;
     only fetched when the session page truncated something.

Raw HTML is cached in .cache/ so an interrupted run resumes cheaply.

Usage:
  python scrape.py            # scrape only if sessions.json is missing or > 7 days old
  python scrape.py --force    # re-scrape (re-downloads pages; cache is cleared)
  python scrape.py --reparse  # rebuild sessions.json from cached HTML, no network
"""
import argparse
import json
import re
import shutil
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from bs4 import BeautifulSoup

HERE = Path(__file__).resolve().parent
OUT = HERE / "sessions.json"
CACHE = HERE / ".cache"
BASE = "https://submissions.mirasmart.com/InformsAnnual2026/Itinerary/"
MAX_AGE = timedelta(days=7)
DELAY = 0.5  # seconds between requests (~2 req/s)
MISS_LIMIT = 50  # consecutive evt-id misses past the last listed id before stopping

TRUNC = re.compile(r"(\.\.\.|…)\s*$")


def clean(s):
    return re.sub(r"\s+", " ", s or "").strip()


def log(msg):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", file=sys.stderr, flush=True)


# ---------------------------------------------------------------- fetching

class Fetcher:
    def __init__(self, offline=False):
        self.offline = offline
        self.pw = self.browser = self.ctx = None
        self.last = 0.0
        self.fetched = self.cached = 0

    def _start(self):
        from playwright.sync_api import sync_playwright
        log("launching headless Chromium and passing the site's JavaScript check...")
        self.pw = sync_playwright().start()
        self.browser = self.pw.chromium.launch(headless=True)
        self.ctx = self.browser.new_context()
        page = self.ctx.new_page()
        page.goto(BASE + "EventsAAG.aspx", wait_until="networkidle", timeout=120000)
        (CACHE / "EventsAAG.html").write_text(page.content())
        page.close()
        log("site check passed")

    def get(self, name, url, referer):
        """Return HTML for url, using .cache/<name>.html if present. None on error page."""
        path = CACHE / f"{name}.html"
        if path.exists():
            self.cached += 1
            html = path.read_text()
            return None if html == "MISS" else html
        if self.offline:
            return None
        if self.ctx is None:
            self._start()
        for attempt in range(3):
            wait = DELAY - (time.time() - self.last)
            if wait > 0:
                time.sleep(wait)
            self.last = time.time()
            self.fetched += 1
            try:
                r = self.ctx.request.get(url, headers={"Referer": referer}, timeout=60000)
            except Exception as e:  # network hiccup: back off and retry
                log(f"  network error on {name}, retrying: {e}")
                time.sleep(5 * (attempt + 1))
                continue
            if "WebError.aspx" in r.url or r.status >= 400:
                path.write_text("MISS")
                return None
            html = r.text()
            path.write_text(html)
            return html
        return None

    def listing(self):
        path = CACHE / "EventsAAG.html"
        if not path.exists():
            if self.offline:
                sys.exit("no cached EventsAAG.html; run without --reparse")
            self._start()
        return path.read_text()

    def close(self):
        if self.browser:
            self.browser.close()
            self.pw.stop()


# ---------------------------------------------------------------- parsing

def parse_listing(html):
    """evt id -> {code, title, type, track, room, time} from the grid page."""
    soup = BeautifulSoup(html, "html.parser")
    out = {}
    for box in soup.select("div.EventContainer"):
        a = box.find("a", href=re.compile(r"EventDetail\.aspx\?evt=\d+"))
        if not a:
            continue
        evt = int(re.search(r"evt=(\d+)", a["href"]).group(1))
        label = clean(a.get_text())
        m = re.match(r"^([A-Z]{1,3}\d{1,3}[A-Za-z]?)\s+-\s+(.*)$", label)
        code, title = (m.group(1), m.group(2)) if m else ("", label)
        get = lambda suffix: clean(box.find(id=re.compile(suffix + "$")).get_text()) if box.find(id=re.compile(suffix + "$")) else ""
        t = box.find(id="divTime")
        out[evt] = {
            "evt": evt, "code": code, "title": title,
            "type": get("lblEventType"), "track": get("lblTrack"),
            "room": get("lblRoom"), "time": clean(t.get_text()) if t else "",
        }
    return out


def to24(t):
    return datetime.strptime(t.strip().upper(), "%I:%M %p").strftime("%H:%M")


def parse_timespan(s):
    m = re.search(r"(\d{1,2}:\d{2}\s*[AP]M)\s*-\s*(\d{1,2}:\d{2}\s*[AP]M)", s, re.I)
    return (to24(m.group(1)), to24(m.group(2))) if m else ("", "")


def parse_authors_inline(node):
    """Parse 'Name, Affil; Name, Affil.' text where the presenter is bold."""
    presenter = None
    b = node.find(["b", "strong"]) or node.find("a", style=re.compile("bold"))
    if b:
        presenter = clean(b.get_text())
    text = clean(node.get_text(" "))
    text = re.sub(r"\s+,", ",", text)
    text = re.sub(r"\s+;", ";", text)
    truncated = bool(TRUNC.search(text))
    text = TRUNC.sub("", text).rstrip(". ")
    authors = []
    for chunk in [c.strip() for c in text.split(";") if c.strip()]:
        name, _, affil = chunk.partition(",")
        authors.append({"name": clean(name), "affiliation": clean(affil),
                        "presenter": clean(name) == presenter})
    return authors, presenter, truncated


def parse_authors_full(html):
    """Full author list from PresentationDetail: <a>Name</a>, <span class=PersonAffiliation>."""
    soup = BeautifulSoup(html, "html.parser")
    sec = soup.find(id="ctl00_BodyContent_divAuthorSection")
    title = soup.find("h3")
    authors = []
    if sec:
        for a in sec.find_all("a"):
            name = clean(a.get_text())
            aff = a.find_next_sibling("span", class_="PersonAffiliation")
            bold = "bold" in (a.get("style") or "") or a.find_parent(["b", "strong"]) is not None
            authors.append({"name": name, "affiliation": clean(aff.get_text()) if aff else "",
                            "presenter": bold})
    return (clean(title.get_text()) if title else ""), authors


def parse_event(html):
    soup = BeautifulSoup(html, "html.parser")
    head = ""
    for el in soup.find_all(string=re.compile(r"(Sunday|Monday|Tuesday|Wednesday|Saturday|Thursday|Friday),\s+\w+\s+\d+")):
        head = clean(el)
        break
    fields = {}
    for lab in soup.select("span.FieldLabel"):
        key = clean(lab.get_text())
        val = lab.find_next_sibling(["span", "a"])
        if val is not None and key not in fields:
            fields[key] = clean(val.get_text())
    talks = []
    for box in soup.select("div.PresentationBox"):
        a = box.find("a", href=re.compile(r"evdid=\d+"))
        tnode, anode = box.find(class_="Title"), box.find(class_="AuthorBlock")
        title = clean(tnode.get_text()) if tnode else ""
        authors, presenter, trunc = parse_authors_inline(anode) if anode else ([], None, False)
        num = box.find(class_="PresentationNumbers")
        times = box.find(class_="PresentationTimes")
        talks.append({
            "evdid": int(re.search(r"evdid=(\d+)", a["href"]).group(1)) if a else None,
            "number": clean(num.get_text()).replace("Program Number:", "").strip() if num else "",
            "time": "-".join(parse_timespan(times.get_text())) if times else "",
            "title": TRUNC.sub("", title).strip(),
            "authors": authors, "presenter": presenter,
            "_truncated": trunc or bool(TRUNC.search(title)),
        })
    return head, fields, talks


# ---------------------------------------------------------------- main

def scrape(offline=False):
    CACHE.mkdir(exist_ok=True)
    f = Fetcher(offline=offline)
    try:
        listing = parse_listing(f.listing())
        ids = sorted(listing)
        log(f"program grid lists {len(ids)} sessions")
        # Also probe ids past the last listed one in case the grid omits some.
        log(f"checking for unlisted sessions after evt={ids[-1] if ids else 0} "
            f"(stops after {MISS_LIMIT} misses in a row)...")
        extra, misses, n = [], 0, (ids[-1] if ids else 0) + 1
        while misses < MISS_LIMIT and not offline:
            html = f.get(f"evt_{n}", f"{BASE}EventDetail.aspx?evt={n}", BASE + "EventsAAG.aspx")
            if html is None:
                misses += 1
            else:
                misses = 0
                extra.append(n)
            n += 1
        log(f"found {len(extra)} unlisted sessions")
        todo = ids + extra
        log(f"fetching {len(todo)} session pages plus talk pages with truncated author lists "
            f"(~2 pages/s; new pages are cached in .cache/, so it's safe to interrupt and rerun)")
        sessions, t0, f.fetched, f.cached = [], time.time(), 0, 0
        for i, evt in enumerate(todo):
            html = f.get(f"evt_{evt}", f"{BASE}EventDetail.aspx?evt={evt}", BASE + "EventsAAG.aspx")
            if html is None:
                continue
            head, fields, talks = parse_event(html)
            base = listing.get(evt, {"evt": evt, "code": "", "title": fields.get("Session Title", ""),
                                     "type": fields.get("Session Type", ""), "track": fields.get("Topic", ""),
                                     "room": fields.get("Room", ""), "time": head})
            start, end = parse_timespan(base["time"] or head)
            dm = re.match(r"(\w+),\s+(\w+\s+\d+)", head)
            for t in talks:
                if t.pop("_truncated") and t["evdid"]:
                    ph = f.get(f"pres_{t['evdid']}", f"{BASE}PresentationDetail.aspx?evdid={t['evdid']}",
                               f"{BASE}EventDetail.aspx?evt={evt}")
                    if ph:
                        full_title, full_auth = parse_authors_full(ph)
                        if full_title:
                            t["title"] = full_title
                        if full_auth:
                            if not any(a["presenter"] for a in full_auth) and t["presenter"]:
                                for a in full_auth:
                                    a["presenter"] = a["name"] == t["presenter"]
                            t["authors"] = full_auth
            chairs = [v for k, v in fields.items() if k.lower().startswith(("session chair", "chair"))]
            panelists = [v for k, v in fields.items() if "panel" in k.lower()]
            moderators = [v for k, v in fields.items() if "moderator" in k.lower()]
            sessions.append({
                **base,
                "title": fields.get("Session Title", base["title"]),
                "day": dm.group(1) if dm else "", "date": dm.group(2) if dm else "",
                "start": start, "end": end,
                "chairs": chairs, "panelists": panelists, "moderators": moderators,
                "fields": fields,
                "url": f"{BASE}EventDetail.aspx?evt={evt}",
                "talks": talks,
            })
            if (i + 1) % 10 == 0 or i + 1 == len(todo):
                el = time.time() - t0
                eta = el / (i + 1) * (len(todo) - i - 1)
                log(f"{i + 1}/{len(todo)} sessions ({s_code(sessions[-1]) if sessions else ''}) | "
                    f"pages downloaded {f.fetched}, from cache {f.cached} | "
                    f"elapsed {el / 60:.1f} min, ~{eta / 60:.0f} min left")
    finally:
        f.close()
    sessions.sort(key=lambda s: (s["code"] == "", s["code"], s["evt"]))
    OUT.write_text(json.dumps({
        "scraped_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source": BASE + "EventsAAG.aspx",
        "sessions": sessions,
    }, indent=1, ensure_ascii=False))
    n_talks = sum(len(s["talks"]) for s in sessions)
    log(f"wrote {OUT.name}: {len(sessions)} sessions, {n_talks} talks")


def s_code(s):
    return s["code"] or f"evt {s['evt']}"


def is_stale():
    if not OUT.exists():
        return True
    ts = datetime.fromisoformat(json.loads(OUT.read_text())["scraped_at"])
    return datetime.now(timezone.utc) - ts > MAX_AGE


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true", help="re-scrape even if sessions.json is fresh")
    ap.add_argument("--reparse", action="store_true", help="rebuild sessions.json from .cache only")
    args = ap.parse_args()
    if args.reparse:
        scrape(offline=True)
    elif args.force or is_stale():
        if args.force and CACHE.exists():
            shutil.rmtree(CACHE)
        scrape()
    else:
        age = datetime.now(timezone.utc) - datetime.fromisoformat(json.loads(OUT.read_text())["scraped_at"])
        log(f"sessions.json is {age.days}d {age.seconds // 3600}h old (< 7 days), skipping scrape; "
            "use --force to re-scrape")
