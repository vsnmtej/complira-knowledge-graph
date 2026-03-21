"""
Parser factory (OCP).

Factory pattern for creating appropriate parser based on scan format.

To add new parser (e.g., OSV, VEX):
1. Implement new parser class extending BaseScanParser
2. Register in _parsers dict
3. No changes needed in ScanIngestionService (OCP)
"""

from typing import Dict
from api.parsers.base import IScanParser
from api.parsers.sarif import SARIFParser
from api.parsers.cyclonedx import CycloneDXParser
from api.parsers.grype_analyzer import GryperAnalyzer
import structlog

logger = structlog.get_logger()


class ParserFactory:
    """
    Factory for creating appropriate parser based on scan format (OCP).

    Supports:
    - sarif: SARIF 2.1.0 (SAST/DAST tools)
    - cyclonedx: CycloneDX 1.4/1.5 (SBOM/SCA tools)
    - grype: Grype native JSON (fix.state → scanner_vex_status)

    Future:
    - osv: OSV (Open Source Vulnerabilities)
    - vex: VEX (Vulnerability Exploitability eXchange)
    - csaf: CSAF (Common Security Advisory Framework)
    """

    _parsers: Dict[str, type] = {
        "sarif": SARIFParser,
        "cyclonedx": CycloneDXParser,
        "grype": GryperAnalyzer,      # Grype native JSON (fix.state → scanner_vex_status)
        # Future parsers:
        # "osv": OSVParser,
        # "vex": VEXParser,
        # "csaf": CSAFParser,
    }

    @classmethod
    def get_parser(cls, format: str) -> IScanParser:
        """
        Get parser for specified format.

        Args:
            format: Scan format (sarif, cyclonedx, etc.)

        Returns:
            IScanParser: Parser instance for the format

        Raises:
            ValueError: If format is not supported

        Example:
            parser = ParserFactory.get_parser("sarif")
            parsed_data = parser.parse(payload)
        """
        parser_class = cls._parsers.get(format.lower())

        if not parser_class:
            supported = list(cls._parsers.keys())
            logger.error(
                "Unsupported scan format",
                format=format,
                supported=supported,
            )
            raise ValueError(
                f"Unsupported scan format: {format}. Supported: {supported}"
            )

        logger.debug(
            "Creating parser",
            format=format,
            parser_class=parser_class.__name__,
        )

        return parser_class()

    @classmethod
    def register_parser(cls, format: str, parser_class: type) -> None:
        """
        Register custom parser (extensibility).

        Allows adding new parsers at runtime without modifying factory code.

        Args:
            format: Format identifier (e.g., "osv", "vex")
            parser_class: Parser class (must implement IScanParser)

        Example:
            ParserFactory.register_parser("osv", OSVParser)
        """
        logger.info(
            "Registering custom parser",
            format=format,
            parser_class=parser_class.__name__,
        )

        cls._parsers[format.lower()] = parser_class

    @classmethod
    def supported_formats(cls) -> list:
        """
        Get list of supported scan formats.

        Returns:
            list: Supported format identifiers

        Example:
            formats = ParserFactory.supported_formats()
            # ["sarif", "cyclonedx"]
        """
        return list(cls._parsers.keys())

    @classmethod
    def is_supported(cls, format: str) -> bool:
        """
        Check if format is supported.

        Args:
            format: Format identifier

        Returns:
            bool: True if format is supported

        Example:
            if ParserFactory.is_supported("sarif"):
                parser = ParserFactory.get_parser("sarif")
        """
        return format.lower() in cls._parsers
