from __future__ import annotations

import json

from conservation_kernel.experiments import run_experiment


if __name__ == "__main__":
    print(json.dumps(run_experiment(steps=10), indent=2, sort_keys=True))
