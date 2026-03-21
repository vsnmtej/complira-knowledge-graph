"""
Repository management endpoints.

POST /v1/repositories - Create new repository
GET /v1/repositories - List repositories
GET /v1/repositories/{repository_id} - Get repository details
PUT /v1/repositories/{repository_id} - Update repository
DELETE /v1/repositories/{repository_id} - Soft delete repository
GET /v1/repositories/{repository_id}/summary - Get repository summary with insights
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from typing import Optional, List
import structlog
import secrets
from datetime import datetime

from api.core.security import Customer, get_current_customer
from api.core.database import get_database
from api.models.requests.repositories import CreateRepositoryRequest, UpdateRepositoryRequest
from api.models.responses.repositories import (
    CreateRepositoryResponse,
    RepositoryResponse,
    ListRepositoriesResponse,
    RepositorySummaryResponse,
    DeleteRepositoryResponse,
)
from api.models.responses import APIResponse, ResponseMetadata

logger = structlog.get_logger()

router = APIRouter()


def generate_repository_id() -> str:
    """Generate a unique repository ID."""
    return f"repo_{secrets.token_hex(12)}"


@router.post("", response_model=APIResponse[CreateRepositoryResponse])
async def create_repository(
    request: CreateRepositoryRequest,
    customer: Customer = Depends(get_current_customer),
):
    """
    POST /v1/repositories

    Create a new repository for the authenticated customer.

    **Use Cases:**
    - Register a repository for vulnerability scanning
    - Optionally assign to a project for organization
    - Add metadata (description, URL, default branch, tags)

    **Example:**
    ```bash
    curl -X POST https://api.complira.dev/v1/repositories \
      -H "X-API-Key: your_api_key" \
      -H "Content-Type: application/json" \
      -d '{
        "name": "backend-api",
        "project_id": "proj_abc123",
        "description": "Main backend API service",
        "repository_url": "https://github.com/myorg/backend-api",
        "default_branch": "main",
        "tags": ["backend", "api", "production"]
      }'
    ```
    """
    import time
    start_time = time.time()

    try:
        db = get_database()

        # If project_id specified, verify it exists and belongs to customer
        project_name = None
        if request.project_id:
            project_query = """
            FOR project IN projects
                FILTER project.project_id == @project_id
                FILTER project.customer_id == @customer_id
                FILTER project.active == true
                RETURN project
            """
            cursor = db.aql.execute(
                project_query,
                bind_vars={"project_id": request.project_id, "customer_id": customer.id}
            )
            projects = list(cursor)

            if not projects:
                raise HTTPException(
                    status_code=404,
                    detail=f"Project not found or inactive: {request.project_id}"
                )

            project_name = projects[0]["name"]

        # Generate repository ID
        repository_id = generate_repository_id()
        created_at = datetime.utcnow()

        # Create repository document
        repository_doc = {
            "_key": repository_id,
            "repository_id": repository_id,
            "customer_id": customer.id,
            "project_id": request.project_id,
            "name": request.name,
            "description": request.description,
            "repository_url": request.repository_url,
            "default_branch": request.default_branch,
            "tags": request.tags or [],
            "scan_count": 0,
            "created_at": created_at.isoformat() + "Z",
            "updated_at": created_at.isoformat() + "Z",
            "last_scan_at": None,
            "active": True,
        }

        # Ensure repositories collection exists
        if not db.has_collection("repositories"):
            collection = db.create_collection("repositories", edge=False)
            # Create indexes
            collection.add_hash_index(fields=["customer_id"], unique=False)
            collection.add_hash_index(fields=["repository_id"], unique=True)
            collection.add_skiplist_index(fields=["customer_id", "project_id"], unique=False)
            collection.add_skiplist_index(fields=["customer_id", "active"], unique=False)
        else:
            collection = db.collection("repositories")

        # Insert repository
        collection.insert(repository_doc)

        # Update project repository count if assigned
        if request.project_id:
            update_count_query = """
            LET project = FIRST(
                FOR p IN projects
                    FILTER p.project_id == @project_id
                    FILTER p.customer_id == @customer_id
                    RETURN p
            )
            LET repo_count = LENGTH(
                FOR r IN repositories
                    FILTER r.project_id == @project_id
                    FILTER r.customer_id == @customer_id
                    FILTER r.active == true
                    RETURN 1
            )
            UPDATE project WITH {
                repository_count: repo_count,
                updated_at: @updated_at
            } IN projects
            """
            db.aql.execute(
                update_count_query,
                bind_vars={
                    "project_id": request.project_id,
                    "customer_id": customer.id,
                    "updated_at": created_at.isoformat() + "Z",
                }
            )

        logger.info(
            "Repository created",
            customer_id=customer.id,
            repository_id=repository_id,
            repository_name=request.name,
            project_id=request.project_id,
        )

        execution_time_ms = (time.time() - start_time) * 1000

        return APIResponse(
            success=True,
            data=CreateRepositoryResponse(
                repository_id=repository_id,
                project_id=request.project_id,
                name=request.name,
                description=request.description,
                repository_url=request.repository_url,
                default_branch=request.default_branch,
                tags=request.tags or [],
                created_at=created_at.isoformat() + "Z",
                scan_count=0,
            ),
            metadata=ResponseMetadata(
                cache_hit=False,
                execution_time_ms=execution_time_ms,
            ),
        )

    except HTTPException:
        raise

    except Exception as e:
        logger.error(
            "Repository creation failed",
            customer_id=customer.id,
            error=str(e),
            error_type=type(e).__name__,
        )
        raise HTTPException(
            status_code=500,
            detail="Internal server error during repository creation"
        )


@router.get("", response_model=APIResponse[ListRepositoriesResponse])
async def list_repositories(
    customer: Customer = Depends(get_current_customer),
    project_id: Optional[str] = Query(None, description="Filter by project ID"),
    active: Optional[bool] = Query(None, description="Filter by active status"),
    tags: Optional[str] = Query(None, description="Filter by tags (comma-separated)"),
):
    """
    GET /v1/repositories

    List all repositories for the authenticated customer.

    **Query Parameters:**
    - project_id: Filter by project ID (use "null" for unassigned repositories)
    - active: Filter by active status (true/false)
    - tags: Filter by tags (comma-separated, e.g., "backend,production")

    **Example:**
    ```bash
    curl https://api.complira.dev/v1/repositories?project_id=proj_abc123&active=true \
      -H "X-API-Key: your_api_key"
    ```
    """
    import time
    start_time = time.time()

    try:
        db = get_database()

        # Build filter conditions
        filter_conditions = ["repo.customer_id == @customer_id"]
        bind_vars = {"customer_id": customer.id}

        if project_id is not None:
            if project_id.lower() == "null":
                filter_conditions.append("repo.project_id == null")
            else:
                filter_conditions.append("repo.project_id == @project_id")
                bind_vars["project_id"] = project_id

        if active is not None:
            filter_conditions.append("repo.active == @active")
            bind_vars["active"] = active

        if tags:
            tag_list = [t.strip() for t in tags.split(",")]
            filter_conditions.append("LENGTH(INTERSECTION(repo.tags, @tags)) > 0")
            bind_vars["tags"] = tag_list

        filter_clause = " AND ".join(filter_conditions)

        # Query repositories with project names
        query = f"""
        FOR repo IN repositories
            FILTER {filter_clause}
            LET project = FIRST(
                FOR p IN projects
                    FILTER p.project_id == repo.project_id
                    FILTER p.customer_id == @customer_id
                    RETURN p
            )
            SORT repo.created_at DESC
            RETURN MERGE(repo, {{
                project_name: project.name
            }})
        """

        cursor = db.aql.execute(query, bind_vars=bind_vars)
        repositories = list(cursor)

        # Convert to response models
        repository_responses = [
            RepositoryResponse(
                repository_id=r["repository_id"],
                project_id=r.get("project_id"),
                project_name=r.get("project_name"),
                name=r["name"],
                description=r.get("description"),
                repository_url=r.get("repository_url"),
                default_branch=r.get("default_branch"),
                tags=r.get("tags", []),
                scan_count=r.get("scan_count", 0),
                created_at=r["created_at"],
                updated_at=r["updated_at"],
                last_scan_at=r.get("last_scan_at"),
                active=r.get("active", True),
            )
            for r in repositories
        ]

        execution_time_ms = (time.time() - start_time) * 1000

        return APIResponse(
            success=True,
            data=ListRepositoriesResponse(
                repositories=repository_responses,
                total=len(repository_responses),
            ),
            metadata=ResponseMetadata(
                cache_hit=False,
                execution_time_ms=execution_time_ms,
            ),
        )

    except Exception as e:
        logger.error(
            "Repository listing failed",
            customer_id=customer.id,
            error=str(e),
        )
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/{repository_id}", response_model=APIResponse[RepositoryResponse])
async def get_repository(
    repository_id: str,
    customer: Customer = Depends(get_current_customer),
):
    """
    GET /v1/repositories/{repository_id}

    Get details for a specific repository.

    **Example:**
    ```bash
    curl https://api.complira.dev/v1/repositories/repo_abc123 \
      -H "X-API-Key: your_api_key"
    ```
    """
    import time
    start_time = time.time()

    try:
        db = get_database()

        # Query repository with project name
        query = """
        FOR repo IN repositories
            FILTER repo.repository_id == @repository_id
            FILTER repo.customer_id == @customer_id
            LET project = FIRST(
                FOR p IN projects
                    FILTER p.project_id == repo.project_id
                    FILTER p.customer_id == @customer_id
                    RETURN p
            )
            RETURN MERGE(repo, {
                project_name: project.name
            })
        """

        cursor = db.aql.execute(
            query,
            bind_vars={"repository_id": repository_id, "customer_id": customer.id}
        )
        repositories = list(cursor)

        if not repositories:
            raise HTTPException(
                status_code=404,
                detail=f"Repository not found: {repository_id}"
            )

        repo = repositories[0]

        execution_time_ms = (time.time() - start_time) * 1000

        return APIResponse(
            success=True,
            data=RepositoryResponse(
                repository_id=repo["repository_id"],
                project_id=repo.get("project_id"),
                project_name=repo.get("project_name"),
                name=repo["name"],
                description=repo.get("description"),
                repository_url=repo.get("repository_url"),
                default_branch=repo.get("default_branch"),
                tags=repo.get("tags", []),
                scan_count=repo.get("scan_count", 0),
                created_at=repo["created_at"],
                updated_at=repo["updated_at"],
                last_scan_at=repo.get("last_scan_at"),
                active=repo.get("active", True),
            ),
            metadata=ResponseMetadata(
                cache_hit=False,
                execution_time_ms=execution_time_ms,
            ),
        )

    except HTTPException:
        raise

    except Exception as e:
        logger.error(
            "Repository retrieval failed",
            customer_id=customer.id,
            repository_id=repository_id,
            error=str(e),
        )
        raise HTTPException(status_code=500, detail="Internal server error")


@router.put("/{repository_id}", response_model=APIResponse[RepositoryResponse])
async def update_repository(
    repository_id: str,
    request: UpdateRepositoryRequest,
    customer: Customer = Depends(get_current_customer),
):
    """
    PUT /v1/repositories/{repository_id}

    Update an existing repository.

    **Note:** You can reassign a repository to a different project or set project_id to null to unassign.

    **Example:**
    ```bash
    curl -X PUT https://api.complira.dev/v1/repositories/repo_abc123 \
      -H "X-API-Key: your_api_key" \
      -H "Content-Type: application/json" \
      -d '{
        "name": "backend-api-v2",
        "project_id": "proj_xyz789",
        "description": "Updated description",
        "tags": ["backend", "production", "critical"]
      }'
    ```
    """
    import time
    start_time = time.time()

    try:
        db = get_database()
        collection = db.collection("repositories")

        # Verify repository exists and belongs to customer
        query = """
        FOR repo IN repositories
            FILTER repo.repository_id == @repository_id
            FILTER repo.customer_id == @customer_id
            RETURN repo
        """

        cursor = db.aql.execute(
            query,
            bind_vars={"repository_id": repository_id, "customer_id": customer.id}
        )
        repositories = list(cursor)

        if not repositories:
            raise HTTPException(
                status_code=404,
                detail=f"Repository not found: {repository_id}"
            )

        repository = repositories[0]
        old_project_id = repository.get("project_id")

        # If changing project_id, verify new project exists
        if request.project_id is not None and request.project_id != old_project_id:
            if request.project_id:  # Not setting to null
                project_query = """
                FOR project IN projects
                    FILTER project.project_id == @project_id
                    FILTER project.customer_id == @customer_id
                    FILTER project.active == true
                    RETURN project
                """
                cursor = db.aql.execute(
                    project_query,
                    bind_vars={"project_id": request.project_id, "customer_id": customer.id}
                )
                projects = list(cursor)

                if not projects:
                    raise HTTPException(
                        status_code=404,
                        detail=f"Project not found or inactive: {request.project_id}"
                    )

        # Build update document
        update_doc = {
            "_key": repository["_key"],
            "updated_at": datetime.utcnow().isoformat() + "Z",
        }

        if request.name is not None:
            update_doc["name"] = request.name
        if request.project_id is not None:
            update_doc["project_id"] = request.project_id
        if request.description is not None:
            update_doc["description"] = request.description
        if request.repository_url is not None:
            update_doc["repository_url"] = request.repository_url
        if request.default_branch is not None:
            update_doc["default_branch"] = request.default_branch
        if request.tags is not None:
            update_doc["tags"] = request.tags
        if request.active is not None:
            update_doc["active"] = request.active

        # Update repository
        collection.update(update_doc)

        # Update repository counts for affected projects
        affected_projects = set()
        if old_project_id:
            affected_projects.add(old_project_id)
        if request.project_id is not None and request.project_id:
            affected_projects.add(request.project_id)

        for proj_id in affected_projects:
            update_count_query = """
            LET project = FIRST(
                FOR p IN projects
                    FILTER p.project_id == @project_id
                    FILTER p.customer_id == @customer_id
                    RETURN p
            )
            LET repo_count = LENGTH(
                FOR r IN repositories
                    FILTER r.project_id == @project_id
                    FILTER r.customer_id == @customer_id
                    FILTER r.active == true
                    RETURN 1
            )
            UPDATE project WITH {
                repository_count: repo_count,
                updated_at: @updated_at
            } IN projects
            """
            db.aql.execute(
                update_count_query,
                bind_vars={
                    "project_id": proj_id,
                    "customer_id": customer.id,
                    "updated_at": update_doc["updated_at"],
                }
            )

        # Fetch updated repository with project name
        fetch_query = """
        FOR repo IN repositories
            FILTER repo.repository_id == @repository_id
            FILTER repo.customer_id == @customer_id
            LET project = FIRST(
                FOR p IN projects
                    FILTER p.project_id == repo.project_id
                    FILTER p.customer_id == @customer_id
                    RETURN p
            )
            RETURN MERGE(repo, {
                project_name: project.name
            })
        """
        cursor = db.aql.execute(
            fetch_query,
            bind_vars={"repository_id": repository_id, "customer_id": customer.id}
        )
        updated_repo = list(cursor)[0]

        logger.info(
            "Repository updated",
            customer_id=customer.id,
            repository_id=repository_id,
            updates=list(update_doc.keys()),
        )

        execution_time_ms = (time.time() - start_time) * 1000

        return APIResponse(
            success=True,
            data=RepositoryResponse(
                repository_id=updated_repo["repository_id"],
                project_id=updated_repo.get("project_id"),
                project_name=updated_repo.get("project_name"),
                name=updated_repo["name"],
                description=updated_repo.get("description"),
                repository_url=updated_repo.get("repository_url"),
                default_branch=updated_repo.get("default_branch"),
                tags=updated_repo.get("tags", []),
                scan_count=updated_repo.get("scan_count", 0),
                created_at=updated_repo["created_at"],
                updated_at=updated_repo["updated_at"],
                last_scan_at=updated_repo.get("last_scan_at"),
                active=updated_repo.get("active", True),
            ),
            metadata=ResponseMetadata(
                cache_hit=False,
                execution_time_ms=execution_time_ms,
            ),
        )

    except HTTPException:
        raise

    except Exception as e:
        logger.error(
            "Repository update failed",
            customer_id=customer.id,
            repository_id=repository_id,
            error=str(e),
        )
        raise HTTPException(
            status_code=500,
            detail="Internal server error during repository update"
        )


@router.delete("/{repository_id}", response_model=APIResponse[DeleteRepositoryResponse])
async def delete_repository(
    repository_id: str,
    customer: Customer = Depends(get_current_customer),
):
    """
    DELETE /v1/repositories/{repository_id}

    Soft delete a repository (sets active=false).

    **Important:**
    - Historical scan data is preserved
    - Repository can be reactivated by setting active=true via PUT

    **Example:**
    ```bash
    curl -X DELETE https://api.complira.dev/v1/repositories/repo_abc123 \
      -H "X-API-Key: your_api_key"
    ```
    """
    import time
    start_time = time.time()

    try:
        db = get_database()
        collection = db.collection("repositories")

        # Verify repository exists and belongs to customer
        query = """
        FOR repo IN repositories
            FILTER repo.repository_id == @repository_id
            FILTER repo.customer_id == @customer_id
            RETURN repo
        """

        cursor = db.aql.execute(
            query,
            bind_vars={"repository_id": repository_id, "customer_id": customer.id}
        )
        repositories = list(cursor)

        if not repositories:
            raise HTTPException(
                status_code=404,
                detail=f"Repository not found: {repository_id}"
            )

        repository = repositories[0]

        # Check if already deleted
        if not repository.get("active", True):
            raise HTTPException(
                status_code=400,
                detail=f"Repository already deleted: {repository_id}"
            )

        # Soft delete repository
        deleted_at = datetime.utcnow()
        collection.update({
            "_key": repository["_key"],
            "active": False,
            "updated_at": deleted_at.isoformat() + "Z",
        })

        # Update project repository count if assigned
        if repository.get("project_id"):
            update_count_query = """
            LET project = FIRST(
                FOR p IN projects
                    FILTER p.project_id == @project_id
                    FILTER p.customer_id == @customer_id
                    RETURN p
            )
            LET repo_count = LENGTH(
                FOR r IN repositories
                    FILTER r.project_id == @project_id
                    FILTER r.customer_id == @customer_id
                    FILTER r.active == true
                    RETURN 1
            )
            UPDATE project WITH {
                repository_count: repo_count,
                updated_at: @updated_at
            } IN projects
            """
            db.aql.execute(
                update_count_query,
                bind_vars={
                    "project_id": repository["project_id"],
                    "customer_id": customer.id,
                    "updated_at": deleted_at.isoformat() + "Z",
                }
            )

        logger.warning(
            "Repository deleted",
            customer_id=customer.id,
            repository_id=repository_id,
            repository_name=repository["name"],
        )

        execution_time_ms = (time.time() - start_time) * 1000

        return APIResponse(
            success=True,
            data=DeleteRepositoryResponse(
                repository_id=repository_id,
                name=repository["name"],
                deleted_at=deleted_at.isoformat() + "Z",
                message=f"Repository '{repository['name']}' has been deleted. Historical scan data is preserved.",
            ),
            metadata=ResponseMetadata(
                cache_hit=False,
                execution_time_ms=execution_time_ms,
            ),
        )

    except HTTPException:
        raise

    except Exception as e:
        logger.error(
            "Repository deletion failed",
            customer_id=customer.id,
            repository_id=repository_id,
            error=str(e),
        )
        raise HTTPException(
            status_code=500,
            detail="Internal server error during repository deletion"
        )


@router.get("/{repository_id}/summary", response_model=APIResponse[RepositorySummaryResponse])
async def get_repository_summary(
    repository_id: str,
    customer: Customer = Depends(get_current_customer),
):
    """
    GET /v1/repositories/{repository_id}/summary

    Get aggregated insights for a repository across all scans.

    **Returns:**
    - Scan session count and timeline
    - Current findings from latest scan
    - Vulnerability trends (new vs resolved over time)
    - Top CVEs in this repository

    **Example:**
    ```bash
    curl https://api.complira.dev/v1/repositories/repo_abc123/summary \
      -H "X-API-Key: your_api_key"
    ```
    """
    import time
    start_time = time.time()

    try:
        db = get_database()

        # Verify repository exists with project name
        repo_query = """
        FOR repo IN repositories
            FILTER repo.repository_id == @repository_id
            FILTER repo.customer_id == @customer_id
            LET project = FIRST(
                FOR p IN projects
                    FILTER p.project_id == repo.project_id
                    FILTER p.customer_id == @customer_id
                    RETURN p
            )
            RETURN MERGE(repo, {
                project_name: project.name
            })
        """

        cursor = db.aql.execute(
            repo_query,
            bind_vars={"repository_id": repository_id, "customer_id": customer.id}
        )
        repositories = list(cursor)

        if not repositories:
            raise HTTPException(
                status_code=404,
                detail=f"Repository not found: {repository_id}"
            )

        repository = repositories[0]

        # Placeholder aggregations (to be implemented with actual scan data)
        scan_count = repository.get("scan_count", 0)
        first_scan = None
        last_scan = repository.get("last_scan_at")

        current_findings = {
            "critical": 0,
            "high": 0,
            "medium": 0,
            "low": 0,
            "total": 0,
        }

        trends = {
            "new_last_7_days": 0,
            "resolved_last_7_days": 0,
            "net_change": 0,
        }

        top_vulnerabilities = []

        execution_time_ms = (time.time() - start_time) * 1000

        return APIResponse(
            success=True,
            data=RepositorySummaryResponse(
                repository_id=repository_id,
                repository_name=repository["name"],
                project_id=repository.get("project_id"),
                project_name=repository.get("project_name"),
                scan_count=scan_count,
                first_scan=first_scan,
                last_scan=last_scan,
                current_findings=current_findings,
                trends=trends,
                top_vulnerabilities=top_vulnerabilities,
            ),
            metadata=ResponseMetadata(
                cache_hit=False,
                execution_time_ms=execution_time_ms,
            ),
        )

    except HTTPException:
        raise

    except Exception as e:
        logger.error(
            "Repository summary retrieval failed",
            customer_id=customer.id,
            repository_id=repository_id,
            error=str(e),
        )
        raise HTTPException(status_code=500, detail="Internal server error")
