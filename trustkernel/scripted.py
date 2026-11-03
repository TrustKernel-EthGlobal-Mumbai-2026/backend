"""Deterministic transport test double. Never represents actual Sol/Terra inference."""
import json
import uuid
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.runnables import RunnableLambda


NOTE = ('SCRIPTED SMOKE OUTPUT, not model inference. Claim: synthetic snapshot E_SNAPSHOT closes at 2540 USD. '
        'Assumption: the unverified demand note may be inaccurate. Hypothesis: the short trend is inconclusive. '
        'Decision: Hold as a hypothetical research label. Depends_on: E_SNAPSHOT, E_NEWS. '
        'No trade is executed; independent verification is absent.')


class ScriptedModel(BaseChatModel):
    model_name: str = 'scripted-offline'

    @property
    def _llm_type(self):
        return 'trustkernel-scripted-offline'

    def bind_tools(self, tools, **kwargs):
        return self.bind(tools=tools, **kwargs)

    def with_structured_output(self, schema, **kwargs):
        return self.bind(schema_name=schema.__name__) | RunnableLambda(lambda msg: schema.model_validate_json(msg.content))

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        schema = kwargs.get('schema_name')
        if schema:
            values = {
                'ResearchPlan': dict(recommendation='Hold', rationale=NOTE, strategic_actions='Research only; no orders.'),
                'TraderProposal': dict(action='Hold', reasoning=NOTE),
                'PortfolioDecision': dict(rating='Hold', executive_summary=NOTE, investment_thesis=NOTE)
            }
            msg = AIMessage(content=json.dumps(values[schema]))
        elif kwargs.get('tools') and not any(isinstance(m, ToolMessage) for m in messages):
            calls = []
            for tool in kwargs['tools']:
                args = {}
                fields = tool.tool_call_schema.model_fields
                defaults = dict(start_date='2026-10-26', end_date='2026-10-28', curr_date='2026-10-28',
                                indicator='rsi', topic='ETH', look_back_days=3, limit=3)
                for name, field in fields.items():
                    if name in defaults:
                        args[name] = defaults[name]
                calls.append(dict(name=tool.name, args=args, id=str(uuid.uuid4()), type='tool_call'))
            msg = AIMessage(content='', tool_calls=calls)
        else:
            msg = AIMessage(content=NOTE)
        return ChatResult(generations=[ChatGeneration(message=msg)])
