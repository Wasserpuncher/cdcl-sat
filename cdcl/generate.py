"""Formula families to test against -- including ones whose answer is known in
advance, which is the only way to test UNSAT without trusting a solver.
"""

from __future__ import annotations

import random

from .dimacs import CNF, lit_from_dimacs


def random_ksat(num_vars: int, num_clauses: int, k: int = 3, seed: int = 0) -> CNF:
    """Uniform random k-SAT.

    The interesting knob is the ratio of clauses to variables. For 3-SAT, almost
    every instance below ~4.26 is satisfiable and almost every one above it is
    not -- and the instances *at* 4.26 are the hard ones. It is a genuine phase
    transition, and it is where solvers are measured.
    """
    rng = random.Random(seed)
    clauses = []
    for _ in range(num_clauses):
        variables = rng.sample(range(1, num_vars + 1), k)
        clause = [lit_from_dimacs(v if rng.random() < 0.5 else -v) for v in variables]
        clauses.append(clause)
    return CNF(num_vars=num_vars, clauses=clauses)


def phase_transition(num_vars: int, seed: int = 0) -> CNF:
    """Random 3-SAT at the hardest ratio: 4.26 clauses per variable."""
    return random_ksat(num_vars, int(round(4.26 * num_vars)), k=3, seed=seed)


def pigeonhole(holes: int) -> CNF:
    """PHP(n+1, n): put n+1 pigeons into n holes, no two in the same hole.

    Unsatisfiable, obviously, and provably so -- which is the point. No solver
    ever gets to *guess* right on this one. It is also famously hard for exactly
    the kind of reasoning CDCL does: resolution proofs of PHP are known to be
    exponentially long (Haken, 1985), so this is the family that shows you the
    method's ceiling, not just its speed.
    """
    pigeons = holes + 1

    def var(pigeon: int, hole: int) -> int:
        return pigeon * holes + hole + 1          # 1-based DIMACS variable

    clauses = []

    # Every pigeon is in some hole.
    for p in range(pigeons):
        clauses.append([lit_from_dimacs(var(p, h)) for h in range(holes)])

    # No hole holds two pigeons.
    for h in range(holes):
        for p1 in range(pigeons):
            for p2 in range(p1 + 1, pigeons):
                clauses.append([lit_from_dimacs(-var(p1, h)),
                                lit_from_dimacs(-var(p2, h))])

    return CNF(num_vars=pigeons * holes, clauses=clauses)


def graph_colouring(edges: list[tuple[int, int]], num_nodes: int,
                    colours: int) -> CNF:
    """Can this graph be coloured with `colours` colours? A classic NP-complete
    problem reduced to SAT, which is what SAT solvers are actually used for."""
    def var(node: int, colour: int) -> int:
        return node * colours + colour + 1

    clauses = []
    for node in range(num_nodes):
        clauses.append([lit_from_dimacs(var(node, c)) for c in range(colours)])
        for c1 in range(colours):
            for c2 in range(c1 + 1, colours):
                clauses.append([lit_from_dimacs(-var(node, c1)),
                                lit_from_dimacs(-var(node, c2))])

    for a, b in edges:
        for c in range(colours):
            clauses.append([lit_from_dimacs(-var(a, c)), lit_from_dimacs(-var(b, c))])

    return CNF(num_vars=num_nodes * colours, clauses=clauses)
