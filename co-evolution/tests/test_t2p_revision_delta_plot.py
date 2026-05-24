from pathlib import Path
import sys
import tempfile
import unittest

SRC_DIRECTORY = Path(__file__).resolve().parents[1] / "src"
MHC_SRC_DIRECTORY = Path(__file__).resolve().parents[2] / "method-history-collector" / "src"
for directory in (SRC_DIRECTORY, MHC_SRC_DIRECTORY):
    if str(directory) not in sys.path:
        sys.path.insert(0, str(directory))

try:
    import pandas as pd
except ImportError:  # pragma: no cover
    pd = None

from ptc.plot.t2p_revision_delta_cdf import delta_cdf, main


@unittest.skipIf(pd is None, "pandas is required for t2p revision delta plot tests")
class TestT2PRevisionDeltaPlot(unittest.TestCase):
    def test_delta_cdf_uses_production_minus_test(self):
        df = pd.DataFrame(
            [
                {"from_ch_all": 5, "to_ch_all": 0},
                {"from_ch_all": 1, "to_ch_all": 1},
                {"from_ch_all": 0, "to_ch_all": 2},
                {"from_ch_all": 1, "to_ch_all": 3},
            ]
        )

        cdf = delta_cdf(df, "ch_all")

        self.assertEqual(
            {-5: 0.25, -4: 0.25, -3: 0.25, -2: 0.25, -1: 0.25, 0: 0.5, 1: 0.5, 2: 1.0},
            cdf.to_dict(),
        )

    def test_generates_cdf_plot_for_selected_filters(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            experiment_dir = self.create_experiment(tmpdir)
            self.write_t2p_change_rows(experiment_dir, "historyFinder", "nc", "projectA")
            self.write_t2p_change_rows(experiment_dir, "historyFinder", "other", "projectA")
            self.write_t2p_change_rows(experiment_dir, "codeShovel", "nc", "projectA")
            self.write_t2p_change_rows(experiment_dir, "historyFinder", "nc", "projectB")

            main(
                [
                    "--workspace-directory",
                    tmpdir,
                    "--experiment-name",
                    "demo",
                    "--tools",
                    "historyFinder",
                    "--strategies",
                    "nc",
                    "--projects",
                    "projectA",
                ]
            )

            selected_plot = experiment_dir / "figure" / "t2p-revision-delta-cdf--historyFinder--nc.pdf"
            unselected_strategy_plot = (
                experiment_dir / "figure" / "t2p-revision-delta-cdf--historyFinder--other.pdf"
            )
            unselected_tool_plot = experiment_dir / "figure" / "t2p-revision-delta-cdf--codeShovel--nc.pdf"

            self.assertTrue(selected_plot.exists())
            self.assertFalse(unselected_strategy_plot.exists())
            self.assertFalse(unselected_tool_plot.exists())

    def test_codeshovel_unsupported_change_still_generates_plot(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            experiment_dir = self.create_experiment(tmpdir)
            self.write_t2p_change_rows(experiment_dir, "codeShovel", "nc", "projectA")

            main(
                [
                    "--workspace-directory",
                    tmpdir,
                    "--experiment-name",
                    "demo",
                    "--tools",
                    "codeShovel",
                    "--strategies",
                    "nc",
                    "--projects",
                    "projectA",
                ]
            )

            self.assertTrue(
                (experiment_dir / "figure" / "t2p-revision-delta-cdf--codeShovel--nc.pdf").exists()
            )

    def create_experiment(self, workspace_dir: str) -> Path:
        experiment_dir = Path(workspace_dir) / "experiment" / "demo"
        (experiment_dir / "t2p-change").mkdir(parents=True)
        return experiment_dir

    def write_t2p_change_rows(
        self,
        experiment_dir: Path,
        tool: str,
        strategy: str,
        project: str,
    ) -> None:
        output_file = experiment_dir / "t2p-change" / tool / strategy / f"{project}.csv"
        output_file.parent.mkdir(parents=True, exist_ok=True)
        rows = [
            {
                "project": project,
                "from_ch_all": 5,
                "to_ch_all": 0,
                "from_ch_diff": 2,
                "to_ch_diff": 4,
                "from_ch_documentation": 1,
                "to_ch_documentation": 3,
            },
            {
                "project": project,
                "from_ch_all": 1,
                "to_ch_all": 1,
                "from_ch_diff": 0,
                "to_ch_diff": 1,
                "from_ch_documentation": 0,
                "to_ch_documentation": 2,
            },
            {
                "project": project,
                "from_ch_all": 0,
                "to_ch_all": 2,
                "from_ch_diff": 2,
                "to_ch_diff": 0,
                "from_ch_documentation": 4,
                "to_ch_documentation": 1,
            },
        ]
        pd.DataFrame(rows).to_csv(output_file, index=False)


if __name__ == "__main__":
    unittest.main()
