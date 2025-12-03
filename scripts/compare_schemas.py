#!/usr/bin/env python3
"""Compare API schemas to detect breaking changes."""

import argparse
import json
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from hydroqc.schema_extractor import SchemaExtractor, compare_schemas


def load_schema_file(filepath: str) -> dict:
    """Load a schema file."""
    with open(filepath, "r", encoding="utf-8") as f:
        return json.load(f)


def print_differences(
    differences: list[dict],
    verbose: bool = False,
    previous_meta: dict = None,
    current_meta: dict = None,
) -> None:
    """Print schema differences in a readable format."""
    if not differences:
        print("✅ No differences found - schemas are identical")
        return

    # Print rate information if available
    if previous_meta and current_meta:
        prev_rate = f"{previous_meta.get('rate', '?')}"
        if previous_meta.get("rate_option") and previous_meta["rate_option"] != "NONE":
            prev_rate += f"-{previous_meta['rate_option']}"
        curr_rate = f"{current_meta.get('rate', '?')}"
        if current_meta.get("rate_option") and current_meta["rate_option"] != "NONE":
            curr_rate += f"-{current_meta['rate_option']}"

        if prev_rate != curr_rate:
            print(f"📌 Comparing different rates: {prev_rate} → {curr_rate}\n")

    # Group by severity
    high = [d for d in differences if d.get("severity") == "high"]
    medium = [d for d in differences if d.get("severity") == "medium"]
    low = [d for d in differences if d.get("severity") == "low"]

    print(f"\n📊 Found {len(differences)} differences:")
    print(f"  🔴 {len(high)} high severity (breaking changes)")
    print(f"  🟡 {len(medium)} medium severity")
    print(f"  🟢 {len(low)} low severity\n")

    if high:
        print("🔴 HIGH SEVERITY (Breaking Changes):")
        print("=" * 60)
        for diff in high:
            endpoint = diff.get("endpoint", "unknown")
            change_type = diff["type"]
            path = diff.get("path", "")

            if change_type == "TYPE_CHANGE":
                print(
                    f"  [{endpoint}] {path}: "
                    f"{diff['old_type']} → {diff['new_type']}"
                )
            elif change_type == "PROPERTY_REMOVED":
                print(f"  [{endpoint}] Removed: {path}")
            elif change_type == "ENDPOINT_REMOVED":
                print(f"  Endpoint removed: {endpoint}")
            else:
                print(f"  [{endpoint}] {change_type}: {diff}")
        print()

    if medium:
        print("🟡 MEDIUM SEVERITY:")
        print("=" * 60)
        for diff in medium:
            endpoint = diff.get("endpoint", "unknown")
            change_type = diff["type"]
            path = diff.get("path", "")

            if change_type == "FORMAT_CHANGE":
                print(
                    f"  [{endpoint}] {path}: "
                    f"format {diff.get('old_format')} → {diff.get('new_format')}"
                )
            else:
                print(f"  [{endpoint}] {change_type}: {diff}")
        print()

    if low and verbose:
        print("🟢 LOW SEVERITY (New features):")
        print("=" * 60)
        for diff in low:
            endpoint = diff.get("endpoint", "unknown")
            change_type = diff["type"]
            path = diff.get("path", "")

            if change_type == "PROPERTY_ADDED":
                print(f"  [{endpoint}] New field: {path}")
            elif change_type == "ENDPOINT_ADDED":
                print(f"  New endpoint: {endpoint}")
            else:
                print(f"  [{endpoint}] {change_type}: {diff}")
        print()


def create_issue_body(differences: list[dict]) -> str:
    """Create GitHub issue body from differences."""
    high = [d for d in differences if d.get("severity") == "high"]
    medium = [d for d in differences if d.get("severity") == "medium"]
    low = [d for d in differences if d.get("severity") == "low"]

    body = "# 🚨 API Schema Changes Detected\n\n"
    body += "The automated schema monitor detected changes in the Hydro-Québec API.\n\n"

    body += f"## Summary\n\n"
    body += f"- 🔴 **{len(high)} breaking changes** (high severity)\n"
    body += f"- 🟡 **{len(medium)} potential issues** (medium severity)\n"
    body += f"- 🟢 **{len(low)} new features** (low severity)\n\n"

    if high:
        body += "## 🔴 Breaking Changes\n\n"
        body += "These changes may break existing integrations:\n\n"
        for diff in high:
            endpoint = diff.get("endpoint", "unknown")
            change_type = diff["type"]
            path = diff.get("path", "")

            if change_type == "TYPE_CHANGE":
                body += f"- **[{endpoint}]** `{path}`: Type changed from `{diff['old_type']}` to `{diff['new_type']}`\n"
            elif change_type == "PROPERTY_REMOVED":
                body += f"- **[{endpoint}]** Property removed: `{path}`\n"
            elif change_type == "ENDPOINT_REMOVED":
                body += f"- **Endpoint removed:** `{endpoint}`\n"
        body += "\n"

    if medium:
        body += "## 🟡 Format Changes\n\n"
        for diff in medium:
            endpoint = diff.get("endpoint", "unknown")
            path = diff.get("path", "")
            body += f"- **[{endpoint}]** `{path}`: Format changed\n"
        body += "\n"

    body += "## Action Required\n\n"
    body += "1. Review the changes above\n"
    body += "2. Update code to handle new schema\n"
    body += "3. Update tests\n"
    body += "4. Test with real account data\n"
    body += "5. Update documentation if needed\n\n"

    body += "## Details\n\n"
    body += "<details>\n<summary>Full diff JSON</summary>\n\n```json\n"
    body += json.dumps(differences, indent=2)
    body += "\n```\n</details>\n"

    return body


