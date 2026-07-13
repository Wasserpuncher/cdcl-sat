"""The proof has to leave the building.

A checker living in the same repository as the solver is still, in the end,
code by the same author. The standard DRAT text format is the escape hatch:
write the proof out, and anyone can run it through `drat-trim` -- written by
other people, for other solvers -- and get an answer that owes nothing to
anything here.

These tests check the format is actually the format: DIMACS literals, one clause
per line, 0-terminated, ending in a bare `0` for the empty clause.
"""

from __future__ import annotations

import pytest

from cdcl import check, from_drat, solve, to_drat
from cdcl.dimacs import lit_to_dimacs, parse
from cdcl.generate import pigeonhole


@pytest.mark.parametrize("holes", [3, 4, 5])
def test_a_proof_survives_a_round_trip_through_the_text_format(holes):
    cnf = pigeonhole(holes)
    model, proof, _ = solve(cnf, emit_proof=True)
    assert model is None

    recovered = from_drat(to_drat(proof))

    assert recovered == proof
    ok, message = check(cnf, recovered)
    assert ok, message


def test_the_format_is_dimacs_literals_terminated_by_zero():
    cnf = pigeonhole(3)
    _, proof, _ = solve(cnf, emit_proof=True)

    lines = to_drat(proof).splitlines()

    assert len(lines) == len(proof)
    for line, clause in zip(lines, proof):
        tokens = line.split()
        assert tokens[-1] == "0", f"clause not 0-terminated: {line!r}"
        assert [int(t) for t in tokens[:-1]] == [lit_to_dimacs(l) for l in clause]


def test_the_empty_clause_is_a_bare_zero():
    """Every UNSAT proof ends here, and drat-trim looks for exactly this."""
    cnf = pigeonhole(3)
    _, proof, _ = solve(cnf, emit_proof=True)

    assert to_drat(proof).splitlines()[-1] == "0"


def test_deletion_lines_are_read_and_ignored():
    """We never emit them, but a proof from another solver may have them, and
    ignoring a deletion is sound -- it only makes checking slower."""
    text = "1 2 0\nd 1 2 0\n-1 0\n0\n"

    proof = from_drat(text)

    assert len(proof) == 3          # the 'd' line is not a derivation step


def test_comments_and_blank_lines_are_skipped():
    proof = from_drat("c a comment\n\n1 0\n\nc another\n0\n")
    assert len(proof) == 2


def test_a_proof_read_from_text_still_catches_a_bad_step():
    """The round trip must not launder a broken proof into a valid one."""
    cnf = parse("p cnf 2 1\n1 2 0\n")     # satisfiable: no proof can exist

    ok, _ = check(cnf, from_drat("1 0\n2 0\n0\n"))

    assert not ok
