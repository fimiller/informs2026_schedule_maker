"""Streamlit front end for the INFORMS 2026 itinerary builder.

Run:  .venv/bin/streamlit run app.py
(Scrape from the terminal with:  .venv/bin/python scrape.py)
"""

import streamlit as st

from core import config, mip
from ui.actions import code_version, do_build, example_build, program_status, run_scrape
from ui.panels import outlook_downloads, schedule_view
from ui.text import RULES_TEXT


st.set_page_config(page_title="INFORMS 2026 Itinerary", layout="wide")

st.markdown("<style>.katex-display { overflow-x: auto; overflow-y: hidden; padding: 2px 0; }</style>",
            unsafe_allow_html=True)  # wide equations scroll instead of being clipped (sidebar)

st.title("INFORMS Annual Meeting 2026 - Itinerary Builder")

st.radio("Solver", list(mip.SOLVERS), format_func=mip.SOLVERS.get, horizontal=True, key="solver",
         on_change=lambda: st.session_state.update(rebuild=True),
         help="Both solve the same MIP to proven optimality (see 'Optimization model' in the sidebar). Gurobi needs a license; "
              "HiGHS is open source.")

with st.sidebar:
    with st.expander("How the schedule is built", expanded=False):
        st.markdown(RULES_TEXT)
    with st.expander("Optimization model (math)", expanded=False):
        if "sched" in st.session_state:
            st.caption("Last solve")
            st.table({k: [str(v)] for k, v in st.session_state["sched"]["stats"].items()})
        st.markdown((config.HERE / "MODEL.md").read_text())
    st.header("Program data")
    status = program_status()
    if status is None:
        st.warning("No sessions.json yet. Run the scraper in a terminal:\n\n"
                   "`.venv/bin/python scrape.py`")
    else:
        ts, age, n_s, n_t = status
        st.write(f"**{n_s}** sessions, **{n_t}** talks")
        st.write(f"Scraped {ts.astimezone().strftime('%b %d %H:%M')} ({age.days}d {age.seconds // 3600}h ago)")
        if age.days >= 7:
            st.warning("Older than 7 days; the program may have changed. "
                       "Re-scrape with `.venv/bin/python scrape.py`.")
    with st.expander("Scrape from here instead (slow; keep this tab open)"):
        st.caption("The terminal is more reliable for a long scrape. Don't run two at once.")
        c1, c2 = st.columns(2)
        if c1.button("Scrape if stale"):
            run_scrape(force=False)
            st.rerun()
        if c2.button("Force re-scrape", help="Deletes the page cache and re-downloads everything"):
            run_scrape(force=True)
            st.rerun()
    st.caption("Anyone can share their sessions.json so others skip the scrape:")
    up = st.file_uploader("sessions.json", type="json", label_visibility="collapsed")
    if up is not None and st.button("Use uploaded sessions.json"):
        config.SESSIONS.write_bytes(up.getvalue())
        st.success("Saved.")
        st.rerun()

if "people_text" not in st.session_state:
    st.session_state["people_text"] = config.PEOPLE.read_text() if config.PEOPLE.exists() else ""

if "my_text" not in st.session_state:
    st.session_state["my_text"] = config.MY_SESSIONS.read_text() if config.MY_SESSIONS.exists() else ""

if "pending_my_text" in st.session_state:
    st.session_state["my_text"] = st.session_state.pop("pending_my_text")

with st.expander("Inputs: people.txt and my_sessions.txt", expanded="sched" not in st.session_state):
    left, right = st.columns([3, 2])
    with left:
        st.caption("`Name | tier | note | affiliation`; tier 1 must see, 2 want to see (default), "
                   "3 if convenient. Lines starting with # are ignored.")
        uploaded = st.file_uploader("Load a people.txt", type="txt")
        if uploaded is not None and st.session_state.get("uploaded_id") != uploaded.file_id:
            st.session_state["uploaded_id"] = uploaded.file_id
            st.session_state["people_text"] = uploaded.getvalue().decode("utf-8")
        st.text_area("people.txt", key="people_text", height=320)
    with right:
        st.caption("One per line: a session code to attend (`TC27`), one to skip (`-TC27`), or a busy "
                   "block for meetings you've already set up (`Coffee - Tue 10am - Jane Smith`, "
                   "`Lunch - Mon 12:15-13:00 - Name`). Busy blocks keep that time free; if the person is "
                   "in people.txt they count as already met. The Schedule tab's pickers edit this for you.")
        st.text_area("my_sessions.txt", key="my_text", height=150)
        st.checkbox("Save to people.txt / my_sessions.txt when building", value=True, key="save")

ready = program_status() is not None

if "verify_msg" in st.session_state:
    st.success(st.session_state.pop("verify_msg"))

if st.button("Build itinerary", type="primary", disabled=not ready) or (
        ready and (st.session_state.pop("rebuild", False) or "sched" not in st.session_state)):
    do_build()
elif "build_label" in st.session_state:
    st.success(st.session_state["build_label"], icon="✅")


tab_cal, tab_md, tab_raw, tab_ex = st.tabs(["Schedule", "Itinerary", "Plain text", "Example"])

have = "sched" in st.session_state

if have:
    md, sched = st.session_state["itinerary"], st.session_state["sched"]

for tab in (tab_cal, tab_md, tab_raw) if not have else ():
    tab.info("No itinerary yet. Scrape the program (`.venv/bin/python scrape.py`), then click "
             "Build itinerary. The Example tab shows what you'll get.")

if have:
    with tab_cal:
        schedule_view(sched, pickers=True)
        st.divider()
        outlook_downloads(sched, "mine")
    with tab_md:
        st.download_button("Download itinerary.md", md, file_name="itinerary.md")
        st.markdown(md)
    with tab_raw:
        st.code(md, language=None)

with tab_ex:
    st.markdown(
        "An example run on a **snapshot of part of the program** with a made-up people list and "
        "my_sessions.txt. It uses the same matching, model and output as your own schedule.\n\n"
        "- **people.txt:** all three tiers; a tier-1 person you'll see present, a co-author-only person, "
        "and someone not in the program; a person with two talks; a nickname (Dan = Daniel) and an "
        "accent (Jelic = Jelić); one affiliation written two ways; a common name sent to VERIFY; an "
        "affiliation pin that picks one of two people with the same name; and `-` for a namesake who "
        "isn't your person.\n"
        "- **my_sessions.txt:** your own session (`mine`, amber), a pick that beats tier-2 and tier-3 "
        "talks, a skip (`-SB12`), busy blocks that count as meeting someone (one with a person who isn't "
        "in the program), a busy block with no one named, and a pick dropped because it clashes with "
        "a line higher in the file. The build adds the `# why` comments.")
    ex_people = (config.EXAMPLE_DIR / "people.txt").read_text()
    ex_my = (config.EXAMPLE_DIR / "my_sessions.txt").read_text()
    try:
        ex_md, ex_sched = example_build(ex_people, ex_my, st.session_state["solver"], version=code_version())
    except RuntimeError as e:
        st.error(str(e))
        st.stop()
    with st.expander("Example people.txt"):
        st.code(ex_people, language=None)
    with st.expander("Example my_sessions.txt (after the build adds comments)"):
        st.code(ex_sched["my_sessions_annotated"], language=None)
    schedule_view(ex_sched, pickers=False)
    with st.expander("Example itinerary (text)"):
        st.markdown(ex_md)
    outlook_downloads(ex_sched, "example")
