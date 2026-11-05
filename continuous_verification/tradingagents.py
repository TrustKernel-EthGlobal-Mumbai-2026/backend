"""TradingAgents host plumbing over accepted continuous-verification 0.2.

No policy evaluator, provider/model launch, service coverage assertion or global
clearance. B's reviewed persistence/checkpoint facade is still an integration gate.
"""
from copy import deepcopy
from dataclasses import asdict, dataclass
from pathlib import Path

from .contracts import (
    CONTRACT_VERSION, canonical_json, text_digest, digest,
    validate_event, validate_request, validate_checkpoint, validate_policy,
    validate_result, assessment_binding, binding_matches,
)

UPSTREAM_COMMIT = "c4544913a14ed3df5f1ed7b9e8483270ce20682a"
TRUSTED_INSTRUCTION = (Path(__file__).parent / "prompts/tradingagents.md").read_text(encoding="utf-8")


class BoundaryError(RuntimeError):
    """An unavailable or stale boundary cannot authorize a report."""


def make_stored_assessor(backend):
    """Prepare B's provisional execute seam; no real-service parity claimed.

    backend is preconfigured by the trusted host with its own Principal. Only A's
    request crosses this boundary; local policy/events/coverage are never sent as
    authority. FeedbackBoundary validates the returned binding against its exact
    service-resolved view. No fallback to a fabricated or local successful result.
    """
    def assess(request, *, checkpoint, events, policy):
        validate_request(request)
        return backend.execute("verify", deepcopy(request))
    return assess


def make_host_ingest(backend, *, run_id, accept_receipt):
    """Prepare assigned-collector ingest; receipt DTO awaits B review.

    accept_receipt(response, event) must explicitly validate B's actual durable
    receipt. No configure/register/coverage/policy operation is agent-accessible.
    Stable content-derived batch IDs permit retry of the exact event only.
    """
    def ingest(event):
        validate_event(event)
        if event["run_id"] != run_id:
            raise BoundaryError("Cross-run host ingest")
        response = backend.execute("ingest_events", dict(run_id=run_id,
            batch_id="tradingagents-" + digest(event), events=[deepcopy(event)]))
        if accept_receipt(deepcopy(response), deepcopy(event)) is not True:
            raise BoundaryError("Unaccepted host-ingest receipt")
        return response
    return ingest


@dataclass(frozen=True)
class Limits:
    source_rounds: int = 2
    verify_calls: int = 2
    remediations: int = 1

    def __post_init__(self):
        if any(type(v) is not int or v < 0 for v in asdict(self).values()):
            raise ValueError("Allowances must be nonnegative integers")


