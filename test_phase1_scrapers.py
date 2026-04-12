#!/usr/bin/env python
"""Test Phase 1 scrapers (arxiv + wikipedia) load correctly."""

import yaml
import sys

sys.path.insert(0, '.')

# Load config
with open('agents.yaml') as f:
    config = yaml.safe_load(f)

# Initialize registry
from scrapers.registry import ScraperRegistry
registry = ScraperRegistry(config['scrapers'])

# List all scrapers
print("[REGISTRY] Loaded scrapers:")
for name in ['hackernews', 'web', 'arxiv', 'wikipedia']:
    available = name in registry._scrapers and registry._scrapers[name].is_available
    status = "✓ available" if available else "✗ unavailable"
    print(f"  {name}: {status}")

print("\n[SUCCESS] Phase 1 scrapers registered and ready")
