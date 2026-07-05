class InsufficientData(Exception):
    """Raised when a series is below the absolute floor to forecast at all."""

    def __init__(self, min_required: int, received: int):
        self.min_required = min_required
        self.received = received
        super().__init__(f"need at least {min_required} points, received {received}")
