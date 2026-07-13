"""CDCL: a SAT solver that learns from its mistakes.

Plain backtracking search tries an assignment, hits a contradiction, undoes the
last decision and tries the other way. It will happily rediscover the same
contradiction a million times over, because it never asks *why* the search
failed.

Conflict-Driven Clause Learning asks. On every conflict it walks back through
the implications that caused it, extracts the actual reason as a new clause, and
adds that clause to the formula. The reason is now a fact: the search can never
repeat it. Then it jumps straight back to the level where that new clause would
have made a difference -- possibly many levels at once, past decisions that had
nothing to do with the conflict.

That single idea -- the conflict is information, not just a dead end -- is what
separates a solver that dies at 30 variables from one that handles thousands.

The pieces below are the standard ones (Marques-Silva & Sakallah 1996; MiniSat):
two watched literals, 1UIP learning, VSIDS branching, Luby restarts, LBD-based
forgetting. Nothing here is novel; the point is that all of it is here, readable.
"""

from __future__ import annotations

import random

from .dimacs import CNF

UNDEF = -1


class OrderHeap:
    """A max-heap of variables by activity, with positions tracked so a variable
    can be re-scored or re-inserted in log time. VSIDS needs exactly this."""

    def __init__(self, activity: list[float]) -> None:
        self.activity = activity
        self.heap: list[int] = []
        self.pos: dict[int, int] = {}

    def _less(self, a: int, b: int) -> bool:
        return self.activity[a] > self.activity[b]      # max-heap

    def _swap(self, i: int, j: int) -> None:
        self.heap[i], self.heap[j] = self.heap[j], self.heap[i]
        self.pos[self.heap[i]] = i
        self.pos[self.heap[j]] = j

    def _up(self, i: int) -> None:
        while i > 0:
            parent = (i - 1) >> 1
            if not self._less(self.heap[i], self.heap[parent]):
                break
            self._swap(i, parent)
            i = parent

    def _down(self, i: int) -> None:
        n = len(self.heap)
        while True:
            left, right = 2 * i + 1, 2 * i + 2
            best = i
            if left < n and self._less(self.heap[left], self.heap[best]):
                best = left
            if right < n and self._less(self.heap[right], self.heap[best]):
                best = right
            if best == i:
                return
            self._swap(i, best)
            i = best

    def insert(self, var: int) -> None:
        if var in self.pos:
            return
        self.heap.append(var)
        self.pos[var] = len(self.heap) - 1
        self._up(len(self.heap) - 1)

    def decrease(self, var: int) -> None:
        """Activity went up, so the variable moves up the heap."""
        if var in self.pos:
            self._up(self.pos[var])

    def pop(self) -> int:
        top = self.heap[0]
        last = self.heap.pop()
        del self.pos[top]
        if self.heap:
            self.heap[0] = last
            self.pos[last] = 0
            self._down(0)
        return top

    def empty(self) -> bool:
        return not self.heap


def luby(y: float, x: int) -> float:
    """The Luby restart sequence: 1,1,2,1,1,2,4,1,1,2,1,1,2,4,8,...

    Restarting on a fixed schedule is a bad idea -- too often and you never
    finish a hard subproblem, too rarely and you stay stuck in one. Luby is the
    provably good compromise when you have no idea how long the run will take.
    """
    size, seq = 1, 0
    while size < x + 1:
        seq += 1
        size = 2 * size + 1
    while size - 1 != x:
        size = (size - 1) >> 1
        seq -= 1
        x = x % size
    return y ** seq


