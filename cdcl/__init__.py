"""A CDCL SAT solver whose answers you can check without trusting it.

    >>> from cdcl import dimacs, solve, check
    >>> cnf = dimacs.parse("p cnf 2 2\\n1 2 0\\n-1 2 0\\n")
    >>> model, proof, _ = solve(cnf)
    >>> cnf.is_satisfied_by(model)       # don't take the solver's word for it
    True

If the formula is unsatisfiable, `model` is None and `proof` is a DRUP
derivation of the empty clause that `check` verifies independently.
"""

from .dimacs import CNF, parse
from .proof import brute_force, check, from_drat, is_rup, to_drat
from .solver import Solver, solve

__all__ = ["CNF", "parse", "solve", "Solver", "check", "is_rup", "brute_force",
           "to_drat", "from_drat", "dimacs"]
__version__ = "1.0.0"

from . import dimacs  # noqa: E402  -- re-exported for `from cdcl import dimacs`
