"""
Curated static mapping from Checkov check_id → NIST SP 800-53 Rev 5 control IDs.

Used by EvidenceEdgeService.create_detected_control_edges() to create
detected_control_maps_to edges (detected_controls → oscal_controls).

Source: Checkov open-source compliance documentation.
Scope:  Common AWS, Azure, GCP, and Terraform checks with confirmed NIST mappings.
Add new entries as coverage is validated against Checkov compliance output.

Key format:
  check_id   → Checkov check identifier (e.g. "CKV_AWS_19")
  control_id → NIST 800-53 Rev 5 uppercase with dot-notation (e.g. "AC-2", "AC-2.1")
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# check_id → list[control_id]
# ---------------------------------------------------------------------------

CHECKOV_NIST_MAP: dict[str, list[str]] = {

    # ── S3 / Object Storage ─────────────────────────────────────────────────
    "CKV_AWS_19": ["SC-28"],                  # S3 server-side encryption enabled
    "CKV_AWS_20": ["AC-3", "AC-6"],           # S3 bucket public read access blocked
    "CKV_AWS_21": ["CP-9"],                   # S3 versioning enabled
    "CKV_AWS_52": ["AU-2", "AU-9"],           # S3 access logging enabled
    "CKV_AWS_54": ["AC-3", "AC-6"],           # S3 block public ACLs
    "CKV_AWS_55": ["AC-3", "AC-6"],           # S3 ignore public ACLs
    "CKV_AWS_56": ["AC-3", "AC-6"],           # S3 block public policy
    "CKV_AWS_57": ["AC-3", "AC-6"],           # S3 restrict public buckets
    "CKV2_AWS_1": ["AC-3", "AC-6"],           # S3 Block Public Access (account level)
    "CKV2_AWS_61": ["SC-28"],                 # S3 default encryption with KMS CMK
    "CKV2_AWS_62": ["SC-28"],                 # S3 encryption at rest

    # ── IAM ─────────────────────────────────────────────────────────────────
    "CKV_AWS_1": ["AC-2", "AC-3"],            # IAM policy no admin wildcard
    "CKV_AWS_40": ["AC-6"],                   # IAM user no directly attached policies
    "CKV_AWS_41": ["IA-5"],                   # IAM access key rotation
    "CKV_AWS_44": ["AC-2", "IA-5"],           # IAM account password policy
    "CKV_AWS_9": ["AC-2"],                    # IAM password min length
    "CKV_AWS_10": ["AC-2"],                   # IAM password requires lowercase
    "CKV_AWS_11": ["AC-2"],                   # IAM password requires uppercase
    "CKV_AWS_12": ["AC-2"],                   # IAM password requires symbol
    "CKV_AWS_13": ["AC-2"],                   # IAM password requires number
    "CKV_AWS_14": ["AC-2"],                   # IAM password prevent reuse
    "CKV2_AWS_14": ["AC-6"],                  # IAM role cross-account not admin

    # ── EC2 / Instance ───────────────────────────────────────────────────────
    "CKV_AWS_8": ["SC-8", "IA-3"],            # EC2 instance metadata service v2 only
    "CKV_AWS_24": ["SC-7"],                   # EC2 no public IP on launch
    "CKV_AWS_126": ["SC-28"],                 # EC2 EBS root volume encryption
    "CKV_AWS_130": ["SC-28"],                 # EC2 EBS volumes encrypted
    "CKV_AWS_135": ["AU-2"],                  # EC2 detailed monitoring enabled

    # ── Security Groups ──────────────────────────────────────────────────────
    "CKV_AWS_25": ["SC-7"],                   # Security group no SSH 0.0.0.0/0
    "CKV_AWS_26": ["SC-7"],                   # Security group no RDP 0.0.0.0/0
    "CKV_AWS_79": ["SC-7"],                   # Security group no ingress 0.0.0.0/0
    "CKV_AWS_277": ["SC-7"],                  # SG no IPv6 open ingress

    # ── RDS ─────────────────────────────────────────────────────────────────
    "CKV_AWS_16": ["SC-28"],                  # RDS storage encryption
    "CKV_AWS_17": ["AC-3", "SC-7"],           # RDS no public access
    "CKV_AWS_129": ["AU-2", "AU-9"],          # RDS logging enabled
    "CKV_AWS_133": ["CP-9"],                  # RDS backup retention configured
    "CKV_AWS_157": ["SC-8"],                  # RDS CA updated

    # ── KMS ─────────────────────────────────────────────────────────────────
    "CKV_AWS_7": ["SC-28"],                   # KMS CMK key rotation enabled

    # ── CloudTrail / Logging ─────────────────────────────────────────────────
    "CKV_AWS_35": ["AU-2", "AU-3"],           # CloudTrail enabled
    "CKV_AWS_36": ["AU-3", "AU-9"],           # CloudTrail log file validation
    "CKV_AWS_67": ["AU-9"],                   # CloudTrail CloudWatch Logs integration

    # ── EKS ─────────────────────────────────────────────────────────────────
    "CKV_AWS_58": ["SC-28"],                  # EKS secrets encryption
    "CKV_AWS_39": ["AC-3", "SC-7"],           # EKS private cluster endpoint
    "CKV_AWS_58": ["SC-28"],                  # EKS envelope encryption for secrets
    "CKV2_AWS_7": ["AC-3", "SC-7"],           # EKS private API endpoint only

    # ── Lambda ───────────────────────────────────────────────────────────────
    "CKV_AWS_45": ["AC-3", "AC-6"],           # Lambda no admin IAM policy
    "CKV_AWS_116": ["AU-2"],                  # Lambda DLQ configured
    "CKV_AWS_117": ["SC-7"],                  # Lambda VPC configuration
    "CKV_AWS_272": ["SC-28"],                 # Lambda code signing

    # ── SNS / SQS ────────────────────────────────────────────────────────────
    "CKV_AWS_26": ["SC-7"],                   # SNS no open subscription
    "CKV_AWS_27": ["SC-28"],                  # SQS encrypted at rest
    "CKV_AWS_265": ["SC-28"],                 # SNS topic server-side encryption

    # ── ELB / ALB ────────────────────────────────────────────────────────────
    "CKV_AWS_91": ["SC-8"],                   # ALB listener HTTPS
    "CKV_AWS_92": ["AU-2"],                   # ALB access logging enabled
    "CKV_AWS_150": ["SC-8"],                  # ELB HTTPS listener

    # ── CloudFront ───────────────────────────────────────────────────────────
    "CKV_AWS_86": ["SC-8"],                   # CloudFront HTTPS only
    "CKV_AWS_68": ["SC-28"],                  # CloudFront WAF enabled

    # ── Azure ────────────────────────────────────────────────────────────────
    "CKV_AZURE_1": ["AU-2", "AU-3"],          # Azure Activity Log monitoring
    "CKV_AZURE_2": ["SC-28"],                 # Azure Storage account encryption
    "CKV_AZURE_3": ["AU-2", "AU-12"],         # Azure Storage account logging
    "CKV_AZURE_4": ["SC-7"],                  # Azure Storage firewall rules
    "CKV_AZURE_35": ["AU-2"],                 # Azure SQL auditing
    "CKV_AZURE_36": ["AU-2"],                 # Azure SQL threat detection
    "CKV_AZURE_37": ["SC-28"],                # Azure SQL transparent data encryption
    "CKV_AZURE_42": ["SC-28"],                # Azure Key Vault soft delete
    "CKV_AZURE_110": ["AC-3", "AC-6"],        # Azure VM no public IP
    "CKV_AZURE_131": ["SC-8"],                # Azure App Service HTTPS only

    # ── GCP ──────────────────────────────────────────────────────────────────
    "CKV_GCP_1": ["AU-2", "AU-3"],            # GCP project logging enabled
    "CKV_GCP_3": ["SC-7"],                    # GCP VPC default firewall restricted
    "CKV_GCP_26": ["SC-8"],                   # GCP instances not using default SA
    "CKV_GCP_29": ["SC-28"],                  # GCP VM disk encryption
    "CKV_GCP_33": ["AU-2"],                   # GCP Cloud DNS logging

    # ── Kubernetes ───────────────────────────────────────────────────────────
    "CKV_K8S_1": ["AC-3", "AC-6"],           # K8s no host PID
    "CKV_K8S_6": ["AC-6"],                   # K8s no root containers
    "CKV_K8S_8": ["SI-2"],                   # K8s liveness probe configured
    "CKV_K8S_9": ["SI-2"],                   # K8s readiness probe configured
    "CKV_K8S_14": ["AC-6"],                  # K8s no default service account
    "CKV_K8S_21": ["AC-3", "SC-7"],          # K8s namespace isolation
    "CKV_K8S_28": ["SC-7"],                  # K8s no host network
    "CKV_K8S_30": ["AC-6"],                  # K8s no privilege escalation
    "CKV_K8S_36": ["AC-6"],                  # K8s read-only root filesystem
    "CKV_K8S_37": ["AC-3", "AC-6"],          # K8s drop all capabilities
}


def _normalize_oscal_key(control_id: str) -> str:
    """
    Normalize a NIST 800-53 control_id string to the oscal_controls collection key format.

    Rules (from agents/oscal.py + llm_agents/regulatory_mapper.py):
      - lowercase
      - dots replaced with underscores   (AC-2.1  → ac-2_1)
      - parentheses stripped             (AC-2(1) → ac-2_1)

    Examples:
      "AC-2"   → "ac-2"
      "SC-28"  → "sc-28"
      "AC-2.1" → "ac-2_1"
    """
    normalized = control_id.lower().strip()
    normalized = normalized.replace("(", "_").replace(")", "")
    normalized = normalized.replace(".", "_")
    # collapse any double underscores that may result from "()" removal
    while "__" in normalized:
        normalized = normalized.replace("__", "_")
    return normalized.rstrip("_")
