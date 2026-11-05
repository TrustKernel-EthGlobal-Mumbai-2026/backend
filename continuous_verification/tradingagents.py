"""Host-side feedback plumbing, not a verifier or an accepted service wire API.

LocalBinding/LocalFeedback are lane-local bridge values. A/B integration must
translate accepted contracts and validate issuer/policy before constructing them.
Nothing here launches a model, provider, historical runner or persistent service.
"""
from dataclasses import asdict, dataclass
from hashlib import sha256
import json
from pathlib import Path

UPSTREAM_COMMIT = "c4544913a14ed3df5f1ed7b9e8483270ce20682a"
TRUSTED_INSTRUCTION = (Path(__file__).parent / "prompts/tradingagents.md").read_text(encoding="utf-8")


class BoundaryError(RuntimeError):
    """An unavailable or stale boundary cannot authorize a report."""


@dataclass(frozen=True)
class LocalBinding:
    run_id: str
    proposal_id: str
    revision: int
    text_digest: str
    checkpoint_id: str
    policy_binding: str


@dataclass(frozen=True)
class LocalFeedback:
    binding: LocalBinding
    assessment_id: str
    readiness: str
    disposition: str
    findings_json: str

    def __post_init__(self):
        if self.readiness not in {"READY", "NOT_READY", "CAPTURE_GAP", "ERROR"}:
            raise ValueError("Unknown readiness")
        if self.disposition not in {"ADVISE", "HOLD", "RECHECK"}:
            raise ValueError("Unknown disposition")
        if not self.assessment_id or not isinstance(json.loads(self.findings_json), list):
            raise ValueError("Assessment ID and findings list required")


@dataclass(frozen=True)
class Limits:
    source_rounds: int = 2
    verify_calls: int = 2
    remediations: int = 1

    def __post_init__(self):
        if any(type(v) is not int or v < 0 for v in asdict(self).values()):
            raise ValueError("Allowances must be nonnegative integers")


class FeedbackBoundary:
    """Single-run, single-writer local host; callbacks are trusted host code.

    checkpoint(proposal_record) must establish an immutable captured input prefix.
    assess(binding) must return normalized authenticated A/B results, never infer
    success from missing evidence. Until integration those callbacks are doubles.
    emit must durably record observations in an integrated host; this class makes
    no persistence claim. An exception propagates and leaves release unavailable.
    authorize is optional, separate host enforcement, evaluated again at use time.
    proposal_id names this report artifact only, not a later paper decision.
    """

    def __init__(self, *, run_id, proposal_id, policy_binding, checkpoint, assess,
                 emit, limits=Limits(), authorize=None):
        if not all(isinstance(v, str) and v for v in (run_id, proposal_id, policy_binding)):
            raise ValueError("Host identities must be nonempty strings")
        self.run_id, self.proposal_id, self.policy_binding = run_id, proposal_id, policy_binding
        self.checkpoint, self.assess, self.emit = checkpoint, assess, emit
        self.limits, self.authorize = limits, authorize
        self.counts = dict(source_rounds=0, verify_calls=0, remediations=0)
        self.proposals = []
        self.current = self.feedback = None
        self.pending_returns = {}
        self.delivered = {}
        self.included = set()
        self.stopped = False
        self._input_sequence = 0

    def next_input_sequence(self):
        self._input_sequence += 1
        return self._input_sequence

    def _spend(self, name):
        if self.stopped or self.counts[name] >= getattr(self.limits, name):
            raise BoundaryError("Stopped or exhausted " + name)
        self.counts[name] += 1  # Failures spend allowance too; no retry windfall.

    def submit(self, text):
        if self.stopped or not isinstance(text, str) or not text.strip():
            raise BoundaryError("Stopped or empty proposal")
        self.current = self.feedback = None  # Even a denied revision cannot reuse advice.
        if self.proposals:
            self._spend("remediations")
        revision = len(self.proposals) + 1
        record = dict(run_id=self.run_id, proposal_id=self.proposal_id,
                      revision=revision, text=text, text_digest=sha256(text.encode()).hexdigest())
        self.proposals.append(record.copy())
        self.emit("proposal.submitted", record.copy())
        checkpoint_id = self.checkpoint(record.copy())
        if not isinstance(checkpoint_id, str) or not checkpoint_id:
            raise BoundaryError("No registered checkpoint")
        self.current = LocalBinding(self.run_id, self.proposal_id, revision,
                                    record["text_digest"], checkpoint_id, self.policy_binding)
        try:
            self.emit("proposal.bound", asdict(self.current))
        except Exception:
            self.current = None
            raise
        return self.current

    def verify(self, *, origin="voluntary"):
        if origin not in {"voluntary", "host"} or self.current is None:
            raise BoundaryError("No proposal or unknown caller")
        self.feedback = None
        self._spend("verify_calls")
        binding = self.current
        self.emit("verification.requested", dict(binding=asdict(binding), origin=origin))
        result = self.assess(binding)
        if not isinstance(result, LocalFeedback) or result.binding != binding or self.current != binding:
            raise BoundaryError("Stale or malformed assessment binding")
        self.emit("feedback.prepared", dict(binding=asdict(binding), assessment_id=result.assessment_id))
        self.feedback = result
        payload = json.dumps(asdict(result), sort_keys=True, separators=(",", ":"))
        self.pending_returns[payload] = result
        return payload

    def observe_tool_return(self, call_id, payload):
        """Call only after observing a real return, not while preparing feedback."""
        result = self.pending_returns.get(payload)
        if not call_id or result is None:
            raise BoundaryError("Unrecognized feedback return")
        if call_id in self.delivered and self.delivered[call_id] != payload:
            raise BoundaryError("Tool call ID reused with different feedback")
        self.emit("feedback.delivered", dict(call_id=call_id, payload=payload))
        self.delivered[call_id] = payload

    def observe_next_input(self, input_id, tool_returns):
        """Exact (call ID, content) pairs from the assembled next model request."""
        if not input_id:
            raise BoundaryError("Model input identity required")
        for call_id, payload in tool_returns:
            if self.delivered.get(call_id) == payload:
                self.emit("feedback.input_included", dict(input_id=input_id, call_id=call_id, payload=payload))
                self.included.add(payload)

    def acknowledge(self, assessment_id, text):
        result = self.feedback
        if result is None or result.assessment_id != assessment_id:
            raise BoundaryError("No current assessment to acknowledge")
        self.emit("feedback.acknowledged", dict(assessment_id=assessment_id, text=text))

    def source_round(self, operations):
        """One dispatched batch of trusted host source callbacks, counted separately."""
        self.feedback = None  # New evidence cannot reuse old advice.
        self.current = None  # Host must register a new revision/checkpoint.
        self._spend("source_rounds")
        self.emit("source.round_started", dict(round=self.counts["source_rounds"]))
        return [operation() for operation in operations]

    def report_boundary_allowed(self, text):
        """Only an explicit trusted host authorizer can enforce the named boundary."""
        result = self.feedback
        if (self.stopped or self.authorize is None or self.current is None or result is None
                or result.binding != self.current or result.readiness != "READY"
                or result.disposition != "ADVISE"):
            return False
        if not isinstance(text, str) or sha256(text.encode()).hexdigest() != self.current.text_digest:
            return False
        payload = json.dumps(asdict(result), sort_keys=True, separators=(",", ":"))
        if payload not in self.included:
            return False
        return self.authorize(self.current, result) is True

    def abstain(self, reason):
        self.stopped = True
        self.feedback = None
        self.emit("proposal.abstained", dict(reason=reason, binding=asdict(self.current) if self.current else None))


