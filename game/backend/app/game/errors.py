class GameError(Exception):
    """A rule violation reported to the client as {"detail": code}."""

    def __init__(self, code: str, status: int = 400) -> None:
        super().__init__(code)
        self.code = code
        self.status = status
