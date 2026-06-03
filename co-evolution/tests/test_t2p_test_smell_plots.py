from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

SRC_DIRECTORY = Path(__file__).resolve().parents[1] / "src"
MHC_SRC_DIRECTORY = Path(__file__).resolve().parents[2] / "method-history-collector" / "src"
for directory in (SRC_DIRECTORY, MHC_SRC_DIRECTORY):
    if str(directory) not in sys.path:
        sys.path.insert(0, str(directory))

try:
    import pandas as pd
except ImportError:  # pragma: no cover
    pd = None

from mhc.command_util import load_test_smell_acronyms, load_test_smell_names, resolve_smell_detector
from ptc.plot.t2p_test_smell_common import (
    COMPARABLE_CHANGE,
    PRODUCTION_RECURRENT,
    TEST_RECURRENT,
    assign_change_group,
    expand_smell_types,
    load_recurrent_change_frame,
)
from ptc.plot.t2p_test_smell_presence import build_parser as build_presence_parser
from ptc.plot.t2p_test_smell_presence import main as presence_main
from ptc.plot.t2p_test_smell_type import main as type_main
from ptc.plot.t2p_test_smell_type import smell_type_summary


@unittest.skipIf(pd is None, "pandas is required for test smell plot tests")
class TestT2PTestSmellPlots(unittest.TestCase):
    def test_smell_config_loads_acronym_and_full_name(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            config_file = Path(tmpdir) / "test-smell.yml"
            config_file.write_text(
                "\n".join(
                    [
                        "smell_detectors:",
                        "  jnose:",
                        "    smells:",
                        "      Assertion Roulette: AR",
                    ]
                ),
                encoding="utf-8",
            )

            self.assertEqual({"Assertion Roulette": "AR"}, load_test_smell_acronyms("jnose", config_file))
            self.assertEqual({"AR": "Assertion Roulette"}, load_test_smell_names("jnose", config_file))

    def test_smell_detector_defaults_to_jnose(self):
        with mock.patch.dict("os.environ", {}, clear=True):
            self.assertEqual("jnose", resolve_smell_detector())

        parser = build_presence_parser()
        self.assertEqual("jnose", parser.parse_args([]).smell_detector)
        self.assertEqual("custom", parser.parse_args(["--smell-detector", "custom"]).smell_detector)

    def test_assign_change_group(self):
        self.assertEqual(PRODUCTION_RECURRENT, assign_change_group(2, 3))
        self.assertEqual(TEST_RECURRENT, assign_change_group(15, 5))
        self.assertEqual(COMPARABLE_CHANGE, assign_change_group(9, 5))

    def test_load_recurrent_change_frame_joins_smells_and_filters_small_projects(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            experiment_dir = self.create_experiment(tmpdir)
            self.write_t2p_change(
                experiment_dir,
                "demo",
                [
                    self.row("demo", "test://A", "prod://A", 2, 3),
                    self.row("demo", "test://B", "prod://B", 15, 5),
                    self.row("demo", "test://C", "prod://C", 9, 5),
                ],
            )
            self.write_t2p_change(
                experiment_dir,
                "small",
                [self.row("small", "test://small", "prod://small", 30, 1)],
            )
            self.write_smells(
                experiment_dir,
                "demo",
                [
                    {"project": "demo", "name": "testA", "smell": "AR", "url": "test://A"},
                    {"project": "demo", "name": "testA", "smell": "ET", "url": "test://A"},
                    {"project": "demo", "name": "testB", "smell": "AR", "url": "test://B"},
                ],
            )

            frame = load_recurrent_change_frame(
                experiment_dir,
                "historyFinder",
                "nc",
                "jnose",
                None,
                min_t2p_links=2,
            )

            self.assertEqual(["demo"], sorted(frame["project"].unique()))
            self.assertEqual([PRODUCTION_RECURRENT, TEST_RECURRENT, COMPARABLE_CHANGE], frame["change_group"].tolist())
            smell_counts = dict(zip(frame["from_url"], frame["smell_count"]))
            self.assertEqual(2, smell_counts["test://A"])
            self.assertEqual(1, smell_counts["test://B"])
            self.assertEqual(0, smell_counts["test://C"])

    def test_expand_smell_types_and_summary(self):
        frame = pd.DataFrame(
            [
                {
                    "from_url": "test://A",
                    "test_revision": 15,
                    "revision_delta": 10,
                    "change_group": TEST_RECURRENT,
                    "smell_types": "AR;ET",
                },
                {
                    "from_url": "test://B",
                    "test_revision": 5,
                    "revision_delta": 1,
                    "change_group": COMPARABLE_CHANGE,
                    "smell_types": "AR",
                },
            ]
        )

        expanded = expand_smell_types(frame, {"AR": "Assertion Roulette", "ET": "Eager Test"})
        self.assertEqual(["Assertion Roulette", "Eager Test", "Assertion Roulette"], expanded["smell_name"].tolist())

        with mock.patch("ptc.plot.t2p_test_smell_type.MIN_SMELL_TYPE_COUNT", 1):
            summary = smell_type_summary(expanded)

        ar = summary[summary["smell_name"] == "Assertion Roulette"].iloc[0]
        self.assertEqual(2, ar["count"])
        self.assertEqual(50.0, ar["test_recurrent_percent"])

    def test_plot_modules_create_output_files(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            experiment_dir = self.create_experiment(tmpdir)
            rows = [
                self.row("demo", f"test://{index}", f"prod://{index}", 20 + index, 1)
                for index in range(6)
            ]
            self.write_t2p_change(experiment_dir, "demo", rows)
            self.write_smells(
                experiment_dir,
                "demo",
                [
                    {"project": "demo", "name": f"test{index}", "smell": "AR", "url": f"test://{index}"}
                    for index in range(5)
                ],
            )

            args = [
                "--workspace-directory",
                tmpdir,
                "--experiment-name",
                "demo-exp",
                "--tools",
                "historyFinder",
                "--strategies",
                "nc",
                "--projects",
                "demo",
                "--min-t2p-links",
                "0",
                "--smell-detector",
                "jnose",
            ]
            presence_main(args)
            type_main(args)

            self.assertTrue(
                (experiment_dir / "figure" / "t2p-test-smell-presence--historyFinder--nc--jnose.pdf").exists()
            )
            self.assertTrue(
                (experiment_dir / "figure" / "t2p-test-smell-type--historyFinder--nc--jnose.pdf").exists()
            )

    def create_experiment(self, workspace_dir: str) -> Path:
        experiment_dir = Path(workspace_dir) / "experiment" / "demo-exp"
        (experiment_dir / "t2p-change" / "historyFinder" / "nc").mkdir(parents=True)
        return experiment_dir

    def write_t2p_change(self, experiment_dir: Path, project: str, rows: list[dict]) -> None:
        output_file = experiment_dir / "t2p-change" / "historyFinder" / "nc" / f"{project}.csv"
        output_file.parent.mkdir(parents=True, exist_ok=True)
        pd.DataFrame(rows).to_csv(output_file, index=False)

    def write_smells(self, experiment_dir: Path, project: str, rows: list[dict]) -> None:
        output_file = experiment_dir / "test-smell" / "jnose" / f"{project}.csv"
        output_file.parent.mkdir(parents=True, exist_ok=True)
        pd.DataFrame(rows).to_csv(output_file, index=False)

    def row(self, project: str, from_url: str, to_url: str, from_ch_diff: int, to_ch_diff: int) -> dict:
        return {
            "project": project,
            "from_name": from_url.removeprefix("test://"),
            "to_name": to_url.removeprefix("prod://"),
            "from_url": from_url,
            "to_url": to_url,
            "from_ch_diff": from_ch_diff,
            "to_ch_diff": to_ch_diff,
        }


if __name__ == "__main__":
    unittest.main()
