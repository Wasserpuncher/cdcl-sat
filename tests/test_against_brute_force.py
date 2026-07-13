"""The solver is checked against an oracle that cannot be wrong.

Brute force is hopeless past ~22 variables and *exactly right* below that. So
every small instance gets solved twice, and the two must agree -- not just on
the answer, but in a way that catches the two failure modes separately:

* claiming SAT when it isn't -- caught by checking the model against the formula
* claiming UNSAT when it isn't -- caught by brute force finding a model

The second is the dangerous one. A solver that silently loses a clause reports
UNSAT with total confidence, and nothing in its own output looks wrong.
"""

from __future__ import annotations

import pytest

from cdcl import brute_force, check, solve
from cdcl.dimacs import CNF, parse
from cdcl.generate import graph_colouring, random_ksat


@pytest.mark.parametrize("seed", range(60))
def test_agrees_with_brute_force_on_random_3sat(seed):
    cnf = random_ksat(num_vars=12, num_clauses=51, k=3, seed=seed)

    model, proof, _ = solve(cnf, emit_proof=True)
    reference = brute_force(cnf)

    if model is not None:
        assert cnf.is_satisfied_by(model), "solver returned a model that is not a model"
        assert reference is not None, "solver says SAT, brute force says UNSAT"
    else:
        assert reference is None, "solver says UNSAT, but brute force found a model"
        ok, message = check(cnf, proof)
        assert ok, f"UNSAT claimed without a valid proof: {message}"


@pytest.mark.parametrize("seed", range(30))
@pytest.mark.parametrize("ratio", [2.0, 4.26, 6.0])
def test_agrees_across_the_phase_transition(seed, ratio):
    """Below 4.26 almost everything is satisfiable, above it almost nothing is.
    Testing all three regimes means both answers get exercised."""
    num_vars = 10
    cnf = random_ksat(num_vars, int(ratio * num_vars), k=3, seed=seed * 7 + 1)

    model, proof, _ = solve(cnf, emit_proof=True)
    reference = brute_force(cnf)

    assert (model is None) == (reference is None)
    if model is not None:
        assert cnf.is_satisfied_by(model)
    else:
        assert check(cnf, proof)[0]


@pytest.mark.parametrize("k", [2, 4, 5])
@pytest.mark.parametrize("seed", range(10))
def test_agrees_on_other_clause_widths(k, seed):
    cnf = random_ksat(num_vars=11, num_clauses=40, k=k, seed=seed)

    model, proof, _ = solve(cnf, emit_proof=True)
    reference = brute_force(cnf)

    assert (model is None) == (reference is None)
    if model is not None:
        assert cnf.is_satisfied_by(model)


class TestEdgeCases:
    def test_empty_formula_is_trivially_satisfiable(self):
        cnf = CNF(num_vars=3, clauses=[])
        model, _, _ = solve(cnf)
        assert model is not None
        assert cnf.is_satisfied_by(model)

    def test_the_empty_clause_is_unsatisfiable(self):
        cnf = CNF(num_vars=2, clauses=[[]])
        model, proof, _ = solve(cnf, emit_proof=True)
        assert model is None
        assert check(cnf, proof)[0]

    def test_directly_contradictory_units(self):
        cnf = parse("p cnf 1 2\n1 0\n-1 0\n")
        model, proof, _ = solve(cnf, emit_proof=True)
        assert model is None
        assert check(cnf, proof)[0]

    def test_a_tautology_is_not_a_constraint(self):
        """(x OR NOT x) is always true and must not make anything unsatisfiable."""
        cnf = parse("p cnf 1 1\n1 -1 0\n")
        model, _, _ = solve(cnf)
        assert model is not None

    def test_unit_clauses_force_their_value(self):
        cnf = parse("p cnf 3 3\n1 0\n-2 0\n1 2 3 0\n")
        model, _, _ = solve(cnf)
        assert model is not None
        assert model[0] is True     # variable 1 forced true
        assert model[1] is False    # variable 2 forced false
        assert cnf.is_satisfied_by(model)

    def test_a_long_implication_chain(self):
        """x1 -> x2 -> ... -> x60, with x1 asserted and x60 denied: UNSAT, and
        only propagation can see it."""
        clauses = ["1 0", "-60 0"]
        clauses += [f"-{i} {i + 1} 0" for i in range(1, 60)]
        cnf = parse(f"p cnf 60 {len(clauses)}\n" + "\n".join(clauses) + "\n")

        model, proof, _ = solve(cnf, emit_proof=True)
        assert model is None
        assert check(cnf, proof)[0]


class TestRealProblems:
    def test_a_triangle_needs_three_colours(self):
        triangle = [(0, 1), (1, 2), (0, 2)]

        two, _, _ = solve(graph_colouring(triangle, 3, colours=2))
        three_cnf = graph_colouring(triangle, 3, colours=3)
        three, _, _ = solve(three_cnf)

        assert two is None, "a triangle is not 2-colourable"
        assert three is not None and three_cnf.is_satisfied_by(three)

    def test_a_square_is_two_colourable(self):
        square = [(0, 1), (1, 2), (2, 3), (3, 0)]
        cnf = graph_colouring(square, 4, colours=2)

        model, _, _ = solve(cnf)

        assert model is not None
        assert cnf.is_satisfied_by(model)
