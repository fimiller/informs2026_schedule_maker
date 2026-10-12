"""Find each person's appearances in the program; decide found / missing / VERIFY."""

from .names import cluster_affs, fold, match_name, same_aff
from .timefmt import t12


def find_occurrences(person, sessions):
    occ = []
    for s in sessions.values():
        for role, names in (("chair", s["chairs"]), ("panelist", s.get("panelists", [])),
                            ("moderator", s.get("moderators", []))):
            for nm in names:
                m = match_name(person["name"], nm)
                if m:
                    occ.append({"evt": s["evt"], "role": role, "talk": None, "aff": "",
                                "as": nm, "quality": m[0], "why": m[1]})
        for ti, t in enumerate(s["talks"]):
            for a in t["authors"]:
                m = match_name(person["name"], a["name"])
                if m:
                    occ.append({"evt": s["evt"], "role": "presenter" if a["presenter"] else "co-author",
                                "talk": ti, "aff": a["affiliation"], "as": a["name"],
                                "quality": m[0], "why": m[1]})
    return occ


def resolve(person, sessions):
    """Sets person['status'] in {'found','missing','verify'} and person['occ'] (trusted)."""
    occ = find_occurrences(person, sessions)
    person["verify"] = []
    if person["pin"] == "-":  # resolved as "none of these people is mine"
        person["occ"], person["status"], person["dropped"], person["affs"] = [], "missing", occ, []
        return
    if person["pin"]:
        pin_ok = lambda o: o["aff"] and (same_aff(o["aff"], person["pin"])
                                         or fold(person["pin"]) in fold(o["aff"]))
        kept = [o for o in occ if pin_ok(o) or (not o["aff"] and o["quality"] == "strong")]
        person["occ"] = kept
        person["status"] = "found" if kept else "missing"
        person["dropped"] = [o for o in occ if o not in kept]
        person["affs"] = sorted({o["aff"] for o in kept if o["aff"]}) or [person["pin"]]
        return
    strong = [o for o in occ if o["quality"] == "strong"]
    loose = [o for o in occ if o["quality"] == "loose"]
    clusters = cluster_affs(sorted({o["aff"] for o in strong if o["aff"]}))
    if len(clusters) > 1:
        person["status"], person["occ"], person["verify"] = "verify", [], occ
        person["verify_reason"] = f"{len(clusters)} different affiliations for this name"
    elif strong:
        home = clusters[0] if clusters else []
        absorbed = [o for o in loose if home and o["aff"] and any(same_aff(o["aff"], h) for h in home)]
        person["status"], person["occ"] = "found", strong + absorbed
        person["verify"] = [o for o in loose if o not in absorbed]
        person["verify_reason"] = "possible extra appearances under a variant name"
    elif loose:
        person["status"], person["occ"], person["verify"] = "verify", [], loose
        person["verify_reason"] = "only variant-name matches"
    else:
        person["status"], person["occ"] = "missing", []
    person["affs"] = sorted({o["aff"] for o in person["occ"] if o["aff"]})
    person["dropped"] = []


def verify_data(people, sessions):
    """VERIFY entries for the app's resolver: candidate affiliations with their appearances."""
    out = []
    for p in people:
        if not p["verify"]:
            continue
        occ = p["verify"] + ([o for o in p["occ"] if o not in p["verify"]] if p["status"] == "found" else [])
        clusters = cluster_affs(sorted({o["aff"] for o in occ if o["aff"]}))
        options = []
        for cl in clusters:
            hits = [o for o in occ if o["aff"] and any(same_aff(o["aff"], c) for c in cl)]
            label = max(cl, key=lambda a: (sum(o["aff"] == a for o in hits), -len(a)))
            options.append({"affiliation": label, "variants": cl, "appearances": [appearance(o, sessions) for o in hits]})
        no_aff = [appearance(o, sessions) for o in occ if not o["aff"]]
        out.append({"name": p["name"], "tier": p["tier"], "reason": p.get("verify_reason", ""),
                    "scheduled": p["status"] == "found", "options": options, "no_affiliation": no_aff})
    return out


def appearance(o, sessions):
    s = sessions[o["evt"]]
    what = s["talks"][o["talk"]]["title"] if o["talk"] is not None else s["title"]
    extra = f" [{o['why']}]" if o["why"] else ""
    return f"{o['as']}: {o['role']} in {s['id']} ({s['day']} {t12(s['start'])}, {s['room'] or 'room TBA'}): \"{what}\"{extra}"
