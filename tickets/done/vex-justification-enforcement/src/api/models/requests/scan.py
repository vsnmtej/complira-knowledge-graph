"""
Scan ingestion request models.
"""

from typing import Literal, Dict, Any
from pydantic import BaseModel, Field


class ScanIngestRequest(BaseModel):
    """
    Request model for POST /v1/scan/ingest.

    Accepts scan results in multiple formats and ingests them into the graph.
    """

    format: Literal["sarif", "cyclonedx", "csv", "json"] = Field(
        ...,
        description="Scanner output format (sarif, cyclonedx, csv, json)"
    )

    scan_type: Literal["sast", "dast", "sca", "container", "sbom", "iac"] = Field(
        ...,
        description="Type of scan (sast=Static Analysis, dast=Dynamic Analysis, sca=Software Composition Analysis, container=Container Scan, sbom=Software Bill of Materials, iac=Infrastructure as Code)"
    )

    payload: Dict[str, Any] = Field(
        ...,
        description="Scanner output (JSON object). For SARIF, this is the full SARIF JSON. For CycloneDX, this is the full SBOM JSON."
    )

    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Optional scan metadata (repository URL, commit SHA, branch, PR number, etc.)"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "format": "sarif",
                "scan_type": "sast",
                "payload": {
                    "version": "2.1.0",
                    "$schema": "https://json.schemastore.org/sarif-2.1.0.json",
                    "runs": [
                        {
                            "tool": {
                                "driver": {
                                    "name": "Semgrep",
                                    "version": "1.0.0"
                                }
                            },
                            "results": [
                                {
                                    "ruleId": "CVE-2021-44228",
                                    "level": "error",
                                    "message": {
                                        "text": "Log4Shell vulnerability detected"
                                    },
                                    "locations": [
                                        {
                                            "physicalLocation": {
                                                "artifactLocation": {
                                                    "uri": "src/main/java/App.java"
                                                },
                                                "region": {
                                                    "startLine": 42
                                                }
                                            }
                                        }
                                    ]
                                }
                            ]
                        }
                    ]
                },
                "metadata": {
                    "repository": "https://github.com/org/repo",
                    "commit_sha": "abc123",
                    "branch": "main"
                }
            }
        }
