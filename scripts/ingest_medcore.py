"""
MedCore Systems — Tenant bootstrap + evidence ingestion script.

Creates:
  - Organization: MedCore Systems
  - User: ciso@medcore.dev / Demo1234!
  - Projects: Pump API Service, Pump Firmware, Pump Mobile App, Cloud Infrastructure
  - Repositories: one per project
  - Scan runs: ingests all 4 evidence files via POST /v1/scan/ingest

Usage:
    PYTHONPATH=src python scripts/ingest_medcore.py
"""

import json
import sys
import time
from pathlib import Path

import requests

BASE = "http://localhost:8000/v1"
EVIDENCE_DIR = Path("/Users/venkatapydialli/Downloads/pump_evidence")

EMAIL    = "ciso@medcore.dev"
PASSWORD = "Demo1234!"
ORG_NAME = "MedCore Systems"

# ── helpers ──────────────────────────────────────────────────────────────────

def ok(resp: requests.Response, label: str) -> dict:
    if not resp.ok:
        print(f"  ❌ {label}: HTTP {resp.status_code} — {resp.text[:300]}")
        sys.exit(1)
    data = resp.json()
    print(f"  ✅ {label}")
    return data


# ── 1. Sign up ────────────────────────────────────────────────────────────────

print("\n── 1. Create MedCore tenant ──────────────────────────────────────────")
r = requests.post(f"{BASE}/auth/signup", json={
    "email": EMAIL,
    "password": PASSWORD,
    "name": "MedCore CISO",
    "organization_name": ORG_NAME,
    "organization_domain": "medcore.dev",
})
if r.status_code in (400, 409, 500) and "already" in r.text.lower():
    print("  ℹ️  User already exists — skipping signup")
elif not r.ok:
    print(f"  ❌ Signup failed: {r.status_code} {r.text[:300]}")
    sys.exit(1)
else:
    data = r.json()
    print(f"  ✅ Signup: {data.get('message', data.get('detail', 'OK'))}")


# ── 2. Login → JWT ────────────────────────────────────────────────────────────

print("\n── 2. Login ──────────────────────────────────────────────────────────")
r = requests.post(f"{BASE}/auth/login", json={"email": EMAIL, "password": PASSWORD})
login = ok(r, "Login")
# login response is flat (no "data" wrapper)
jwt = login["access_token"]
jwt_headers = {"Authorization": f"Bearer {jwt}", "Content-Type": "application/json"}
org_id = login["user"]["organization_id"]
print(f"     org_id = {org_id}")


# ── 3. Create API key for ingestion ───────────────────────────────────────────

print("\n── 3. Create API key ─────────────────────────────────────────────────")
r = requests.post(f"{BASE}/account/api-keys", headers=jwt_headers, json={
    "name": "MedCore CI/CD Key",
    "description": "Used for evidence ingestion from scan pipeline",
    "expires_days": 365,
})
key_resp = ok(r, "API key created")
api_key = key_resp["data"]["api_key"]
api_headers = {"X-API-Key": api_key, "Content-Type": "application/json"}
print(f"     key = {api_key[:16]}…")


# ── 4. Create projects ────────────────────────────────────────────────────────

print("\n── 4. Create projects ────────────────────────────────────────────────")
projects = [
    {
        "name": "Pump API Service",
        "description": "Java Spring Boot backend API — FDA 510(k) cleared, HIPAA/EU MDR scope",
        "tags": ["api", "java", "hipaa", "fda-510k", "critical"],
    },
    {
        "name": "Pump Firmware",
        "description": "Embedded Yocto Linux firmware for the IV infusion pump device",
        "tags": ["firmware", "yocto", "iec-62304", "eu-mdr", "critical"],
    },
    {
        "name": "Pump Mobile App",
        "description": "React Native companion app for iOS/Android — EU MDR, HIPAA",
        "tags": ["mobile", "react-native", "hipaa", "eu-mdr"],
    },
    {
        "name": "Cloud Infrastructure",
        "description": "AWS Terraform + Kubernetes Helm charts for MedCore cloud backend",
        "tags": ["infra", "terraform", "aws", "k8s", "pci-dss"],
    },
]

# Fetch existing projects first
existing_projects = requests.get(f"{BASE}/projects", headers=jwt_headers).json()
existing_proj_map = {p["name"]: p["project_id"] for p in existing_projects.get("data", {}).get("projects", [])}

project_ids = {}
for proj in projects:
    if proj["name"] in existing_proj_map:
        project_ids[proj["name"]] = existing_proj_map[proj["name"]]
        print(f"  ℹ️  Project exists: {proj['name']} → {project_ids[proj['name']]}")
    else:
        r = requests.post(f"{BASE}/projects", headers=jwt_headers, json=proj)
        resp = ok(r, f"Project: {proj['name']}")
        project_ids[proj["name"]] = resp["data"]["project_id"]
        print(f"     id = {project_ids[proj['name']]}")


# ── 5. Create repositories ────────────────────────────────────────────────────

