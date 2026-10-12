"""Side-effecting app actions: program status, running the scraper, building the itinerary."""

import json
import subprocess
import sys
from datetime import datetime, timezone

import streamlit as st

import build
from core import config, ics


def program_status():
    if not config.SESSIONS.exists():
        return None
    data = json.loads(config.SESSIONS.read_text())
    ts = datetime.fromisoformat(data["scraped_at"])
    age = datetime.now(timezone.utc) - ts
    n_talks = sum(len(s["talks"]) for s in data["sessions"])
    return ts, age, len(data["sessions"]), n_talks


def run_scrape(force):
    """Run scrape.py as a subprocess and stream its progress lines into the page."""
    cmd = [sys.executable, "-u", str(config.HERE / "scrape.py")] + (["--force"] if force else [])
    with st.status("Scraping the program (about an hour for a full scrape)...", expanded=True) as box:
        last = st.empty()
        lines = []
        proc = subprocess.Popen(cmd, cwd=config.HERE, stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT, text=True, bufsize=1)
        for line in proc.stdout:
            lines.append(line.rstrip())
            last.code("\n".join(lines[-15:]))
        proc.wait()
        if proc.returncode == 0:
            box.update(label="Scrape finished", state="complete", expanded=False)
        else:
            box.update(label=f"Scrape failed (exit {proc.returncode})", state="error")


def do_build():
    people_text, my_text = st.session_state["people_text"], st.session_state["my_text"]
    if st.session_state.get("save", True):
        config.PEOPLE.write_text(people_text)
        config.MY_SESSIONS.write_text(my_text)
    with st.status("Building itinerary...", expanded=False) as box:
        try:
            md, _, sched = build.build_itinerary(people_text, my_text, log=st.write,
                                                 solver=st.session_state["solver"])
        except (ValueError, RuntimeError) as e:
            box.update(label="Build failed", state="error", expanded=True)
            st.error(str(e))
            return
        stt = sched["stats"]
        label = (f"Itinerary built with {stt['solver']}: {stt['status']} in {stt['solve time (s)']}s "
                 f"({stt['binary variables']} binaries, {stt['constraints']} constraints, "
                 f"{stt['stages']} priority stages; required kept {stt['required kept']})")
        st.session_state["build_label"] = label
        box.update(label=label, state="complete")
    config.OUT.write_text(md)
    ics.write_calendar_files(sched)
    config.HTML_OUT.write_text(sched["html"])
    st.session_state["itinerary"], st.session_state["sched"] = md, sched
    annotated = sched["my_sessions_annotated"]
    if annotated != my_text:  # add '# why' comments; shown in the text box on the rerun
        if st.session_state.get("save", True):
            config.MY_SESSIONS.write_text(annotated)
        st.session_state["pending_my_text"] = annotated
        st.rerun()


def code_version():
    """Changes whenever a source file changes, so cached example results never go stale."""
    return max(f.stat().st_mtime for d in ("", "core", "ui") for f in (config.HERE / d).glob("*.py"))


@st.cache_data(show_spinner="Building the example...")
def example_build(people_text, my_text, solver, version=0.0):
    md, _, sched = build.build_itinerary(people_text, my_text, config.EXAMPLE_DIR / "sessions.json",
                                         log=lambda m: None, solver=solver)
    return md, sched
