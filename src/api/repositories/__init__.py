"""
Database access abstraction layer (repositories).

Implements Repository Pattern for clean database access:
- IRepository[T] protocol (DIP)
- Specific repositories per entity type
- CRUD operations abstraction
- Clear separation from business logic

SOLID Principles:
- SRP: Each repository handles one entity type only
- DIP: Services depend on IRepository abstraction
"""
