"""SYNTHETIC FIXTURES — software testing only.

Nothing produced by this package is research data. It exists so the pipeline, the LP, the
duality checks and the metrics can be exercised deterministically without the real
Food.com files, and so that a contributor can see the whole system run before the data
gate is passed.

Every artifact generated here is stamped `SYNTHETIC` in its provenance. The evaluation
harness refuses to emit research numbers from a non-research-grade encoder, and the demo
labels synthetic data on every screen. A number from this package must never appear in the
paper.
"""

SYNTHETIC_MARKER = "SYNTHETIC-FIXTURE-NOT-RESEARCH-DATA"
