"""``python -m dienstpilot_ml.training``: train and register the C3 candidates."""

import argparse
import subprocess
from pathlib import Path

from dienstpilot_ml.training.pipeline import KINDS, log_to_mlflow, train

REPO = Path(__file__).resolve().parents[4]


def main() -> None:
    """Parse the arguments and run training."""
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--data", type=Path, default=REPO / "data/synthetic/v1")
    ap.add_argument("--store", type=Path, default=REPO / "ml/mlflow")
    args = ap.parse_args()
    ds, candidates, info = train(args.data)
    commit = subprocess.run(
        ["git", "rev-parse", "HEAD"], capture_output=True, text=True, cwd=REPO, check=False
    ).stdout.strip()
    versions = log_to_mlflow(args.store, ds, candidates, info, {"git_commit": commit})
    for c in candidates:
        print(
            f"{c.kind:15s} cv deviance {c.cv['mean_poisson_deviance']:.4f}"
            f"  mae {c.cv['mean_mae']:.4f}  registry v{versions[c.kind]}"
        )
    assert set(versions) == set(KINDS)


if __name__ == "__main__":
    main()
