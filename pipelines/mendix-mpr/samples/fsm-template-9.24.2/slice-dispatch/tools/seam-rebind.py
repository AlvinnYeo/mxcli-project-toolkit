#!/usr/bin/env python3
"""Increment 8: rebind slice microflows/rules to the DispatchCore external entities (recipe A step 6, recipe B join).
usage: MXCLI=<mxcli> APP=<DispatchApp.mpr> seam-rebind.py <Module.Doc>... > slice-seam-rebind.mdl
Reads `describe microflow|rule` from the target app and rewrites text:
  R1 navigation to a technician/skill/group now ends at the MONO mirror: .../Technician.Technician -> TicketManagement.MonoTechnician
  R2 object comparison across the seam -> key comparison (recipe B):  <nav> = $Technician -> <nav>/TicketManagement.MonoTechnician/SystemID = $Technician/SystemID
  R3 enumeration literal of a TicketManagement enum -> string literal (seam P8: enumerations arrive as Edm.String)
  R4 database retrieve of an external entity by association -> retrieve over the navigation (seam limits -> XPath)
  R5 an XPath bracket that walks from a MONO mirror into a local association cannot cross the seam -> [true()] (HAND-OFF,
     listed on stderr and in the output header): the filter is dropped, not translated.
Each document is emitted as drop + create (exec refuses to splice some changes; the slice-side layout reset is accepted)."""
import os, re, subprocess, sys
M, APP = os.environ["MXCLI"], os.environ["APP"]
NAV_T = r"(?:_Appointment_Technician|_WorkOrder_Technician|AppointmentAssignment_Technician|WorkOrderAssignment_Technician)"
handoffs = []
def describe(kind, doc):
    return subprocess.run([M, "-p", APP, "-c", f"describe {kind} {doc}"], capture_output=True, text=True).stdout
