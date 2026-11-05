# Authored operator examples

These files contain no captured research data. They install no account settings
and call no model/provider. Copy them beside a new operator workspace and review
all IDs before use.

For an existing **copied** local service database, edit existing-host.json to name
that file, its service ID and allowed runs. No collector or bootstrap is needed:

```text
trustkernel --config existing-host.json verify --request exact-retained-request.json
trustkernel-mcp --config existing-host.json
```

The request must come from the actual stored host context; this directory does
not invent an assessment request or seed a successful fixture result.

For explicit new empty state, new-host.json selects authored identities and a
procedural policy example. It has no evidence, capture claims or live policy:

```text
trustkernel --config new-host.json init
trustkernel --config new-host.json get_run_state --request run-state-request.json
```

Coverage remains UNKNOWN. Only separately trusted collector code may append
accepted events and establish checkpoints. A configured agent client always has
verify/read only. See [portability and ownership](../../docs/continuous/PORTABILITY.md).
