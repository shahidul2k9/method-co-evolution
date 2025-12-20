import argparse
import sys
from method_history_collector import *

def main():
    parser = argparse.ArgumentParser(description="Method History Collector (MHC)")

    parser.add_argument("command", type=str, help="Command to execute (e.g., history)")
    parser.add_argument("--cache_directory", type=str, required=True, help="Cache directory path")
    parser.add_argument("--repository_directory", type=str, required=True, help="Repository directory path")
    parser.add_argument("--data_directory", type=str, required=True, help="Data directory path")
    parser.add_argument("--jar_directory", type=str, required=True, help="Jar directory path")

    # Conditional args for history command
    parser.add_argument("--tool_name", type=str, help="Tool name (required for history command)")
    parser.add_argument("--repository_name", type=str, help="Repository name (required for history command)")

    args = parser.parse_args()

    mhc = MethodHistoryCollector(args.cache_directory, args.repository_directory, args.data_directory, "repository.csv",
                                 args.jar_directory)

    if args.command.lower() == "history":
        if not args.tool_name or not args.repository_name:
            print("Error: tool_name and repository_name are required for history command.")
            sys.exit(1)
        mhc.collect_method_history( [args.repository_name], [args.tool_name])
    else:
        print(f"Unknown command: {args.command}")
        sys.exit(1)


if __name__ == "__main__":
    main()
