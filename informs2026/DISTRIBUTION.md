# Shipping this to non-technical users

Notes on turning the itinerary builder into something people can use without a terminal,
Python, or a Gurobi license.

## What makes it hard today

| Piece | Problem for a non-technical user |
|---|---|
| `scrape.py` | Needs Playwright plus a ~100 MB Chromium download, and takes about an hour per scrape |
| Gurobi | The academic license is per person and can't be redistributed |
| Python venv | Has to be installed and run from a terminal |
| `app.py` writes files | It saves `people.txt`, `my_sessions.txt` and the outputs to disk. That's fine for one person, but users would overwrite each other on a shared server |
| Personal data | People lists and meeting plans are private |

**The key simplification:** users never need to scrape. One person (you) scrapes about once
a week and ships `sessions.json` with the app. Users only edit their people list and picks.
Use **HiGHS** for everyone else: it's free, needs no license, and gives the same schedules.

## Options

### 1. Hosted web app (recommended)
Users open a link and work in the browser.
- **Hosting:** Streamlit Community Cloud (free, needs a GitHub repo; make it private, with
  invited viewers) or a small university server.
- **Data:** commit a fresh `sessions.json` weekly. Hide the scrape buttons.
- **Per-user state:** keep `people.txt` and `my_sessions.txt` in the browser session only,
  never on the server's disk. Users save their work with **Download my files** and restore
  it with **Upload my files**. Optional later: a login plus small storage so their lists persist.
- **Effort:** about a day of changes (checklist below). Low risk.
- **Tradeoff:** people lists pass through the server. That's acceptable for a lab, and less so for strangers.

### 2. Runs entirely in the browser (stlite / Pyodide)
The same Streamlit app compiled to WebAssembly and served as static files (e.g. GitHub Pages).
Nothing leaves the user's device.
- **Solver:** `highspy` may not be available in Pyodide, but `scipy.optimize.milp`, which
  uses HiGHS internally, is. `core/mip.py` would need a third, scipy-based backend.
- **Effort:** 2–4 days, and **needs a short trial first** to confirm the packages load and
  the model solves fast enough in the browser.
- **Tradeoff:** best for privacy, and it costs nothing to host. Slower first load (~10–20 s).

### 3. Double-click desktop app
Bundle Python and the app into a Mac/Windows app (PyInstaller or Briefcase) that opens the
UI in the user's browser.
- **Effort:** 2–3 days, plus ongoing upkeep.
- **Tradeoffs:** the bundle is about 200–400 MB. A Mac release needs Apple signing and
  notarization (a $99/yr developer account), or users get scary warnings. Each update
  means re-sending the app.

### 4. Middle ground for a lab: a launcher script
Ship the folder plus `Start Planner.command`, which installs dependencies on first run and
opens the app. It's cheap, but still fragile: macOS security prompts, missing Python, and
so on. It's fine for colleagues you can help in person.

## Code changes for option 1 (checklist)
- [ ] `ui/actions.do_build`: stop writing `people.txt` / `my_sessions.txt` / outputs to disk;
      keep them in `st.session_state` only.
- [ ] Add **Download my files** (a zip of `people.txt` + `my_sessions.txt`) and **Upload my files**.
- [ ] Default the solver to HiGHS and hide the Gurobi option when `gurobipy` is missing.
- [ ] Hide the sidebar scrape buttons. Show "Program updated <date>" from the shipped `sessions.json`.
- [ ] Start new users with an empty `people.txt` (just the format comment) and an empty
      `my_sessions.txt`, not your lists.
- [ ] Remove personal files from the repo: `people.txt`, `my_sessions.txt`, `itinerary.*`, `calendar/`.
- [ ] Turn off the Deploy button and footer: `.streamlit/config.toml` → `[client] toolbarMode = "minimal"`.
- [ ] Add a short "How to use" box at the top of the app: add names → Build → pick overlaps →
      download the phone calendar and phone page.

## Recommendation
For your lab, go with **option 1** (private Streamlit Cloud app, shipped `sessions.json`, HiGHS,
session-only data). If privacy or hosting becomes a concern, try **option 2** next. Its
browser-only design is the best long-term fit, but it needs a short trial first.
