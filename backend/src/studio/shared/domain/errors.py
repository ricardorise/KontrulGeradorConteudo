class DomainError(Exception):
    """Violação de regra de negócio."""


class InvalidInput(DomainError):
    pass


class NotFound(DomainError):
    pass


class Conflict(DomainError):
    pass
