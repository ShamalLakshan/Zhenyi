"""
Custom exceptions for the Zhenyi research pipeline.
All exceptions are non-fatal by design — callers catch and degrade gracefully.
"""


class ZhenyiError(Exception):
    """Base exception for all Zhenyi errors."""
    pass


class NoAvailableKeysError(ZhenyiError):
    """Raised when all keys for a provider are exhausted or in cooldown."""
    pass


class OrchestratorError(ZhenyiError):
    """Raised when the orchestrator fails to produce a valid plan."""
    pass


class ScraperError(ZhenyiError):
    """Raised by a scraper when it cannot retrieve data."""
    pass


class AgentError(ZhenyiError):
    """Raised when an LLM agent call fails after retries."""
    pass


class ParseError(ZhenyiError):
    """Raised when an agent response cannot be parsed."""
    pass


class ConfigError(ZhenyiError):
    """Raised on invalid configuration."""
    pass
