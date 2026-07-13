"""DIMACS CNF: the format every SAT solver in the world reads.

A formula is a conjunction of clauses; a clause is a disjunction of literals; a
literal is a variable or its negation. In DIMACS a variable is a positive
integer, negation is a minus sign, and a clause ends at a 0:

    p cnf 3 2          3 variables, 2 clauses
    1 -3 0             (x1 OR NOT x3)
    2 3 -1 0           (x2 OR x3 OR NOT x1)

Internally literals are packed to non-negative ints so they can index arrays:
variable v (0-based) becomes 2v for the positive literal and 2v+1 for the
negative one, which makes negation a single XOR with 1.
"""

from __future__ import annotations

from dataclasses import dataclass


def lit_from_dimacs(value: int) -> int:
    """DIMACS literal (e.g. -3) -> internal literal."""
    var = abs(value) - 1
    return 2 * var + (1 if value < 0 else 0)


def lit_to_dimacs(lit: int) -> int:
    """Internal literal -> DIMACS literal."""
    var = lit >> 1
    return -(var + 1) if (lit & 1) else (var + 1)


@dataclass
class CNF:
    num_vars: int
    clauses: list[list[int]]      # internal literals

    @property
    def num_clauses(self) -> int:
        return len(self.clauses)

    def to_dimacs(self) -> str:
        lines = [f"p cnf {self.num_vars} {len(self.clauses)}"]
        for clause in self.clauses:
            lines.append(" ".join(str(lit_to_dimacs(l)) for l in clause) + " 0")
        return "\n".join(lines) + "\n"

    def is_satisfied_by(self, model: dict[int, bool]) -> bool:
        """Check a model against every clause. This is the whole point.

        A SAT solver's "satisfiable" is only worth as much as this check --
        which is why the solver never gets to be the one that reports success.
        """
        for clause in self.clauses:
            if not any(model[l >> 1] != bool(l & 1) for l in clause):
                return False
        return True


def parse(text: str) -> CNF:
    num_vars = 0
    clauses: list[list[int]] = []
    current: list[int] = []
    seen_header = False

    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("c"):
            continue
        if line.startswith("p"):
            parts = line.split()
            if len(parts) < 4 or parts[1] != "cnf":
                raise ValueError(f"bad header: {line!r}")
            num_vars = int(parts[2])
            seen_header = True
            continue
        if not seen_header:
            raise ValueError("clause before 'p cnf' header")
        for token in line.split():
            value = int(token)
            if value == 0:
                clauses.append(current)
                current = []
            else:
                if abs(value) > num_vars:
                    raise ValueError(
                        f"literal {value} exceeds the declared {num_vars} variables")
                current.append(lit_from_dimacs(value))

    if current:
        raise ValueError("last clause is not terminated by 0")

    return CNF(num_vars=num_vars, clauses=clauses)