class HostEventCapture:
    """Single-writer event builder; emit is trusted host ingest, not a service.

    Content is privacy-filtered before hashing. emit(event) must succeed before
    sequence advancement; on failure the caller must stop/retry the exact event.
    It asserts no stream coverage, authentication or durable acknowledgement.
    Identity uniqueness/retry/restart persistence must be supplied by B.
    """

    def __init__(self, *, run_id, stream_id, producer_id, redaction_profile, redact, emit):
        self.run_id, self.stream_id = run_id, stream_id
        self.producer_id, self.redaction_profile = producer_id, redaction_profile
        self.redact, self.emit = redact, emit
        self.events = []
        self.tool_returns = {}

    def _record(self, event_type, content, payload, parents=()):
        retained = self.redact(content)
        if not isinstance(retained, str):
            raise BoundaryError("Redactor must return retained text")
        sequence = len(self.events) + 1
        event = dict(contract_version=CONTRACT_VERSION, run_id=self.run_id,
            stream_id=self.stream_id, event_id=f"{self.stream_id}:{sequence}", sequence=sequence,
            event_type=event_type, producer=dict(id=self.producer_id, kind="instrumented",
            adapter_version="tradingagents-feedback-0.2"), occurred_at=None, observed_at=None,
            recorded_at=None, parents=list(parents), content=retained, content_digest=text_digest(retained),
            origin=dict(uri=None, json_pointer=None, span=[0, len(retained)],
                        redaction_profile=self.redaction_profile), payload=deepcopy(payload))
        validate_event(event)
        self.emit(deepcopy(event))
        self.events.append(event)
        return deepcopy(event)

    def tool_result(self, *, call_id, tool_name, content, status):
        # Native tool status indicates invocation completion, not source authority.
        candidate = dict(tool_name=tool_name, content=self.redact(content), status=status)
        if call_id in self.tool_returns:
            old = self.tool_returns[call_id]
            if candidate != old[0]:
                raise BoundaryError("Tool call identity reused with different return")
            return deepcopy(old[1])
        event = self._record("tool_result", content,
                             dict(call_id=call_id, tool_name=tool_name, status=status))
        self.tool_returns[call_id] = (candidate, event)
        return event

    def model_input(self, *, messages, report_id, report_revision, included_event_ids, boundary):
        # Call at the actual assembled-input seam; historical transcripts without
        # this observation must use UNKNOWN, never reconstructed ASSEMBLED.
        return self._record("model_input", canonical_json(messages), dict(
            input_id=f"{self.stream_id}:input:{len(self.events) + 1}", report_id=report_id,
            report_revision=report_revision, included_event_ids=list(included_event_ids), boundary=boundary),
            parents=included_event_ids)

    def report(self, *, content, report_id, revision, input_event_id, completion, phase):
        # Completion and phase are explicit host observations, never inferred from
        # nonempty text or a successful graph process exit.
        return self._record("report", content, dict(report_id=report_id, revision=revision,
            report_type="market", input_event_id=input_event_id, completion=completion, phase=phase),
            parents=[] if input_event_id is None else [input_event_id])

    def assembled_native_input(self, messages, *, report_id, report_revision):
        """Observe actual assembly; only intact ToolMessages identify call origins.

        Flattened marker text has no call identity, even with a unique body/name
        match. Without separately instrumented transformation lineage it makes
        linkage UNKNOWN. Preserve raw input and any independently proven refs;
        do not let withheld links become a false omission FAIL or a false PASS.
        This method accepts host-observed messages, never reconstructed logs.
        """
        included, uncertain = [], False
        for message in messages:
            content = message.get("content")
            if not isinstance(content, str):
                content = canonical_json(content)
            if message.get("type") == "tool":
                observed = self.tool_returns.get(message.get("tool_call_id"))
                if (observed is None or message.get("name") != observed[1]["payload"]["tool_name"]
                        or self.redact(content) != observed[1]["content"]):
                    uncertain = True
                    continue
                event = observed[1]
                if event["event_id"] not in included:
                    included.append(event["event_id"])
            elif message.get("type") == "human":
                first_line, newline, _ = content.partition("\n")
                if (not isinstance(message.get("content"), str) or
                        newline and first_line.startswith("[") and first_line.endswith(" returned]")):
                    uncertain = True  # Text is preserved; no call is selected.
        return self.model_input(messages=messages, report_id=report_id, report_revision=report_revision,
                                included_event_ids=included, boundary="UNKNOWN" if uncertain else "ASSEMBLED")

    def feedback(self, *, event_type, assessment_id, proposal_id, proposal_revision, related_event_ids, content):
        if event_type not in {"feedback_delivery", "feedback_inclusion", "feedback_acknowledgement", "correction"}:
            raise BoundaryError("Unknown feedback observation")
        return self._record(event_type, content, dict(assessment_id=assessment_id,
            proposal_id=proposal_id, proposal_revision=proposal_revision,
            related_event_ids=list(related_event_ids)), parents=related_event_ids)


