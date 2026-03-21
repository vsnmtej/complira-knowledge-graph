#!/bin/bash
#
# Quick start script for local API development
#
# Usage:
#   ./scripts/run_api_dev.sh [--port 8000] [--no-reload]
#

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Default configuration
PORT=8000
RELOAD="--reload"
HOST="0.0.0.0"

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --port)
            PORT="$2"
            shift 2
            ;;
        --no-reload)
            RELOAD=""
            shift
            ;;
        --help)
            echo "Usage: $0 [--port 8000] [--no-reload]"
            echo ""
            echo "Options:"
            echo "  --port PORT      Port to run API on (default: 8000)"
            echo "  --no-reload      Disable auto-reload on file changes"
            echo "  --help           Show this help message"
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            echo "Use --help for usage information"
            exit 1
            ;;
    esac
done

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}  Complira API Development Server${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""

# Step 1: Check prerequisites
echo -e "${YELLOW}[1/5]${NC} Checking prerequisites..."

# Check Python
if ! command -v python3 &> /dev/null; then
    echo -e "${RED}✗${NC} Python 3 not found. Please install Python 3.12+"
    exit 1
fi
echo -e "${GREEN}✓${NC} Python 3 found: $(python3 --version)"

# Check virtual environment
if [ ! -d ".venv" ]; then
    echo -e "${RED}✗${NC} Virtual environment not found. Run 'uv sync' first."
    exit 1
fi
echo -e "${GREEN}✓${NC} Virtual environment found"

# Step 2: Check infrastructure
echo ""
echo -e "${YELLOW}[2/5]${NC} Checking infrastructure..."

# Check ArangoDB
if docker compose ps arangodb | grep -q "Up"; then
    echo -e "${GREEN}✓${NC} ArangoDB is running"
else
    echo -e "${YELLOW}⚠${NC}  ArangoDB not running. Starting..."
    docker compose up -d arangodb
    echo -e "${GREEN}✓${NC} ArangoDB started"
fi

# Check Redis
if docker compose ps redis | grep -q "Up"; then
    echo -e "${GREEN}✓${NC} Redis is running"
else
    echo -e "${YELLOW}⚠${NC}  Redis not running. Starting..."
    docker compose up -d redis
    echo -e "${GREEN}✓${NC} Redis started"
fi

# Wait for services to be ready
echo -e "${BLUE}→${NC} Waiting for services to be ready..."
sleep 3

# Step 3: Check database
echo ""
echo -e "${YELLOW}[3/5]${NC} Checking database..."

if source .venv/bin/activate && python -c "
from complira_graph.db import get_db
try:
    db = get_db()
    count = list(db.aql.execute('RETURN LENGTH(vulnerabilities)'))[0]
    print(f'✓ Reference database has {count} CVEs')
    exit(0)
except Exception as e:
    print(f'✗ Database check failed: {e}')
    exit(1)
" 2>/dev/null; then
    echo -e "${GREEN}✓${NC} Database is ready"
else
    echo -e "${YELLOW}⚠${NC}  Database empty or error occurred"
    echo -e "${BLUE}→${NC} You may want to seed the database first:"
    echo -e "    ${BLUE}complira seed --skip-llm${NC}"
    echo ""
fi

# Step 4: Check dependencies
echo ""
echo -e "${YELLOW}[4/5]${NC} Checking API dependencies..."

if source .venv/bin/activate && python -c "
import fastapi
import uvicorn
import bcrypt
import redis
print('✓ All dependencies installed')
" 2>/dev/null; then
    echo -e "${GREEN}✓${NC} API dependencies OK"
else
    echo -e "${RED}✗${NC} Missing dependencies. Run 'uv sync' to install."
    exit 1
fi

# Step 5: Start API server
echo ""
echo -e "${YELLOW}[5/5]${NC} Starting API server..."
echo ""
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}  API Server Running${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
echo -e "  ${BLUE}API:${NC}              http://localhost:${PORT}"
echo -e "  ${BLUE}Swagger UI:${NC}       http://localhost:${PORT}/docs"
echo -e "  ${BLUE}ReDoc:${NC}            http://localhost:${PORT}/redoc"
echo -e "  ${BLUE}Health Check:${NC}     http://localhost:${PORT}/health"
echo ""
echo -e "${BLUE}Available Endpoints:${NC}"
echo -e "  ${GREEN}Reference API (no auth):${NC}"
echo -e "    GET /v1/reference/cve/{cve_id}"
echo -e "    GET /v1/reference/enrich?cve_ids=..."
echo -e "    GET /v1/reference/cwe/{cwe_id}"
echo -e "    GET /v1/reference/controls/{cve_id}"
echo ""
echo -e "  ${YELLOW}Scan API (requires X-API-Key):${NC}"
echo -e "    POST /v1/scan/ingest"
echo -e "    GET  /v1/scans"
echo -e "    GET  /v1/scan/{session_id}"
echo -e "    GET  /v1/scan/{session_id}/findings"
echo ""
echo -e "${BLUE}Quick Test:${NC}"
echo -e "  curl http://localhost:${PORT}/health"
echo -e "  curl http://localhost:${PORT}/v1/reference/cve/CVE-2024-21413 | jq"
echo ""
echo -e "${YELLOW}Press Ctrl+C to stop the server${NC}"
echo ""
echo -e "${GREEN}========================================${NC}"
echo ""

# Activate virtual environment and run server
source .venv/bin/activate
exec uvicorn api.main:app --host $HOST --port $PORT $RELOAD
