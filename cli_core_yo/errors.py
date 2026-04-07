"""Framework exceptions and exit-code mapping for cli-core-yo."""

from __future__ import annotations


class CliCoreYoError(Exception):
    """Base exception for all cli-core-yo framework errors."""

    exit_code: int = 1
    error_code: str = "cli_core_yo_error"

    def __init__(
        self,
        message: str,
        *,
        details: object | None = None,
        json_mode: bool | None = None,
    ) -> None:
        super().__init__(message)
        self.details = details
        self.json_mode = json_mode


class ContractViolationError(CliCoreYoError):
    """Raised when the invocation violates the framework contract."""

    exit_code = 2
    error_code = "contract_violation"


class RuntimeValidationError(CliCoreYoError):
    """Raised when runtime enforcement blocks command execution."""

    exit_code = 3
    error_code = "runtime_validation_failed"


class ContextNotInitializedError(CliCoreYoError):
    """Raised when get_context() is called before runtime initialization."""

    exit_code: int = 1

    def __init__(self) -> None:
        super().__init__("RuntimeContext has not been initialized.")


class RegistryFrozenError(CliCoreYoError):
    """Raised when a registration is attempted after the registry is frozen."""

    exit_code: int = 1

    def __init__(self, action: str = "register") -> None:
        super().__init__(f"Cannot {action}: command registry is frozen.")


class RegistryConflictError(CliCoreYoError):
    """Raised when a command name collision is detected."""

    exit_code: int = 1

    def __init__(self, path: str, detail: str = "") -> None:
        msg = f"Registration conflict at '{path}'"
        if detail:
            msg += f": {detail}"
        super().__init__(msg)


class PluginLoadError(CliCoreYoError):
    """Raised when a plugin fails to import or raises during registration."""

    exit_code: int = 1

    def __init__(self, plugin_name: str, reason: str = "") -> None:
        msg = f"Failed to load plugin '{plugin_name}'"
        if reason:
            msg += f": {reason}"
        super().__init__(msg)
        self.plugin_name = plugin_name


class SpecValidationError(CliCoreYoError):
    """Raised when CliSpec validation fails."""

    exit_code: int = 1

    def __init__(self, detail: str) -> None:
        super().__init__(f"Invalid CliSpec: {detail}")
