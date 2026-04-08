"""
Custom exceptions for the Council pipeline.
All exceptions are non-fatal by design — callers catch and degrade gracefully.
"""


class CouncilError(Exception):
    """Base exception for all council errors."""
    pass


class NoAvailableKeysError(CouncilError):
    """Raised when all keys for a provider are exhausted or in cooldown."""
    pass


class OrchestratorError(CouncilError):
    """Raised when the orchestrator fails to produce a valid plan."""
    pass


class ScraperError(CouncilError):
    """Raised by a scraper when it cannot retrieve data."""
    pass


class AgentError(CouncilError):
    """Raised when an LLM agent call fails after retries."""
    pass


class ParseError(CouncilError):
    """Raised when an agent response cannot be parsed."""
    pass


class ConfigError(CouncilError):
    """Raised on invalid configuration."""
    pass
