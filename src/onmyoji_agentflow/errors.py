"""Exceptions shared across the package."""


class AgentflowError(Exception):
    """Base error."""


class RequestHumanTakeover(AgentflowError):
    """Raised when the program cannot continue without the user (name kept from OAS)."""


class DeviceError(AgentflowError):
    pass


class WorkflowError(AgentflowError):
    """Invalid workflow / resource definition."""


class RunFailure(AgentflowError):
    """A workflow run failed; ``kind`` is one of the failure kinds in supervisor.monitor."""

    def __init__(self, kind: str, message: str, state: str | None = None):
        super().__init__(f"[{kind}] {message}")
        self.kind = kind
        self.state = state
        self.message = message


class ConfirmationDenied(AgentflowError):
    pass


class BudgetExceeded(AgentflowError):
    pass


class LLMError(AgentflowError):
    pass
