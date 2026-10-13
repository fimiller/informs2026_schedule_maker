"""Paths, conference structure (blocks, events, optional meal slots) and model constants."""
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent  # project folder
PEOPLE = HERE / "people.txt"
MY_SESSIONS = HERE / "my_sessions.txt"
SESSIONS = HERE / "sessions.json"
OUT = HERE / "itinerary.md"
ICS_OUT = HERE / "itinerary.ics"
ICS_DIR = HERE / "calendar"  # one .ics per event, for drag-and-drop into Outlook
HTML_OUT = HERE / "itinerary.html"  # phone-friendly, offline, self-contained
PDF_OUT = HERE / "itinerary.pdf"  # week calendar on one page (build.py --pdf)
EXAMPLE_DIR = HERE / "example"

DAYS = ["Sat", "Sun", "Mon", "Tue", "Wed"]

DAY_LONG = {"Sat": "Saturday, Oct 31", "Sun": "Sunday, Nov 1", "Mon": "Monday, Nov 2",
            "Tue": "Tuesday, Nov 3", "Wed": "Wednesday, Nov 4"}

BLOCKS = [  # (day, code, start, end)
    ("Sun", "SA", "08:00", "09:15"), ("Sun", "SB", "11:00", "12:15"), ("Sun", "SC", "13:15", "14:30"),
    ("Sun", "SD", "14:45", "16:00"), ("Sun", "SE", "16:15", "17:30"),
    ("Mon", "MA", "08:00", "09:15"), ("Mon", "MB", "11:00", "12:15"), ("Mon", "MC", "13:15", "14:30"),
    ("Mon", "MD", "14:45", "16:00"), ("Mon", "ME", "16:15", "17:30"),
    ("Tue", "TA", "08:00", "09:15"), ("Tue", "TB", "11:00", "12:15"), ("Tue", "TC", "13:15", "14:30"),
    ("Tue", "TD", "14:45", "16:00"), ("Tue", "TE", "16:15", "17:30"),
    ("Wed", "WA", "08:00", "09:15"), ("Wed", "WB", "09:30", "10:45"),
]

FIXED_EVENTS = [  # shown for context, not schedulable
    ("Sun", "18:30", "20:30", "Welcome reception"),
    ("Mon", "18:45", "20:45", "Community receptions"),
    ("Tue", "18:45", "20:45", "Community receptions"),
    ("Wed", "11:00", "12:00", "Closing plenary"),
]

# Meal slots the planner could suggest. Off by default (SUGGEST_MEALS = False): every meal or
# coffee is an invitation you make yourself, so it only appears once it's in my_sessions.txt as
# a busy block (e.g. "Coffee - Tue 9:30am - Name"). Anyone without a talk you attend or a busy
# block shows up under "People not yet met". Set SUGGEST_MEALS = True to have the model propose
# breakfast/coffee slots again.
SUGGEST_MEALS = False

MEAL_SLOTS = [
    ("Sun-coffee-pm", "coffee", "Sun", "14:30", "14:45", ""),
    ("Mon-breakfast", "breakfast", "Mon", "07:00", "08:00", ""),
    ("Mon-coffee-am", "coffee", "Mon", "09:15", "09:45", ""),
    ("Mon-coffee-pm", "coffee", "Mon", "14:30", "14:45", ""),
    ("Tue-breakfast", "breakfast", "Tue", "07:00", "08:00", ""),
    ("Tue-coffee-am", "coffee", "Tue", "09:15", "09:45", ""),
    ("Tue-coffee-pm", "coffee", "Tue", "14:30", "14:45", ""),
    ("Wed-breakfast", "breakfast", "Wed", "07:00", "08:00", ""),
    ("Wed-coffee", "coffee", "Wed", "10:45", "11:00", ""),
]

MEALS = MEAL_SLOTS if SUGGEST_MEALS else []

MEAL_KINDS_BY_TIER = {1: {"breakfast", "coffee"}, 2: {"breakfast", "coffee"}, 3: {"breakfast", "coffee"}}

GROUP_MAX = {"breakfast": 3, "coffee": 3}

# Priorities are lexicographic stages (required > tier 1 > tier 2 > tier 3; see solve()).
# These small weights only act inside the last stage, as tie-breaks.
W_FIND = {1: 0.03, 2: 0.02, 3: 0.01}  # attend a session where they're only co-author/chair

W_SLOT = 0.001  # cost per meal slot used (mild preference for grouping -> more free time)

W_SAMEDAY = 0.0005  # meet presenters on a day they are certainly at the meeting

W_ORDER = 4e-6  # canonical tie-break between equally good meal assignments

PRESENT_ROLES = {"presenter", "panelist", "moderator"}

FIND_ROLES = {"co-author", "chair"}
