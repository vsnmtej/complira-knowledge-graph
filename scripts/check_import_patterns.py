#!/usr/bin/env python3
"""
Validate import patterns - ensure proper separation of concerns.

This script enforces architectural boundaries by detecting:
- Endpoints importing repositories (should use services)
- Services importing endpoints (circular dependency)
- Parsers importing services/repositories (should be pure)

Usage:
    python scripts/check_import_patterns.py

Exit codes:
    0 - No violations found
    1 - Violations detected
"""

import sys
import re
from pathlib import Path
from typing import List, Dict, Tuple

# Import restrictions: directory -> (pattern, error message)
RESTRICTIONS: Dict[str, List[Tuple[str, str]]] = {
    # Endpoints should NOT import repositories directly
    'src/api/v1/endpoints/': [
        (r'from api\.repositories(?:\.[\w]+)? import', 'Endpoints should use services, not repositories directly'),
        (r'from arango import', 'Endpoints should not access database directly'),
        (r'import arango', 'Endpoints should not access database directly'),
    ],

    # Services should NOT import endpoints
    'src/api/services/': [
        (r'from api\.v1\.endpoints(?:\.[\w]+)? import', 'Services should not import endpoints (circular dependency)'),
        (r'from fastapi import.*APIRouter', 'Services should not define routes (use endpoints)'),
        (r'@router\.', 'Services should not define routes (use endpoints)'),
    ],

    # Parsers should NOT import services/repositories
    'src/api/parsers/': [
        (r'from api\.services(?:\.[\w]+)? import', 'Parsers should not import services (pure data transformation)'),
        (r'from api\.repositories(?:\.[\w]+)? import', 'Parsers should not import repositories (pure data transformation)'),
        (r'from arango import', 'Parsers should not access database'),
    ],

    # Repositories should NOT import services/endpoints
    'src/api/repositories/': [
        (r'from api\.services(?:\.[\w]+)? import', 'Repositories should not import services (circular dependency)'),
        (r'from api\.v1\.endpoints(?:\.[\w]+)? import', 'Repositories should not import endpoints'),
    ],
}


def check_file(filepath: Path) -> List[Dict]:
    """
    Check file for import pattern violations.

    Args:
        filepath: Path to Python file to check

    Returns:
        List of violation dictionaries
    """
    violations = []

    # Find applicable restrictions
    applicable_restrictions = []
    for path_prefix, restrictions in RESTRICTIONS.items():
        if path_prefix in str(filepath):
            applicable_restrictions = restrictions
            break

    if not applicable_restrictions:
        return []

    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            for line_num, line in enumerate(f, 1):
                # Skip comments
                if line.strip().startswith('#'):
                    continue

                for pattern, message in applicable_restrictions:
                    if re.search(pattern, line):
                        violations.append({
                            'file': str(filepath.relative_to(Path.cwd())),
                            'line': line_num,
                            'content': line.strip(),
                            'pattern': pattern,
                            'message': message,
                        })

    except Exception as e:
        print(f"Error reading {filepath}: {e}", file=sys.stderr)

    return violations


def main():
    """Check all Python files for import pattern violations."""
    print("Checking import patterns...")

    violations = []

    # Check src/api directory
    src_api = Path('src/api')
    if src_api.exists():
        for filepath in src_api.rglob('*.py'):
            # Skip test files
            if 'test_' in filepath.name or '/tests/' in str(filepath):
                continue

            violations.extend(check_file(filepath))

    if violations:
        print("\n❌ Import pattern violations detected:\n")

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
                print(f"    Line {v['line']}: {v['message']}")
                print(f"      Code: {v['content']}")
            print()

        print("💡 How to fix:")
        print()
        print("  ✅ Endpoint importing repository:")
        print("     BAD:  from api.repositories.scan import ScanRepository")
        print("     GOOD: from api.services.scan import ScanService")
        print()
        print("  ✅ Service importing endpoint:")
        print("     BAD:  from api.v1.endpoints.scan import router")
        print("     GOOD: Services should not know about endpoints")
        print()
        print("  ✅ Parser importing service:")
        print("     BAD:  from api.services.scan import ScanService")
        print("     GOOD: Parsers should be pure - no dependencies")
        print()
        print(f"  Found {len(violations)} violation(s) in {len(violations_by_file)} file(s)")
        print()

        sys.exit(1)

    print("✅ No import pattern violations found")
    sys.exit(0)


if __name__ == '__main__':
    main()
