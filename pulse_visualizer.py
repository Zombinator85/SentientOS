import argparse
from datetime import datetime, timedelta
from pathlib import Path

import matplotlib.pyplot as plt  # type: ignore
import presence_pulse_api as pulse


def plot_pulse(hours: int = 24) -> Path:
    intervals = [i for i in range(hours)]
    values = []
    for h in intervals:
        mins = (hours - h) * 60
        values.append(pulse.pulse(mins))
    plt.figure(figsize=(8, 3))
    plt.plot(list(range(hours)), list(reversed(values)))
    plt.xlabel("Hours Ago")
    plt.ylabel("Pulse/min")
    out = Path("pulse_visualization.png")
    plt.tight_layout()
    plt.savefig(out)
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description="Presence pulse visualization")
    ap.add_argument("--hours", type=int, default=24)
    args = ap.parse_args()
    print(plot_pulse(args.hours))


if __name__ == "__main__":  # pragma: no cover - manual
    main()
