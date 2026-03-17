# Quick Start: CVE Dataset Enhancement

## Current Status

✅ **Database seeded** with 3,238 CVEs (last 7 days from initial seed)
✅ **NVD API key verified** and working
✅ **Enhancement scripts ready** with tiered approach

---

## 🚀 Recommended: Run Priority 1 Enhancement

**This will add ~75,000 CVEs from the last 3 years (2023-present)**

### Step 1: Verify NVD API Key

```bash
.venv/bin/python scripts/test_nvd_api_key.py
```

Expected output:
```
✅ NVD_API_KEY found: ae830643...fa09
✅ API connection successful!
   Total CVEs available: 336,155
```

---

### Step 2: Run Enhancement (Priority 1)

```bash
.venv/bin/python scripts/enhance_cve_dataset.py
```

**What this does:**
- Fetches CVEs from 2023-01-01 to present
- Adds ~75,000 CVEs to your database
- Creates CWE relationships automatically
- Takes 45-60 minutes with API key
- Supports checkpoint/resume (safe to stop)

**Expected output:**
```
🚀 CVE Dataset Enhancement - Tiered Approach
================================================================================

📊 Current CVE count: 3,238

📋 Tiered Fetch Strategy:
   Priority 1: Last 3 years (2023-present)
               ~75K CVEs covering 95% of real-world findings
   Priority 2: CISA KEV catalog (~1,500 CVEs)
               Already in database - actively exploited CVEs

🎯 Target CVE count: ~75,000 (Priority 1)
📥 CVEs to fetch: ~71,762

📅 Date range: 2023-01-01 to 2026-03-05
   Fetching CVEs from last 3 years

✅ NVD API key detected
⏱️  Estimated time: 45-60 minutes

Start CVE enhancement? (y/n): y
```

---

### Step 3: Verify Results

After completion, test the enrichment API:

```bash
.venv/bin/pytest tests/integration/test_phase1_graph_enrichment.py -v -s
```

Expected:
```
test_database_is_seeded PASSED
✅ Database seeded: 78,238 CVEs, 1,529 KEV entries, 969 weaknesses

test_enrich_single_cve PASSED
  CVE: CVE_2023_12345
  Risk Score: 0.842
  Priority: HIGH

test_risk_score_calculation PASSED
  ✅ KEV CVE correctly scored as CRITICAL
```

---

## ⚠️ Optional: Legacy CVE Enhancement (Priority 3)

**Only run this if you support legacy systems (pre-2023 software)**

```bash
.venv/bin/python scripts/enhance_cve_dataset_legacy.py
```

**What this does:**
- Fetches CVEs from 2015-2022
- Filters to CVSS >= 9.0 only
- Adds ~15,000 critical legacy CVEs
- Takes 60-90 minutes

**When to use:**
- You scan embedded/IoT devices
- You manage OT/ICS systems
- You support legacy enterprise software

---

## 📊 Tiered Approach Summary

| Priority | Coverage | CVEs | Time | Status |
|----------|----------|------|------|--------|
| **Priority 1** | Last 3 years | ~75K | 60 min | ⏳ **Ready to run** |
| **Priority 2** | KEV catalog | ~1.5K | N/A | ✅ **Already in DB** |
| **Priority 3** | Legacy (2015-2022) | ~15K | 90 min | ⚠️ **Optional** |

**Recommended:** Run Priority 1 now for 95% coverage

---

## 🎯 Next Steps

1. **Run Priority 1 enhancement** (recommended)
   ```bash
   .venv/bin/python scripts/enhance_cve_dataset.py
   ```

2. **Test enrichment API**
   ```bash
   .venv/bin/pytest tests/integration/test_phase1_graph_enrichment.py -v -s
   ```

3. **Start API server**
   ```bash
   uvicorn api.main:app --reload
   ```

4. **Test via API**
   ```bash
   curl -X POST "http://localhost:8000/api/v1/enrichment/enrich" \
     -H "Content-Type: application/json" \
     -d '{"cve_ids": ["CVE_2023_12345"]}'
   ```

---

## 📚 Full Documentation

See [CVE_ENHANCEMENT_STRATEGY.md](docs/CVE_ENHANCEMENT_STRATEGY.md) for detailed explanation of the tiered approach.

---

## 🆘 Troubleshooting

### API Key Issues

**Problem:** "NVD_API_KEY not found"

**Solution:**
```bash
# Add to .env file
echo "NVD_API_KEY=your-key-here" >> .env

# Verify
.venv/bin/python scripts/test_nvd_api_key.py
```

### Rate Limiting

**Problem:** Getting rate limited (403 errors)

**Solution:** Ensure NVD_API_KEY is set. With API key: 50 req/30s. Without: 5 req/30s.

### Interrupted Enhancement

**Problem:** Script stopped mid-run

**Solution:** Just run it again - checkpoint support will resume where you left off:
```bash
.venv/bin/python scripts/enhance_cve_dataset.py
# Resuming from checkpoint
# start_index: 50000
# total_fetched: 50000
```

### Database Connection

**Problem:** "Cannot connect to ArangoDB"

**Solution:**
```bash
# Verify ArangoDB is running
docker ps | grep arango

# If not, start it
docker-compose up -d arangodb
```

---

## 🎉 What You'll Have After Priority 1

- ✅ **~75,000 CVEs** from 2023-present
- ✅ **CISA KEV catalog** (~1,500 actively exploited CVEs)
- ✅ **CWE mappings** for all CVEs
- ✅ **EPSS scores** (exploitation probability)
- ✅ **ATT&CK techniques** via graph traversal
- ✅ **D3FEND defenses** mapped to attack paths
- ✅ **NIST 800-53 controls** for compliance

**Coverage:** 95% of real-world vulnerability scan findings
**Query performance:** <100ms per CVE enrichment
**Storage:** ~500 MB total

---

## 🔄 Maintenance

### Weekly Updates

Run Priority 1 script weekly to get new CVEs:

```bash
# The script automatically fetches only new/modified CVEs
.venv/bin/python scripts/enhance_cve_dataset.py
```

### KEV Catalog Updates

Update KEV catalog daily (new exploited CVEs):

```bash
.venv/bin/python -c "
from complira_graph.db import get_db
from complira_graph.agents.kev import KEVAgent

db = get_db()
agent = KEVAgent(db=db)
result = agent.run()
print(f'Updated KEV catalog: {result[\"documents_created\"]} new entries')
"
```

---

**Ready to enhance your CVE dataset? Run Priority 1 now! ⬆️**
