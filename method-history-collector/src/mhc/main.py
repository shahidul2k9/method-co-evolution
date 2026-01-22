import argparse
import sys
from mhc.method_history_collector import *


def main():
    parser = argparse.ArgumentParser(description="Method History Collector (MHC)")

    parser.add_argument("command", type=str, help="Command to execute (e.g., history, call-graph)")
    parser.add_argument("--cache_directory", type=str, required=True, help="Cache directory path")
    parser.add_argument("--repository_directory", type=str, required=True, help="Repository directory path")
    parser.add_argument("--data_directory", type=str, required=True, help="Data directory path")
    parser.add_argument("--jar_directory", type=str, required=True, help="Jar directory path")

    # Conditional args for history command
    parser.add_argument("--tool_name", type=str, help="Tool name (required for history command)")
    parser.add_argument("--repository_name", type=str, help="Repository name (required for history command)")

    args = parser.parse_args()

    mhc = MethodHistoryCollector(args.cache_directory, args.repository_directory, args.data_directory,
                                 args.jar_directory)

    if args.command.lower() == "history":
        if not args.tool_name or not args.repository_name:
            print("Error: tool_name and repository_name are required for history command.")
            sys.exit(1)
        mhc.collect_method_history([args.repository_name], [args.tool_name])
    elif args.command.lower() == "call-graph":
        if not args.tool_name or not args.repository_name:
            print("Error: tool_name and repository_name are required for call graph command.")
            sys.exit(1)
        mhc.generate_call_graph([args.repository_name], [args.tool_name])
    elif args.command.lower() == "scan-method":
        if not args.repository_name:
            print("Error: repository_name are required to scan methods.")
            sys.exit(1)
        mhc.scan_method([args.repository_name])
    elif args.command.lower() == "index":
        mhc.update_repository_index()
    else:
        print(f"Unknown command: {args.command}")
        sys.exit(1)


if __name__ == "__main__":
    main()
