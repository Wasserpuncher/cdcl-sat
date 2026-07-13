"""A DRUP proof checker -- the reason you don't have to trust the solver.

"Satisfiable" is easy to check: the solver hands you an assignment, you plug it
into the formula, done. **"Unsatisfiable" is not.** The answer is a claim about
*every* one of 2^n assignments, and there is nothing to plug in. A buggy solver
that drops a clause by accident will confidently report UNSAT, and no amount of
staring at the output will tell you.

So the solver is required to show its work. Every clause it learns is written to
a proof, and a valid CDCL learned clause has a property called RUP: assume the
clause is false, run unit propagation on the formula so far, and you must reach
a contradiction. That check needs no cleverness -- just propagation -- so a
checker can be short and obviously correct even when the solver is neither.

The proof ends with the empty clause. If every step checks out, the formula is
unsatisfiable, and the only thing you had to believe is the ~60 lines below.

This is (a simplified, deletion-free) DRUP, the format SAT competitions have
required since 2014 for exactly this reason: solvers had been getting UNSAT
wrong, and nobody could tell.
"""

from __future__ import annotations

from .dimacs import CNF, lit_from_dimacs, lit_to_dimacs

UNDEF = -1


def _propagate_to_fixpoint(clauses: list[list[int]], assign: dict[int, bool]) -> bool:
    """Unit-propagate. Returns True if a conflict was reached.

    Deliberately the simple quadratic version: no watched literals, no
    heuristics. A checker that is as clever as the solver is a checker that can
    share the solver's bugs.
    """
    changed = True
    while changed:
        changed = False
        for clause in clauses:
            unassigned = None
            satisfied = False
            false_count = 0

            for lit in clause:
                var = lit >> 1
                want = not bool(lit & 1)
                if var not in assign:
                    unassigned = lit
                elif assign[var] == want:
                    satisfied = True
                    break
                else:
                    false_count += 1

            if satisfied:
                continue
            if false_count == len(clause):
                return True                       # every literal false: conflict
            if false_count == len(clause) - 1 and unassigned is not None:
                # Exactly one literal left, and the clause must hold: it is forced.
                assign[unassigned >> 1] = not bool(unassigned & 1)
                changed = True

    return False


def is_rup(clauses: list[list[int]], clause: list[int]) -> bool:
    """Is `clause` implied by `clauses` by unit propagation alone?

    Assume every literal of `clause` is false, propagate, and look for a
    contradiction. If one turns up, the formula could never have made `clause`
    false, so `clause` is safe to add.
    """
    assign: dict[int, bool] = {}
    for lit in clause:
        var = lit >> 1
        want_false = bool(lit & 1)        # negating the literal
        if var in assign and assign[var] != want_false:
            return True                   # clause has x and NOT x: trivially implied
        assign[var] = want_false

    return _propagate_to_fixpoint(clauses, assign)


def check(cnf: CNF, proof: list[list[int]]) -> tuple[bool, str]:
    """Verify a DRUP proof of unsatisfiability. Returns (ok, message)."""
    if not proof:
        return False, "empty proof: nothing was derived"
    if proof[-1]:
        return False, "proof does not end with the empty clause"

    clauses = [list(c) for c in cnf.clauses]

    for step, clause in enumerate(proof):
        if not is_rup(clauses, clause):
            pretty = " ".join(str(l) for l in clause) or "(empty clause)"
            return False, f"step {step + 1}/{len(proof)} is not RUP: {pretty}"
        clauses.append(list(clause))

    return True, f"{len(proof)} clauses verified, ending in the empty clause"


def to_drat(proof: list[list[int]]) -> str:
    """Write the proof in the standard DRAT text format.

    This is the format SAT competitions require and that `drat-trim` reads. It
    is deliberately plain: DIMACS literals, one clause per line, each terminated
    by a 0. The empty clause -- the end of every UNSAT proof -- is a lone `0`.

    Emitting it matters more than it looks. It means the checker in this repo is
    not the last word: anyone can run the proof through drat-trim, which was
    written by other people for other solvers, and get an answer that owes
    nothing to any code here.

    (No `d` deletion lines: this solver's proof only ever adds clauses. That is
    sound -- deletions are an optimisation for the checker, not a requirement --
    but it does make long proofs slower to check than they need to be.)
    """
    lines = []
    for clause in proof:
        literals = " ".join(str(lit_to_dimacs(lit)) for lit in clause)
        lines.append(f"{literals} 0".strip())
    return "\n".join(lines) + "\n"


def from_drat(text: str) -> list[list[int]]:
    """Read a DRAT text proof back into internal literals."""
    proof: list[list[int]] = []
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("c"):
            continue
        if line.startswith("d "):
            continue                      # deletion: sound to ignore when checking
        clause = []
        for token in line.split():
            value = int(token)
            if value == 0:
                break
            clause.append(lit_from_dimacs(value))
        proof.append(clause)
    return proof


def brute_force(cnf: CNF) -> dict[int, bool] | None:
    """The dumbest possible oracle: try all 2^n assignments.

    Useless past ~22 variables, and exactly right below that -- which makes it
    the reference the real solver is tested against.
    """
    n = cnf.num_vars
    for bits in range(1 << n):
        model = {var: bool((bits >> var) & 1) for var in range(n)}
        if cnf.is_satisfied_by(model):
            return model
    return None
