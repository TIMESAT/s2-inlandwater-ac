class WaterACError(Exception):
    """Base class for user-facing errors."""


class InputError(WaterACError):
    """The input product is missing, invalid, or unsupported."""


class ConfigurationError(WaterACError):
    """A requested backend option is invalid."""


class BackendUnavailable(WaterACError):
    """The external atmospheric-correction processor is unavailable."""


class RunFailed(WaterACError):
    """An external processor returned a non-zero status."""

    def __init__(self, message: str, returncode: int):
        super().__init__(message)
        self.returncode = returncode