def make_verify_tool(boundary):
    """Optional native LangChain tool. No agent-controlled checkpoint/policy args."""
    from langchain_core.tools import StructuredTool

    def verify_proposal() -> str:
        """Verify the current host-bound proposal; return scoped findings for recheck."""
        return boundary.verify(origin="voluntary")

    return StructuredTool.from_function(verify_proposal)


def observe_native_returns(boundary, messages):
    """Observe actual ToolMessages before pinned take_turn flattens wrap-up history."""
    for message in messages:
        if getattr(message, "type", None) == "tool" and message.name == "verify_proposal":
            boundary.observe_tool_return(message.tool_call_id, message.content)


def make_trusted_model(llm, boundary):
    """Wrap model input assembly; no invocation occurs while constructing this.

    Caller must offer identical tool tuples to the analyst and its ToolNode, and
    call observe_native_returns at agent reentry. This wrapper does not modify an
    upstream module, build a graph, or provide restart recovery. Its input event
    records attempted invocation; provider acceptance/attention is not inferred.
    """
    from langchain_core.messages import SystemMessage
    from langchain_core.runnables import Runnable

    class TrustedModel(Runnable):
        def __init__(self, delegate):
            self.delegate = delegate

        def bind_tools(self, tools, **kwargs):
            return TrustedModel(self.delegate.bind_tools(tools, **kwargs))

        def invoke(self, prompt, config=None, **kwargs):
            messages = prompt.to_messages() if hasattr(prompt, "to_messages") else list(prompt)
            messages = [SystemMessage(content=TRUSTED_INSTRUCTION), *messages]
            pairs = []
            for message in messages:
                if getattr(message, "type", None) == "tool":
                    pairs.append((message.tool_call_id, message.content))
                elif getattr(message, "type", None) == "human":
                    # Exact pinned _as_text representation; call IDs are recovered
                    # only from separately observed returns, not guessed from text.
                    for call_id, payload in boundary.delivered.items():
                        if message.content == "[verify_proposal returned]\n" + payload:
                            pairs.append((call_id, payload))
            # IDs must remain unique across bound wrappers and unbound wrap-up.
            input_id = f"{boundary.run_id}:input:{boundary.next_input_sequence()}"
            boundary.observe_next_input(input_id, pairs)
            # Fingerprints bind the actual visible envelope at this seam without
            # copying potentially private prompts into a second capture store.
            message_digests = [sha256(json.dumps(m.model_dump(mode="json"), sort_keys=True,
                               separators=(",", ":")).encode()).hexdigest() for m in messages]
            boundary.emit("model.input_attempted", dict(input_id=input_id, trusted_instruction=True,
                                                       message_digests=message_digests))
            return self.delegate.invoke(messages, config=config, **kwargs)

    return TrustedModel(llm)
