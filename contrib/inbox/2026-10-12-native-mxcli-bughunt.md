# mxcli v0.26.0 defects on native-mobile documents — FSM template round trip, 2026-10-12

Unreviewed inbox drop. Source: Siemens FSM template (Mendix 9.24.2), the 12 own `Native*` modules
(NativeMobile, NativeMobileAsset, NativeMobileForm, NativeMobilePart, NativeMobileRelated,
NativeMobileTimeRegistration, NativeMobileWarehouse, NativeModelCheck, NativeNote, NativeReason,
NativeRestAPI, NativeTechnician). Method: `describe module <M> with all` plus the tree fill-in of
`rehost-extract.sh` (1142 documents, all described) -> `mxcli check -p <source app>` with a
quarantine loop (so references resolve; every error below is mxcli rejecting mxcli's own output) ->
`exec` into a copy of the source with the 12 modules dropped. Repros: `pipelines/mendix-mpr/samples/fsm-template-9.24.2/native-bughunt/`.
Counts are error lines across all quarantine rounds (one statement can be reported once per round).

## Defects

| id | document type | verbatim error | repro | modules | count | severity |
|---|---|---|---|---|---|---|
| D3 confirmed (also stated in the Decompose plan entry of CHANGELOG, no repro filed) | microflow, nanoflow (any) | `Error: failed to create microflow: unit 91c57c83-…: this Mendix 9.24.2 project cannot store Microflows$Microflow.StableId (Mendix 10.2.0+); Microflows$SequenceFlow.CaseValues (Mendix 10.15.0+): the properties did not exist yet in this version, and Studio Pro cannot open a document that holds one.` (nanoflow: `CreateNanoflow: insert: … cannot store Microflows$SequenceFlow.CaseValues (Mendix 10.15.0+)`) | `D3-…mdl`: an empty `create or modify microflow Repro.MF_Min () begin return; end;` already fails on a fresh 9.24.2 app | every module with a flow (NativeRestAPI isolated: all 4 flows fail one by one) | 100% of flows tried | blocks round-trip: no microflow or nanoflow can be written to a 9.24.2 project, so nothing that calls one can follow |
| D1 NEW | entity | `statement N: index on unknown attribute 'desc'` — describe printed `index ( desc);` (no column) | `D1-…mdl` | NativeTechnician, NativeReason, NativeMobileWarehouse, NativeMobile, NativeMobilePart, NativeMobileForm, NativeMobileTimeRegistration, NativeNote, NativeMobileAsset, NativeMobileRelated (every entity module but NativeModelCheck/RestAPI) | 23 | blocks round-trip: the entity is rejected, and every flow, page and grant naming it cascades (NativeReason: 0 of 45 documents survive check) |
| D2 NEW | page, snippet (native Repeater widget) | `` `content` is not a container of `repeater` — it declares: template [MDL-WIDGET26] `` | `D2-…mdl` (needs `com.mendix.widget.native.Repeater.mpk` + `mxcli widget init`) | NativeNote, NativeMobile, NativeMobileForm, NativeMobileRelated, NativeMobileAsset, NativeMobilePart, NativeMobileTimeRegistration | 32 | blocks round-trip (same family as the known SafeAreaView `content`; the Repeater slot is also `template`) |
| D4 NEW | page, snippet | `widget 'repeater4': nanoflow data source NativeMobileForm.DS_GetInstanceNativePictureImage has no argument for parameter 'NativeInstanceItem' — Mendix rejects this with CE1571.` (also `nanoflow action … (Action:) has no argument for parameter(s) …`) | `D4-…mdl` excerpt, not isolated (blocked by D3) | NativeMobile, NativeMobileForm, NativeMobilePart, NativeMobileRelated, NativeMobileAsset, NativeMobileTimeRegistration, NativeNote | 70 | blocks round-trip, or silent drift if the source mapped the parameter from the context object: describe prints the call without the mapping |
| D5 NEW | page | `widget 'textBox1': Attribute 'Search' is bound but there is no enclosing data container providing entity context` (also datePicker1..4 `Start`/`End`) | not reduced | NativeMobileTimeRegistration, NativeMobileAsset, NativeMobileRelated | 11 | blocks round-trip (describe loses or never emits the data view the widget sat in; unverified which) |
| D6 NEW | snippet | `dynamictext "text42": ContentParams parameter {1} is written as "$currentObject/NotResolvedReason" — a template parameter is evaluated against the widget's own context object` | not reduced | NativeMobileRelated | 2 | blocks round-trip |
| D7 NEW | page | `widget 'dataView1': selection DataSource references 'grid1' but no widget with that name exists on this page` | not reduced | NativeModelCheck | 1 | blocks round-trip (describe names a widget it did not emit) |
| D8 NEW | microflow | `enum split has 28 branches; at most 16 branches are supported` (`NativeModelCheck_Process`) | not reduced | NativeModelCheck | 1 | blocks round-trip (a limit in create that describe does not respect) |
| D9 NEW | microflow | `MDL-REST04: authentication microflow … has parameter $Token, which Mendix does not supply to an authentication microflow … (CE0336)` | not reduced | NativeRestAPI | 1 | lint on valid source; blocks round-trip through check |
| D10 confirmed | javascript action | `line 13427:67 mismatched input '<' expecting {FOLDER, '('}` (type parameter `Name<Entity>(…)`) | see nativenote finding | NativeMobile | 1 | blocks round-trip |
| D11 confirmed | page (native layout) | `` `content` is not a container of `safeareaview` — it declares: template [MDL-WIDGET26] `` | see nativenote finding | NativeMobile (page Login) | 2 | blocks round-trip |
| D12 confirmed | module | `with all` omits nanoflows, snippets, JS actions; 10 000-line `-c` truncation (NativeMobile ends mid-statement) | n/a | NativeMobile and others | all | silent drift (tree fill-in recovered all 1142 documents) |
| D13 confirmed | exec | forward / cross-module references refused (`child entity module not found: NativeMobilePart`; `microflow not found: NativeReason.…`); grant before association (`entity NativeNote.NativeImage has no member(s) NativeImage_NativeNote`); not atomic | n/a | NativeMobileWarehouse, NativeModelCheck, NativeNote, NativeMobileTimeRegistration, NativeMobileForm, NativeMobilePart | 6 modules | blocks round-trip |
| D14 confirmed | image collection | `image collection not found: FSM_Specific.Material_Design_Icons` seen only against an empty scratch app (missing dependency) — not re-tested against the source | n/a | — | — | — |

Cosmetic, not counted: `commit` default-events notice (167 on the empty-scratch run), `Wrap dataview … in layoutgrid` lint hints.

Not tested because D3 and D13 stop exec first: target `describe` versus source `describe` (nothing but modules, roles and 3 NativeRestAPI constants reached the target).

## Per module

`create` statements = `create or modify` lines in the raw describe (entities, flows, pages, snippets, actions, module and roles).
Rejected by check = statements quarantined by `check` against the source app (root cause or cascade from D1/D2/D4). Executed =
documents written to the 9.24.2 target. Missing dependency: 0 (checked against the full source app).

| module | create statements | clean in check | rejected by check | executed | exec blocker |
|---|---|---|---|---|---|
| NativeTechnician | 15 | 3 | 11 | 0 (module+roles) | D1 cascade |
| NativeReason | 45 | 3 | 37 | 0 (module+roles) | D1 cascade |
| NativeMobileWarehouse | 39 | 6 | 28 | 0 | cross-module ref (D13) |
| NativeModelCheck | 51 | 47 | 3 | 0 | cross-module ref (D13), D3 |
| NativeRestAPI | 12 | 11 | 1 | 3 constants + role | D3 on all 4 flows |
| NativeNote | 66 | 24 | 39 | 0 | grant before association (D13) |
| NativeMobileTimeRegistration | 80 | 14 | 61 | 0 | cross-module ref |
| NativeMobileAsset | 75 | 41 | 32 | 0 | cross-module ref |
| NativeMobileRelated | 97 | 76 | 21 | 0 | check lint D6 |
| NativeMobileForm | 104 | 35 | 62 | 0 | cross-module ref |
| NativeMobilePart | 156 | 45 | 99 | 0 | cross-module ref |
| NativeMobile | 461 | 136 | 308 | 0 | pre-check refusal, D2/D11, D3 |

All 12 modules covered; execute stage reached only the module level, so classes "defect / missing dependency / other"
read: check-rejected = defect or cascade of defect (D1, D2, D4–D9), missing dependency = 0, exec-blocked = D3 and D13.
Re-run once D3 is fixed (or against an 11.x target, where the FSM native modules need the Blank Native starter) to expose
the next layer.
