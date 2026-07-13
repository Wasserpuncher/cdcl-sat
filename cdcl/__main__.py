"""CLI. Every answer comes back with something you can check.

    python -m cdcl solve FILE.cnf     solve a DIMACS file; verify the answer
    python -m cdcl php N              the pigeonhole principle, with a proof
    python -m cdcl bench              where the solver tops out, honestly
"""

from __future__ import annotations

import argparse
import sys
import time

from . import check, dimacs, solve
from .generate import phase_transition, pigeonhole


def _report(cnf, model, proof, solver, elapsed: float) -> int:
    print(f"variables:   {cnf.num_vars}")
    print(f"clauses:     {cnf.num_clauses}")
    print(f"conflicts:   {solver.conflicts}")
    print(f"decisions:   {solver.decisions}")
    print(f"restarts:    {solver.restarts}")
    print(f"time:        {elapsed * 1000:.0f} ms")
    print()

    if model is not None:
        # Never just print "SAT". Check it, and say that you checked it.
        good = cnf.is_satisfied_by(model)
        print("s SATISFIABLE")
        print(f"  model checked against all {cnf.num_clauses} clauses: "
              f"{'every clause satisfied' if good else 'MODEL IS WRONG'}")
        if not good:
            return 2
        assignment = " ".join(
            str(dimacs.lit_to_dimacs(2 * v + (0 if model[v] else 1)))
            for v in range(cnf.num_vars))
        print(f"v {assignment} 0")
        return 10

    print("s UNSATISFIABLE")
    if not proof:
        print("  (no proof was requested)")
        return 20

    start = time.perf_counter()
    ok, message = check(cnf, proof)
    print(f"  proof: {len(proof)} clauses, verified in "
          f"{(time.perf_counter() - start) * 1000:.0f} ms")
    print(f"  {'VERIFIED' if ok else 'PROOF REJECTED'}: {message}")
    return 20 if ok else 2


def main() -> int:
    parser = argparse.ArgumentParser(prog="cdcl", description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("solve", help="solve a DIMACS CNF file")
    p.add_argument("file")
    p.add_argument("--no-proof", action="store_true")

    p = sub.add_parser("php", help="pigeonhole: n+1 pigeons, n holes -- always UNSAT")
    p.add_argument("holes", type=int)

    p = sub.add_parser("random", help="random 3-SAT at the hard ratio")
    p.add_argument("num_vars", type=int)
    p.add_argument("--seed", type=int, default=0)

    sub.add_parser("bench", help="where the solver tops out")

    args = parser.parse_args()

    if args.cmd == "solve":
        with open(args.file) as handle:
            cnf = dimacs.parse(handle.read())
        start = time.perf_counter()
        model, proof, solver = solve(cnf, emit_proof=not args.no_proof)
        return _report(cnf, model, proof, solver, time.perf_counter() - start)

    if args.cmd == "php":
        cnf = pigeonhole(args.holes)
        print(f"PHP({args.holes + 1},{args.holes}): "
              f"{args.holes + 1} pigeons into {args.holes} holes\n")
        start = time.perf_counter()
        model, proof, solver = solve(cnf, emit_proof=True)
        return _report(cnf, model, proof, solver, time.perf_counter() - start)

    if args.cmd == "random":
        cnf = phase_transition(args.num_vars, seed=args.seed)
        start = time.perf_counter()
        model, proof, solver = solve(cnf, emit_proof=True)
        return _report(cnf, model, proof, solver, time.perf_counter() - start)

    if args.cmd == "bench":
        print("random 3-SAT at the phase transition (ratio 4.26), 3 seeds each:")
        for n in (50, 75, 100, 125, 150):
            total = conflicts = 0.0
            for seed in range(3):
                cnf = phase_transition(n, seed=seed)
                start = time.perf_counter()
                model, _, solver = solve(cnf, seed=seed)
                total += time.perf_counter() - start
                conflicts += solver.conflicts
                if model is not None:
                    assert cnf.is_satisfied_by(model)
            print(f"  {n:>4} vars, {int(4.26 * n):>4} clauses: "
                  f"{total / 3 * 1000:>7.0f} ms   {int(conflicts // 3):>6} conflicts")

        print("\npigeonhole -- unsatisfiable, and exponentially hard on purpose:")
        for holes in (4, 5, 6, 7):
            cnf = pigeonhole(holes)
            start = time.perf_counter()
            model, proof, solver = solve(cnf, emit_proof=True)
            elapsed = time.perf_counter() - start
            ok, _ = check(cnf, proof)
            print(f"  PHP({holes + 1},{holes}): {elapsed * 1000:>7.0f} ms   "
                  f"{solver.conflicts:>6} conflicts   proof {len(proof):>5} clauses   "
                  f"verified={ok}")
        return 0

    return 1


if __name__ == "__main__":
    sys.exit(main())
