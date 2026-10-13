# Target architecture — Dispatch & Workforce slice (increment 8, 2026-10-13)

`decompose-app.md` Stage 1b artifact. Kept in the sample folder (no project `PROJECT.md` in this
field run); each decision line below is written in register form. **Gate run unattended** — the
user opted in; the `ASSUMED` lines await the user's review.

Facts used: `cut-score.json` (8-partition cut, verdict `blocked` like every cut on this model),
`captures/04-cut-score-tally.txt`, `crossing-refs.tsv` (catalog of the 10.24 copy, 1081 crossing
refs → 871 ledger rows: 425 out, 446 in), `captures/06-crossing-entities.txt`.

## Register (decisions)

```
CONFIRMED  Slice: Dispatch & Workforce = Scheduler, RosterManagement, Technician, Skill, TimeRegistration
CONFIRMED  Target: a new Mendix 11.13.0 web app (DispatchApp)
CONFIRMED  Work on a fresh copy: <lab>/dispatch/mono (original <lab>/fsm/app read-only)
CONFIRMED  Monolith converted to 10.24 first (mx convert + increment 4 one-time fixes)
CONFIRMED  Lanes: OData and REST only; no Event Broker / Business Events
CONFIRMED  Auth between apps: machine-role basic auth now; token-based (OIDC client credentials) later
CONFIRMED  Mobile partition (Native*, Synchronization, NativeMobileTimeRegistration) out of scope: hand-off rows
CONFIRMED  Data migration of existing rows out of scope
ASSUMED    Landscape = 2 apps in this run (monolith 10.24 + DispatchApp 11.13); the strangled Assets app is
           handled on paper only (section 9) — reason: user forbade touching <lab>/web-assets
ASSUMED    Data ownership: the 21 slice entities are owned by DispatchApp once seam-live — reason: they move whole
ASSUMED    Data ownership: WorkOrder, Appointment, Ticket, WorkOrderAssignment, AppointmentAssignment, Account,
           Warehouse, Asset stay owned by the monolith — reason: TicketManagement is the core (797 in-refs);
           Warehouse/Asset belong to the Assets & Parts capability, still in this monolith copy
ASSUMED    Cut order: monolith publishes first (Stage 2 recipe 1), a DispatchCore OData v1 for the
           TicketManagement reads the slice needs — reason: 307 of 425 out-refs target TicketManagement;
           increment 6 showed 120 -> 32 stubs once the core was published
ASSUMED    Core published first = WorkOrder, Appointment, Ticket, WorkOrderAssignment, AppointmentAssignment
           (+ navigations) — reason: top 5 out-targets by ref count (44/23/9/... + association members)
ASSUMED    Behaviour-carrying monolith calls (TicketManagement.Appointment_*, WorkOrder_*) go to REST actions
           on the monolith (P3), implemented for the planning write path only; the rest are hand-off rows
           — reason: time box; one write journey per crossing kind is the level-3 bar, not every flow
ASSUMED    ModuleIntegration_Administration_Impl rules (Rule_User_HasUserRole_*), Utils helpers: copied —
           reason: pure functions over System.User / the session, no data ownership
ASSUMED    Administration.Account_Technician: re-created in DispatchApp against its own starter Account —
           reason: each app has its own user store; identity federation is the token-auth follow-up
ASSUMED    WorkOrder_Skill / *_Technician associations owned by monolith entities: key copy (B') — the
           monolith publishes the slice key (Technician.SystemID / Skill name) on its entity — reason:
           an external entity cannot own an association to a local entity (seam limits)
ASSUMED    Keys: PublicID AutoNumber default 1 on each published monolith entity (P1) — reason: no existing
           unique key that every create path fills was verified in the time box
ASSUMED    Service paths: odata/dispatchcore/v1 (monolith), rest/dispatchcore/v1 (monolith),
           odata/workforce/v1 (DispatchApp, at strangle) — reason: P10 versioned paths
```

## 1. Target landscape