print("\n── 5. Create repositories ────────────────────────────────────────────")
repos = [
    {
        "name": "pump-api",
        "project_id": project_ids["Pump API Service"],
        "description": "Spring Boot pump API service",
        "repository_url": "https://github.com/medcore-systems/pump-api",
        "default_branch": "main",
        "tags": ["java", "spring-boot"],
    },
    {
        "name": "pump-firmware",
        "project_id": project_ids["Pump Firmware"],
        "description": "Yocto-based infusion pump firmware",
        "repository_url": "https://github.com/medcore-systems/pump-firmware",
        "default_branch": "main",
        "tags": ["c", "yocto", "embedded"],
    },
    {
        "name": "pump-mobile",
        "project_id": project_ids["Pump Mobile App"],
        "description": "React Native companion mobile app",
        "repository_url": "https://github.com/medcore-systems/pump-mobile",
        "default_branch": "main",
        "tags": ["react-native", "typescript"],
    },
    {
        "name": "pump-infra",
        "project_id": project_ids["Cloud Infrastructure"],
        "description": "Terraform + Helm infrastructure definitions",
        "repository_url": "https://github.com/medcore-systems/pump-infra",
        "default_branch": "main",
        "tags": ["terraform", "helm", "aws"],
    },
]

repo_ids = {}
for repo in repos:
    # Check if repo already exists for this project
    existing_repos = requests.get(
        f"{BASE}/repositories",
        headers=jwt_headers,
        params={"project_id": repo["project_id"]},
    ).json()
    existing_repo_map = {r2["name"]: r2["repository_id"] for r2 in existing_repos.get("data", {}).get("repositories", [])}

    if repo["name"] in existing_repo_map:
        repo_ids[repo["name"]] = existing_repo_map[repo["name"]]
        print(f"  ℹ️  Repo exists: {repo['name']} → {repo_ids[repo['name']]}")
    else:
        r = requests.post(f"{BASE}/repositories", headers=jwt_headers, json=repo)
        resp = ok(r, f"Repo: {repo['name']}")
        repo_ids[repo["name"]] = resp["data"]["repository_id"]
        print(f"     id = {repo_ids[repo['name']]}")


# ── 6. Ingest evidence ────────────────────────────────────────────────────────

print("\n── 6. Ingest evidence files ──────────────────────────────────────────")

def ingest(label, filename, scan_type, fmt, repo_name, project_name, branch="main", commit="abc123", tool_name=None):
    path = EVIDENCE_DIR / filename
    with open(path) as f:
        payload_data = json.load(f)

    metadata = {
        "repository": f"https://github.com/medcore-systems/{repo_name}",
        "branch": branch,
        "commit_sha": commit,
    }
    if tool_name:
        metadata["tool_name"] = tool_name

    body = {
        "format": fmt,
        "scan_type": scan_type,
        "payload": payload_data,
        "project_id": project_ids[project_name],
        "repository_id": repo_ids[repo_name],
        "metadata": metadata,
    }
    r = requests.post(f"{BASE}/scan/ingest", headers=api_headers, json=body)
    resp = ok(r, label)
    d = resp.get("data", {})
    print(f"     scan_run_id = {d.get('scan_run_id','?')}  findings = {d.get('findings_count','?')}  status = {d.get('status','?')}")
    return d.get("scan_run_id")

ingest(
    label="trivy_pump_api.json → Pump API Service",
    filename="trivy_pump_api.json",
    scan_type="sca",
    fmt="json",
    repo_name="pump-api",
    project_name="Pump API Service",
    commit="d3adb33f",
    tool_name="trivy",
)

ingest(
    label="trivy_pump_firmware.json → Pump Firmware",
    filename="trivy_pump_firmware.json",
    scan_type="sca",
    fmt="json",
    repo_name="pump-firmware",
    project_name="Pump Firmware",
    commit="f1rmw4r3",
    tool_name="trivy",
)

ingest(
    label="grype_pump_mobile.json → Pump Mobile App",
    filename="grype_pump_mobile.json",
    scan_type="sca",
    fmt="json",
    repo_name="pump-mobile",
    project_name="Pump Mobile App",
    commit="m0b1le99",
)

ingest(
    label="checkov_pump_infra.json → Cloud Infrastructure",
    filename="checkov_pump_infra.json",
    scan_type="iac",
    fmt="json",
    repo_name="pump-infra",
    project_name="Cloud Infrastructure",
    commit="1nfra001",
)

ingest(
    label="prowler_aws_medcore.json → Cloud Infrastructure (CSPM)",
    filename="prowler_aws_medcore.json",
    scan_type="cspm",
    fmt="json",
    repo_name="pump-infra",
    project_name="Cloud Infrastructure",
    commit="1nfra001",
    tool_name="prowler",
)


# ── 7. Summary ────────────────────────────────────────────────────────────────

print("\n── Summary ───────────────────────────────────────────────────────────")
print(f"  Tenant:    {ORG_NAME} (org_id: {org_id})")
print(f"  Login:     {EMAIL} / {PASSWORD}")
print(f"  Projects:  {len(project_ids)}")
print(f"  Repos:     {len(repo_ids)}")
print(f"  Evidence:  4 files ingested")
print("\n  Projects created:")
for name, pid in project_ids.items():
    print(f"    {pid}  {name}")
print("\n✅ MedCore Systems tenant ready. Log in at http://localhost:3000")
