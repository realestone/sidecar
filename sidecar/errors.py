from enum import Enum


class ErrorCode(Enum):
    PROMPT_NOT_FOUND = "prompt_not_found"
    PROMPT_ALREADY_EXISTS = "prompt_already_exists"
    MISSING_VARIABLES = "missing_variables"
    INVALID_NAME = "invalid_name"
    SCHEMA_VERSION = "schema_version"
    STORAGE = "storage"
    SESSION_NOT_FOUND = "session_not_found"
    SESSION_READ = "session_read"
    GIT_ERROR = "git_error"
    ANALYZER_ERROR = "analyzer_error"
    BRIEFING_ERROR = "briefing_error"
    HOOK_ERROR = "hook_error"
    INSTALLER_ERROR = "installer_error"

class SidecarError(Exception):
    def __init__(self, code: ErrorCode, message: str):
        self.code = code
        self.message = message
        super().__init__(message)

    @classmethod
    def prompt_not_found(cls, name: str) -> "SidecarError":
        return cls(ErrorCode.PROMPT_NOT_FOUND, f"Prompt not found: {name}")

    @classmethod
    def prompt_already_exists(cls, name: str) -> "SidecarError":
        return cls(ErrorCode.PROMPT_ALREADY_EXISTS, f"Prompt already exists: {name}")

    @classmethod
    def missing_variables(cls, variables: list[str]) -> "SidecarError":
        return cls(
            ErrorCode.MISSING_VARIABLES,
            f"Missing variables: {', '.join(variables)}",
        )

    @classmethod
    def invalid_name(cls, name: str) -> "SidecarError":
        return cls(
            ErrorCode.INVALID_NAME,
            f"Invalid name: {name!r}. Must match ^[a-z0-9][a-z0-9_-]*$",
        )

    @classmethod
    def schema_version(cls, expected: int, got: int) -> "SidecarError":
        return cls(
            ErrorCode.SCHEMA_VERSION,
            f"Schema version mismatch: expected {expected}, got {got}",
        )

    @classmethod
    def storage(cls, detail: str) -> "SidecarError":
        return cls(ErrorCode.STORAGE, f"Storage error: {detail}")

    @classmethod
    def session_not_found(cls, session_id: str) -> "SidecarError":
        return cls(ErrorCode.SESSION_NOT_FOUND, f"Session not found: {session_id}")

    @classmethod
    def session_read(cls, detail: str) -> "SidecarError":
        return cls(ErrorCode.SESSION_READ, f"Session read error: {detail}")

    @classmethod
    def git_error(cls, detail: str) -> "SidecarError":
        return cls(ErrorCode.GIT_ERROR, f"Git error: {detail}")

    @classmethod
    def analyzer_error(cls, detail: str) -> "SidecarError":
        return cls(ErrorCode.ANALYZER_ERROR, f"Analyzer error: {detail}")

    @classmethod
    def briefing_error(cls, detail: str) -> "SidecarError":
        return cls(ErrorCode.BRIEFING_ERROR, f"Briefing error: {detail}")

    @classmethod
    def hook_error(cls, detail: str) -> "SidecarError":
        return cls(ErrorCode.HOOK_ERROR, f"Hook error: {detail}")

    @classmethod
    def installer_error(cls, detail: str) -> "SidecarError":
        return cls(ErrorCode.INSTALLER_ERROR, f"Installer error: {detail}")
