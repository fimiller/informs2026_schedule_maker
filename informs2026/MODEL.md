# Optimization model

`core/solver.py` (`solve()`) builds this binary integer program each time the itinerary is built. It solves it
with **Gurobi** (default) or **HiGHS**, whichever you choose at the top of the app or with
`build.py --solver highs`. The model is written once in `core/mip.py`, a small solver-neutral layer,
and passed to `gurobipy` or `highspy`. It decides which sessions to attend. Meal suggestions are
**off by default** (`SUGGEST_MEALS = False`): with no meal slots, every $m_{ik}$, $z_k$ and meal
constraint below drops out, $u_i = \mathrm{need}_i$, and anyone not covered by a talk or a busy block
goes on your outreach list instead. The meal parts are kept so suggestions can be switched back on.
People marked VERIFY are left out until you resolve them.

## Sets

| Symbol | Meaning |
|---|---|
| $P$ | people from `people.txt` who were found in the program or are missing from it |
| $T \subseteq P$ | people who present (presenter, panelist or moderator) somewhere |
| $\mathrm{Pres}_i$ | sessions where person $i$ presents |
| $\mathrm{Find}_i$ | sessions where $i$ is only a co-author or chair ("find at session") |
| $\mathrm{Own}_i = \mathrm{Pres}_i \cup \mathrm{Find}_i$ | sessions $i$ is in |
| $S = \bigcup_i \mathrm{Own}_i \cup S^+$ | candidate sessions |
| $S^+,\ S^-$ | sessions picked / skipped in `my_sessions.txt` (`TC27`, `TC27 mine` / `-TC27`) |
| $B$ | busy blocks in `my_sessions.txt` (`Coffee - Tue 9:30am - Name`) |
| $\mathcal{C}$ | overlap cliques: for each day and each start time $\tau$ of a candidate session, $C_\tau = \{s \in S : \mathrm{start}_s \le \tau < \mathrm{end}_s\}$ |
| $K$ | meal slots the model may suggest. **Empty by default** (`SUGGEST_MEALS = False` in `core/config.py`): every meal or coffee is an invitation you make and add as a busy block. Turning it on gives 9 slots (Mon-Wed breakfasts, 6 coffee breaks) |
| $K_i \subseteq K$ | slots allowed for $i$: any breakfast/coffee that doesn't overlap a session in $\mathrm{Own}_i$ (tier 1 gets first claim through the stage order) |
| $O_k \subseteq S$ | candidate sessions overlapping meal slot $k$ |
| $I$ | pairs $(i,j)$ who may **not** share a meal: no common paper and no matching affiliation |
| $N$ | people who need a meal no matter what: not in the program, only co-author/chair, or tier 1 |

## Decision variables

| Variable | Meaning |
|---|---|
| $y_s \in \{0,1\}$ | attend session $s \in S$ |
| $t_i \in \{0,1\}$ | see $i \in T$ present |
| $m_{ik} \in \{0,1\}$ | meet $i$ at meal slot $k \in K_i$ |
| $z_k \in \{0,1\}$ | meal slot $k$ is used |
| $u_i \in [0,1]$ | $i$ needs a meal but doesn't get one |
| $b_j \in \{0,1\}$ | keep busy block $j$ |

Define how much $i$ needs a meal:

$$
\mathrm{need}_i = \begin{cases} 1 & i \in N \\ 1 - t_i & i \in T \setminus N \end{cases}
$$

So a tier 2-3 presenter needs a meal only when their talk is lost to a conflict. For someone
named in busy block $j$, $\mathrm{need}_i$ becomes a variable with
$\mathrm{need}_i \ge \mathrm{base}_i - b_j$ and $\mathrm{need}_i \le 1 - b_j$: a kept busy block
counts as their meal, and if the block is dropped they need one again.

## Objective (lexicographic)

The schedule is chosen by four objectives in strict priority order. Each stage is solved to
proven optimality. Its optimum $f_j^\star$ is then locked in with
$f_j(x) \ge f_j^\star - 10^{-6}\max(1,|f_j^\star|)$ before the next stage runs.

**Stage 1: required items.** These are every line of `my_sessions.txt`: picks $S^+$ and busy blocks $B$.

$$
\max \textstyle\sum_{r} \big(1 + \epsilon_r\big)\, x_r, \quad \epsilon_r = \tfrac{R - \mathrm{rank}_r}{2R^2}
$$

The sum runs over $r \in S^+ \cup B$. Here $x_r$ is $y_s$ for a pick and $b_j$ (keep busy block $j$) for a busy block, and $\mathrm{rank}_r$ is the
line order. The most items are kept, and ties go to lines higher in the file.

**Stage 2: tier 1.** Seeing a talk is worth 2, a needed meal 1:

$$
\begin{aligned} \max\; & \textstyle\sum_{i \in T,\, \tau_i = 1} 2\,t_i \\ & -\; \textstyle\sum_{i \in P,\, \tau_i = 1} u_i \end{aligned}
$$

