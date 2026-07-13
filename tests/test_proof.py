"""Tests for the proof checker itself.

A checker that accepts everything would make every UNSAT answer look verified,
which is worse than having no checker at all. So it has to be shown *rejecting*
things: proofs with a bad step, proofs that never reach the empty clause, and
clauses that simply don't follow.
"""

from __future__ import annotations

import pytest

from cdcl import check, solve
from cdcl.dimacs import lit_from_dimacs, parse
from cdcl.generate import pigeonhole
from cdcl.proof import is_rup


def lits(*values: int) -> list[int]:
    return [lit_from_dimacs(v) for v in values]


class TestRUP:
    def test_a_clause_that_propagation_implies(self):
        # (x1) and (NOT x1 OR x2) imply (x2).
        formula = [lits(1), lits(-1, 2)]
        assert is_rup(formula, lits(2))

    def test_a_clause_that_does_not_follow(self):
        formula = [lits(1, 2)]
        assert not is_rup(formula, lits(1))     # x1 OR x2 does not imply x1

    def test_the_empty_clause_needs_an_actual_contradiction(self):
        assert not is_rup([lits(1)], [])
        assert is_rup([lits(1), lits(-1)], [])

    def test_a_tautology_is_always_implied(self):
        assert is_rup([], lits(1, -1))


class TestCheck:
    def test_accepts_the_solver_s_own_proof(self):
        cnf = pigeonhole(4)
        model, proof, _ = solve(cnf, emit_proof=True)

        assert model is None
        ok, message = check(cnf, proof)
        assert ok, message

    def test_rejects_a_proof_that_never_reaches_the_empty_clause(self):
        cnf = pigeonhole(3)
        _, proof, _ = solve(cnf, emit_proof=True)

        ok, message = check(cnf, proof[:-1])

        assert not ok
        assert "empty clause" in message

    def test_rejects_an_empty_proof(self):
        cnf = pigeonhole(3)
        ok, message = check(cnf, [])
        assert not ok

    def test_rejects_a_step_that_does_not_follow(self):
        """Splice in a clause propagation cannot derive. The checker must catch it.

        The clause has to be chosen with care: in an unsatisfiable formula every
        clause is *semantically* implied, so "wrong" cannot mean "false". RUP is
        the stronger, syntactic question -- can unit propagation get there from
        here -- and (x1) cannot be, from the pigeonhole axioms alone.
        """
        cnf = pigeonhole(3)
        _, proof, _ = solve(cnf, emit_proof=True)

        tampered = [lits(1)] + list(proof)

        ok, message = check(cnf, tampered)

        assert not ok
        assert "not RUP" in message

    def test_the_guarantee_is_soundness_not_tamper_detection(self):
        """Corrupting a proof does not always make it fail to verify -- and that
        is correct, not a hole.

        Flip a literal in a learned clause and the result is often still a clause
        propagation can derive. Accepting it is the right call: it is implied, so
        adding it is sound, and the proof still ends in the empty clause. What
        the checker promises is the direction that matters -- if it accepts, the
        formula really is unsatisfiable. It does not promise to notice that the
        solver took a different route than it claimed.

        The property that must never break is tested next door, against brute
        force: no satisfiable formula ever gets a proof that verifies.
        """
        cnf = pigeonhole(4)
        _, proof, _ = solve(cnf, emit_proof=True)

        rejected = 0
        corrupted = 0
        for index in range(len(proof) - 1):
            if not proof[index]:
                continue
            tampered = [list(c) for c in proof]
            tampered[index][0] ^= 1
            corrupted += 1
            if not check(cnf, tampered)[0]:
                rejected += 1

        assert corrupted > 10
        assert rejected > 0, "a corrupted proof should at least sometimes be caught"
        # And whatever it accepted, the formula was unsatisfiable anyway.
        assert solve(cnf)[0] is None

    def test_rejects_a_proof_for_a_satisfiable_formula(self):
        """You cannot prove the empty clause from a formula that has a model.
        If the checker ever accepts one, it is broken."""
        cnf = parse("p cnf 2 1\n1 2 0\n")

        ok, _ = check(cnf, [lits(1), lits(2), []])

        assert not ok

    @pytest.mark.parametrize("holes", [3, 4, 5])
    def test_every_pigeonhole_proof_verifies(self, holes):
        cnf = pigeonhole(holes)
        model, proof, _ = solve(cnf, emit_proof=True)

        assert model is None, "PHP is unsatisfiable by construction"
        ok, message = check(cnf, proof)
        assert ok, message
