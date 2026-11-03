# BB8 instruction snapshot

This directory freezes the installed personal BB8 guidance at plugin version `0.2.0+codex.20260917171643` (harness base `0.2.0`). Original plugin metadata names the author **Personal**. All68authored source files and21skill entry points are present: BB8 core plus20other specialist/family entries. The installed compiled Python cache is excluded.

The file named `harness/system-prompt.md` is the plugin's authored core behavior guide. It is not a capture of any host's actual hidden system/developer messages or session instructions. No personal knowledge base, context index, conversation history, account state, credentials, environment or private source files were copied.

## Use from any agent in a clone

Ask a file-reading agent: “Read `bb8/skills/bb8/SKILL.md` and follow the linked harness for this task. Use the repository's current README/AGENTS/context docs for project state. Check your actual host tools and permissions before routing.” No personal plugin installation is required to read these instructions.

Start with the [BB8 core](skills/bb8/SKILL.md), then its [core guide](harness/system-prompt.md), [routing contract](harness/routing-contract.md) and [skill catalog](harness/skill-catalog.md). Load the relevant specialist SKILL.md and its references progressively; do not load every framework or invoke every helper automatically. The catalog covers knowledge organisation, research, quantitative analysis, problem solving, communication/storytelling, engineering, product/discovery/design and transcript insights. Family routers and specialist guidance are all included.

Hosts supporting repository `.agents/skills` can discover the thin repository entry point; discovery behavior is host-specific. Plugin-compatible hosts may load this `bb8/` directory as a plugin root according to their own supported local-plugin settings; the preserved `.codex-plugin/plugin.json` points to `./skills/`. This snapshot does not install or register anything globally, guarantee any host plugin format or claim every host exposes these skills automatically. Ordinary agents can use the same files as documentation.

The [capability registry](harness/capability-registry.yaml) preserves original `active` statuses as instruction/catalog state. A listed capability or `agents/openai.yaml` interface is not proof that browsing, connectors, shell, extra agents or paid model tools exist. Check the host's runtime capabilities and current human authorization. When a tool is unavailable, name the gap and continue with a bounded supported approach. Reading guidance does not authorize external messages, spending, deployment, signing or curated-knowledge changes.

## Privacy and local use

One explicit portability transformation replaces Organise's machine-specific knowledge-root default with `<USER_SELECTED_KNOWLEDGE_ROOT>` in [its skill](skills/organise/SKILL.md). Choose that root explicitly for your own approved task. The included `skills/organise/scripts/organise.py` requires `--vault` for vault operations; no vault is bundled or created by loading BB8. Do not infer access to the original owner's knowledge from this catalog. No ingestion, Downloads scan, private index rebuild or global install runs automatically.

## Verify and update

```text
python -S -B bb8/snapshot.py verify
python -S -B -m unittest discover -s tests -p test_bb8_snapshot.py -v
```

`SNAPSHOT.json` records logical source/version, exact source and target hashes, the one path transformation, helper hashes, excluded categories and scope. It excludes its own hash to avoid recursion; the parent repository packaging manifest covers this manifest and the dedicated test. Source copies otherwise retain exact bytes and relative links. An optional `--source-root` comparison uses only a source folder explicitly provided by the caller; no private installation path is embedded as the default.

This is a frozen snapshot, not the current live personal plugin or current personal knowledge. Repository maintainers own future updates: inspect a chosen source version and scope; copy only authored `.codex-plugin/plugin.json`, `harness/**`, `skills/**` guidance/resources; exclude caches/private state; declare any portability transformation; regenerate hashes and run integrity/link/privacy tests; review the diff before publication. Do not silently sync a user's private plugin or replace the repository's active context with archival personal state.

No additional license or authorship is invented by this snapshot. Preserve the actual plugin metadata and follow the repository owner's licensing/publication decisions. Project-specific active state and cross-chat summaries belong to the parent-owned repository context docs, not this frozen BB8 instruction package.
