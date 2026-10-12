"""Tiny solver-neutral MIP layer so core.solver.solve() can run on Gurobi or HiGHS.

Write the model once with Var/Expr arithmetic (x + 2*y <= 1), then
Model.solve_lex([(name, objective), ...], "gurobi" | "highs") for a lexicographic
(priority-ordered) solve. Only the chosen solver is imported.
"""
import time

SOLVERS = {"gurobi": "Gurobi (gurobipy)", "highs": "HiGHS (highspy)"}


class Expr:
    def __init__(self, terms=None, const=0.0):
        self.terms = dict(terms or {})
        self.const = float(const)

    @staticmethod
    def of(x):
        return x if isinstance(x, Expr) else Expr(const=x)

    def __add__(self, other):
        o = Expr.of(other)
        t = dict(self.terms)
        for k, v in o.terms.items():
            t[k] = t.get(k, 0.0) + v
        return Expr(t, self.const + o.const)

    __radd__ = __add__

    def __neg__(self):
        return Expr({k: -v for k, v in self.terms.items()}, -self.const)

    def __sub__(self, other):
        return self + (-Expr.of(other))

    def __rsub__(self, other):
        return Expr.of(other) + (-self)

    def __mul__(self, c):
        return Expr({k: v * c for k, v in self.terms.items()}, self.const * c)

    __rmul__ = __mul__

    # Constraints are (lhs - rhs, sense) pairs, consumed by Model.add().
    def __le__(self, other):
        return (self - other, "<=")

    def __ge__(self, other):
        return (self - other, ">=")

    def value(self, x):
        return self.const + sum(v * x[k] for k, v in self.terms.items())


class Var(Expr):
    def __init__(self, idx):
        super().__init__({idx: 1.0})
        self.idx = idx


def qsum(items):
    t, c = {}, 0.0
    for it in items:
        e = Expr.of(it)
        c += e.const
        for k, v in e.terms.items():
            t[k] = t.get(k, 0.0) + v
    return Expr(t, c)


class Model:
    def __init__(self):
        self.lb, self.ub, self.binary, self.rows = [], [], [], []
        self.obj = Expr()

    def var(self, binary=True, lb=0.0, ub=1.0):
        self.lb.append(float(lb))
        self.ub.append(float(ub))
        self.binary.append(binary)
        return Var(len(self.lb) - 1)

    def fix(self, v, lb=None, ub=None):
        if lb is not None:
            self.lb[v.idx] = float(lb)
        if ub is not None:
            self.ub[v.idx] = float(ub)

    def add(self, constr):
        expr, sense = constr
        self.rows.append((expr.terms, sense, -expr.const))

    def maximize(self, expr):
        self.obj = Expr.of(expr)

    def solve(self, solver="gurobi"):
        """Single objective (self.obj). -> (values, stats)."""
        return self.solve_lex([("objective", self.obj)], solver)

    def solve_lex(self, stages, solver="gurobi"):
        """Lexicographic maximization: stages = [(name, expr), ...], highest priority first.

        Each stage is solved to proven optimality, then locked in with
        expr >= optimum - tol before the next stage runs. -> (values, stats).
        """
        if solver not in SOLVERS:
            raise ValueError(f"unknown solver {solver!r}; choose from {list(SOLVERS)}")
        t0 = time.time()
        be = (_Gurobi if solver == "gurobi" else _Highs)(self)
        values = {}
        for i, (name, expr) in enumerate(stages):
            e = Expr.of(expr)
            x, val = be.optimize(e)
            values[name] = round(val, 6)
            if i < len(stages) - 1:
                be.add_row(e.terms, ">=", val - e.const - 1e-6 * max(1.0, abs(val)))
        n_bin = sum(self.binary)
        return x, {"solver": f"{SOLVERS[solver]} {be.version}", "binary variables": n_bin,
                   "continuous variables": len(self.lb) - n_bin, "constraints": len(self.rows),
                   "stages": len(stages), "objective": values,
                   "solve time (s)": round(time.time() - t0, 4), "status": "optimal"}


class _Gurobi:
    def __init__(self, model):
        try:
            import gurobipy as gp
            from gurobipy import GRB
        except ImportError as e:
            raise RuntimeError("gurobipy is not installed; pick HiGHS or `pip install gurobipy`") from e
        self.gp, self.GRB = gp, GRB
        try:
            env = gp.Env(empty=True)
            env.setParam("OutputFlag", 0)
            env.start()
        except gp.GurobiError as e:
            raise RuntimeError(f"Gurobi license problem ({e}); pick HiGHS instead") from e
        m = self.m = gp.Model("informs2026", env=env)
        m.Params.MIPGap = 0.0  # small preferences must not be lost to the gap
        self.xs = [m.addVar(lb=lo, ub=hi, vtype=GRB.BINARY if b else GRB.CONTINUOUS)
                   for lo, hi, b in zip(model.lb, model.ub, model.binary)]
        for terms, sense, rhs in model.rows:
            self.add_row(terms, sense, rhs)
        self.version = ".".join(map(str, gp.gurobi.version()))

    def _lin(self, terms):
        return self.gp.LinExpr(list(terms.values()), [self.xs[k] for k in terms])

    def add_row(self, terms, sense, rhs):
        self.m.addLConstr(self._lin(terms), self.GRB.LESS_EQUAL if sense == "<=" else self.GRB.GREATER_EQUAL, rhs)

    def optimize(self, expr):
        self.m.setObjective(self._lin(expr.terms) + expr.const, self.GRB.MAXIMIZE)
        self.m.optimize()
        if self.m.Status != self.GRB.OPTIMAL:
            raise RuntimeError(f"Gurobi could not solve the schedule (status {self.m.Status})")
        return [v.X for v in self.xs], self.m.ObjVal


class _Highs:
    def __init__(self, model):
        try:
            import highspy
            import numpy as np
        except ImportError as e:
            raise RuntimeError("highspy is not installed; `pip install highspy`") from e
        self.hs, self.np = highspy, np
        h = self.h = highspy.Highs()
        h.setOptionValue("output_flag", False)
        h.setOptionValue("mip_rel_gap", 0.0)
        h.setOptionValue("mip_abs_gap", 1e-9)
        self.n = len(model.lb)
        h.addVars(self.n, np.array(model.lb), np.array(model.ub))
        ints = np.array([i for i, b in enumerate(model.binary) if b], dtype=np.int32)
        if len(ints):
            h.changeColsIntegrality(len(ints), ints, np.array([highspy.HighsVarType.kInteger] * len(ints)))
        for terms, sense, rhs in model.rows:
            self.add_row(terms, sense, rhs)
        h.changeObjectiveSense(highspy.ObjSense.kMaximize)
        self.version = h.version()

    def add_row(self, terms, sense, rhs):
        inf, np = self.hs.kHighsInf, self.np
        lo, hi = (-inf, rhs) if sense == "<=" else (rhs, inf)
        self.h.addRow(lo, hi, len(terms), np.array(list(terms), dtype=np.int32),
                      np.array(list(terms.values()), dtype=float))

    def optimize(self, expr):
        np, h = self.np, self.h
        cost = np.zeros(self.n)
        for k, v in expr.terms.items():
            cost[k] = v
        h.changeColsCost(self.n, np.arange(self.n, dtype=np.int32), cost)
        h.changeObjectiveOffset(expr.const)
        h.run()
        status = h.getModelStatus()
        if status != self.hs.HighsModelStatus.kOptimal:
            raise RuntimeError(f"HiGHS could not solve the schedule ({h.modelStatusToString(status)})")
        return list(h.getSolution().col_value), h.getInfo().objective_function_value