**Stage 3: tier 2.** The same with $\tau_i = 2$.

**Stage 4: tier 3 and tie-breaks.** The same with $\tau_i = 3$, plus

$$
\begin{aligned}
& \textstyle\sum_{s} w_s\, y_s \;-\; W^{\text{slot}} \sum_k z_k \\
& +\; W^{\text{same}} \textstyle\sum_{(i,k) \in D} m_{ik} \\
& +\; \tfrac{W^{\text{order}}}{|P|\,|K|} \textstyle\sum_{i,k} \pi_i \eta_k\, m_{ik} \\
& +\; \tfrac{10^{-4}}{|P|} \textstyle\sum_i \alpha_i t_i
\end{aligned}
$$

where $w_s = \sum_{i:\, s \in \mathrm{Find}_i} W^{\text{find}}_{\tau_i}$, and $D$ is the set of pairs where meal $k$ is on a day person $i$ presents.

| Weight | Value | Purpose |
|---|---|---|
| $W^{\text{find}}$ | 0.03 / 0.02 / 0.01 by tier | prefer sessions where co-authors/chairs might be |
| $W^{\text{slot}}$ | 0.001 | mild preference for grouping, which leaves more slots free |
| $W^{\text{same}}$ | 0.0005 | meet presenters on a day they're surely at the meeting |
| $W^{\text{order}}$ | 4e-6 | among equally good meal plans, earlier slots go to higher tier, then alphabetical ($\pi$ = priority rank, $\eta$ = slot earliness) |
| $10^{-4}\alpha_i$ | alphabetical | breaks exact ties between equal-tier presenters |

Because the stages are separate, one tier-1 person always outweighs any number of tier-2 people.
Required items always outweigh everything, and the model is always feasible: dropping every
required item is allowed, just maximally penalized.

## Constraints

One session at a time:
$$\sum_{s \in C} y_s \le 1 \qquad \forall C \in \mathcal{C}$$

Skips, and busy blocks against sessions, meals and each other:
$$y_s = 0 \quad s \in S^- \setminus S^+, \qquad b_j + y_s \le 1,\quad b_j + z_k \le 1,\quad b_j + b_{j'} \le 1 \quad \text{when they overlap}$$
(Picks $S^+$ are not forced; stage 1 maximizes them.)

You only see $i$ present if you attend one of their sessions:
$$t_i \le \sum_{s \in \mathrm{Pres}_i} y_s \qquad \forall i \in T$$

Meals only for people who need one; any shortfall is recorded:
$$\sum_{k \in K_i} m_{ik} \le \mathrm{need}_i, \qquad u_i \ge \mathrm{need}_i - \sum_{k \in K_i} m_{ik} \qquad \forall i \in P$$

Slot usage and group size (one group per slot):
$$m_{ik} \le z_k, \qquad \sum_{i} m_{ik} \le G_{\mathrm{kind}(k)} \qquad G = \{\text{breakfast}: 3,\ \text{coffee}: 3\}$$

No meal while you're in a session:
$$z_k + y_s \le 1 \qquad \forall k,\ s \in O_k$$

Only group people who share an institution or a paper:
$$m_{ik} + m_{jk} \le 1 \qquad \forall (i,j) \in I,\ k \in K_i \cap K_j$$

"Never meet someone during their own talk block" is enforced by leaving those slots out of $K_i$.

## Notes

- Required items (and meals, when enabled) are rewarded rather than forced, so the model is always
  feasible. Dropped required items appear under "Required items that didn't fit" in the itinerary
  and as warnings in the app.
- `explain_conflicts()` reconstructs the reason for each skipped talk.
- Both solvers run with a relative MIP gap of 0 (proven optimal). The tie-break weights in the last
  stage are tiny (down to $10^{-6}$), so the default 0.01% gap could silently ignore them.
- Gurobi and HiGHS return the same sessions and the same optimal stage values. With meal
  suggestions on, the meal plan can differ between them when two arrangements tie, because the
  $W^{\text{order}}$ differences (~$10^{-8}$) are at HiGHS's numerical tolerance.
- The model is small: about 30 binaries and 50 constraints for a 16-person list with meals off
  (about 180 binaries with meals on). It solves in milliseconds.
- All weights, slot times and group sizes are constants in `core/config.py`.
- With $K$ empty (the default) there are no $m_{ik}$ or $z_k$ variables, so $u_i = \mathrm{need}_i$:
  the tier stages still use need to favor seeing presenters whose talks would otherwise be lost.
- After solving, `not_met_data()` builds your outreach list ("People not yet met"): everyone not
  seen presenting at an attended session and not in a kept busy block, plus tier-1 people you'll
  only see at a talk. Each person gets bolded actions (Invite / Email first / Catch them / Look for them).
