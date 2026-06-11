"""Compatibility entry point for :mod:`ptc.migration.copy_experiment_artifacts`."""

from ptc.migration.copy_experiment_artifacts import *  # noqa: F403
from ptc.migration.copy_experiment_artifacts import main


if __name__ == "__main__":
    raise SystemExit(main())
