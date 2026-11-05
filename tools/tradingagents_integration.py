"""Opt-in real-import analyst smoke readiness; default NO-PAID preflight."""
import argparse
from contextlib import contextmanager
from copy import deepcopy
import hashlib
import importlib
import json
import os
from pathlib import Path
import sys
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.dont_write_bytecode = True

from continuous_verification import digest
from continuous_verification.tradingagents import UPSTREAM_COMMIT

PROFILE = dict(model="gpt-6.1-sol", endpoint="https://api.openai.com/v1", effort="medium",
    service_tier="default", max_model_calls=4, max_output_tokens=1024,
    source_rounds=1, verify_calls=2, remediations=1, graph_tool_rounds=3,
    max_concurrency=1, recursion_limit=12, request_timeout_seconds=25,
    wall_seconds=120, max_input_bytes=40000, retries=0,
    cumulative_hard_limit_usd=5.0, proposed_incremental_limit_usd=1.30,
    tool_choice="auto", live_sources=False)


def preflight_plan():
    """Presence/status only; never open budget files or inspect credential values."""
    return dict(profile=deepcopy(PROFILE), profile_digest=digest(PROFILE), execution_enabled=False,
        credential_status="ENV_NAME_PRESENT_VALUE_UNREAD" if "OPENAI_API_KEY" in os.environ else "ENV_NAME_ABSENT",
        budget_status="NOT_OPENED_OR_MUTATED; existing cumulative ledger/unknown holds require separate review",
        model_access="NOT_CHECKED; no account/provider request", new_user_approval="REQUIRED",
        paid_launch_status="DISABLED_PENDING_NEW_APPROVAL_AND_RUNTIME_GATES",
        scope="real imported bounded market analyst/subgraph; not full GraphSetup",
        source_mode="authored frozen tool returns; no native vendor/source body runs")


def checked_upstream(path):
    """Reuse the original pin/origin/tracked-integrity guard before child sandbox."""
    from trustkernel import runner
    root = Path(path).resolve()
    if root.name != "TradingAgents" or root.parent.name != "upstream":
        raise ValueError("Expected reviewed upstream/TradingAgents checkout")
    with patch.object(runner, "ROOT", root.parent.parent):
        runner.upstream_check()
    return root


@contextmanager
def real_runtime(upstream):
    """Import actual installed pinned package, blocking implicit dotenv discovery.

    This executes normal Python imports, never AST extraction. File bytes are not
    patched; process-local frozen tools are installed separately during a run.
    """
    import dotenv
    sys.path.insert(0, str(upstream))
    with patch.object(dotenv, "find_dotenv", return_value=""), patch.object(dotenv, "load_dotenv", return_value=False):
        package = importlib.import_module("tradingagents")
        market = importlib.import_module("tradingagents.agents.analysts.market_analyst")
        setup = importlib.import_module("tradingagents.graph.setup")
        config = importlib.import_module("tradingagents.dataflows.config")
        defaults = importlib.import_module("tradingagents.default_config")
        modules = [package, market, setup]
        for module in modules:
            if not Path(module.__file__).resolve().is_relative_to(upstream):
                raise ValueError("Unexpected installed module origin")
        yield dict(package=package, market=market, setup=setup, config=config, defaults=defaults,
            import_proof=[dict(module=m.__name__, file=str(Path(m.__file__).relative_to(upstream)),
                sha256=hashlib.sha256(Path(m.__file__).read_bytes()).hexdigest()) for m in modules])
