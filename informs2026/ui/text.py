"""Plain-English description of the assignment rules (sidebar)."""




RULES_TEXT = """
**How your schedule is built**

1. **Required first.** Everything in `my_sessions.txt` is scheduled before anything else: sessions
   you picked (your own session included) and busy blocks such as coffees you've already arranged.
   If two required items overlap, the line higher in the file wins and the other is listed as
   "didn't fit".
2. **Then tier 1, then tier 2, then tier 3.** Within each tier the planner tries to see every
   person present (go to their talk); anyone it can't fit goes on your outreach list. A lower tier
   never displaces a higher one.
3. **No meals are assumed.** Every coffee, breakfast, lunch or dinner is an invitation you make.
   It appears on your schedule only once you add it to my_sessions.txt as a busy block (e.g.
   `Coffee - Tue 9:30am - Name`). Someone you have a busy block with counts as met.
4. **Who to invite:** people not in the program (email first), people whose talk you can't attend
   because of a clash, people listed only as co-author or chair, and tier-1 people even if you'll
   see their talk (a talk alone isn't much time). These are all in "People not yet met".
5. **Co-authors and chairs** aren't guaranteed to be in the room, so those sessions are marked "find
   at session". They're attended only when nothing more important is in that block.
6. **Free blocks** stay free so you can add sessions yourself.
7. **People not yet met** is your outreach list: everyone you won't automatically see, with the
   action in bold: **Invite**, **Email first**, **Catch them** around a clashing talk, or **Look for
   them** at a session where they're a co-author or chair.
"""
