class WebPageError(Exception):
    """A web page could not be imported. `message` is safe to show to the user."""

    def __init__(self, code: str, message: str, status_code: int = 400):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code