class FeedbackBoundary:
    """Local host controller using A's accepted request/result and exact bindings.

    submit receives a trusted, service-resolved checkpoint/events/policy view.
    assess has A's exact pure signature for offline use; B's future stored-reference
    bridge must resolve that same view without trusting agent policy/coverage.
    emit records local lifecycle observations; it does not claim durable storage.
    authorize controls only the referenced report boundary, never decision truth.
    """

    def __init__(self, *, run_id, proposal_id, assess, emit, limits=Limits(), authorize=None):
        if not all(isinstance(v, str) and v for v in (run_id, proposal_id)):
            raise ValueError("Host identities must be nonempty strings")
        self.run_id, self.proposal_id = run_id, proposal_id
        self.assess, self.emit, self.limits, self.authorize = assess, emit, limits, authorize
        self.counts = dict(source_rounds=0, verify_calls=0, remediations=0)
        self.proposals, self.requests = [], []
        self.current = self.packet = self.feedback = None
        self.pending_returns, self.delivered, self.included = {}, {}, set()
        self.stopped, self._input_sequence = False, 0

    def next_input_sequence(self):
        self._input_sequence += 1
        return self._input_sequence

    def _spend(self, name):
        if self.stopped or self.counts[name] >= getattr(self.limits, name):
            raise BoundaryError("Stopped or exhausted " + name)
        self.counts[name] += 1

    def submit(self, request, *, checkpoint, events, policy):
        self.current = self.packet = self.feedback = None
        if self.stopped:
            raise BoundaryError("Stopped")
        packet = deepcopy(dict(request=request, checkpoint=checkpoint, events=events, policy=policy))
        request = packet["request"]
        validate_request(request, previous=self.requests[-1] if self.requests else None)
        validate_checkpoint(packet["checkpoint"])
        validate_policy(packet["policy"])
        if request["run_id"] != self.run_id or request["proposal"]["proposal_id"] != self.proposal_id:
            raise BoundaryError("Wrong run/proposal scope")
        if any(r["request_id"] == request["request_id"] for r in self.requests):
            raise BoundaryError("Request identity already used")
        if self.proposals:
            if request["proposal"]["revision"] <= self.proposals[-1]["revision"]:
                raise BoundaryError("Proposal revision must increase for a new request/view")
            self._spend("remediations")
        expected = assessment_binding(**packet)
        if request["checkpoint"] != dict(checkpoint_id=checkpoint["checkpoint_id"],
                revision=checkpoint["revision"], digest=digest(checkpoint)):
            raise BoundaryError("Checkpoint reference mismatch")
        if request["policy"] != dict(policy_id=policy["policy_id"], version=policy["version"],
                digest=digest(policy), checks=[c["check_id"] for c in policy["checks"]]):
            raise BoundaryError("Policy reference mismatch")
        self.requests.append(deepcopy(request))
        self.proposals.append(deepcopy(request["proposal"]))
        self.emit("proposal.submitted", deepcopy(request))
        self.emit("proposal.bound", deepcopy(expected))
        self.current, self.packet = expected, packet
        return deepcopy(expected)

    def verify(self, *, origin="voluntary"):
        if origin not in {"voluntary", "host"} or self.current is None:
            raise BoundaryError("No proposal or unknown caller")
        self.feedback = None
        self._spend("verify_calls")
        expected = deepcopy(self.current)
        packet = deepcopy(self.packet)
        self.emit("verification.requested", dict(binding=expected, origin=origin))
        result = self.assess(**deepcopy(packet))
        validate_result(result)
        if result["run_id"] != self.run_id or result["request_id"] != packet["request"]["request_id"]:
            raise BoundaryError("Stale assessment scope")
        if result["binding"] is not None and not binding_matches(result["binding"], **packet):
            raise BoundaryError("Stale assessment binding")
        if self.current != expected:
            raise BoundaryError("Changed current binding during assessment")
        self.emit("feedback.prepared", dict(binding=expected, assessment_id=result["assessment_id"]))
        self.feedback = deepcopy(result)
        payload = canonical_json(result)
        self.pending_returns[payload] = deepcopy(result)
        return payload

    def observe_tool_return(self, call_id, payload):
        if not call_id or payload not in self.pending_returns:
            raise BoundaryError("Unrecognized feedback return")
        if call_id in self.delivered and self.delivered[call_id] != payload:
            raise BoundaryError("Tool call ID reused with different feedback")
        self.emit("feedback.delivered", dict(call_id=call_id, payload=payload))
        self.delivered[call_id] = payload

    def observe_next_input(self, input_id, tool_returns):
        if not input_id:
            raise BoundaryError("Model input identity required")
        for call_id, payload in tool_returns:
            if self.delivered.get(call_id) == payload:
                self.emit("feedback.input_included", dict(input_id=input_id, call_id=call_id, payload=payload))
                self.included.add(payload)

    def acknowledge(self, assessment_id, text):
        if self.feedback is None or self.feedback["assessment_id"] != assessment_id:
            raise BoundaryError("No current assessment to acknowledge")
        self.emit("feedback.acknowledged", dict(assessment_id=assessment_id, text=text))

    def source_round(self, operations):
        self.feedback = self.current = self.packet = None
        self._spend("source_rounds")
        self.emit("source.round_started", dict(round=self.counts["source_rounds"]))
        return [operation() for operation in operations]

    def report_boundary_allowed(self, report_event):
        """Named report predicate only; never a downstream decision authorization."""
        result = self.feedback
        if (self.stopped or self.authorize is None or self.packet is None or result is None
                or result["binding"] != self.current or result["status"] != "ASSESSED"
                or result["disposition"] != "ADVISE"):
            return False
        if not binding_matches(result["binding"], **self.packet):
            return False
        p = self.packet["request"]["proposal"]
        report = next((e for e in self.packet["events"] if e["event_id"] == p["report_event_id"]), None)
        if (report is None or report["event_type"] != "report" or not isinstance(report_event, dict)
                or report_event != report
                or (report["payload"]["report_id"], report["payload"]["revision"]) != (p["report_id"], p["report_revision"])):
            return False
        if canonical_json(result) not in self.included:
            return False
        return self.authorize(deepcopy(self.packet), deepcopy(result)) is True

    def abstain(self, reason):
        self.stopped, self.feedback = True, None
        self.emit("proposal.abstained", dict(reason=reason, binding=deepcopy(self.current)))


