"""Broad surface disposition using frozen pure rules, never accepted support."""
import re

from verification import processing, refine_rules
from .ledger import sha

URL = re.compile(r"https?://[^\s<>\"'()]+")


def _frame_specs(body):
    for start, end, frame_kind, section in refine_rules.frames(body):
        if frame_kind != "sentence_frame":
            continue
        children = refine_rules.decompose(body, start, end)
        if section.lower() in refine_rules.SCALAR_SECTIONS:
            children = [dict(start=start, end=end, role="scalar_declaration", rule="R010", connector=None,
                             condition_spans=[], extra=["scalar_report_field_not_semantic_predication"])]
        yield start, end, section, children


def _atoms(ledger, parent, text, text_id=None, source_id=None):
    run = parent["run_id"]
    event_seq = parent.get("seq", parent.get("output_seq"))
    for match in processing.NUMBER.finditer(text):
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", match.group()):
            continue
        ledger.add("atoms", [parent["id"], "numeric", match.start(), match.end()], run, refs=[parent["id"]],
                   text_id=text_id, source_id=source_id, event_seq=event_seq, start=match.start(), end=match.end(),
                   quote=match.group(), kind="numeric", value=match.group(), status="lexical_numeric_role_unresolved")
    for match in processing.TIME.finditer(text):
        ledger.add("atoms", [parent["id"], "date", match.start(), match.end()], run, refs=[parent["id"]],
                   text_id=text_id, source_id=source_id, event_seq=event_seq, start=match.start(), end=match.end(),
                   quote=match.group(), kind="date", value=match.group(), status="lexical_time_not_resolved_instant")
    for match in URL.finditer(text):
        end = match.end()
        while end > match.start() and text[end - 1] in ".,;":
            end -= 1
        quote = text[match.start():end]
        fields = dict(text_id=text_id, source_id=source_id, event_seq=event_seq, start=match.start(), end=end,
                      quote=quote, url=quote, identity_status="exact_URL_only_not_independent_authority")
        ledger.add("urls", [parent["id"], match.start(), end], run, refs=[parent["id"]], **fields)
        ledger.add("atoms", [parent["id"], "url", match.start(), end], run, refs=[parent["id"]],
                   **fields, kind="url", value=quote, status="literal_URL_no_content_entailment")


def extract(ledger):
    texts = [r for r in ledger.records.values() if r["table"] == "texts" and r["role"] in ("generated_narrative", "saved_report_unresolved")]
    sources = [r for r in ledger.records.values() if r["table"] == "sources"]
    for source in sources:
        _atoms(ledger, source, source["content"], source_id=source["id"])
    for text in texts:
        run, body, tid = text["run_id"], text["text"], text["id"]
        passages = []
        for start, end, heading in processing.segments(body):
            quote = body[start:end]
            disposition, tags, rule = processing.classify(quote, heading)
            passages.append(ledger.add("passages", [tid, start, end], run, refs=[tid], text_id=tid,
                                       start=start, end=end, quote=quote, disposition=disposition, heading=heading,
                                       rule=rule, tags=tags, processing_version=processing.VERSION))
        for start, end, section, children in _frame_specs(body):
            frame_candidates = []
            for child in children:
                if refine_rules.condition_attachment_issues(body, child, start, end):
                    raise ValueError("Frozen rule produced an invalid condition attachment")
                paragraph = processing.paragraph_bounds(body, start, end)
                normalization = refine_rules.normalization(body, child, start, end, *paragraph)
                overlapping = [p["id"] for p in passages if p["start"] < child["end"] and child["start"] < p["end"]]
                rule_ids = list(dict.fromkeys([child.get("boundary_rule"), child["rule"], normalization["slot_rule"]]))
                row = ledger.add("candidates", [tid, child["start"], child["end"], child["role"]], run,
                                 refs=[tid, *overlapping, text["call_id"], text["event_id"]], text_id=tid,
                                 passage_id=overlapping[0] if overlapping else None, passage_ids=overlapping,
                                 start=child["start"], end=child["end"], quote=body[child["start"]:child["end"]],
                                 normalization=normalization, rule_ids=[r for r in rule_ids if r],
                                 extraction_input=child, frame_start=start, frame_end=end, section=section,
                                 status="provisional_candidate_not_verified_truth", call_id=text["call_id"], actor=text["actor"],
                                 output_event_id=text["event_id"], event_seq=text["output_seq"],
                                 source_sha256=text["sha256"], refinement_version=refine_rules.VERSION)
                frame_candidates.append(row)
                reasons = sorted(set(normalization["unresolved"] + ["factual_support_unassessed", "full_material_dependencies_unknown"]))
                ledger.add("unresolved", [row["id"], "semantics"], run, refs=[row["id"]], subject_id=row["id"], reasons=reasons, status="UNRESOLVED")
                if text["call_id"]:
                    ledger.add("relations", [row["id"], "context"], run, refs=[text["call_id"], row["id"]],
                               relation="candidate_produced_in_recorded_call", status="context_only_not_material_dependency",
                               from_id=text["call_id"], to_id=row["id"],
                               witness={"input_seq": text["input_seq"], "output_seq": text["output_seq"], "accepted_factual_support": False})
            for component in frame_candidates:
                role = component["normalization"]["role"]
                if role not in ("declared_reason", "rejected_reason", "reason_polarity_unresolved"):
                    continue
                heads = [c for c in frame_candidates if c["normalization"]["role"] == "reason_conclusion"]
                ledger.add("relations", [component["id"], "reason"], run, refs=[component["id"], *[h["id"] for h in heads]],
                           relation="explicit_stated_reason", status="extractor_proposed_" + role,
                           from_id=component["id"], to_id=heads[0]["id"] if len(heads) == 1 else None,
                           witness={"text_id": tid, "frame_start": start, "frame_end": end,
                                    "marker": component["normalization"]["connector"],
                                    "not_validated_cause_or_sufficient_premise": True, "accepted_factual_support": False})
        _atoms(ledger, text, body, text_id=tid)


