"""
Base parser classes and protocols.

Provides:
- ParsedFinding: Normalized finding schema (output of all parsers)
- ParsedScanData: Parser output model
- IScanParser: Parser protocol (DIP)
- BaseScanParser: Base parser with shared logic (DRY)
"""

from typing import Protocol, List, Dict, Any
from abc import ABC, abstractmethod
from pydantic import BaseModel
import structlog

logger = structlog.get_logger()


# ========== Data Models ==========


class ParsedFinding(BaseModel):
    """
    Normalized finding schema (output of all parsers).

    All parsers (SARIF, CycloneDX, etc.) convert to this common format.
    """
    cve_id: str
    severity: str  # CRITICAL, HIGH, MEDIUM, LOW, INFO, NONE, UNKNOWN
    description: str
    location: str  # File path or component@version
    tool_name: str
    scan_type: str  # "sarif" | "cyclonedx" | "osv" | "vex"
    raw_data: Dict[str, Any]  # Original finding for traceability


class ParsedScanData(BaseModel):
    """
    Parser output model.

    All parsers return this standardized structure.
    """
    tool_name: str
    tool_version: str
    scan_timestamp: str
    findings: List[ParsedFinding]
    components: List[Dict[str, Any]]  # SBOMs only (empty for SAST/DAST)
    metadata: Dict[str, Any]


# ========== Protocols (DIP) ==========


class IScanParser(Protocol):
    """
    Scan parser abstraction (DIP).

    All parsers must implement this interface.
    Allows ScanIngestionService to depend on abstraction, not concrete parsers.
    """

    def parse(self, payload: Dict[str, Any]) -> ParsedScanData:
        """Parse scan payload and return normalized data."""
        ...

    def validate(self, payload: Dict[str, Any]) -> bool:
        """Validate payload conforms to expected schema."""
        ...


# ========== Base Parser (DRY) ==========


class BaseScanParser(ABC):
    """
    Base parser with shared logic (DRY).

    All concrete parsers (SARIF, CycloneDX, etc.) extend this class.

    SOLID Principles:
    - SRP: Only parsing logic, no business logic or DB access
    - OCP: Extensible via inheritance, closed for modification
    - Template Method Pattern: Common validation/error handling
    """

    def __init__(self):
        """Initialize parser with error tracking."""
        self.errors: List[str] = []
        self.logger = structlog.get_logger(
            parser=self.__class__.__name__
        )

    @abstractmethod
    def parse(self, payload: Dict[str, Any]) -> ParsedScanData:
        """
        Parse scan payload.

        Implemented by subclasses (SARIFParser, CycloneDXParser, etc.).

        Args:
            payload: Raw scan payload (dict/JSON object)

        Returns:
            ParsedScanData: Normalized scan data

        Raises:
            ValueError: If payload is invalid or parsing fails
        """
        pass

    @abstractmethod
    def _extract_findings(self, payload: Dict[str, Any]) -> List[ParsedFinding]:
        """
        Extract findings from format-specific structure.

        Implemented by subclasses.

        Args:
            payload: Raw scan payload

        Returns:
            list: ParsedFinding objects
        """
        pass

    @abstractmethod
    def _extract_metadata(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        Extract tool metadata.

        Implemented by subclasses.

        Args:
            payload: Raw scan payload

        Returns:
            dict: Metadata (tool info, timestamps, etc.)
        """
        pass

    def validate(self, payload: Dict[str, Any]) -> bool:
        """
        Common validation logic (DRY).

        Subclasses can override for format-specific validation.

        Args:
            payload: Scan payload to validate

        Returns:
            bool: True if valid, False otherwise
        """
        self.errors = []  # Reset errors

        if not payload:
            self.errors.append("Payload is empty")
            return False

        if not isinstance(payload, dict):
            self.errors.append("Payload must be dict/JSON object")
            return False

        return True

    def _handle_parse_error(self, error: Exception, context: str) -> None:
        """
        Centralized error handling (DRY).

        Args:
            error: Exception that occurred
            context: Context string (e.g., "SARIF parsing")
        """
        error_msg = f"{context}: {type(error).__name__} - {str(error)}"
        self.errors.append(error_msg)
        self.logger.error(
            "Parser error",
            context=context,
            error=str(error),
            error_type=type(error).__name__,
        )
