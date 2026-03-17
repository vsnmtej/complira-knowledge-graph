#!/usr/bin/env python3
"""
Check for direct database access bypassing repositories.

This script enforces the Repository Pattern by detecting:
- Direct db.collection() calls outside repositories
- Direct ArangoClient instantiation outside core/database.py
- Direct client.db() calls outside core infrastructure

Usage:
    python scripts/check_direct_db_access.py

Exit codes:
    0 - No violations found
    1 - Violations detected
"""

import sys
import re
from pathlib import Path
from typing import List, Dict

# Patterns that indicate direct DB access
VIOLATION_PATTERNS = [
    (r'db\.collection\(', 'db.collection() - use repository instead'),
    (r'ArangoClient\(', 'ArangoClient() - use get_customer_db() or get_reference_db()'),
    (r'client\.db\(', 'client.db() - use get_customer_db() or get_reference_db()'),
    (r'\.insert\(', 'Direct .insert() - use repository.create()'),
    (r'\.update\(', 'Direct .update() - use repository.update()'),
    (r'\.delete\(', 'Direct .delete() - use repository.delete()'),
]

# Allowed files (infrastructure only)
ALLOWED_FILES = [
    'src/api/core/database.py',
    'src/api/repositories/base.py',
    'src/complira_graph/db.py',
]


def check_file(filepath: Path) -> List[Dict]:
    """
    Check file for direct database access violations.

    Args:
        filepath: Path to Python file to check

    Returns:
        List of violation dictionaries
    """
    # Skip allowed files
    if any(allowed in str(filepath) for allowed in ALLOWED_FILES):
        return []

    # Skip test files (they may mock database access)
    if 'test_' in filepath.name or '/tests/' in str(filepath):
        return []

    violations = []

    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            for line_num, line in enumerate(f, 1):
                # Skip comments
                if line.strip().startswith('#'):
                    continue

                for pattern, description in VIOLATION_PATTERNS:
                    if re.search(pattern, line):
                        violations.append({
                            'file': str(filepath.relative_to(Path.cwd())),
                            'line': line_num,
                            'content': line.strip(),
                            'pattern': pattern,
                            'description': description,
                        })

    except Exception as e:
        print(f"Error reading {filepath}: {e}", file=sys.stderr)

    return violations


def main():
    """Check all Python files for direct database access."""
    print("Checking for direct database access violations...")

    violations = []

    # Check src/api directory (most important)
    src_api = Path('src/api')
    if src_api.exists():
        for filepath in src_api.rglob('*.py'):
            violations.extend(check_file(filepath))

    # Check src/complira_graph directory
    src_graph = Path('src/complira_graph')
    if src_graph.exists():
        for filepath in src_graph.rglob('*.py'):
            violations.extend(check_file(filepath))

    if violations:
        print("\n❌ Direct database access detected:\n")

        # Group violations by file
        violations_by_file = {}
        for v in violations:
            file_path = v['file']
            if file_path not in violations_by_file:
                violations_by_file[file_path] = []
            violations_by_file[file_path].append(v)

        # Print violations
        for file_path, file_violations in violations_by_file.items():
            print(f"  {file_path}:")
            for v in file_violations:
                print(f"    Line {v['line']}: {v['description']}")
                print(f"      Code: {v['content']}")
            print()

        print("💡 How to fix:")
        print("  ✅ Use repositories for database access:")
        print("     customer_db = get_customer_db(customer_id)")
        print("     finding_repo = ScanFindingRepository(customer_db)")
        print("     findings = finding_repo.list(...)")
        print()
        print("  ✅ Create repository if it doesn't exist:")
        print("     class MyRepository(BaseRepository):")
        print("         def __init__(self, db):")
        print("             super().__init__(db, 'my_collection')")
        print()
        print(f"  Found {len(violations)} violation(s) in {len(violations_by_file)} file(s)")
        print()

        sys.exit(1)

    print("✅ No direct database access violations found")
    sys.exit(0)


if __name__ == '__main__':
    main()