def validate_extraction(by):
    texts = {t["id"]: t for t in by["texts"]}
    for text in texts.values():
        if text["role"] not in ("generated_narrative", "saved_report_unresolved"):
            continue
        passages = sorted([p for p in by["passages"] if p["text_id"] == text["id"]], key=lambda p: p["start"])
        cursor = 0
        for passage in passages:
            if passage["start"] != cursor:
                raise ValueError("Passage partition has gap/overlap")
            cursor = passage["end"]
            disposition, tags, rule = processing.classify(passage["quote"], passage["heading"])
            if ((passage["disposition"], passage["tags"], passage["rule"]) != (disposition, tags, rule)
                    or passage["processing_version"] != processing.VERSION):
                raise ValueError("Passage disposition replay mismatch")
        if cursor != len(text["text"]):
            raise ValueError("Surface disposition does not cover all narrative characters")
        expected_partition = [(a, b, heading) for a, b, heading in processing.segments(text["text"])]
        if [(p["start"], p["end"], p["heading"]) for p in passages] != expected_partition:
            raise ValueError("Passage partition replay mismatch")
        expected_candidates = {}
        for a, b, section, children in _frame_specs(text["text"]):
            for child in children:
                key = (child["start"], child["end"], child["role"])
                expected_candidates[key] = (a, b, section, child)
        actual_candidates = [c for c in by["candidates"] if c["text_id"] == text["id"]]
        if len(actual_candidates) != len(expected_candidates):
            raise ValueError("Candidate extraction inventory replay mismatch")
        for candidate in actual_candidates:
            key = (candidate["start"], candidate["end"], candidate["normalization"]["role"])
            if key not in expected_candidates:
                raise ValueError("Candidate extraction boundary replay mismatch")
            a, b, section, child = expected_candidates[key]
            expected = refine_rules.normalization(text["text"], child, a, b, *processing.paragraph_bounds(text["text"], a, b))
            rules = list(dict.fromkeys([child.get("boundary_rule"), child["rule"], expected["slot_rule"]]))
            if (candidate["normalization"] != expected or candidate["extraction_input"] != child
                    or (candidate["frame_start"], candidate["frame_end"], candidate["section"]) != (a, b, section)
                    or candidate["rule_ids"] != [r for r in rules if r]
                    or candidate["status"] != "provisional_candidate_not_verified_truth"
                    or candidate["refinement_version"] != refine_rules.VERSION):
                raise ValueError("Candidate normalization/rule replay mismatch")
    for candidate in by["candidates"]:
        text = texts[candidate["text_id"]]["text"]
        normalization = candidate["normalization"]
        if normalization["accepted_factual_support"] is not False:
            raise ValueError("Unsupported accepted factual support")
        if candidate["source_sha256"] != sha(text):
            raise ValueError("Candidate parent version mismatch")
        def slots(value):
            if isinstance(value, dict):
                if {"start", "end", "text"} <= value.keys():
                    a, b = value["start"], value["end"]
                    if not 0 <= a <= b <= len(text) or text[a:b] != value["text"]:
                        raise ValueError("Normalization slot/cue span mismatch")
                for child in value.values():
                    slots(child)
            elif isinstance(value, list):
                for child in value:
                    slots(child)
        slots(normalization)
        for guard in normalization["condition_spans"]:
            scope = normalization["scope"]
            a = min(candidate["start"], guard["start"], guard["marker"]["start"])
            b = max(candidate["end"], guard["end"], guard["marker"]["end"])
            if not scope["attachment_start"] <= a <= b <= scope["attachment_end"] or ";" in text[a:b]:
                raise ValueError("Condition attachment crosses local branch")
