"""
Redaction Utilities
───────────────────
Automatically redacts sensitive data (API keys, auth headers, passwords)
from request/response payloads before storing in logs.

Sensitive field patterns:
- Headers: authorization, api-key, x-api-key, x-goog-api-key, token, secret
- Request body fields: api_key, apikey, password, secret, auth_token, key
- Environment-like patterns: *_KEY_*, *_SECRET_*, *_TOKEN_*
"""

import json
import re
from typing import Any, Dict

SENSITIVE_HEADERS = {
    "authorization",
    "api-key",
    "x-api-key",
    "x-goog-api-key",
    "x-anthropic-api-key",
    "x-cohere-api-key",
    "authorization-token",
    "token",
    "x-auth-token",
    "cookie",
    "set-cookie",
}

SENSITIVE_FIELD_PATTERNS = [
    r".*api.?key.*",
    r".*password.*",
    r".*secret.*",
    r".*token.*",
    r".*auth.*",
]

REDACTED_PLACEHOLDER = "[REDACTED]"


def is_sensitive_field(key: str) -> bool:
    """Check if a field name matches a sensitive pattern."""
    key_lower = key.lower()
    
    # Check exact header matches
    if key_lower in SENSITIVE_HEADERS:
        return True
    
    # Check regex patterns
    for pattern in SENSITIVE_FIELD_PATTERNS:
        if re.match(pattern, key_lower, re.IGNORECASE):
            return True
    
    return False


def redact_headers(headers: Dict[str, Any]) -> Dict[str, Any]:
    """Redact sensitive headers. Returns new dict with sensitive values replaced."""
    if not headers:
        return headers
    
    redacted = {}
    for key, value in headers.items():
        if is_sensitive_field(key):
            redacted[key] = REDACTED_PLACEHOLDER
        else:
            redacted[key] = value
    return redacted


def redact_json_payload(payload: Any) -> Any:
    """
    Recursively redact sensitive fields from a JSON-serializable object.
    Returns new object with sensitive values replaced.
    """
    if isinstance(payload, dict):
        return {
            key: REDACTED_PLACEHOLDER if is_sensitive_field(key) else redact_json_payload(value)
            for key, value in payload.items()
        }
    elif isinstance(payload, list):
        return [redact_json_payload(item) for item in payload]
    else:
        return payload


def redact_request_payload(request_dict: Dict[str, Any]) -> Dict[str, Any]:
    """
    Redact full request payload (headers, body, params, etc).
    
    Expects dict with keys like:
    - headers: dict of HTTP headers
    - data / body / json: request body
    - params: query parameters
    - url: API endpoint
    """
    if not request_dict:
        return request_dict
    
    redacted = {}
    
    for key, value in request_dict.items():
        if key.lower() == "headers" and isinstance(value, dict):
            redacted[key] = redact_headers(value)
        elif key.lower() in ["data", "body", "json", "params"] and isinstance(value, dict):
            redacted[key] = redact_json_payload(value)
        elif key.lower() == "url" and isinstance(value, str):
            # Redact API keys in URL (e.g., ?key=xyz&token=abc)
            redacted[key] = redact_url(value)
        else:
            redacted[key] = value
    
    return redacted


def redact_url(url: str) -> str:
    """Redact sensitive query parameters from URL."""
    if not isinstance(url, str):
        return url
    
    # Replace common sensitive query parameters
    url = re.sub(r'([?&])(?:api.?key|apikey|key|token|secret|auth)=([^&]+)',
                 r'\1\g<2>=REDACTED', url, flags=re.IGNORECASE)
    return url


def redact_response_payload(response_dict: Dict[str, Any]) -> Dict[str, Any]:
    """
    Redact full response payload.
    Usually responses don't contain secrets, but redact anyway for safety.
    """
    if not response_dict:
        return response_dict
    
    return redact_json_payload(response_dict)


def redact_string(text: str, label: str = "text") -> str:
    """
    Redact potential keys/tokens from a raw string response.
    Handles common patterns: "api_key: xyz", "token=abc", etc.
    """
    if not isinstance(text, str):
        return text
    
    # Replace common patterns
    text = re.sub(r'(["\']?)(?:api.?key|apikey|key|password|secret|token|auth)(?:["\']?)[:=]\s*(["\']?)([^,\n\]}"\']+)',
                  r'\1[REDACTED]\3', text, flags=re.IGNORECASE)
    return text


def safe_json_dumps(obj: Any, **kwargs) -> str:
    """
    Like json.dumps but with redaction.
    Recursively redacts sensitive fields before serialization.
    """
    redacted = redact_json_payload(obj)
    return json.dumps(redacted, **kwargs)
