class InsufficientData(Exception):
    """Raised when a series is below the absolute floor to forecast at all."""

    def __init__(self, min_required: int, received: int):
        self.min_required = min_required
        self.received = received
        super().__init__(f"need at least {min_required} points, received {received}")


class SeriesRejected(Exception):
    """Raised by the validation gate for asks no model can honestly serve
    (guide §4 step 2: reject-with-reason rather than forecast nonsense)."""

    def __init__(self, reason: str, detail: str, min_required: int = 0):
        self.reason = reason  # machine-readable slug, e.g. "horizon_too_long"
        self.detail = detail
        self.min_required = min_required
        super().__init__(detail)
