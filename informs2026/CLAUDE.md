# INFORMS 2026 itinerary builder

Builds a personal itinerary for the INFORMS Annual Meeting 2026 (San Francisco,
Sun Nov 1 - Wed Nov 4) from a list of people the user wants to see.

## Files
User-edited inputs:
- `people.txt` - source of truth. `Name | tier | note | affiliation`. Tier 1 must see /
  2 want to see (default) / 3 if convenient. 4th field pins an affiliation substring to
  resolve ambiguous names; `-` = "none of these program entries is my person" (missing).
  The app's Resolve VERIFY panel writes it via `core.inputs.set_affiliation`.
- `my_sessions.txt` - required items, one per line: `TC27` attend, `TC27 mine` the user's own
  session (amber), `-TC27` never attend, busy blocks like `Coffee - Tue 9:30am - Caroline
  Johnston` (`core.inputs.parse_busy`; length by keyword, coffee 30 min). Busy blocks forbid
  overlapping sessions; a person named in one counts as met. Builds add a `# why` comment to
  lines without one (`annotate_my_sessions`); existing comments are never changed. The
  Schedule-tab pickers rewrite code lines and keep the others.

Entry points (keep these thin):
- `scrape.py` - downloads the program into `sessions.json`; raw HTML cached in `.cache/`.
- `build.py` - CLI + `build_itinerary()` pipeline (shared with the app). Writes
  `itinerary.md`, `itinerary.ics`, `calendar/*.ics`, `itinerary.html` (+ `itinerary.pdf` with `--pdf`).
- `app.py` - Streamlit page layout only (`.venv/bin/streamlit run app.py`). Tabs: Schedule,
  Itinerary, Plain text, Example. Sidebar: rules text, model + last-solve stats, program data.
  The user prefers running the scraper from the terminal.

`core/` (no Streamlit):
- `config.py` paths, conference blocks/events, meal slots (`SUGGEST_MEALS = False`), weights.
- `timefmt.py` minutes helpers; `fmt`/`t12`/`span12` = 12-hour AM/PM, `fmt24` for .ics/ids.
- `names.py` name + affiliation matching (accents, nicknames, acronyms like MIT).
- `inputs.py` read/write people.txt and my_sessions.txt, load sessions.json, busy blocks.
- `matching.py` appearances per person; found / missing / VERIFY; VERIFY data for the app.
- `mip.py` solver-neutral Var/Expr/Model; `solve_lex` for staged objectives; Gurobi or HiGHS
  (only the chosen one is imported).
- `solver.py` the scheduling MIP (`solve`). `MODEL.md` must stay in sync with it.
- `report.py` itinerary.md text, conflict reasons, outreach list (`not_met_data`, `where_line`).
- `schedule.py` structured events + overlap groups for the calendar and exports.
- `ics.py` calendar files: VTIMEZONE (DST ends Nov 1), two VALARMs (-15 min first, since
  Outlook keeps only the first; then at start). No attendees.
- `phone_html.py` self-contained phone page with an Auto/Light/Dark switch (localStorage) and
  `@media print` styles (forced light, no nav/switch, cards kept whole).
- `pdf.py` `calendar_pdf(cal_html)`: prints `ui.calendar.calendar_html(sched, print_view=True)`
  (hours trimmed to the events, no hover hint) on one landscape Letter page, scaled to fit, with
  Playwright's Chromium (lru_cache). The app passes it to `st.download_button` as a
  deferred callable, which Streamlit runs via `asyncio.to_thread`, so the sync API is fine there.

`ui/` (Streamlit pieces): `actions.py` (build/scrape/status, cached example build),
`calendar.py` (week calendar HTML), `panels.py` (overlap pickers, Resolve VERIFY, People not
yet met, phone/Outlook/HTML/PDF downloads), `text.py` (sidebar rules text).

Other: `example/` (people.txt, my_sessions.txt and a 22-session sessions.json snapshot for the
Example tab; together they show every feature, so extend them when adding one), `MODEL.md`
(the MIP), `DISTRIBUTION.md` (options for shipping to non-technical users),
`../lab_share.md` (lab email + people-free prompt; keep it in sync when features change),
`requirements.txt`, `.venv/` (Python 3.12: playwright+chromium, bs4, gurobipy, highspy,
streamlit). The example build is cached by `ui.actions.code_version()` (source mtimes), so
code changes invalidate it.

