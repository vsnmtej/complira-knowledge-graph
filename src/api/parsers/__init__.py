"""
Scan format parsers.

Implements Strategy Pattern for scan format parsing:
- IScanParser protocol (DIP)
- BaseScanParser (DRY)
- SARIFParser (SARIF 2.1.0)
- CycloneDXParser (CycloneDX 1.4/1.5)
- ParserFactory (OCP)

SOLID Principles:
- SRP: Each parser handles one format only
- OCP: Add new parsers by extending BaseScanParser, no changes to service/factory
- LSP: All parsers substitutable via IScanParser interface
- ISP: IScanParser interface is minimal (parse, validate only)
- DIP: ScanIngestionService depends on IScanParser abstraction, not concrete parsers
"""
