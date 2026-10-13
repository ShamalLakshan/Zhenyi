"""
Gateway Models & Provider Specifications
─────────────────────────────────────────
Defines data structures for API keys, rate limits, provider specifications,
and test verification results for Zhenyi's Unified LLM Gateway.
"""

from enum import Enum
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field
import time


class ProviderTier(int, Enum):
    TIER_0_SPEED = 0       # Fast, high-RPM volume (Groq, Cerebras, Cloudflare)
    TIER_1_REASONING = 1   # Deep reasoning (SambaNova 405B, OpenRouter, GitHub Models)
    TIER_2_CONTEXT = 2     # Massive context (Gemini 2.5 Flash - 1M tokens)
    TIER_3_SYNTHESIS = 3   # Grounding & RAG synthesis (Cohere, Gemini)
    TIER_4_LOCAL = 4       # Offline / Local fallback (Ollama, vLLM)


class KeyStatus(str, Enum):
    READY = "ready"
    COOLING = "cooling"
    EXHAUSTED = "exhausted"
    DISABLED = "disabled"
    ERROR = "error"


class ResearchMode(str, Enum):
    ECONOMY = "economy"           # Uses Tier 0 (Groq/Cerebras) to conserve scarce daily quotas
    DEEP_RESEARCH = "deep_research" # Uses Tier 1 & Tier 2 for frontier depth and 1M context


class ProviderSpec(BaseModel):
    name: str
    display_name: str
    base_url: str
    tier: ProviderTier
    default_model: str
    available_models: List[str]
    rpm_default: int
    daily_quota_default: int
    strengths: List[str]
    requires_key: bool = True
    setup_url: str = ""


# Default provider specifications for all free-tier providers
PROVIDER_SPECS: Dict[str, ProviderSpec] = {
    "groq": ProviderSpec(
        name="groq",
        display_name="Groq Cloud",
        base_url="https://api.groq.com/openai/v1",
        tier=ProviderTier.TIER_0_SPEED,
        default_model="llama-3.3-70b-versatile",
        available_models=["llama-3.3-70b-versatile", "llama-3.1-8b-instant"],
        rpm_default=30,
        daily_quota_default=14400,
        strengths=["speed", "triage", "extraction", "high_volume"],
        setup_url="https://console.groq.com",
    ),
    "cerebras": ProviderSpec(
        name="cerebras",
        display_name="Cerebras",
        base_url="https://api.cerebras.ai/v1",
        tier=ProviderTier.TIER_0_SPEED,
        default_model="llama3.1-8b",
        available_models=["llama3.1-8b", "llama3.3-70b"],
        rpm_default=30,
        daily_quota_default=14400,
        strengths=["ultra_speed", "scoring", "fast_analysis"],
        setup_url="https://cloud.cerebras.ai",
    ),
    "sambanova": ProviderSpec(
        name="sambanova",
        display_name="SambaNova Cloud",
        base_url="https://api.sambanova.ai/v1",
        tier=ProviderTier.TIER_1_REASONING,
        default_model="Meta-Llama-3.1-405B-Instruct",
        available_models=[
            "Meta-Llama-3.1-405B-Instruct",
            "Meta-Llama-3.3-70B-Instruct",
            "Meta-Llama-3.1-8B-Instruct",
            "Qwen2.5-72B-Instruct",
        ],
        rpm_default=20,
        daily_quota_default=1000,
        strengths=["frontier_reasoning", "deep_analysis", "synthesis", "405b"],
        setup_url="https://cloud.sambanova.ai",
    ),
    "gemini": ProviderSpec(
        name="gemini",
        display_name="Google Gemini",
        base_url="https://generativelanguage.googleapis.com",
        tier=ProviderTier.TIER_2_CONTEXT,
        default_model="gemini-2.5-flash",
        available_models=["gemini-2.5-flash", "gemini-2.5-flash-lite"],
        rpm_default=15,
        daily_quota_default=1000,
        strengths=["massive_context", "multimodal", "global_synthesis", "planning"],
        setup_url="https://aistudio.google.com",
    ),
    "openrouter": ProviderSpec(
        name="openrouter",
        display_name="OpenRouter (Free Endpoints)",
        base_url="https://openrouter.ai/api/v1",
        tier=ProviderTier.TIER_1_REASONING,
        default_model="meta-llama/llama-3.3-70b-instruct:free",
        available_models=[
            "meta-llama/llama-3.3-70b-instruct:free",
            "deepseek/deepseek-r1:free",
            "qwen/qwen-2.5-72b-instruct:free",
            "meta-llama/llama-3.3-70b-instruct",
        ],
        rpm_default=20,
        daily_quota_default=200,
        strengths=["diverse_models", "deepseek_r1", "reasoning"],
        setup_url="https://openrouter.ai",
    ),
    "github": ProviderSpec(
        name="github",
        display_name="GitHub Models",
        base_url="https://models.inference.ai.azure.com",
        tier=ProviderTier.TIER_1_REASONING,
        default_model="gpt-4o-mini",
        available_models=["gpt-4o-mini", "Meta-Llama-3.3-70B-Instruct", "Phi-4"],
        rpm_default=15,
        daily_quota_default=150,
        strengths=["structured_json", "high_precision", "verification"],
        setup_url="https://github.com/marketplace/models",
    ),
    "cohere": ProviderSpec(
        name="cohere",
        display_name="Cohere",
        base_url="https://api.cohere.com/v1",
        tier=ProviderTier.TIER_3_SYNTHESIS,
        default_model="command-a-03-2025",
        available_models=["command-a-03-2025"],
        rpm_default=20,
        daily_quota_default=1000,
        strengths=["synthesis", "citation_grounding", "rag"],
        setup_url="https://dashboard.cohere.com",
    ),
    "cloudflare": ProviderSpec(
        name="cloudflare",
        display_name="Cloudflare Workers AI",
        base_url="https://api.cloudflare.com/client/v4/accounts/{account_id}/ai/v1",
        tier=ProviderTier.TIER_0_SPEED,
        default_model="@cf/meta/llama-3.3-70b-instruct",
        available_models=[
            "@cf/meta/llama-3.3-70b-instruct",
            "@cf/deepseek-ai/deepseek-r1-distill-qwen-32b",
            "@cf/meta/llama-3.1-8b-instruct",
        ],
        rpm_default=30,
        daily_quota_default=10000,
        strengths=["edge_speed", "high_volume", "fast_triage"],
        setup_url="https://dash.cloudflare.com",
    ),
    "huggingface": ProviderSpec(
        name="huggingface",
        display_name="Hugging Face Inference",
        base_url="https://api-inference.huggingface.co/v1",
        tier=ProviderTier.TIER_1_REASONING,
        default_model="Qwen/Qwen2.5-72B-Instruct",
        available_models=[
            "Qwen/Qwen2.5-72B-Instruct",
            "mistralai/Mistral-Small-24B-Instruct-2501",
        ],
        rpm_default=10,
        daily_quota_default=500,
        strengths=["open_ecosystem", "specialized_models"],
        setup_url="https://huggingface.co/settings/tokens",
    ),
    "ollama": ProviderSpec(
        name="ollama",
        display_name="Ollama (Local / Air-Gapped)",
        base_url="http://localhost:11434/v1",
        tier=ProviderTier.TIER_4_LOCAL,
        default_model="llama3.2:latest",
        available_models=["llama3.2:latest", "qwen2.5:7b", "mistral:latest"],
        rpm_default=120,
        daily_quota_default=999999,
        strengths=["offline", "zero_quota_limits", "privacy"],
        requires_key=False,
        setup_url="https://ollama.com",
    ),
}


