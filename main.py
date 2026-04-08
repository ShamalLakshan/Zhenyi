"""
LLM Research Council — Main Entry Point
────────────────────────────────────────
Run with:   python main.py
Commands:
  <any text>   Run a research query
  /status      Show key pool and scraper status
  /history     Show recent queries
  /chain <id>  Show thought chain for a query ID
  /help        Show commands
  /quit        Exit
"""

import asyncio
import logging
import sys
from dotenv import load_dotenv

load_dotenv()

# ── Logging setup ─────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.WARNING,           # keep console clean
    format="%(levelname)s [%(name)s] %(message)s",
    handlers=[
        logging.FileHandler("council.log", encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
# Show INFO from pipeline and registry, suppress from noisy libs
logging.getLogger("core.pipeline").setLevel(logging.INFO)
logging.getLogger("scrapers.registry").setLevel(logging.INFO)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logging.getLogger("openai").setLevel(logging.WARNING)
logging.getLogger("cohere").setLevel(logging.WARNING)

from core.key_pool import KeyPool
from core.state_store import init_db, get_thought_chain, get_recent_queries
from core.pipeline import run
from scrapers.registry import ScraperRegistry
from core.exceptions import ConfigError


# ── Formatting helpers ────────────────────────────────────────────────────────

def _bar(value: float, width: int = 20) -> str:
    filled = int(value * width)
    return "█" * filled + "░" * (width - filled)


def _print_result(result: dict):
    qid   = result.get("query_id", "?")
    prof  = result.get("profile", "?")
    conf  = result.get("confidence", 0.0)
    dur   = result.get("duration_ms", 0.0)
    plan  = result.get("plan", {})

    print()
    print("═" * 64)
    print(f"  Query ID   : {qid}")
    print(f"  Profile    : {prof}")
    print(f"  Confidence : {_bar(conf)} {conf:.2f}")
    print(f"  Duration   : {dur/1000:.1f}s")

    # Role assignments
    roles = plan.get("roles", {})
    if roles:
        print(f"  Roles      :")
        for role, cfg in roles.items():
            p = cfg.get("provider", "?")
            m = cfg.get("model", "?")
            print(f"    {role:<14} → {p}/{m}")

    print()
    print("  ANSWER")
    print("  " + "─" * 60)
    # Word-wrap answer at 62 chars
    answer = result.get("answer", "No answer.")
    for line in answer.splitlines():
        if not line.strip():
            print()
            continue
        words = line.split()
        current = "  "
        for word in words:
            if len(current) + len(word) + 1 > 64:
                print(current)
                current = "  " + word
            else:
                current = current + " " + word if current.strip() else "  " + word
        if current.strip():
            print(current)

    sources = result.get("sources", [])
    if sources:
        print()
        print("  SOURCES")
        print("  " + "─" * 60)
        for s in sources[:8]:
            print(f"    {s}")

    print("═" * 64)


def _print_status(pool: KeyPool, registry: ScraperRegistry):
    print()
    print("── KEY POOL STATUS ─────────────────────────────────────────")
    report = pool.status_report()
    for provider, keys in report.items():
        print(f"\n  {provider.upper()}")
        for k in keys:
            env   = k.get("env_var", "?")
            ready = "✓ ready" if k.get("ready") else "✗ not ready"
            if not k.get("configured"):
                ready = "– not configured"
            daily = k.get("daily_remaining", 0)
            cool  = k.get("cooldown_seconds", 0.0)
            print(f"    {env:<20} {ready:<16} daily_remaining={daily}", end="")
            if cool > 0:
                print(f" cooldown={cool:.0f}s", end="")
            print()

    print()
    print("── SCRAPER STATUS ──────────────────────────────────────────")
    for name, info in registry.status().items():
        avail  = "✓ available" if info.get("available") else "✗ unavailable"
        circuit = " [circuit open]" if info.get("circuit_open") else ""
        enabled = "" if info.get("enabled") else " [disabled]"
        print(f"  {name:<16} {avail}{circuit}{enabled}")
    print()


async def _print_chain(query_id: str):
    chain = await get_thought_chain(query_id)
    if not chain:
        print(f"  No thought chain found for query_id: {query_id}")
        return
    print(f"\n── THOUGHT CHAIN: {query_id} ────────────────────────────────")
    for step in chain:
        ts = step.get("created_at", 0)
        import datetime
        t = datetime.datetime.fromtimestamp(ts).strftime("%H:%M:%S")
        print(f"  [{t}] {step['step']:<22} {step['note']}")
    print()


async def _print_history():
    rows = await get_recent_queries(10)
    if not rows:
        print("  No query history yet.")
        return
    print("\n── RECENT QUERIES ──────────────────────────────────────────")
    for r in rows:
        import datetime
        ts = r.get("created_at", 0)
        t = datetime.datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M")
        qid  = r.get("query_id", "?")
        prof = r.get("profile", "?")
        conf = r.get("confidence", 0.0)
        dur  = (r.get("duration_ms") or 0) / 1000
        text = (r.get("query_text") or "")[:50]
        print(f"  [{t}] {qid} | {prof:<16} | conf={conf:.2f} | {dur:.1f}s | {text}")
    print()


def _print_help():
    print("""
  COMMANDS
  ────────────────────────────────────────────
  <any text>      Run a research query
  /status         Show key pool + scraper status
  /history        Show last 10 queries
  /chain <id>     Show thought chain for query ID
  /help           Show this help
  /quit  /exit    Exit
""")


# ── Main ──────────────────────────────────────────────────────────────────────

async def main():
    print()
    print("  ┌─────────────────────────────────────────────┐")
    print("  │         LLM Research Council  v1.0          │")
    print("  └─────────────────────────────────────────────┘")
    print()

    # Init database
    await init_db()

    # Init key pool
    try:
        pool = KeyPool()
    except ConfigError as e:
        print(f"  [ERROR] Config error: {e}")
        print("  Make sure agents.yaml exists in the current directory.")
        return

    configured = pool.total_configured_keys()
    if configured == 0:
        print("  [WARNING] No API keys configured.")
        print("  Copy .env.example to .env and fill in your keys.")
        print()

    # Init scrapers
    scraper_configs = pool.config.get("scrapers", {})
    registry = ScraperRegistry(scraper_configs)

    print(f"  Keys configured : {configured}")
    print(f"  Type /help for commands, or enter a query to start.")
    print()

    while True:
        try:
            raw = input("council> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n  Goodbye.")
            break

        if not raw:
            continue

        # Commands
        if raw.lower() in ("/quit", "/exit", "quit", "exit", "q"):
            print("  Goodbye.")
            break
        elif raw.lower() == "/help":
            _print_help()
        elif raw.lower() == "/status":
            _print_status(pool, registry)
        elif raw.lower() == "/history":
            await _print_history()
        elif raw.lower().startswith("/chain"):
            parts = raw.split(maxsplit=1)
            if len(parts) < 2:
                print("  Usage: /chain <query_id>")
            else:
                await _print_chain(parts[1].strip())
        elif raw.startswith("/"):
            print(f"  Unknown command: {raw}. Type /help for commands.")
        else:
            # Run pipeline
            try:
                result = await run(raw, pool, registry)
                _print_result(result)
            except Exception as e:
                print(f"\n  [ERROR] Pipeline raised an unhandled exception: {e}")
                print("  This is a bug — please check council.log for details.")
                logging.getLogger(__name__).exception("Unhandled pipeline error")


if __name__ == "__main__":
    asyncio.run(main())
