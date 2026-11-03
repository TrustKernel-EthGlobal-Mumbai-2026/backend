# Knowledge schema

Use the smallest schema that preserves identity, lifecycle, sensitivity, and provenance. The schema is versioned; migrate deliberately rather than silently changing field meanings.

## Layers

### Original source

An immutable copy of the received item under `10 Sources/Originals/YYYY/MM/<source-id>/`. Identify it by SHA-256. Never edit it in place.

### Source note

One Markdown record under `10 Sources/Notes/YYYY/MM/`. It describes a source and may contain extraction, summary, highlights, claims, questions, tensions, and candidate connections. Machine-generated sections must remain distinguishable from human annotations.

Required properties for `bb8.source.v1`:

```yaml
---
schema: bb8.source.v1
id: src_<stable-id>
type: file
title: Example
status: preserved
captured: 2026-09-17T10:30:00+05:30
source_path: 10 Sources/Originals/2026/09/src_<stable-id>/example.pdf
content_hash: sha256:<digest>
sensitivity: private
topics: []
projects: []
aliases: []
---
```

Allowed lifecycle statuses are `inbox`, `preserved`, `processed`, `curated`, and `archived`.

### Curated knowledge

Durable concepts, claims, frameworks, people/organizations, decisions, and maps. Use `bb8.knowledge.v1`, a stable ID, `derived_from` links, confidence where material, and an explicit distinction between user statements, sourced claims, and BB8 inferences.

## Rules

- IDs survive title and folder changes.
- Use ISO 8601 dates; timestamps include timezone.
- Use controlled values for schema, type, status, and sensitivity.
- Prefer links and stable IDs over duplicating source text.
- Put detailed provenance and relationships in the body when YAML would require nesting.
- Never overwrite human annotations during regeneration.

