# cdcl-sat

**A SAT solver in pure Python — and you never have to trust it.**

Every answer it gives comes with something you can check yourself. If the formula
is satisfiable, it hands you the assignment, and you plug it into the clauses. If
it is **un**satisfiable, it hands you a **proof**, and an independent checker
verifies it. Neither answer requires you to believe a single line of the solver.

That matters more than it sounds. "Satisfiable" is self-evidencing — there's an
assignment, check it, done. **"Unsatisfiable" is a claim about all 2ⁿ
assignments at once, and there is nothing to plug in.** A solver with a bug that
quietly drops a clause will report UNSAT with total confidence, and no amount of
staring at the output will tell you. This is not hypothetical: SAT competitions
have required proofs since 2014 precisely because solvers were getting UNSAT
wrong and nobody could tell.

```console
$ python -m cdcl php 6            # 7 pigeons into 6 holes
s UNSATISFIABLE
  proof: 1074 clauses, verified in 1153 ms
  VERIFIED: 1074 clauses verified, ending in the empty clause
```

## The checker is the point, and it is deliberately stupid

A learned clause from a CDCL solver has a property called RUP: assume the clause
is false, run unit propagation, and you must hit a contradiction. Checking that
needs no cleverness — just propagation. So `proof.py` is a plain quadratic loop
with no watched literals, no heuristics, and no shared code with the solver.

That is on purpose. **A checker as clever as the solver is a checker that can
share the solver's bugs.** The whole value of the thing is that it is dumb enough
to be obviously right.

And if you don't trust that one either — fair, it lives in the same repository as
the solver — the proof leaves the building in the standard format:

```console
$ python -m cdcl php 6 --proof-out php.drat --cnf-out php.cnf
$ drat-trim php.cnf php.drat        # someone else's checker, someone else's code
```

`drat-trim` was written by other people for other solvers. It owes nothing to
anything here, and it will tell you whether the proof holds.

The price is real, and here it is:

| | solving | checking the proof |
| --- | ---: | ---: |
| PHP(7,6) | 89 ms | 1.2 s |
| PHP(8,7) | 1.7 s | **299 s** |

Checking is ~175× slower than solving on PHP(8,7). That is the cost of not having
to trust anything, and it is a trade I would make again.

(All timings here are from an i7-8550U. Absolute numbers move with the machine;
the conflict counts below do not, and they are the ones that carry the argument.)

## What it does

The standard CDCL machinery, all of it readable:

```
dimacs.py     the format every solver reads
solver.py     two watched literals, 1UIP learning, VSIDS, Luby restarts, LBD forgetting
proof.py      the DRUP checker -- independent, and deliberately naive
generate.py   random k-SAT, pigeonhole, graph colouring
```

The one idea that makes CDCL work: **a conflict is information, not just a dead
end.** Plain backtracking undoes its last decision and tries the other way — and
will happily rediscover the same contradiction a million times, because it never
asks *why* it failed. CDCL walks back through the implications, extracts the
actual reason as a new clause, and adds it to the formula. Now the search can
never repeat that mistake, and it jumps straight back to the level where the new
clause would have mattered — possibly past many decisions that had nothing to do
with the conflict.

## How fast, honestly

Random 3-SAT at ratio 4.26 — the phase transition, where instances are hardest:

```
  50 vars,  213 clauses:      4 ms       56 conflicts
 100 vars,  426 clauses:     47 ms      442 conflicts
 150 vars,  639 clauses:    396 ms    2,781 conflicts
 200 vars,  852 clauses:  4,184 ms   22,725 conflicts
```

`python -m cdcl bench` prints the first three rows; the 200-variable run is not
in it, because at that size the run stops being a benchmark and starts being a
wait. (The same command also verifies a pigeonhole proof, which takes several
minutes on its own — it is not a quick command.)

That is *pure Python*. MiniSat does 200 variables in single-digit milliseconds and
this is not a competitor to anything — a real solver is C++ and thirty years of
tuning. What it is, is complete and correct and 981 lines you can read.

## The ceiling, which is a theorem

Pigeonhole — n+1 pigeons into n holes — is unsatisfiable, obviously, and the
solver has to *prove* it:

```
PHP(5,4):        28 conflicts
PHP(6,5):       165 conflicts
PHP(7,6):     1,074 conflicts
PHP(8,7):    16,338 conflicts
PHP(9,8): 1,089,128 conflicts     (2 minutes)
```

This is not a performance bug that better code would fix. Haken proved in 1985
that **every** resolution proof of pigeonhole is exponentially long, and clause
learning is a resolution proof system. So that curve is a law, not a limitation
of this implementation — a hundred million dollars of solver engineering hits the
same wall a few holes later. It is one of the nicer things you can watch a
program do: bump into a theorem.

## How I know it's right

```console
$ python -m pytest -q
209 passed
```

The solver is checked against an oracle that cannot be wrong: **brute force**,
which is hopeless past ~22 variables and exactly right below that. Every small
instance is solved twice and the answers must agree — which catches the two
failure modes separately:

- claiming SAT when it isn't → the model is checked against every clause
- claiming UNSAT when it isn't → brute force finds the model it missed

The second is the dangerous one, and it is the reason the proof machinery exists.

There is one honest subtlety, and it has its own test. Corrupting a proof does
not always make it fail to verify — flip a literal in a learned clause and the
result is often *still* a clause propagation can derive, so accepting it is
correct. What the checker guarantees is the direction that matters: **if it
accepts, the formula really is unsatisfiable.** It does not promise to notice
that the solver took a different route than it claimed. Soundness, not
tamper-detection.

## Limits

- **Pure Python.** Two to three orders of magnitude off a real solver.
- **The proof checker is quadratic** and becomes the bottleneck well before the
  solver does. Deliberate — see above — but it means million-clause proofs are
  out of reach.
- **No proof deletion lines.** The DRAT output is monotone (clauses are only
  added), which is sound but makes long proofs slower to check than they need
  to be.
- **No clause minimization**, no inprocessing, no XOR reasoning, no
  cardinality detection.

## Install

<!-- readme-check: skip=clones-this-repo-into-itself -->
```console
$ git clone https://github.com/Wasserpuncher/cdcl-sat
$ cd cdcl-sat
$ python -m pytest -q
$ python -m cdcl php 6              # UNSAT, with a proof that verifies
$ python -m cdcl random 150         # random 3-SAT at the hard ratio
```

Python 3.10+, no dependencies.

## License

MIT
