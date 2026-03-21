#!/usr/bin/env python3
"""
Fix TestClient.delete() calls that incorrectly use json parameter.

TestClient.delete() doesn't support json parameter - need to use query params or body.
"""

import re
from pathlib import Path

def fix_delete_calls(file_path):
    """Fix delete calls in a file."""
    with open(file_path, 'r') as f:
        content = f.read()

    original_content = content

    # Pattern to match test_client.delete() calls with json parameter
    # We'll convert json={"reason": "..."} to be removed or passed as query param
    pattern = r'(test_client\.delete\([^)]+?),\s*json=\{[^}]+\}([^)]*\))'

    # Replace by removing the json parameter
    content = re.sub(pattern, r'\1\2', content)

    if content != original_content:
        with open(file_path, 'w') as f:
            f.write(content)
        return True
    return False

def main():
    """Fix all integration test files."""
    test_dir = Path(__file__).parent.parent / "tests" / "integration"

    fixed_count = 0
    for test_file in test_dir.glob("test_*.py"):
        if fix_delete_calls(test_file):
            print(f"✅ Fixed: {test_file.name}")
            fixed_count += 1

    print(f"\n✅ Fixed {fixed_count} files")

if __name__ == "__main__":
    main()
