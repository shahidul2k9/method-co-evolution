from pathlib import Path
import shutil
import sys
import tempfile
import unittest
import warnings

SRC_DIRECTORY = Path(__file__).resolve().parents[1] / "src"
MHC_SRC_DIRECTORY = Path(__file__).resolve().parents[2] / "method-history-collector" / "src"
for directory in (SRC_DIRECTORY, MHC_SRC_DIRECTORY):
    if str(directory) not in sys.path:
        sys.path.insert(0, str(directory))

try:
    import pandas as pd
except ImportError:  # pragma: no cover
    pd = None

from ptc.plot.revision_mww import main


@unittest.skipIf(pd is None, "pandas is required for revision_mwu plot tests")
class TestRevisionMwuPlot(unittest.TestCase):
    def test_generates_one_diff_table_per_tool(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            experiment_dir = self.create_experiment(tmpdir)
            self.write_revision_mwu_csv(experiment_dir)

            with warnings.catch_warnings(record=True) as caught_warnings:
                warnings.simplefilter("always")
                main(["--workspace-directory", tmpdir, "--experiment-name", "demo"])

            first_tex = experiment_dir / "figure" / "revision_mwu--historyFinder.tex"
            second_tex = experiment_dir / "figure" / "revision_mwu--codeShovel.tex"
            self.assertTrue(first_tex.exists())
            self.assertTrue(second_tex.exists())

            first_text = first_tex.read_text(encoding="utf-8")
            self.assertIn("projectA", first_text)
            self.assertIn("all", first_text)
            self.assertNotIn("projectOnlyAllChange", first_text)

            if shutil.which("pdflatex") is None:
                self.assertTrue(any("pdflatex not found" in str(warning.message) for warning in caught_warnings))
            else:
                self.assertTrue((experiment_dir / "figure" / "revision_mwu--historyFinder.pdf").exists())
                self.assertTrue((experiment_dir / "figure" / "revision_mwu--codeShovel.pdf").exists())

    def create_experiment(self, workspace_dir: str) -> Path:
        experiment_dir = Path(workspace_dir) / "experiment" / "demo"
        (experiment_dir / "aggregate").mkdir(parents=True)
        return experiment_dir

    def write_revision_mwu_csv(self, experiment_dir: Path) -> None:
        rows = [
            {
                "project": "projectA",
                "tool": "historyFinder",
                "change": "diff",
                "size": 6,
                "main_size": 3,
                "test_size": 3,
                "mwu_u1": 9,
                "mwu_u2": 0,
                "mwu_p": 0.1,
                "mwu_d": 1,
                "mwu_size": "large",
                "N": "",
                "S": "",
                "M": "",
                "L": "x",
            },
            {
                "project": "all",
                "tool": "historyFinder",
                "change": "diff",
                "size": 6,
                "main_size": 3,
                "test_size": 3,
                "mwu_u1": 9,
                "mwu_u2": 0,
                "mwu_p": 0.1,
                "mwu_d": 1,
                "mwu_size": "large",
                "N": "",
                "S": "",
                "M": "",
                "L": "x",
            },
            {
                "project": "projectOnlyAllChange",
                "tool": "historyFinder",
                "change": "all",
                "size": 6,
                "main_size": 3,
                "test_size": 3,
                "mwu_u1": 9,
                "mwu_u2": 0,
                "mwu_p": 0.1,
                "mwu_d": 1,
                "mwu_size": "large",
                "N": "",
                "S": "",
                "M": "",
                "L": "x",
            },
            {
                "project": "projectB",
                "tool": "codeShovel",
                "change": "diff",
                "size": 6,
                "main_size": 3,
                "test_size": 3,
                "mwu_u1": 9,
                "mwu_u2": 0,
                "mwu_p": 0.2,
                "mwu_d": 0.8,
                "mwu_size": "large",
                "N": "",
                "S": "",
                "M": "",
                "L": "x",
            },
        ]
        pd.DataFrame(rows).to_csv(experiment_dir / "aggregate" / "revision_mwu.csv", index=False)


if __name__ == "__main__":
    unittest.main()
