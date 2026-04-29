from pathlib import Path
import sys
import unittest

SRC_DIRECTORY = Path(__file__).resolve().parents[1] / "src"
if str(SRC_DIRECTORY) not in sys.path:
    sys.path.insert(0, str(SRC_DIRECTORY))

from ptc.generator.t2p_link_evaluation import aggregate_project_groups


class TestT2PLinkEvaluation(unittest.TestCase):
    def test_aggregate_groups_use_tctracer_label_for_exact_tctracer_projects(self):
        groups = aggregate_project_groups({"commons-io", "commons-lang", "gson", "jfreechart"})

        self.assertEqual(["avg-tctracer"], [name for name, _ in groups])

    def test_aggregate_groups_add_tctracer_when_subset_is_available(self):
        groups = aggregate_project_groups({"commons-io", "commons-lang", "gson", "jfreechart", "jenkins"})

        self.assertEqual(["avg-tctracer"], [name for name, _ in groups])

    def test_aggregate_groups_use_testlinker_label_for_exact_testlinker_projects(self):
        groups = aggregate_project_groups({"commons-io", "commons-lang", "gson", "jfreechart", "dubbo", "jenkins"})

        self.assertEqual(["avg-tctracer", "avg-testlinker"], [name for name, _ in groups])

    def test_aggregate_groups_add_both_benchmark_subsets_when_available(self):
        groups = aggregate_project_groups(
            {"commons-io", "commons-lang", "gson", "jfreechart", "dubbo", "jenkins", "ant"}
        )

        self.assertEqual(["avg-tctracer", "avg-testlinker"], [name for name, _ in groups])

    def test_aggregate_groups_use_avg_when_no_benchmark_group_is_present(self):
        groups = aggregate_project_groups({"ant", "gson"})

        self.assertEqual(["avg"], [name for name, _ in groups])


if __name__ == "__main__":
    unittest.main()
