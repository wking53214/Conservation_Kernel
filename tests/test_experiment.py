import json
from pathlib import Path

from conservation_kernel.experiments import run_experiment


def test_control_treatment_experiment_runs_ten_boundaries_and_records_rejections():
    report = run_experiment(steps=10)

    assert report["control"]["accepted_transformations"] == 10
    assert report["treatment"]["accepted_transformations"] == 10
    assert report["treatment"]["rejected_attempts"] == 5
    assert report["treatment"]["blocked_attack_rate"] == 1.0
    assert all(value == 0.0 for value in report["treatment"]["metrics"].values())
    assert report["treatment"]["reconstruction"]["root_artifact_ids"] == ["artifact-ground-truth"]
    assert report["treatment"]["reconstruction"]["transformation_ids_in_order"][-1] == "tx-summary-10"
    assert any(value > 0 for value in report["control"]["metrics"].values())


def test_checked_in_metrics_snapshot_matches_the_reproducible_run():
    report = run_experiment(steps=10)
    snapshot = json.loads(Path("experiments/metrics/initial_run.json").read_text())

    assert snapshot["control"]["metrics"] == report["control"]["metrics"]
    assert snapshot["treatment"]["metrics_on_accepted_transformations"] == report["treatment"]["metrics"]
    assert snapshot["treatment"]["blocked_attack_rate"] == report["treatment"]["blocked_attack_rate"]