class Solver:
    def __init__(self, cnf: CNF, seed: int = 0, emit_proof: bool = False) -> None:
        self.num_vars = cnf.num_vars
        self.clauses: list[list[int]] = []
        self.learnts: list[list[int]] = []

        # value[var]: UNDEF, or True/False
        self.value: list[object] = [UNDEF] * self.num_vars
        self.level: list[int] = [0] * self.num_vars
        self.reason: list[list[int] | None] = [None] * self.num_vars
        self.trail: list[int] = []
        self.trail_lim: list[int] = []
        self.qhead = 0

        self.watches: list[list[list[int]]] = [[] for _ in range(2 * self.num_vars)]

        self.activity: list[float] = [0.0] * self.num_vars
        self.var_inc = 1.0
        self.var_decay = 0.95
        self.order = OrderHeap(self.activity)

        # Phase saving: remember the value a variable last had, and try it first.
        # Cheap, and it stops restarts from throwing away good partial work.
        self.saved_phase: list[bool] = [False] * self.num_vars

        self.rng = random.Random(seed)
        self.emit_proof = emit_proof
        self.proof: list[list[int]] = []      # learned clauses, in order

        self.conflicts = 0
        self.decisions = 0
        self.propagations = 0
        self.restarts = 0

        self.ok = True
        for clause in cnf.clauses:
            self._add_original(clause)
        for var in range(self.num_vars):
            self.order.insert(var)

    # ---- assignment bookkeeping -------------------------------------------------

    def _lit_value(self, lit: int):
        value = self.value[lit >> 1]
        if value is UNDEF:
            return UNDEF
        return value != bool(lit & 1)     # negate if the literal is negative

    def _enqueue(self, lit: int, reason: list[int] | None) -> None:
        var = lit >> 1
        self.value[var] = not bool(lit & 1)
        self.level[var] = self.decision_level
        self.reason[var] = reason
        self.trail.append(lit)

    @property
    def decision_level(self) -> int:
        return len(self.trail_lim)

    def _add_original(self, clause: list[int]) -> None:
        """Add a clause from the input formula, simplifying the trivial cases."""
        if not self.ok:
            return

        seen = set()
        simplified = []
        for lit in clause:
            if (lit ^ 1) in seen:
                return                    # clause contains x and NOT x: always true
            if lit not in seen:
                seen.add(lit)
                simplified.append(lit)

        if not simplified:
            self.ok = False               # the empty clause: formula is unsatisfiable
            return
        if len(simplified) == 1:
            # A unit clause is not a choice; it is a fact. Assert it at level 0.
            value = self._lit_value(simplified[0])
            if value is False:
                self.ok = False
            elif value is UNDEF:
                self._enqueue(simplified[0], None)
            return

        self._attach(simplified, self.clauses)

    def _attach(self, clause: list[int], store: list[list[int]]) -> None:
        store.append(clause)
        # Watch the first two literals. Everything the scheme needs follows from
        # the invariant that a clause only needs attention when a watched literal
        # becomes false.
        self.watches[clause[0] ^ 1].append(clause)
        self.watches[clause[1] ^ 1].append(clause)

    # ---- unit propagation -------------------------------------------------------

    def _propagate(self) -> list[int] | None:
        """Assign everything forced by the current trail. Returns a conflict clause."""
        conflict = None

        while self.qhead < len(self.trail):
            lit = self.trail[self.qhead]
            self.qhead += 1
            self.propagations += 1

            watch_list = self.watches[lit]
            self.watches[lit] = []
            keep = self.watches[lit]

            i = 0
            while i < len(watch_list):
                clause = watch_list[i]
                i += 1

                # Make sure the false literal sits at index 1.
                false_lit = lit ^ 1
                if clause[0] == false_lit:
                    clause[0], clause[1] = clause[1], clause[0]

                first = clause[0]
                if self._lit_value(first) is True:
                    keep.append(clause)       # already satisfied, nothing to do
                    continue

                # Look for a literal that is not false, and watch that instead.
                found = False
                for k in range(2, len(clause)):
                    if self._lit_value(clause[k]) is not False:
                        clause[1], clause[k] = clause[k], clause[1]
                        self.watches[clause[1] ^ 1].append(clause)
                        found = True
                        break
                if found:
                    continue

                # No replacement: every literal but the first is false.
                keep.append(clause)
                if self._lit_value(first) is False:
                    # All false: this clause is the conflict.
                    conflict = clause
                    self.qhead = len(self.trail)
                    while i < len(watch_list):
                        keep.append(watch_list[i])
                        i += 1
                    break
                # Exactly one unassigned literal left: it is forced.
                self._enqueue(first, clause)

            if conflict is not None:
                break

        return conflict

    # ---- conflict analysis: the 1UIP clause -------------------------------------

    def _analyze(self, conflict: list[int]) -> tuple[list[int], int]:
        """Walk back through the implication graph and extract why we failed.

        The result is a clause that is implied by the formula and is false under
        the current assignment -- and, crucially, contains exactly one literal
        from the current decision level (the "first unique implication point").
        That property is what makes the clause immediately useful: after
        backjumping it becomes a unit and forces the opposite choice.
        """
        seen = [False] * self.num_vars
        learnt: list[int] = [0]           # slot 0 reserved for the asserting literal
        counter = 0                       # literals from the current level still to expand
        lit = None
        index = len(self.trail) - 1
        clause = conflict

        while True:
            start = 0 if lit is None else 1   # skip the propagated literal itself
            for j in range(start, len(clause)):
                q = clause[j]
                var = q >> 1
                if not seen[var] and self.level[var] > 0:
                    seen[var] = True
                    self._bump(var)
                    if self.level[var] >= self.decision_level:
                        counter += 1
                    else:
                        learnt.append(q)

            # Walk the trail backwards to the most recent literal we care about.
            while not seen[self.trail[index] >> 1]:
                index -= 1
            lit = self.trail[index]
            index -= 1
            seen[lit >> 1] = False
            counter -= 1

            if counter <= 0:
                break
            reason = self.reason[lit >> 1]
            assert reason is not None, "a decision cannot be the reason for itself"
            clause = reason

        learnt[0] = lit ^ 1               # the negation of the UIP: the asserting literal

        # Backjump to the second-highest level in the clause; there the clause is unit.
        if len(learnt) == 1:
            backjump = 0
        else:
            best = max(range(1, len(learnt)), key=lambda k: self.level[learnt[k] >> 1])
            learnt[1], learnt[best] = learnt[best], learnt[1]
            backjump = self.level[learnt[1] >> 1]

        return learnt, backjump

    def _bump(self, var: int) -> None:
        self.activity[var] += self.var_inc
        if self.activity[var] > 1e100:
            # Rescale before the floats stop being able to tell activities apart.
            for v in range(self.num_vars):
                self.activity[v] *= 1e-100
            self.var_inc *= 1e-100
        self.order.decrease(var)

    def _decay(self) -> None:
        self.var_inc /= self.var_decay

    # ---- backtracking -----------------------------------------------------------

    def _backtrack(self, level: int) -> None:
        if self.decision_level <= level:
            return
        for i in range(len(self.trail) - 1, self.trail_lim[level] - 1, -1):
            lit = self.trail[i]
            var = lit >> 1
            self.saved_phase[var] = self.value[var]   # remember, for phase saving
            self.value[var] = UNDEF
            self.reason[var] = None
            self.order.insert(var)
        del self.trail[self.trail_lim[level]:]
        del self.trail_lim[level:]
        self.qhead = len(self.trail)

    def _decide(self) -> int | None:
        while not self.order.empty():
            var = self.order.pop()
            if self.value[var] is UNDEF:
                phase = self.saved_phase[var]
                return 2 * var + (0 if phase else 1)
        return None

    # ---- learned clause management ----------------------------------------------

    def _lbd(self, clause: list[int]) -> int:
        """Literal Block Distance: how many decision levels the clause spans.

        The empirical finding behind every modern solver: a learned clause whose
        literals come from few decision levels is far more likely to be useful
        again. LBD 2 clauses are kept forever; the rest are candidates to forget.
        """
        return len({self.level[lit >> 1] for lit in clause})

    def _reduce_db(self) -> None:
        """Forget half the learned clauses. Keeping all of them is what actually
        kills a CDCL solver -- propagation slows to a crawl."""
        keep: list[list[int]] = []
        drop: list[list[int]] = []
        for clause in self.learnts:
            if len(clause) <= 2 or self._lbd(clause) <= 3:
                keep.append(clause)
            else:
                drop.append(clause)

        drop.sort(key=len, reverse=True)          # forget the longest first
        half = len(drop) // 2
        forgotten = set(id(c) for c in drop[:half])

        if not forgotten:
            return

        for lit in range(2 * self.num_vars):
            self.watches[lit] = [c for c in self.watches[lit] if id(c) not in forgotten]

        self.learnts = keep + drop[half:]

    # ---- the main loop ----------------------------------------------------------

    def solve(self, max_conflicts: int | None = None) -> dict[int, bool] | None:
        """Returns a model (var -> bool) if satisfiable, or None if unsatisfiable."""
        if not self.ok:
            if self.emit_proof:
                self.proof.append([])          # the empty clause
            return None

        conflict = self._propagate()
        if conflict is not None:
            self.ok = False
            if self.emit_proof:
                self.proof.append([])
            return None

        restart_index = 0
        budget = 100 * luby(2.0, restart_index)
        conflicts_since_restart = 0
        max_learnts = max(len(self.clauses) // 3, 100)

        while True:
            conflict = self._propagate()

            if conflict is not None:
                self.conflicts += 1
                conflicts_since_restart += 1

                if self.decision_level == 0:
                    # A conflict with no decisions in play: the formula itself is
                    # contradictory. Nothing left to undo.
                    self.ok = False
                    if self.emit_proof:
                        self.proof.append([])
                    return None

                learnt, backjump = self._analyze(conflict)
                self._backtrack(backjump)

                if self.emit_proof:
                    self.proof.append(list(learnt))

                if len(learnt) == 1:
                    self._enqueue(learnt[0], None)
                else:
                    self._attach(learnt, self.learnts)
                    self._enqueue(learnt[0], learnt)

                self._decay()

                if max_conflicts is not None and self.conflicts >= max_conflicts:
                    raise TimeoutError(f"gave up after {self.conflicts} conflicts")
                continue

            # No conflict. Restart if this run has gone on long enough.
            if conflicts_since_restart >= budget:
                self.restarts += 1
                restart_index += 1
                budget = 100 * luby(2.0, restart_index)
                conflicts_since_restart = 0
                self._backtrack(0)
                continue

            if len(self.learnts) >= max_learnts + len(self.trail):
                self._reduce_db()

            lit = self._decide()
            if lit is None:
                # Every variable is assigned and nothing is in conflict: a model.
                return {var: bool(self.value[var]) for var in range(self.num_vars)}

            self.decisions += 1
            self.trail_lim.append(len(self.trail))
            self._enqueue(lit, None)


def solve(cnf: CNF, seed: int = 0, emit_proof: bool = False,
          max_conflicts: int | None = None):
    """Solve `cnf`. Returns (model, proof): exactly one of them is meaningful.

    If satisfiable, `model` is an assignment -- and you should check it yourself
    with `cnf.is_satisfied_by(model)`, because a solver's word is worth nothing.
    If unsatisfiable, `model` is None and `proof` is a DRUP derivation of the
    empty clause, which `cdcl.proof.check` will verify against the formula.
    """
    solver = Solver(cnf, seed=seed, emit_proof=emit_proof)
    model = solver.solve(max_conflicts=max_conflicts)
    return model, solver.proof, solver
