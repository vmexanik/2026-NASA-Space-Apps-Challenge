"""Exceptions raised by the FIRMS client."""


class FirmsError(Exception):
    """Base class of every FIRMS client error."""


class FirmsConfigError(FirmsError):
    """The client cannot start: no MAP_KEY was found."""


class FirmsHTTPError(FirmsError):
    """FIRMS answered with an HTTP error, e.g. 400 'Invalid MAP_KEY.'."""

    def __init__(self, status: int, body: str) -> None:
        super().__init__(f"HTTP {status}: {body[:300]}")
        self.status: int = status
        self.body: str = body


class FirmsResponseError(FirmsError):
    """FIRMS answered 200 but the body is not what the API promises."""

    def __init__(self, body: str) -> None:
        super().__init__(f"unexpected answer: {body.strip()[:300]}")
        self.body: str = body


class FirmsNetworkError(FirmsError):
    """FIRMS could not be reached, even after the retries."""
