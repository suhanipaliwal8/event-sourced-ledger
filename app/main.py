from fastapi import FastAPI, Response

from app.api.errors import register_error_handlers
from app.api.routes import router
from app.db.health import database_is_reachable

app = FastAPI(title="Event-Sourced Ledger")
register_error_handlers(app)
app.include_router(router)


@app.get("/health")
def health() -> dict:
    """Liveness: the process is up. Deliberately does NOT touch the database."""
    return {"status": "ok"}


@app.get("/health/ready")
def ready(response: Response) -> dict:
    """Readiness: the database is reachable, so we can serve traffic."""
    if database_is_reachable():
        return {"status": "ready"}
    response.status_code = 503
    return {"status": "unavailable"}