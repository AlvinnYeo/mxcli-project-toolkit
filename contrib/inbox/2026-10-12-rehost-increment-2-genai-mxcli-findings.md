# mxcli v0.26.0 defects found regenerating the GenAI Showcase App (Rehost increment 2)

**From:** mendix/genai-showcase-app (Rehost increment 2) — MendixMau
**Date:** 2026-10-12
**Kind:** bug
**Field evidence:** `pipelines/mendix-mpr/samples/genai-showcase-11.12.0/` (run.log, ledger, mx check / mxbuild captures, FINDINGS.md); Mendix 11.12.0 source, 36 modules regenerated into `mxcli new --version 11.12.0`; Linux container, no Studio Pro
**Proposed target:** `bug-logs/mxcli-bugs.md` (one BUG-n each), upstream mxcli issues; extractor items to `pipelines/mendix-mpr/`

---

Format: defect — verbatim message — one-line repro — what works around it (or "nothing").

## mxcli defects
- **`-c describe module … with all` truncates at 10 000 lines without a warning.** There is no message:
  the output simply stops in the middle of a statement. Repro: `mxcli -p <genai>.mpr -c "describe module AgentCommons with all" | wc -l` stops at the 10 000-line cap.
  Workaround: `rehost-extract.sh` `describe_module()` drops the incomplete last statement and describes
  the documents it is missing one by one.
- **`with all` leaves document types out.** Nanoflows, snippets, JS actions, JSON structures,
  import/export mappings, task queues, image collections and some pages are missing (10 of 22 pages in
  AgentCommons). Repro: compare `describe module M with all` against `project-tree --json` for M.
  Workaround: the `project-tree` fill-in in `rehost-extract.sh`.
- **`describe java action` puts the parameter separator after the `--` comment.** Verbatim:
  `Name: String not null  -- This sets the Name of the tool...,` then check:
  `line 255:4 mismatched input 'Name' expecting ')'`. Repro: `describe java action GenAICommons.<any action with a documented parameter>`
  and `check` the output. Workaround: `lib/fix-describe-output.py`.
- **A microflow and a Java action with the same name.** If the flow is created first:
  `warning: could not look up Java action … java action not found` → `Error: failed to create microflow:
  refusing to write unit …: attribute reference not qualified`. Repro: exec
  GenAICommons.ConsumedKnowledgeBase_GetCollectionOptions (the flow) before the Java action with the same
  name. Workaround: `lib/topo-order-mdl.py` orders the Java/JS action first.
- **A grant that names an association member before the association exists.** Verbatim:
  `Error: entity EchoConnector.Credentials has no member(s) Credentials_Configuration; grant only names
  members of the entity`. Repro: describe order of the EchoConnector module. Workaround: topo makes
  grants their own units, which depend on the associations they name.
- **Message definitions cannot be expressed.** Verbatim: `Error: export mapping GenAICommons.EM_Reference:
  message definition "GenAICommons.MD_Reference.Reference" not found — this project has no message
  definitions`. Repro: exec any export mapping built on a message definition. Workaround: nothing. These
  are ledger failed-exec rows, and they cause 4 × CE1613 at mxbuild (`The selected export mapping '…' no longer exists`).
- **A Mendix 9-built MPK cannot be installed into 11.** Verbatim: `build a reference project from the
  package: mx module-import failed: exit status 117` / `The package could not be imported, because it was
  created with version 9.24.2 of Mendix Studio Pro. Please open it in any version in the range from
  10.21.0 to 10.24.99 first.` Repro: `mxcli marketplace install 220472 --version 3.4.1 -p <11.12 app>`.
  Workaround: regenerate the module from source with the Rehost extractor.
- **The marketplace version stamped in the source is absent.** Verbatim: `version "1.5.1" not found; run
  'mxcli marketplace versions <id>'`. Repro: `mxcli marketplace install 239450 --version 1.5.1`; the
  oldest version listed is 3.0.0. Workaround: regenerate from source.
- **Template module versions do not match the source, and there is no headless update.**
  `marketplace install` of a module that is already present is "NOT done automatically". Repro:
  `mxcli new --version 11.12.0` ships Administration 4.3.2 while the source has 4.5.0. Workaround:
  nothing; these are ledger hand-off rows.
- **#923: merges and decisions cannot be represented.** describe prints WARNING lines, and the target
  describe drifts on layout (`'@curve(from: (15, 0), to: (-30, 0))' -> "@caption 'empty'"`). Repro:
  describe any flow with a shared merge. Workaround: `lib/compare-mdl.py` rates #923 warnings as
  `not-expressible`.
