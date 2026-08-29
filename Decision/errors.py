


class AppError(Exception):
    def __init__(self, message: str,code="APP_ERROR"):
        super().__init__(message)
        self.code = code


class LLMParseError(AppError):
    def __init__(self, message: str,retryable:bool = True):
        super().__init__(message, code="LLM_PARSE_ERROR")
        self.retryable = retryable

class LLMAPIError(AppError):
    def __init__(self, message: str, retryable: bool = False):
        super().__init__(message, code="LLM_API_ERROR")
        self.retryable = retryable
