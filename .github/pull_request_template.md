# Pull Request

## Description

<!-- Describe your changes in detail -->

## Type of Change

- [ ] New feature (non-breaking change which adds functionality)
- [ ] Bug fix (non-breaking change which fixes an issue)
- [ ] Breaking change (fix or feature that would cause existing functionality to not work as expected)
- [ ] Documentation update
- [ ] Refactoring (no functional changes)

## Related Issues

<!-- Link to related issues, e.g., "Closes #123" -->

---

## Architectural Review Checklist

### General
- [ ] Code is in the correct directory (parsers/repositories/services/endpoints)
- [ ] No duplicate logic (DRY principle followed)
- [ ] Follows existing patterns (no ad-hoc implementations)
- [ ] Code is self-documenting with clear names and docstrings

### Repository Pattern
- [ ] All database access uses repositories
- [ ] No `db.collection()` calls in services/endpoints
- [ ] Repository extends `BaseRepository`
- [ ] Repository methods are tested

### Service Layer
- [ ] Business logic is in services, not endpoints
- [ ] Service extends `BaseGraphService` (if using graph operations)
- [ ] Service receives dependencies via constructor
- [ ] Service methods are unit tested

### Multi-Tenant Database
- [ ] Customer data uses `get_customer_db(customer_id)`
- [ ] Reference data uses `get_reference_db()`
- [ ] No hard-coded database names
- [ ] No mixing customer data in reference DB

### Parser Pattern (if applicable)
- [ ] New parsers registered in `ParserFactory`
- [ ] Parser extends `BaseScanParser`
- [ ] Parser returns `ParsedScanData`
- [ ] No direct parser instantiation in services

### Testing
- [ ] Unit tests for new repositories
- [ ] Unit tests for new services
- [ ] Integration tests for new endpoints
- [ ] Architecture tests pass (`pytest tests/architecture/`)
- [ ] All tests pass (`pytest tests/`)
- [ ] Test coverage is adequate (>80% for new code)

### Code Quality
- [ ] Pre-commit hooks pass
- [ ] No linting errors (`ruff check`)
- [ ] Code is formatted (`black`, `isort`)
- [ ] Type hints added where appropriate
- [ ] No security issues (`bandit`)

### Documentation
- [ ] Docstrings for public methods
- [ ] README updated (if new feature)
- [ ] API docs updated (if new endpoint)
- [ ] Architectural governance followed

---

## How to Test

<!-- Describe how reviewers can test your changes -->

```bash
# Example commands to test the changes
pytest tests/unit/services/test_my_service.py -v
```

---

## Screenshots (if applicable)

<!-- Add screenshots to help explain your changes -->

---

## Additional Notes

<!-- Any additional information for reviewers -->

---

## Reviewer Guidelines

### Red Flags to Watch For

- [ ] Direct database access (`db.collection()`) in services/endpoints
- [ ] Business logic in endpoints (should be in services)
- [ ] Hard-coded database names
- [ ] Direct parser instantiation (`SARIFParser()` instead of factory)
- [ ] Copy-pasted code (violates DRY)
- [ ] Missing tests
- [ ] Missing docstrings

### Questions to Ask

1. Is the code in the right place?
2. Does it follow established patterns?
3. Is there any code duplication?
4. Are abstractions used correctly?
5. Is customer data properly isolated?
6. Are there tests?
7. Is the code self-documenting?

---

**By submitting this PR, I confirm that:**
- [ ] I have read the [Architectural Governance Guide](../docs/ARCHITECTURAL_GOVERNANCE.md)
- [ ] I have followed the patterns outlined in [CONTRIBUTING.md](../CONTRIBUTING.md)
- [ ] I have tested my changes locally
- [ ] I have added appropriate tests
- [ ] Pre-commit hooks pass without errors
