class PipelineError(Exception):
    """Only a safe code is persisted/logged; provider payloads may contain personal data."""

    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


class LeaseLost(PipelineError):
    def __init__(self):
        super().__init__("JOB_LEASE_LOST")