def parse_args() -> argparse.Namespace:
    """Parse CLI arguments."""
    parser = argparse.ArgumentParser(description="Compare API schemas")
    parser.add_argument(
        "--previous",
        default="schemas/archive",
        help="Previous schema file or directory (default: schemas/archive)",
    )
    parser.add_argument(
        "--current",
        default="schemas/latest/api_schemas.json",
        help="Current schema file (default: schemas/latest/api_schemas.json)",
    )
    parser.add_argument(
        "--verbose", "-v", action="store_true", help="Show all differences"
    )
    parser.add_argument(
        "--create-issue",
        action="store_true",
        help="Create GitHub issue body file if breaking changes found",
    )
    parser.add_argument(
        "--output-format",
        choices=["text", "json", "github"],
        default="text",
        help="Output format (default: text)",
    )

    return parser.parse_args()


def main() -> int:
    """Main entry point."""
    args = parse_args()

    # Find previous schema
    previous_path = Path(args.previous)
    if previous_path.is_dir():
        # Find latest file in directory
        schema_files = sorted(previous_path.glob("*_api_schemas.json"))
        if not schema_files:
            print(f"❌ No schema files found in {previous_path}", file=sys.stderr)
            return 1
        previous_file = str(schema_files[-1])
        print(f"Comparing with: {previous_file}")
    else:
        previous_file = str(previous_path)

    # Load schemas
    try:
        previous_data = load_schema_file(previous_file)
        current_data = load_schema_file(args.current)
    except FileNotFoundError as e:
        print(f"❌ Schema file not found: {e}", file=sys.stderr)
        return 1

    # Compare all endpoints
    all_differences = []

    for endpoint_name, current_schema in current_data["schemas"].items():
        if endpoint_name in previous_data["schemas"]:
            diffs = compare_schemas(
                previous_data["schemas"][endpoint_name], current_schema
            )
            for diff in diffs:
                diff["endpoint"] = endpoint_name
                all_differences.append(diff)
        else:
            all_differences.append(
                {"type": "ENDPOINT_ADDED", "endpoint": endpoint_name, "severity": "low"}
            )

    # Check for removed endpoints
    for endpoint_name in previous_data["schemas"]:
        if endpoint_name not in current_data["schemas"]:
            all_differences.append(
                {
                    "type": "ENDPOINT_REMOVED",
                    "endpoint": endpoint_name,
                    "severity": "high",
                }
            )

    # Output results
    if args.output_format == "json":
        print(json.dumps(all_differences, indent=2))
    elif args.output_format == "github":
        print(create_issue_body(all_differences))
    else:
        print_differences(
            all_differences,
            args.verbose,
            previous_data.get("metadata"),
            current_data.get("metadata"),
        )

    # Create GitHub issue file if requested and breaking changes found
    if args.create_issue:
        high_severity = [d for d in all_differences if d.get("severity") == "high"]
        if high_severity:
            issue_body = create_issue_body(all_differences)
            with open("schema_diff_issue.md", "w", encoding="utf-8") as f:
                f.write(issue_body)
            print("\n📝 Created schema_diff_issue.md for GitHub issue")

            # Output for GitHub Actions
            print("::set-output name=has_breaking_changes::true")
        else:
            print("::set-output name=has_breaking_changes::false")

    # Return exit code based on severity
    if any(d.get("severity") == "high" for d in all_differences):
        return 2  # Breaking changes
    elif any(d.get("severity") == "medium" for d in all_differences):
        return 1  # Warnings
    return 0  # No issues


if __name__ == "__main__":
    sys.exit(main())
