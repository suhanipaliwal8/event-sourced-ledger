class DomainError(Exception):
    """Base class for every business-rule violation."""


class InvalidMoneyError(DomainError):
    """Money was created with bad values (e.g. a float, or a bad currency)."""


class InvalidTransactionError(DomainError):
    """A transaction or entry breaks a structural rule."""


class UnbalancedTransactionError(InvalidTransactionError):
    """The entries of a transaction do not sum to zero."""

class AccountNotFoundError(DomainError):
    """A transaction refers to an account that does not exist."""


class CurrencyMismatchError(DomainError):
    """An entry's currency differs from its account's currency."""


class DuplicateTransactionError(DomainError):
    """A transaction with this id has already been posted."""


class ConcurrentModificationError(DomainError):
    """Another writer appended to the same account at the same time. Safe to retry."""