class KeyModel(BaseModel):
    id: str
    provider: str
    label: str
    key_masked: str
    rpm_limit: int = 30
    daily_quota: int = 1000
    daily_used: int = 0
    tokens_used_today: int = 0
    status: KeyStatus = KeyStatus.READY
    cooldown_until: float = 0.0
    consecutive_errors: int = 0
    last_used_at: Optional[float] = None
    last_exhaustion_time: float = 0.0
    created_at: float = Field(default_factory=time.time)
    updated_at: float = Field(default_factory=time.time)

    @property
    def is_cooling(self) -> bool:
        return time.time() <= self.cooldown_until

    @property
    def cooldown_remaining_seconds(self) -> float:
        return max(0.0, self.cooldown_until - time.time())

    @property
    def daily_remaining(self) -> int:
        return max(0, self.daily_quota - self.daily_used)

    @property
    def is_usable(self) -> bool:
        return (
            self.status == KeyStatus.READY
            and not self.is_cooling
            and self.daily_remaining > 0
        )


class KeyCreateRequest(BaseModel):
    provider: str
    key_value: str
    label: Optional[str] = None
    rpm_limit: Optional[int] = None
    daily_quota: Optional[int] = None


class KeyUpdateRequest(BaseModel):
    label: Optional[str] = None
    rpm_limit: Optional[int] = None
    daily_quota: Optional[int] = None
    status: Optional[KeyStatus] = None


class KeyTestRequest(BaseModel):
    provider: str
    key_value: str
    model: Optional[str] = None


class KeyTestResult(BaseModel):
    key_id: Optional[str] = None
    provider: str
    model: str
    success: bool
    latency_ms: float
    message: str
    timestamp: float = Field(default_factory=time.time)