def make_verify_tool(boundary):
    """Optional native LangChain tool. No agent-controlled checkpoint/policy args."""
    from langchain_core.tools import StructuredTool

    def verify_proposal() -> str:
        """Verify the current host-bound proposal; return scoped findings for recheck."""
        return boundary.verify(origin="voluntary")

    return StructuredTool.from_function(verify_proposal)


def observe_native_returns(boundary, messages, *, capture=None, classify_status=None):
    """Observe actual ToolMessages before pinned take_turn flattens wrap-up history."""
    for message in messages:
        if capture is not None and getattr(message, "type", None) == "tool":
            # ToolNode's success flag alone may wrap a provider NO_DATA/error
            # string. A trusted source-specific classifier must establish SUCCESS.
            status = (classify_status(message) if classify_status is not None else
                      "ERROR" if getattr(message, "status", None) == "error" else "UNKNOWN")
            capture.tool_result(call_id=message.tool_call_id, tool_name=message.name or "unknown_tool",
                content=message.content if isinstance(message.content, str) else canonical_json(message.content),
                status=status)
        if getattr(message, "type", None) == "tool" and message.name == "verify_proposal":
            boundary.observe_tool_return(message.tool_call_id, message.content)


def make_trusted_model(llm, boundary, *, capture_input=None):
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
                if getattr(message, "type", None) == "tool" and message.name == "verify_proposal":
                    pairs.append((message.tool_call_id, message.content))
                # Human marker text carries no call-specific identity. It cannot
                # establish feedback inclusion without transformation lineage.
            # IDs must remain unique across bound wrappers and unbound wrap-up.
            input_id = f"{boundary.run_id}:input:{boundary.next_input_sequence()}"
            if capture_input is not None:
                event = capture_input([m.model_dump(mode="json") for m in messages])
                validate_event(event)
                if event["run_id"] != boundary.run_id or event["event_type"] != "model_input":
                    raise BoundaryError("Wrong captured model-input scope")
                input_id = event["event_id"]
            boundary.observe_next_input(input_id, pairs)
            # Fingerprints bind the actual visible envelope at this seam without
            # copying potentially private prompts into a second capture store.
            message_digests = [digest(m.model_dump(mode="json")) for m in messages]
            boundary.emit("model.input_attempted", dict(input_id=input_id, trusted_instruction=True,
                                                       message_digests=message_digests))
            return self.delegate.invoke(messages, config=config, **kwargs)

    return TrustedModel(llm)
