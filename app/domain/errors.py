class DomainError(Exception):
    """Base class for every business-rule violation."""


class InvalidMoneyError(DomainError):
    """Money was created with bad values (e.g. a float, or a bad currency)."""


class InvalidTransactionError(DomainError):
    """A transaction or entry breaks a structural rule."""


class UnbalancedTransactionError(InvalidTransactionError):
    """The entries of a transaction do not sum to zero."""