import sys
import unittest
from unittest.mock import patch

import mhc.main as mhc_main
from mhc.config import *


class TestMhcScript(unittest.TestCase):
    @patch('mhc.main.MethodHistoryCollector')
    def test_history_command_success(self, mock_mhc_class):
        mock_mhc_instance = mock_mhc_class.return_value
        mock_mhc_instance.collect_method_history.return_value = None

        # Simulate command-line arguments
        test_args = [
            'main.py',  # argv[0] is the script name
            'history',  # command
            '--cache_directory', CACHE_DIRECTORY,
            '--repository_directory', REPOSITORY_DIRECTORY,
            '--data_directory', DATA_DIRECTORY,
            '--jar_directory', JAR_DIRECTORY,
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
        mock_mhc_class.assert_called_once_with(CACHE_DIRECTORY, REPOSITORY_DIRECTORY,
                                               DATA_DIRECTORY, JAR_DIRECTORY)

        # Check that collect_method_history was called with correct arguments
        mock_mhc_instance.collect_method_history.assert_called_once_with(['codeShovel'], ['checkstyle'])

    @patch('mhc.main.MethodHistoryCollector')
    def test_history_command_missing_tool_or_repo(self, mock_mhc_class):
        test_args = [
            'main.py',
            'history',
            '--cache_directory', CACHE_DIRECTORY,
            '--repository_directory', REPOSITORY_DIRECTORY,
            '--data_directory', DATA_DIRECTORY,
            '--jar_directory', JAR_DIRECTORY,
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
            '--cache_directory', CACHE_DIRECTORY,
            '--repository_directory', REPOSITORY_DIRECTORY,
            '--data_directory', DATA_DIRECTORY,
            '--jar_directory', JAR_DIRECTORY,
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
            '--cache_directory', CACHE_DIRECTORY,
            '--repository_directory', REPOSITORY_DIRECTORY,
            '--data_directory', DATA_DIRECTORY,
            '--jar_directory', JAR_DIRECTORY,
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
