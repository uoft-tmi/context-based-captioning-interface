class SessionExpiredError(Exception):
    pass


class DemoAccessDenied(Exception):
    pass


class ModelUnavailableError(Exception):
    pass


class ProviderRequestError(ModelUnavailableError):
    def __init__(self, message: str, *, retryable: bool = False):
        super().__init__(message)
        self.retryable = retryable