| App | Version | Role |
|---|---|---|
| Monolith (`<lab>/dispatch/mono`) | 10.24.0 | core: tickets, work orders, appointments, customers, assets, forms, mobile; publishes DispatchCore |
| DispatchApp (`<lab>/dispatch/DispatchApp`) | 11.13.0 | planner board, rosters, technicians, skills, time registration; consumes DispatchCore; publishes Workforce at strangle |
| (paper) AssetsApp | 11.13.0 | strangled Assets & Parts landscape of increment 7 — section 9 |

App count 2 (+1 on paper) — within the Stage 0 scope (each app is a licensed node).

## 2. Capability → module → app map — 42/42 own modules assigned

- **DispatchApp (5):** Scheduler, RosterManagement, Technician, Skill, TimeRegistration.
- **Monolith (37):** AppSettings, AssetManagement, CustomerManagement, Dashboard, FSMPublishedAPI,
  FSM_Specific, FeatureToggle, Form, General, IDCreation, MasterData,
  ModuleIntegration_Administration_Impl, ModuleIntegration_DeepLink_Impl,
  ModuleIntegration_Logging_Impl, Note, Part, Reason, TicketManagement, Tool, Visualizations,
  WarehouseManagement, Synchronization, Utils, NativeMobile, NativeMobileAsset, NativeMobileForm,
  NativeMobilePart, NativeMobileRelated, NativeMobileTimeRegistration, NativeMobileWarehouse,
  NativeNote, NativeReason, NativeRestAPI, NativeTechnician, NativeModelCheck, LoadTest,
  TEST_NativeLocalLogin. (`LoadTest`, `TEST_NativeLocalLogin`, `NativeModelCheck`: retire candidates,
  ASSUMED left in place — not this slice's decision.)
- **Copied into DispatchApp (no ownership):** the `ModuleIntegration_Administration_Impl` rules and
  the `Utils` helpers the slice calls; marketplace: CommunityCommons, NanoflowCommons, Atlas (starter).

## 3. Data ownership — crossing entities, one owner each

| Entity | Owner | In-refs / out-refs (catalog) |
|---|---|---|
| Technician.Technician, TechnicianGroup, TechnicianLocation | DispatchApp | 107 + 11 in |
| Skill.Skill | DispatchApp | 18 in |
| RosterManagement.Roster, TechnicianRoster | DispatchApp | 9 + 6 in |
| TimeRegistration.TimeRegistration, WorkBreak, RegistrationCode | DispatchApp | 16 + 15 + 11 in |
| Scheduler.PlannerContext (+7 helpers) | DispatchApp | 4 in |
| TicketManagement.WorkOrder | monolith | 44 out |
| TicketManagement.Appointment | monolith | 23 out |
| TicketManagement.Ticket | monolith | 9 out |
| TicketManagement.WorkOrderAssignment, AppointmentAssignment | monolith | association members |
| Administration.Account | each app its own | 11 out |
| WarehouseManagement.Warehouse, AssetManagement.Asset | monolith | 7 + 10 out |

## 4. Contract per seam

| Seam | Lane | Key | Path |
|---|---|---|---|
| WorkOrder, Appointment, Ticket, WorkOrderAssignment, AppointmentAssignment → DispatchApp | OData read (external entities in one consumer module `TicketManagement`, P6) | PublicID (P1) | `odata/dispatchcore/v1` |
| Warehouse, Asset reads → DispatchApp | OData read, same service | PublicID | `odata/dispatchcore/v1` |
| Planning writes (Appointment_PlanManual, WorkOrder_RemoveTechnician, …) | REST action, primitive query params, String result (P3) | PublicID / SystemID | `rest/dispatchcore/v1/...` |
| TimeRegistration_Appointment (slice-owned → monolith entity) | key copy B′ (AppointmentPublicID on TimeRegistration) | Appointment PublicID | — |
| WorkOrder_Skill, *Assignment_Technician (monolith-owned → slice entity) | key copy B′ on the monolith side; hand-off until strangle | Technician.SystemID | — |
| Technician, Skill, Roster, TimeRegistration → monolith (in-edges) | OData read from DispatchApp at strangle | PublicID | `odata/workforce/v1` |
| Mobile partition (146 refs) | hand-off | — | — |

## 5. Auth between apps

Machine user role `DispatchCoreClient` on the monolith services (P2), one read-only module role per
published module; basic auth, the password in each app's machine-local constant store, model default
`__SET_ME__` plus a guard (P11). Target: token-based service auth via the OIDC SSO module (client
credentials). Measured per service: 200 / 401 / 404.

## 6. Cut order

1. Monolith (10.24) publishes DispatchCore OData v1 (+ REST actions for the planning writes).
2. Export the 5 slice modules (MPK) from the 10.24 copy; install into DispatchApp after
   CommunityCommons / NanoflowCommons and the copied helpers.
3. DispatchApp consumes DispatchCore; TicketManagement stubs are replaced by external entities
   (recipe A) — build-green and seam-live in one pass where the name matches.
4. Strangle (5b, if the time box allows): DispatchApp publishes Workforce v1; monolith swaps the
   slice entities for external entities in one consumer module, drops the 5 modules.

## 7. Mobile/offline partition

The monolith keeps the native profile and every synced entity (`NativeMobileTimeRegistration`,
`NativeTechnician`, `Synchronization`). DispatchApp owns no native profile. The 146 crossing refs to
the mobile partition (37 out to NativeMobileTimeRegistration, 55 in from Synchronization, …) are
hand-off rows (CONFIRMED out of scope). At strangle they would need REST-fed local copies
(seam limits → Offline).

## 8. Non-goals

- Data migration of existing rows (CONFIRMED out of scope) — DispatchApp starts empty.
- Mobile rewiring (CONFIRMED hand-off).
- Identity federation between the two user stores (token-auth follow-up).
- Redesigned UI: moved pages keep their legacy widgets converted for the React client only where
  `mx check` demands it.

## 9. Three-app relocation (paper only)

Today (increment 7): the strangled AssetsApp consumes `Technician` and `Roster` (and TechnicianGroup)
from the monolith's `odata/core/v1` (CoreAPI, machine role `CoreAPIClient`), and writes rosters
through `rest/core/v1/rosters` (`slice-assets-core/mdl/slice-core-rewire.mdl`).

After the Dispatch move:

| Item | Before | After |
|---|---|---|
| Technician, TechnicianGroup, Roster, TechnicianRoster publisher | monolith `odata/core/v1` | DispatchApp `odata/workforce/v1` |
| Roster upsert/delete REST actions (`rest/core/v1/rosters`, P7 `Roster_Delete`) | monolith | DispatchApp `rest/workforce/v1/rosters` |
| Consumers that re-point | — | AssetsApp (CoreSeam consumed service → second consumed service `WorkforceAPI`, its own consumer module per P6); monolith (its own Technician/Roster in-edges, 446 in-rows) |
| Machine role | `CoreAPIClient` on the monolith | a `WorkforceClient` on DispatchApp; AssetsApp's constant store gets a second secret |
| Monolith CoreAPI v1 | serves Technician/Roster from local tables | P10: keep `v1` serving until AssetsApp moved, then publish `v2` without those entities (removal = breaking change) |

Ledger effect: in AssetsApp's `cut-ledger.tsv` the rows now `resolved:odata` against `odata/core/v1`
for Technician/Roster stay `resolved:odata` but their evidence must name the new publisher; during
the overlap the monolith's CoreAPI serves a copy that DispatchApp owns → a **dual-owner hand-off row**
(P13) per entity until the monolith drops its copy. In this slice's in-edge ledger, the AssetsApp
consumer is not visible (cross-app consumers are not in any catalog) — one `--extra` row per consumer
must be added by hand. In the monolith's ledger of increment 7 (`inedge-ledger.tsv`), the Roster
rows marked `resolved:rest` become `resolved:rewired` to DispatchApp. Cut order: DispatchApp
publishes Workforce v1 first, AssetsApp re-points, then the monolith's CoreAPI v2 drops the entities.
