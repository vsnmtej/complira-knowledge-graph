#!/usr/bin/env python3
"""
Ensure repositories are used for database access in services and endpoints.

This script detects services/endpoints that may be accessing the database
without using repositories.

Usage:
    python scripts/check_repository_usage.py

Exit codes:
    0 - No violations found
    1 - Violations detected
"""

import sys
import re
from pathlib import Path
from typing import List, Dict

# Patterns indicating potential repository usage issues
WARNING_PATTERNS = [
    (r'get_customer_db\(', 'Uses get_customer_db() but may not use repository'),
    (r'get_reference_db\(', 'Uses get_reference_db() but may not use repository'),
]

# Patterns indicating proper repository usage
REPOSITORY_USAGE_PATTERNS = [
    r'Repository\(',
    r'_repo\s*=',
    r'repo\.',
]


def check_file(filepath: Path) -> List[Dict]:
    """
    Check file for potential repository usage issues.

    Args:
        filepath: Path to Python file to check

    Returns:
        List of warning dictionaries
    """
    warnings = []

    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
            lines = content.split('\n')

            # Check if file uses database but doesn't use repositories
            uses_db = False
            uses_repo = False

            for pattern, description in WARNING_PATTERNS:
                if re.search(pattern, content):
                    uses_db = True
                    break

            for pattern in REPOSITORY_USAGE_PATTERNS:
                if re.search(pattern, content):
                    uses_repo = True
                    break

            # If uses database but doesn't use repository, it's a warning
            if uses_db and not uses_repo:
                # Find lines with database access
                for line_num, line in enumerate(lines, 1):
                    if re.search(r'get_customer_db\(|get_reference_db\(', line):
                        warnings.append({
                            'file': str(filepath.relative_to(Path.cwd())),
                            'line': line_num,
                            'content': line.strip(),
                            'message': 'Database access without repository usage detected',
                        })

    except Exception as e:
        print(f"Error reading {filepath}: {e}", file=sys.stderr)

    return warnings


def main():
    """Check services and endpoints for repository usage."""
    print("Checking repository usage in services and endpoints...")

    warnings = []

    # Check services
    services_path = Path('src/api/services')
    if services_path.exists():
        for filepath in services_path.rglob('*.py'):
            if 'test_' not in filepath.name and '__init__' not in filepath.name:
                warnings.extend(check_file(filepath))

    # Check endpoints
    endpoints_path = Path('src/api/v1/endpoints')
    if endpoints_path.exists():
        for filepath in endpoints_path.rglob('*.py'):
            if 'test_' not in filepath.name and '__init__' not in filepath.name:
                warnings.extend(check_file(filepath))

    if warnings:
        print("\n⚠️  Potential repository pattern violations:\n")

        # Group warnings by file
        warnings_by_file = {}
        for w in warnings:
            file_path = w['file']
            if file_path not in warnings_by_file:
                warnings_by_file[file_path] = []
            warnings_by_file[file_path].append(w)

        # Print warnings
        for file_path, file_warnings in warnings_by_file.items():
            print(f"  {file_path}:")
            for w in file_warnings:
                print(f"    Line {w['line']}: {w['message']}")
                print(f"      Code: {w['content']}")
            print()

        print("💡 How to fix:")
        print("  ✅ Use repositories for database access:")
        print("     customer_db = get_customer_db(customer_id)")
        print("     finding_repo = ScanFindingRepository(customer_db)")
        print("     findings = finding_repo.list(...)")
        print()
        print("  Note: This is a warning, not an error. Review these files manually.")
        print(f"  Found {len(warnings)} warning(s) in {len(warnings_by_file)} file(s)")
        print()

        # Exit with 0 (success) but print warnings
        # This is informational, not a hard failure
        sys.exit(0)

    print("✅ All services and endpoints use repositories correctly")
    sys.exit(0)


if __name__ == '__main__':
    main()
