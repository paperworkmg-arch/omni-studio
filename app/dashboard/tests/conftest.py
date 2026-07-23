"""Pytest configuration for the Omni-Studio dashboard."""
import sys
from pathlib import Path

# Ensure dashboard modules can be imported during tests
DASHBOARD_DIR = Path(__file__).parent.parent
OMNI_SOURCE_DIR = DASHBOARD_DIR.parent / "omni-source"
VAULT_DIR = OMNI_SOURCE_DIR / "data" / "vault"
sys.path.insert(0, str(DASHBOARD_DIR))
sys.path.insert(0, str(OMNI_SOURCE_DIR))
sys.path.insert(0, str(VAULT_DIR))
