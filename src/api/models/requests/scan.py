"""
Scan ingestion request models.
"""

from typing import Literal, Dict, List, Union, Any, Optional
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

    scan_type: Literal["sast", "dast", "sca", "container", "sbom", "iac", "cspm"] = Field(
        ...,
        description="Type of scan (sast=Static Analysis, dast=Dynamic Analysis, sca=Software Composition Analysis, container=Container Scan, sbom=Software Bill of Materials, iac=Infrastructure as Code, cspm=Cloud Security Posture Management)"
    )

    payload: Union[Dict[str, Any], List[Any]] = Field(
        ...,
        description="Scanner output. JSON object for most tools; JSON array for Prowler and other tools that output a top-level array."
    )

    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Optional scan metadata (repository URL, commit SHA, branch, PR number, etc.)"
    )

    project_id: Optional[str] = Field(
        None,
        description="Optional project ID to associate this scan with a project"
    )

    repository_id: Optional[str] = Field(
        None,
        description="Optional repository ID to associate this scan with a repository"
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
