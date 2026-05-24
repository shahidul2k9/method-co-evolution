from pathlib import Path
import sys
import unittest

SRC_DIRECTORY = Path(__file__).resolve().parents[1] / "src"
if str(SRC_DIRECTORY) not in sys.path:
    sys.path.insert(0, str(SRC_DIRECTORY))

from ptc.experiment_util import build_experiment_parser


class TestExperimentParser(unittest.TestCase):
    def test_replace_option_defaults_to_true_when_included(self):
        parser = build_experiment_parser(
            "demo",
            include_replace=True,
        )

        args = parser.parse_args([])

        self.assertTrue(args.replace)

    def test_replace_option_parses_true(self):
        parser = build_experiment_parser(
            "demo",
            include_replace=True,
        )

        args = parser.parse_args(["--replace"])

        self.assertTrue(args.replace)

    def test_no_replace_option_parses_false(self):
        parser = build_experiment_parser(
            "demo",
            include_replace=True,
        )

        args = parser.parse_args(["--no-replace"])

        self.assertFalse(args.replace)

    def test_replace_option_is_absent_by_default(self):
        parser = build_experiment_parser("demo")

        args = parser.parse_args([])

        self.assertFalse(hasattr(args, "replace"))


if __name__ == "__main__":
    unittest.main()
