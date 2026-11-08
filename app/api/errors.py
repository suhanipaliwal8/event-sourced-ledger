from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.domain import errors as e

# (exception type, HTTP status, stable machine-readable code)
# ORDER MATTERS: subclasses must come before their parent classes
# (UnbalancedTransactionError is a kind of InvalidTransactionError).
_ERROR_MAP = [
    (e.AccountNotFoundError, 404, "account_not_found"),
    (e.SystemAccountNotAllowedError, 403, "system_account_not_allowed"),
    (e.InsufficientFundsError, 409, "insufficient_funds"),
    (e.DuplicateTransactionError, 409, "duplicate_transaction"),
    (e.ConcurrentModificationError, 409, "concurrent_modification"),
    (e.CurrencyMismatchError, 422, "currency_mismatch"),
    (e.FutureTransactionError, 422, "occurred_at_in_future"),
    (e.UnbalancedTransactionError, 422, "unbalanced_transaction"),
    (e.InvalidMoneyError, 422, "invalid_money"),
    (e.InvalidTransactionError, 422, "invalid_transaction"),
]


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(e.DomainError)
    async def handle_domain_error(request: Request, exc: e.DomainError) -> JSONResponse:
        for exc_type, status_code, code in _ERROR_MAP:
            if isinstance(exc, exc_type):
                return JSONResponse(
                    status_code=status_code,
                    content={"error": {"code": code, "message": str(exc)}},
                )
        # A DomainError we forgot to map: still a clean response, never a crash.
        return JSONResponse(
            status_code=400,
            content={"error": {"code": "domain_error", "message": str(exc)}},
        )