## Commands
```
.venv/bin/python build.py              # re-scrapes only if sessions.json > 7 days old
.venv/bin/python build.py --no-scrape
.venv/bin/python build.py --solver highs
.venv/bin/python build.py --pdf        # also write itinerary.pdf
.venv/bin/python scrape.py             # resumes from .cache (~70 min from scratch)
.venv/bin/python scrape.py --force     # deletes .cache and re-scrapes everything
.venv/bin/python scrape.py --reparse   # rebuild sessions.json from .cache, no network
.venv/bin/streamlit run app.py
```

## How the site works (mirasmart, checked Oct 2026)
- `Itinerary/EventsAAG.aspx` sets cookies via JS (redirect through default.aspx), so the
  first load goes through Playwright. After that `ctx.request.get` is enough.
- The grid page has every session: `EventDetail.aspx?evt=N`, `CODE - Title`, track, room, time.
  evt ids run 1..~1165 with gaps.
- `EventDetail.aspx?evt=N` returns WebError.aspx **unless a Referer header is sent**.
  It has the date, `span.FieldLabel` fields (Session Chair 1/2, ...), and `div.PresentationBox`
  per talk. Titles and author lists there are truncated with "..."; presenter is in `<b>`.
- `PresentationDetail.aspx?evdid=N` has the full title and authors
  (`#ctl00_BodyContent_divAuthorSection`, presenter link has `font-weight:bold`).
- Site search (`SearchHome.aspx?s=`) was rejected: accent-sensitive (Garcia != García),
  shows one day per page (other days are postback tabs), matches any word in any field.

## Matching rules (core/names.py, core/matching.py)
- Accent/case folding (incl. ı ł ø ß), middle names/initials ignored, nickname table
  (Tom=Thomas, Dan=Daniel, Gabe=Gabriel, ...).
- `strong` = same first (or nickname) + same last name. `loose` = first initial only,
  compound surname, or first name in middle position.
- Ambiguous -> VERIFY (not scheduled): strong matches with >1 distinct affiliation
  cluster, or only loose matches. Fix by adding affiliation as 4th field in people.txt.
- Roles: presenter / co-author / chair / panelist / moderator. Presenter, panelist and
  moderator count as "presenting"; co-author and chair are "find at session".

## Scheduling (MIP in core/solver.py; Gurobi default, HiGHS optional; see MODEL.md)
- Lexicographic stages via `mip.Model.solve_lex`: (1) required items = every my_sessions.txt
  line (picks + busy blocks), ties to lines higher in the file; (2) tier 1; (3) tier 2;
  (4) tier 3 + tie-breaks. Within a tier: talk seen = 2, needed meal = 1. Each stage's optimum
  is locked in as a constraint. Required items are soft, so the model is always feasible;
  dropped ones are reported (itinerary section, app warnings).
- y[session] attend; at most one at a time (interval cliques at start times). b[j] keep busy block j.
- Meal needed if: not in program, talk lost, tier 1, or only co-author/chair (a kept busy
  block with the person counts as their meal). NO meals are suggested by default
  (`SUGGEST_MEALS = False`, user's choice): every coffee/lunch/dinner is an invitation the user
  makes and adds as a busy block. Flipping the flag re-enables breakfast/coffee suggestions. Shared meal only if same affiliation cluster or co-authors.
- After solving, `not_met_data()` builds "People not yet met: reach out" (the user's outreach
  list): everyone not seen presenting at an attended session and not in a kept busy block, plus
  tier-1 people seen only at a talk. Actions start with a bold verb (Invite / Email first /
  Catch them / Look for them) and name session code + title, talk title + time, and room
  (`where_line`). Shown after Resolve VERIFY in the app and as an itinerary section.
- The sidebar's "How the schedule is built" text (ui/text.py RULES_TEXT) and MODEL.md must stay in sync
  with this.

## Display conventions
- All user-facing times are 12-hour AM/PM (`core.timefmt.fmt`, `t12`, `span12`). 24-hour `fmt24` is
  only for .ics files and internal ids. sessions.json keeps 24-hour strings.