- **NEW — exec writes a microflow whose `import from mapping` result has a null entity, and the `.mpr`
  can no longer be loaded.** Verbatim (mx check):
  `System.ArgumentNullException: Value cannot be null. (Parameter 'value') at
  Mendix.Modeler.DataTypes.EntityType.set_EntityId` — "An error occurred when trying to set the 'Entity'
  property of a Object type in a Microflow with ID …". Repro: exec
  Embeddings_SemanticSearch.Book_CreateDatasetIfNeeded in the order run 4 used (the topo order let the
  flow run ahead of IM_SemanticSearch_Books; that mxcli then writes a null entity is a hypothesis, and so
  is the cause). Workaround: `drop microflow X;` plus the same `create or modify microflow X` in one
  script once the mapping exists. A plain re-`create or modify` is refused with `MDL-V1-REBUILD`.
- **NEW — a Java action type parameter is described as `MxObject: "Entity"`, with no type-parameter
  declaration, and exec writes entity `.Entity`.** Verbatim (mxbuild): `Property 'Entity' of Java action
  parameter 'MxObject': The selected entity '.Entity' no longer exists.` Repro:
  `describe java action GenAICommons.ChunkCollection_AddKnowledgeBaseChunk`, exec it, then `mx check`.
  Workaround: nothing (7 build errors). The same defect affects JS actions (increment-3 inbox file).
- **NEW — a sort on an inherited attribute is written against the specialization.** Verbatim: `CE1613
  "The selected attribute 'Embeddings_SemanticSearch.BookChunk.Similarity' no longer exists." at List
  operation activity 'Sort'`. `sort $BookChunkList by Similarity desc` on a BookChunk that
  `extends GenAICommons.KnowledgeBaseChunk`. The target describe is identical to the source, so a
  describe-only check calls it identical. Repro: exec Embeddings_SemanticSearch.DS_Query_GetBookChunks,
  then `mx check`. Workaround: nothing.
- **NEW — rules cannot be described or created.** Verbatim: `describe rule …` → `Unknown type: rule`.
  exec of a flow whose decision calls a rule: `if condition calls
  'PgVectorKnowledgeBase.Rule_DatabaseConfiguration_IsConfigured(...)', which is not a rule in this
  project`. Repro: `mxcli -c "show rules"` lists 14 rules; `describe rule` refuses all of them.
  Workaround: nothing (8 flows deferred, 12 rules uncounted).
- **NEW — describe emits MDL that its own `check` rejects.** 30 documents. Examples:
  `ContentParams parameter {1} is written as "$ChatContext/Topic"` [MDL-WIDGET24];
  `merge shared1: nothing joins it.` [MDL-FLOW02];
  `layout 'ConversationalUI.Layout_MasterBase' declares no placeholders at all` [MDL081];
  `DecimalPrecision must be a non-negative integer, got &{-1}` [MDL-WIDGET18];
  `argument Task: $Task cannot be stored — widget actionButton17 is not inside a data view` [MDL-PAGEARG01].
  Repro: describe the named document, then `check` the output against any target. Workaround: the
  extractor quarantines these statements (but see the toolkit items below).
- **NEW — exec refuses forward references inside one script, so mutual recursion cannot be created.**
  Verbatim: `references microflow X before it is created (statement 240), and the project does not have
  it`. Repro: GenAICommons.Response_CallRecursively ↔ ChatCompletions_WithHistory. Workaround: nothing.
  Hypothesis: a create-stub-then-modify pass would get round it.
- **NEW — a describe output fails validation.** Verbatim: `microflow
  'GenAICommons.Span_CalculateSumDurationUntilExecution' has validation errors: - variable 'SumDuration'
  is not declared`. Repro: describe it and exec it. Workaround: nothing.
- **Seen, not isolated:** `warning: could not look up Java action System.VerifyPassword` (System Java
  actions are unknown to mxcli); import mapping `with json structure … root (Wrapper)` → `line 342:59
  extraneous input '('`; dynamic text `ContentParams: ({1} = ToolName format (decimalPrecision: -1))` →
  `no viable alternative`.

## Toolkit (extractor) items. These are not mxcli; they are for the next extractor commit.
- `lib/quarantine-mdl.py` does not map lint-form errors (`✗ … [CODE]` followed by `at Q.N`). It also
  trusts mxcli's `statement N:` numbering, which differs from `lib/mdlsplit.py` (AgentCommons 48 vs 49,
  AmazonBedrockConnector 357 vs 360, MxGenAIConnector 135 vs 144).
- `rehost-extract.sh` `check_exec`: when nothing can be quarantined, the remainder is neither executed
  nor deferred. In run 4 this lost 7 modules, 1040 statements and 1520 ledger rows.
- The deferred comment nests on every retry pass, and the `never executed` count is 7× too high.
- The ledger's denominator does not count rules, because they are not in the catalog types.
