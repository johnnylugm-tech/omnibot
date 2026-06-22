"""[FR-06, FR-86] OmniBot FastAPI root application — router assembly and health endpoint.

Wires all API sub-routers and provides the /api/v1/health liveness probe.
No business logic lives here (api_layer_no_business_logic constraint).
"""

from fastapi import FastAPI

from app.api.auth import router as auth_router
from app.api.management import router as mgmt_router
from app.api.webhooks import router as webhooks_router

app = FastAPI(title="OmniBot", version="0.1.0")

app.include_router(webhooks_router, prefix="/api/v1")
app.include_router(auth_router, prefix="/api/v1")
app.include_router(mgmt_router, prefix="/api/v1")


@app.get("/api/v1/health")
def health() -> dict:
    """[FR-86] Liveness probe — returns HTTP 200 when the service is up."""
    return {"status": "ok"}