def rebind(t, doc):
    t = re.sub(r"(TicketManagement\.%s\s*/\s*)Technician\.Technician\b" % NAV_T, r"\1TicketManagement.MonoTechnician", t)
    t = re.sub(r"(TicketManagement\.WorkOrder_Skill\s*/\s*)Skill\.Skill\b", r"\1TicketManagement.MonoSkill", t)
    t = re.sub(r"(TicketManagement\.WorkOrder_TechnicianGroup\s*/\s*)Technician\.TechnicianGroup\b", r"\1TicketManagement.MonoTechnicianGroup", t)
    t = re.sub(r"(TicketManagement\.%s)\s*=\s*\$(\w+)\b(?!/)" % NAV_T, r"\1/TicketManagement.MonoTechnician/SystemID = $\2/SystemID", t)
    t = re.sub(r"(TicketManagement\.WorkOrder_Skill)\s*=\s*\$(\w+)\b(?!/)", r"\1/TicketManagement.MonoSkill/SkillName = $\2/SkillName", t)
    t = re.sub(r"(TicketManagement\.WorkOrder_TechnicianGroup)\s*=\s*\$(\w+)\b(?!/)", r"\1/TicketManagement.MonoTechnicianGroup/Name = $\2/Name", t)
    t = re.sub(r"\bTicketManagement\.ENUM_\w+\.(\w+)", r"'\1'", t)
    t = re.sub(r"retrieve (\$\w+) from TicketManagement\.(\w+)\n(\s*)where (TicketManagement\.\w+) = (\$\w+)\n\s*first;",
               lambda m: f"retrieve {m.group(1)} from {m.group(5)}/{m.group(4)};", t)
    # R8 "A or path[contains(..) or ..]" is refused on external entities (CE0161; each alone passes — probe captures/45):
    #    distribute the path into each contains()
    def r8(m):
        path, inner = m.group(1), m.group(2)
        parts = re.findall(r"contains\((\w+), (\$\w+)\)", inner)
        return " or " + " or ".join(f"contains({path}/{a}, {v})" for a, v in parts)
    t = re.sub(r" or (TicketManagement\.\w+/TicketManagement\.\w+)\[((?:contains\(\w+, \$\w+\)(?: or )?)+)\]", r8, t)
    # R9 siblings through a reverse step ([A_B/B/A_B = $a]: other A of the same B) -> two steps, forward navigation first
    t = re.sub(r"retrieve (\$\w+) from TicketManagement\.(\w+)\n(\s*)where \[TicketManagement\.(\w+)/TicketManagement\.\w+/TicketManagement\.\4 = (\$\w+)\]",
               lambda m: f"retrieve {m.group(1)}_Parent from {m.group(5)}/TicketManagement.{m.group(4)};\n{m.group(3)}retrieve {m.group(1)} from TicketManagement.{m.group(2)}\n{m.group(3)}where [TicketManagement.{m.group(4)} = {m.group(1)}_Parent]", t)
    # R10 describe -> create round trip of a rule call: `User = $currentUser/System.owner/Administration.Account` is
    #     written back as an expression mx check refuses (CE0117 at Decision 'User is SDE?', decompose-app Stage 5b step 7)
    t = t.replace("(User = $currentUser/System.owner/Administration.Account)", "(User = $currentUser)")
    # R11 getCaption() of an external enumeration attribute: it arrives as String (P8)
    t = re.sub(r"getCaption\((\$\w+/Status)\)", r"\1", t)
    # R12 skills of an external work order are MONO mirrors: map them to local skills by SkillName (recipe B join)
    t = re.sub(r"retrieve (\$\w+) from (\$\w+)/TicketManagement\.WorkOrder_Skill;",
               r"\1 = call microflow DispatchSeam.WorkOrder_GetLocalSkills(WorkOrder = \2);", t)
    # R13 a rule-based decision describes as `if not(Rule(...)) then`; re-created it becomes an expression split, and an
    #     expression cannot call a rule (CE0117 at Decision 'User is SDE?'). The rule only tests one user role, so the
    #     test is inlined: a retrieve of that role of the current user before the decision, `= empty` as the condition.
    ROLE = {"SDE": "ServiceDeskEmployee", "SRM": "ServiceRegionManager", "Technician": "Mechanic"}
    L = t.split("\n"); out2 = []
    for k, line in enumerate(L):
        m = re.match(r"^(\s*)if not\(ModuleIntegration_Administration_Impl\.Rule_User_HasUserRole_(\w+)\(User = \$currentUser\)\) then$", line)
        if m and m.group(2) in ROLE:
            ind, r = m.group(1), m.group(2)
            j = len(out2)
            while j > 0 and out2[j - 1].strip().startswith("@"): j -= 1
            out2[j:j] = [f"{ind}retrieve $Role_{r}_{k} from System.UserRole", f"{ind}  where [id = '[%UserRole_{ROLE[r]}%]'][System.UserRoles = $currentUser]", f"{ind}  first;"]
            out2.append(f"{ind}if $Role_{r}_{k} = empty then")
        else:
            out2.append(line)
    t = "\n".join(out2)
    # R6 local technician found through the remote assignment of an appointment -> two steps over the key (recipe B);
    #    drift: the appointment's accepted technician (_Appointment_Technician) stands in for "first assignment"
    t = re.sub(r"retrieve (\$\w+) from Technician\.Technician\n(\s*)where TicketManagement\.AppointmentAssignment_Technician/TicketManagement\.AppointmentAssignment\s*/TicketManagement\.AppointmentAssignment_Appointment = (\$\w+)\n\s*first;",
               lambda m: f"retrieve {m.group(1)}_Mono from {m.group(3)}/TicketManagement._Appointment_Technician;\n{m.group(2)}retrieve {m.group(1)} from Technician.Technician\n{m.group(2)}where [SystemID = {m.group(1)}_Mono/SystemID]\n{m.group(2)}first;", t)
    def br(m):
        s = m.group(0)
        # R7 reverse traversal of a navigation (owner side reached from the destination): OData publishes navigations on
        # the owner only, so XPath on external entities cannot walk them backwards -> [false()] (HAND-OFF, no rows: the
        # safe direction for flows that write or delete what they retrieve)
        for a, e in re.findall(r"TicketManagement\.(_?[A-Za-z]+?)_[A-Za-z]+\s*/\s*TicketManagement\.([A-Za-z]+)", s):
            if a.lstrip("_") == e:
                handoffs.append(f"{doc}: REVERSE {re.sub(chr(10), ' ', s)[:150]}")
                return "[false()]"
        if re.search(r"Mono(?:Technician|Skill|TechnicianGroup)\s*/\s*(?:Technician|Skill|Administration|Scheduler|RosterManagement|TimeRegistration)\.", s) \
           or re.search(r"(?:Technician|Skill)\.\w+\s*/\s*TicketManagement\.", s):
            handoffs.append(f"{doc}: {re.sub(chr(10), ' ', s)[:160]}")
            return "[true()]"
        return s
    # innermost-first is not needed: R5 replaces the whole top-level bracket that crosses
    out, i = [], 0
    while i < len(t):
        if t[i] == "[":
            depth, j = 0, i
            while j < len(t):
                if t[j] == "[": depth += 1
                elif t[j] == "]":
                    depth -= 1
                    if depth == 0: break
                j += 1
            seg = t[i:j + 1]
            out.append(br(re.match(r".*", seg, re.S)) if "'" not in seg[:2] else seg); i = j + 1
        else:
            out.append(t[i]); i += 1
    return "".join(out)
body = []
for doc in sys.argv[1:]:
    kind = "rule" if doc.split(".")[1].startswith(("User_Can", "User_Has")) else "microflow"
    d = describe(kind, doc)
    d = "\n".join(l for l in d.splitlines() if not l.startswith("WARNING")).replace("mdl 1;\n", "", 1)
    n = rebind(d, doc)
    body.append(f"drop {kind} {doc};\n{n.strip()}")
print("mdl 1;\n-- Generated by tools/seam-rebind.py (increment 8). HAND-OFF brackets replaced by [true()]:")
for h in handoffs: print("--   " + h)
print("\n\n".join(body))
print(f"-- {len(handoffs)} hand-off brackets", file=sys.stderr)
