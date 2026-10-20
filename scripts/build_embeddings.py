#!/usr/bin/env python
"""Render recipe text deterministically and encode it with the frozen encoder."""

from __future__ import annotations

import argparse

from foodcom.pipeline import run_embeddings
from foodcom.utils import logging as flog


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--backend",
        choices=["sentence_transformers", "tfidf"],
        default=None,
        help="override the configured encoder. `tfidf` produces the labelled ablation.",
    )
    args = parser.parse_args()

    flog.configure()
    run_id = run_embeddings(backend=args.backend)
    print(f"\nEmbeddings built: run {run_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
