import sys
import unittest
from unittest.mock import patch

import main as mhc_main
import os


class TestMhcScript(unittest.TestCase):
    def setUp(self):
        self.cache_dir = os.environ.get("METHOD_CO_EVOLUTION_CACHE_DIRECTORY")

    @patch('mhc.main.MethodHistoryCollector')
    def test_history_command_success(self, mock_mhc_class):
        mock_mhc_instance = mock_mhc_class.return_value
        mock_mhc_instance.collect_method_history.return_value = None

        # Simulate command-line arguments
        test_args = [
            'main.py',  # argv[0] is the script name
            'history',  # command
            '--cache_directory', self.cache_dir,
            '--repository_directory', f'{self.cache_dir}/repository',
            '--data_directory', f'{self.cache_dir}/data',
            '--jar_directory', f'{self.cache_dir}/jar',
            '--tool_name', 'codeShovel',
            '--repository_name', 'checkstyle'
        ]

        with patch.object(sys, 'argv', test_args):
            # Should run without raising SystemExit
            try:
                mhc_main.main()
            except SystemExit as e:
                self.fail(f"main() exited unexpectedly with {e}")

        # Check that the collector was initialized with correct paths
        mock_mhc_class.assert_called_once_with(f'{self.cache_dir}', f'{self.cache_dir}/repository',
                                               f'{self.cache_dir}/data', f'{self.cache_dir}/jar')

        # Check that collect_method_history was called with correct arguments
        mock_mhc_instance.collect_method_history.assert_called_once_with(['codeShovel'], ['checkstyle'])

    @patch('mhc.main.MethodHistoryCollector')
    def test_history_command_missing_tool_or_repo(self, mock_mhc_class):
        test_args = [
            'main.py',
            'history',
            '--cache_directory', self.cache_dir,
            '--repository_directory', f'{self.cache_dir}/repository',
            '--data_directory', f'{self.cache_dir}/data',
            '--jar_directory', f'{self.cache_dir}/jar',
            # Missing --tool_name and --repository_name
        ]

        with patch.object(sys, 'argv', test_args):
            with self.assertRaises(SystemExit) as cm:
                mhc_main.main()
            self.assertEqual(cm.exception.code, 1)

    @patch('mhc.main.MethodHistoryCollector')
    def test_unknown_command(self, mock_mhc_class):
        test_args = [
            'main.py',
            'unknown',
            '--cache_directory', self.cache_dir,
            '--repository_directory', f'{self.cache_dir}/repository',
            '--data_directory', f'{self.cache_dir}/data',
            '--jar_directory', f'{self.cache_dir}/jar',
        ]

        with patch.object(sys, 'argv', test_args):
            with self.assertRaises(SystemExit) as cm:
                mhc_main.main()
            self.assertEqual(cm.exception.code, 1)

    @patch('mhc.main.MethodHistoryCollector')
    def test_call_graph_generation(self, mock_mhc_class):
        mock_mhc_instance = mock_mhc_class.return_value
        mock_mhc_instance.collect_method_history.return_value = None

        test_args = [
            'main.py',  # argv[0] is the script name
            'call-graph',
            '--cache_directory', self.cache_dir,
            '--repository_directory', f'{self.cache_dir}/repository',
            '--data_directory', f'{self.cache_dir}/data',
            '--jar_directory', f'{self.cache_dir}/jar',
            '--tool_name', 'methodParser',
            '--repository_name', 'checkstyle'
        ]

        with patch.object(sys, 'argv', test_args):
            try:
                mhc_main.main()
            except SystemExit as e:
                self.fail(f"main() exited unexpectedly with {e}")


if __name__ == '__main__':
    unittest.main()
