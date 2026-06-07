"""应用服务共享错误类型。"""

from __future__ import annotations


class ApplicationError(Exception):
    """应用层基类错误。"""

    code = "application_error"

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message

    def __str__(self) -> str:
        return f"[{self.code}] {self.message}"


class ValidationAppError(ApplicationError):
    """参数校验失败。"""

    code = "validation_error"


class NotFoundAppError(ApplicationError):
    """资源不存在。"""

    code = "not_found"


class ConflictAppError(ApplicationError):
    """请求语义冲突。"""

    code = "validation_error"


class ScanFailedAppError(ApplicationError):
    """扫描失败。"""

    code = "scan_failed"


class InternalAppError(ApplicationError):
    """内部错误，供入口层统一隐藏实现细节。"""

    code = "internal_error"
