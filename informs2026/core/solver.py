"""The scheduling MIP (lexicographic: required > tier 1 > tier 2 > tier 3). See MODEL.md."""

from collections import defaultdict

from .config import DAYS, FIND_ROLES, GROUP_MAX, MEALS, MEAL_KINDS_BY_TIER, PRESENT_ROLES, W_FIND, W_ORDER, W_SAMEDAY, W_SLOT
from .mip import Expr, Model, qsum
from .names import fold, match_name, same_aff
from .timefmt import hm, overlaps


def solve(people, sessions, my_picks, skips=frozenset(), solver="gurobi", busy=(), meta=None):
    meta = meta or {"line": {}, "mine": set()}
    act = [p for p in people if p["status"] in ("found", "missing")]
    for p in act:
        p["present_evts"] = sorted({o["evt"] for o in p["occ"] if o["role"] in PRESENT_ROLES})
        p["find_evts"] = sorted({o["evt"] for o in p["occ"] if o["role"] in FIND_ROLES}
                                - set(p["present_evts"]))
        p["own"] = [sessions[e] for e in set(p["present_evts"]) | set(p["find_evts"])]
        p["days"] = {sessions[e]["day"] for e in p["present_evts"]}
        p["met"] = next((b for b in busy if b["who"] and match_name(p["name"], b["who"])), None)
        if p["status"] == "missing":
            p["need_reason"] = "not in the program (may still attend; email first)"
        elif not p["present_evts"]:
            p["need_reason"] = "only listed as " + "/".join(sorted({o["role"] for o in p["occ"]}))
        elif p["tier"] == 1:
            p["need_reason"] = "tier 1: a talk alone is not enough time"
        else:
            p["need_reason"] = None  # only if their talk is lost to a conflict

    cand = sorted({e for p in act for e in p["present_evts"] + p["find_evts"]} | set(my_picks))
    meals = [dict(id=m[0], kind=m[1], day=m[2], s=hm(m[3]), e=hm(m[4]), note=m[5]) for m in MEALS]

    mdl = Model()
    y = {e: mdl.var() for e in cand}
    for e in skips:
        if e in y and e not in my_picks:
            mdl.fix(y[e], ub=0)
    # Busy blocks are required too, but soft: kb[j] = 1 keeps block j.
    kb = {j: mdl.var() for j in range(len(busy))}
    for j, b in enumerate(busy):
        for e in cand:
            if overlaps(b, sessions[e]):
                mdl.add(kb[j] + y[e] <= 1)
        for j2 in range(j + 1, len(busy)):
            if overlaps(b, busy[j2]):
                mdl.add(kb[j] + kb[j2] <= 1)
    # One session at a time: interval-graph cliques occur at session start times.
    for day in DAYS:
        ds = [sessions[e] for e in cand if sessions[e]["day"] == day]
        for pt in sorted({s["s"] for s in ds}):
            clique = [s["evt"] for s in ds if s["s"] <= pt < s["e"]]
            if len(clique) > 1:
                mdl.add(qsum(y[e] for e in clique) <= 1)

    t, need, unmet, m = {}, {}, {}, {}
    for i, p in enumerate(act):
        if p["present_evts"]:
            t[i] = mdl.var()
            mdl.add(t[i] <= qsum(y[e] for e in p["present_evts"]))
        base = Expr.of(1) if p["need_reason"] else Expr.of(0) if i not in t else 1 - t[i]
        if p["met"] is not None:
            # Already meeting them in a busy block; if that block is dropped they need a meal again.
            if p["status"] == "missing" or not p["present_evts"] or p["tier"] == 1:
                base = Expr.of(1)
            need[i] = mdl.var(binary=False)
            mdl.add(need[i] >= base - kb[busy.index(p["met"])])
            mdl.add(need[i] <= 1 - kb[busy.index(p["met"])])
        else:
            need[i] = base
        for k, ml in enumerate(meals):
            if ml["kind"] in MEAL_KINDS_BY_TIER[p["tier"]] and not any(overlaps(ml, s) for s in p["own"]):
                m[i, k] = mdl.var()
        got = qsum(m[i, k] for k in range(len(meals)) if (i, k) in m)
        mdl.add(got <= need[i])
        unmet[i] = mdl.var(binary=False)
        mdl.add(unmet[i] >= need[i] - got)

    z = {k: mdl.var() for k in range(len(meals))}
    for k, ml in enumerate(meals):
        for j, b in enumerate(busy):
            if overlaps(b, ml):
                mdl.add(z[k] + kb[j] <= 1)
    pairs_ok = {}
    for k, ml in enumerate(meals):
        here = [i for i in range(len(act)) if (i, k) in m]
        for i in here:
            mdl.add(m[i, k] <= z[k])
        mdl.add(qsum(m[i, k] for i in here) <= GROUP_MAX[ml["kind"]])
        for e in cand:  # can't eat while attending a session
            if overlaps(ml, sessions[e]):
                mdl.add(z[k] + y[e] <= 1)
        for a in range(len(here)):
            for b in range(a + 1, len(here)):
                i, j = here[a], here[b]
                if (i, j) not in pairs_ok:
                    pairs_ok[i, j] = group_reason(act[i], act[j], sessions)
                if not pairs_ok[i, j]:
                    mdl.add(m[i, k] + m[j, k] <= 1)

    # ---- objectives, highest priority first (lexicographic; see MODEL.md)
    # Stage 1: keep as many required items (my_sessions.txt picks + busy blocks) as possible;
    # among equal counts, prefer lines higher in the file (bonus total < 1, so count dominates).
    req = [(meta["line"].get(e, 0), y[e]) for e in my_picks] + [(b["line"], kb[j]) for j, b in enumerate(busy)]
    R = len(req) or 1
    ranked = sorted(req, key=lambda r: r[0])
    stage_req = qsum((1 + 0.5 * (R - r) / (R * R)) * v for r, (_, v) in enumerate(ranked))
    # Stages 2-4: each tier in turn. Seeing a talk counts 2, getting a needed meal counts 1.
    stage_tier = {tier: qsum(2 * t[i] for i in t if act[i]["tier"] == tier)
                  - qsum(unmet[i] for i in unmet if act[i]["tier"] == tier) for tier in (1, 2, 3)}
    # Last stage also carries the small tie-breaks.
    order = {i: r for r, i in enumerate(sorted(range(len(act)), key=lambda i: fold(act[i]["name"])))}
    ties = qsum(1e-4 * (len(act) - order[i]) / len(act) * t[i] for i in t)
    for e in cand:
        bonus = sum(W_FIND[p["tier"]] for p in act if e in p["find_evts"])
        if bonus:
            ties += bonus * y[e]
    ties -= W_SLOT * qsum(z.values())
    ties += W_SAMEDAY * qsum(v for (i, k), v in m.items() if meals[k]["day"] in act[i]["days"])
    # Meal tie-break: higher tier, then alphabetical, gets earlier slots. A product (not a sum)
    # of priority and earliness, so swapping two people between two slots changes the value.
    by_prio = sorted(range(len(act)), key=lambda i: (act[i]["tier"], fold(act[i]["name"])))
    by_time = sorted(range(len(meals)), key=lambda k: (DAYS.index(meals[k]["day"]), meals[k]["s"]))
    P, M = len(act) or 1, len(meals)
    prio = {i: P - a for a, i in enumerate(by_prio)}
    early = {k: M - b for b, k in enumerate(by_time)}
    ties += qsum(W_ORDER * prio[i] * early[k] / (P * M) * v for (i, k), v in m.items())
    x, stats = mdl.solve_lex([("required", stage_req), ("tier 1", stage_tier[1]), ("tier 2", stage_tier[2]),
                              ("tier 3 + tie-breaks", stage_tier[3] + ties)], solver)
    on = lambda v: x[v.idx] > 0.5

    kept_busy = [b for j, b in enumerate(busy) if on(kb[j])]
    dropped = []
    for e in my_picks:
        if not on(y[e]):
            s_ = sessions[e]
            why = next((f"overlaps {sessions[q]['id']} (line {meta['line'][q]})" for q in my_picks
                        if q != e and on(y[q]) and overlaps(s_, sessions[q])), None) or next(
                (f"overlaps busy '{b['raw']}' (line {b['line']})" for b in kept_busy if overlaps(s_, b)), "conflict")
            dropped.append({"line": meta["line"][e], "item": s_["id"], "why": why})
    for j, b in enumerate(busy):
        if not on(kb[j]):
            why = next((f"overlaps {sessions[q]['id']} (line {meta['line'][q]})" for q in my_picks
                        if on(y[q]) and overlaps(b, sessions[q])), None) or next(
                (f"overlaps busy '{b2['raw']}' (line {b2['line']})" for b2 in kept_busy if overlaps(b, b2)), "conflict")
            dropped.append({"line": b["line"], "item": b["raw"], "why": why})
    stats["required kept"] = f"{len(req) - len(dropped)}/{len(req)}"
    for p in act:
        if p["met"] is not None and p["met"] not in kept_busy:
            p["met"] = None
    attend = [e for e in cand if on(y[e])]
    for i, p in enumerate(act):
        p["seen_at_talk"] = i in t and on(t[i])
        p["needs_meal"] = need[i].value(x) > 0.5
        p["meal"] = next((meals[k]["id"] for k in range(len(meals)) if (i, k) in m and on(m[i, k])), None)
        if p["needs_meal"] and not p["need_reason"]:
            p["need_reason"] = "talk lost to a conflict"
    groups = defaultdict(list)
    for i, p in enumerate(act):
        if p["meal"]:
            groups[p["meal"]].append(p)
    return attend, meals, groups, stats, cand, {"dropped": dropped, "kept_busy": kept_busy}


def group_reason(p, q, sessions):
    """Why p and q may share a meal (shared paper / institution), or None."""
    def papers(x):
        return {(o["evt"], o["talk"]) for o in x["occ"] if o["talk"] is not None}
    shared = papers(p) & papers(q)
    if shared:
        evt, ti = sorted(shared)[0]
        return f"co-authors on \"{sessions[evt]['talks'][ti]['title']}\""
    for a in p["affs"]:
        for b in q["affs"]:
            if same_aff(a, b):
                return f"both at {a}"
    return None
