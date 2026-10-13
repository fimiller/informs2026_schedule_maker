# INFORMS 2026 Itinerary Builder

Builds a personal schedule for the INFORMS Annual Meeting 2026 (San Francisco, Nov 1–4) from a list of people you want to see.

It scrapes the online program, finds every talk, panel and session chaired by the people on your list, and solves an integer program to pick which sessions to attend when they clash. It also gives you an outreach list of people you won't see at a talk, so you know whom to invite for coffee. Outputs:

- `itinerary.md`: a plain-text itinerary
- `itinerary.ics` and `calendar/*.ics`: calendar files for Outlook or your phone, with reminders
- `itinerary.html`: a self-contained page for your phone that works offline
- `itinerary.pdf`: the week calendar on one printable page (in the app, or `build.py --pdf`)

## Setup

Requires Python 3.12.

```
cd informs2026
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/playwright install chromium
```

Gurobi is the default solver and needs a license. [HiGHS](https://highs.dev) is free and solves the same model; select it in the app or with `--solver highs`.

## Usage

1. **Scrape the program** (about 70 minutes the first time; the scraper resumes if interrupted):
   ```
   .venv/bin/python scrape.py
   ```
2. **Write `people.txt`**, one person per line:
   ```
   Name | tier | note | affiliation
   ```
   Tier 1 = must see, 2 = want to see (the default), 3 = if convenient. Add an affiliation to tell apart people who share a name.
3. **Optionally write `my_sessions.txt`** for things you've already decided:
   - `TC27` attend this session
   - `-TC27` never attend it
   - `TC27 mine` your own session
   - `Coffee - Tue 9:30am - Name` a meeting that blocks out time
4. **Build the itinerary**, from the command line:
   ```
   .venv/bin/python build.py --solver highs
   ```
   Or use the interactive app, which has a week calendar, pickers for clashing sessions, and help resolving ambiguous names:
   ```
   .venv/bin/streamlit run app.py
   ```

The app's **Example** tab runs on the files in [`informs2026/example/`](informs2026/example/), so you can try it before scraping.

## More

- [`MODEL.md`](informs2026/MODEL.md): the optimization model
- [`CLAUDE.md`](informs2026/CLAUDE.md): project notes (file layout, name-matching rules, how the scraper works)
- [`DISTRIBUTION.md`](informs2026/DISTRIBUTION.md): ideas for making this usable without a terminal

Built with [Claude Code](https://claude.com/claude-code).
