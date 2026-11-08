from fastapi import FastAPI

from app.api.errors import register_error_handlers
from app.api.routes import router

app = FastAPI(title="Event-Sourced Ledger")
register_error_handlers(app)
app.include_router(router)


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}