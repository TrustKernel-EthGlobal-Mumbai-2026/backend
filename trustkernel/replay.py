"""Process-local tool replacement; original schemas/prompts and graph retained."""
import json
from contextlib import contextmanager
from dataclasses import replace
from unittest.mock import patch

from langchain_core.tools import StructuredTool
from tradingagents.agents.analysts import market_analyst, news_analyst
from tradingagents.graph import analyst_execution

from .trace import digest


@contextmanager
def fixture_tools(fixture, trace):
    replacements = {}
    for module in (market_analyst, news_analyst):
        tools = []
        for original in module.TOOLS:
            name = original.name
            if name not in fixture['tools']:
                raise ValueError(f'Fixture missing tool: {name}')

            def serve(_name=name, **kwargs):
                evidence = fixture['tools'][_name]
                result = dict(fixture_id=fixture['fixture_id'], fixture_kind=fixture['kind'],
                              provenance=fixture['provenance'], content_hash=digest(evidence),
                              request=kwargs, evidence=evidence,
                              replay_semantics='Frozen snapshot; arguments recorded, no live retrieval. Unsupported series explicitly unavailable.')
                trace.emit('evidence.retrieved', result)
                return json.dumps(result, ensure_ascii=False)

            tools.append(StructuredTool.from_function(serve, name=name, description=original.description,
                                                     args_schema=original.args_schema))
        replacements[module] = tuple(tools)
    specs = dict(analyst_execution.ANALYST_NODE_SPECS)
    specs['market'] = replace(specs['market'], tools=replacements[market_analyst])
    specs['news'] = replace(specs['news'], tools=replacements[news_analyst])
    with patch.object(market_analyst, 'TOOLS', replacements[market_analyst]), \
         patch.object(news_analyst, 'TOOLS', replacements[news_analyst]), \
         patch.object(analyst_execution, 'ANALYST_NODE_SPECS', specs):
        yield
