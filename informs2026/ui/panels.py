"""Schedule-tab panels: overlap pickers, Resolve VERIFY, People not yet met, downloads."""

import streamlit as st

from core import config, ics, inputs, phone_html, timefmt
from ui.calendar import DAY_END, DAY_START, PX, calendar_html


AUTO, SKIP = "__auto__", "__skip__"


def parse_my(text):
    """-> {CODE: 'pick'|'skip'} from my_sessions text."""
    out = {}
    for raw in text.splitlines():
        toks = raw.split("#")[0].split()
        if toks:
            code = toks[0].upper()
            out[code.lstrip("-")] = "skip" if code.startswith("-") else "pick"
    return out


def group_state(group, my):
    codes = [o["id"].upper() for o in group["options"]]
    picked = [c for c in codes if my.get(c) == "pick"]
    if picked:
        return picked[0]
    if codes and all(my.get(c) == "skip" for c in codes):
        return SKIP
    return AUTO


def on_pick(group_key):
    group = next(g for g in st.session_state["sched"]["groups"] if g["key"] == group_key)
    choice = st.session_state[f"pick_{group_key}"]
    codes = {o["id"].upper() for o in group["options"]}
    keep = [ln for ln in st.session_state["my_text"].splitlines()
            if not ln.split("#")[0].split() or ln.split("#")[0].split()[0].upper().lstrip("-") not in codes]
    if choice == SKIP:
        keep += [f"-{c}" for c in sorted(codes)]
    elif choice != AUTO:
        keep.append(choice)
    text = "\n".join(keep).strip()
    st.session_state["my_text"] = text + "\n" if text else ""
    st.session_state["rebuild"] = True


NONE = "__none__"


def render_verify(sched):
    """Resolve ambiguous names by writing the affiliation into people.txt, then rebuild."""
    items = sched.get("verify", [])
    st.subheader(f"Resolve VERIFY ({len(items)} left)")
    if not items:
        st.success("Nothing to verify: every name matched a single person.")
        return
    st.caption("Pick which person you mean. Apply writes the affiliation as the 4th field of their "
               "line in people.txt and rebuilds. Repeat until this list is empty.")
    with st.form("verify_form"):
        choices = {}
        for v in items:
            line_no, line = people_line(v["name"])
            state = "scheduled from the confident matches; extras need a look" if v["scheduled"] else "not scheduled yet"
            st.markdown(f"**{v['name']}** [T{v['tier']}]: {v['reason']} ({state})  \n"
                        f"people.txt line {line_no}: `{line}`")
            opts = {o["affiliation"]: o for o in v["options"]}
            labels = {a: f"{a} ({len(o['appearances'])} appearance{'s' * (len(o['appearances']) != 1)})"
                      for a, o in opts.items()}
            labels.update({NONE: "None of these (they're not in the program)", AUTO: "Leave for now",
                           "__other__": "Other affiliation (type below)"})
            for a, o in opts.items():
                with st.expander(f"{a}: where this person appears"):
                    for ap in o["appearances"]:
                        st.markdown(f"- {ap}")
                    if len(o["variants"]) > 1:
                        st.caption("Also listed as: " + "; ".join(o["variants"]))
            if v["no_affiliation"]:
                st.caption("Listed without an affiliation (e.g. as chair): " + "; ".join(v["no_affiliation"]))
            choices[v["name"]] = (
                st.radio("Which one?", list(labels), format_func=labels.get, index=len(labels) - 2,
                         key=f"verify_{v['name']}", horizontal=False),
                st.text_input("Other affiliation", key=f"verify_other_{v['name']}",
                              placeholder="e.g. Northeastern University"))
            st.divider()
        st.session_state["verify_names"] = list(choices)
        st.form_submit_button("Apply and rebuild", type="primary", on_click=apply_verify)


def apply_verify():
    """Form callback (runs before the next script run, so it may edit the people.txt widget state)."""
    text, changed = st.session_state["people_text"], []
    for name in st.session_state.get("verify_names", []):
        choice = st.session_state.get(f"verify_{name}", AUTO)
        other = (st.session_state.get(f"verify_other_{name}") or "").strip()
        aff = {AUTO: None, NONE: "-", "__other__": other or None}.get(choice, choice)
        if aff:
            text, ln, old, new = inputs.set_affiliation(text, name, aff)
            changed.append(f"line {ln}: `{new}`")
    if changed:
        st.session_state["people_text"] = text
        st.session_state["rebuild"] = True
        st.session_state["verify_msg"] = "Updated people.txt " + "; ".join(changed)
    else:
        st.session_state["verify_msg"] = "Nothing selected in Resolve VERIFY."


def render_not_met(sched):
    items = sched.get("not_met", [])
    todo = [x for x in items if not x.get("seen")]
    seen = [x for x in items if x.get("seen")]
    st.subheader(f"People not yet met: reach out ({len(todo)})")
    if not items:
        st.success("Everyone on your list is covered by a talk you're attending or a busy block.")
        return
    st.caption("Your outreach list: not seen presenting at a session you're attending, and no busy block in "
               "my_sessions.txt yet. Once you've agreed a time, add it to my_sessions.txt "
               "(e.g. `Coffee - Tue 3pm - Name`) and they drop off this list.")

    def show(nm):
        aff = f", {nm['affiliation']}" if nm["affiliation"] else ""
        note = f" | *{nm['note']}*" if nm["note"] else ""
        st.markdown(f"#### {nm['name']} [T{nm['tier']}{aff}]{note}\n" + "".join(f"\n- {a}" for a in nm["actions"]))

    for nm in todo:
        show(nm)
    if seen:
        st.markdown("##### Tier 1 you'll see present: a talk may not be enough time, consider inviting too")
        for nm in seen:
            show(nm)


