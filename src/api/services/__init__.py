"""
Business logic services layer.

All services extend BaseGraphService to inherit reusable graph traversal patterns.

SOLID Principles Applied:
- SRP: Each service has single responsibility (one feature)
- OCP: Services extend base without modifying it
- LSP: All services are substitutable via base class
- ISP: Services depend on specific interfaces (IDatabase, ICacheService)
- DIP: Services depend on abstractions, not concretions
"""
