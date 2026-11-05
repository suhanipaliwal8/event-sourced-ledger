from fastapi import FastAPI

app = FastAPI(title="Event-Sourced Ledger")


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}