def people_line(name):
    for n, raw in enumerate(st.session_state["people_text"].splitlines(), 1):
        if raw.strip() and not raw.strip().startswith("#") and raw.split("|")[0].strip() == name:
            return n, raw.strip()
    return "?", name


def option_label(ev):
    ppl = ", ".join(f'{p["name"]} [T{p["tier"]}]' + ("" if p["presenting"] else " (find)") for p in ev["people"])
    mark = "  <- optimizer's pick" if ev["chosen"] and not ev.get("pinned") else ""
    return f'{ev["id"]} {timefmt.fmt(ev["s"])}-{timefmt.fmt(ev["e"])}: {ev["title"]} | {ppl or "your pick"}{mark}'


def render_pickers(sched):
    my = parse_my(st.session_state["my_text"])
    groups = [g for g in sched["groups"] if len(g["options"]) > 1 and not any(o.get("mine") for o in g["options"])]
    if not groups:
        st.info("No overlapping options: every session with someone on your list fits.")
        return
    st.subheader("Overlaps - pick what you'll attend")
    st.caption("Choosing here writes to my_sessions.txt and rebuilds (meals adjust for talks you give up).")
    for g in groups:
        key = f"pick_{g['key']}"
        st.session_state[key] = group_state(g, my)
        labels = {o["id"].upper(): option_label(o) for o in g["options"]}
        labels[AUTO] = "Let the optimizer decide"
        labels[SKIP] = "Skip all of these (keep the block free)"
        title = f"{config.DAY_LONG[g['day']]} {timefmt.fmt(g['s'])}-{timefmt.fmt(g['e'])}" + (
            f" ({g['block']})" if g["block"] else "")
        st.radio(title, list(labels), format_func=labels.get, key=key,
                 on_change=on_pick, args=(g["key"],))


def outlook_downloads(sched, key):
    fixed = st.checkbox("Include conference events (receptions, closing plenary)", key=f"fixed_{key}")
    vevents = ics.ics_events(sched, include_fixed=fixed)
    ics_text = ics.ics_calendar(vevents)

    st.markdown("**Phone calendar**")
    st.download_button(f"Phone calendar: {len(vevents)} events (.ics)", ics_text, file_name="informs2026_phone.ics",
                       mime="text/calendar", key=f"phone_{key}", type="primary")
    st.caption(
        "**iPhone:** AirDrop the file to your phone (or email it to yourself), tap it, then **Add All** and "
        "pick a calendar. Both alerts work (15 minutes before and at the start). **Android:** open Google "
        "Calendar on the web > Settings > **Import & export** > Import, choose the file; it syncs to the phone. "
        "If your phone already shows your Outlook calendar, import into only one of them or every event "
        "appears twice. Re-importing updates events instead of duplicating them.")

    st.markdown("**Phone page**")
    page = sched.get("html") or phone_html.itinerary_html(sched, sched.get("scraped_at", ""))  # older cached results
    st.download_button("Phone page (.html)", page, file_name="informs2026_itinerary.html",
                       mime="text/html", key=f"html_{key}", type="primary")
    st.caption("One self-contained page laid out for a phone: day-by-day sessions with rooms and talk titles, "
               "your busy blocks, and your outreach list. Works offline (no internet needed in the convention "
               "center). Tap **Auto / Light / Dark** at the top to pick a theme (Auto follows the phone). "
               "**iPhone:** AirDrop it and open it in Safari (the Files preview can't switch themes). "
               "**Android:** email it to yourself and open it. Rebuild and resend after changes.")

    st.markdown("**Outlook**")
    c1, c2 = st.columns(2)
    c1.download_button(f"All {len(vevents)} events (.ics)", ics_text,
                       file_name="informs2026.ics", mime="text/calendar", key=f"ics_{key}")
    c2.download_button("One file per event (.zip)", ics.ics_zip(vevents),
                       file_name="informs2026_events.zip", mime="application/zip", key=f"zip_{key}")
    st.caption(
        "**Outlook desktop:** open the .ics (double-click, or File > Open & Export > Import), or unzip "
        "and drag single-event files onto your calendar. **Outlook on the web:** Calendar > Add calendar > "
        "Upload from file. Times are San Francisco time. "
        "Each event has a reminder 15 minutes before and an alert at the start (Outlook keeps only the "
        "15-minute one; Apple and Google Calendar use both). No invitations are sent. Re-importing updates "
        "events instead of duplicating them. "
        f"The same files are written to `{config.ICS_OUT.name}` and `{config.ICS_DIR.name}/` on every build.")


def schedule_view(sched, pickers):
    for d in sched.get("dropped", []):
        st.warning(f"Required item didn't fit: my_sessions.txt line {d['line']}: {d['item']} ({d['why']}). "
                   "The line higher in the file wins; reorder or remove lines to change this.")
    st.iframe(calendar_html(sched), height=int((DAY_END - DAY_START) * PX) + 90)
    if pickers:
        render_pickers(sched)
        render_verify(sched)
        render_not_met(sched)
    else:
        groups = [g for g in sched["groups"] if len(g["options"]) > 1]
        if groups:
            st.markdown("**Overlapping options** (in your own Schedule tab, each of these gets a picker)")
            for g in groups:
                opts = "; ".join(option_label(o) for o in g["options"])
                st.markdown(f"- {config.DAY_LONG[g['day']]} {g['block'] or ''}: {opts}")
        render_not_met(sched)
