"""Table 3 must describe the population the evaluation scored, not an earlier splits run.

Regression: the Results Pack once read Table 3 from the standalone splits stage, which had
run under the 5,000-user cap (126 rankable users in the final stage), while Table 4 scored
the uncapped population (530). The two tables contradicted each other.
"""

from __future__ import annotations

import json

from foodcom.reporting.results_pack import build_results_pack
from foodcom.utils.config import load_configs

UNCAPPED = {
    "history_end_exclusive": "2018-01-01",
    "label_start": "2018-01-01",
    "label_end_inclusive": "2018-12-20",
    "n_history_events": 1000,
    "n_label_events": 100,
    "n_catalogue_recipes": 500,
    "n_users_in_history": 400,
    "n_users_with_any_positive_history": 300,
    "n_history_eligible_users": 91,
    "cohort_capped": False,
    "cohort_cap": None,
    "cohort_seed": 42,
    "n_cohort_users": 91,
    "n_cohort_users_with_any_future_event": 80,
    "n_ranking_eligible_users": 77,
    "min_distinct_positive_history": 5,
}


def test_table3_uses_the_evaluated_runs_own_denominators(tmp_path):
    cfg = load_configs()
    run_dir = tmp_path / "final-20990101T000000Z-deadbeef"
    (run_dir / "metrics").mkdir(parents=True)
    (run_dir / "manifest.json").write_text(
        json.dumps(
            {
                "run_id": run_dir.name,
                "stage": "final",
                "status": "completed",
                "started_utc": "2099-01-01T00:00:00+00:00",
            }
        ),
        encoding="utf-8",
    )
    (run_dir / "metrics" / "split_denominators.json").write_text(
        json.dumps(UNCAPPED), encoding="utf-8"
    )

    out = build_results_pack(cfg, run_dir, out_path=tmp_path / "pack.md")
    text = out.read_text(encoding="utf-8")

    table3 = text.split("### Table 3")[1].split("## 4.")[0]
    assert "| final |" in table3
    assert "| False |" in table3 and "| 77 |" in table3
    assert "at most None" not in text
    assert "no cap was applied" in text
