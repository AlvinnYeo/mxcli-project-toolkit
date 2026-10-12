# Increment 7 in-edge resolution per monolith source document (10.24 catalog before the cut: 642 refs, 194 docs).
# Writes inedge-ledger.tsv and the `in` block of cut-rules.tsv (one rule per document, evidence on every rule).
import collections,os
rows=[l.rstrip('\n').split('\t') for l in open('srcdocs.tsv')]
S='Synchronization.'
EV={
 'retire:admin':('retire','MxAdmin page/flow over slice data, deleted from the monolith (admin of slice data lives in the slice) - mono-strangle-swap.mdl'),
 'retire:helper':('retire','helper module deleted with the cut (cut-score: retire) - mono-strangle-swap.mdl'),
 'retire:dead':('retire','dead after the cut: helper of the old offline used-part processing, now done by the slice REST action rest/assets/v2/usedparts - mono-strangle-rewire.mdl'),
 'retire:retention':('retire','data retention of slice-owned rows (used/suggested/selected parts) is the slice\'s job; call removed from AppSettings.DataRemoval_RemoveWebData - mono-strangle-rewire.mdl, mono-strangle-pages.mdl'),
 'rebind':('resolved:rebind','move entity -> AssetsClient, persistent entity swapped for the external entity of the same name (AssetsAPIv2, odata/assets/v2/); XPath text rebound by bson-rename.py - mono-strangle-move.mdl, mono-strangle-swap.mdl, captures/04,05,07'),
 'pull':('resolved:pull','native copy chain rebound to the external entities and fed by a PULL from the slice (AssetsClient.NativeSync_*, POST rest/core/v1/nativesync[/reference]); journey step 2 - mono-strangle-feed.mdl, mono-strangle-feed2.mdl'),
 'rest':('resolved:rest','device offline action forwarded to the slice REST action (rest/assets/v2: usedparts, usedparts/delete, parts) with on error without rollback + log; journey step 5 - mono-strangle-rewire.mdl'),
 'rewired':('resolved:rewired','flow edited: external-entity reads, key copies (CustomerName, CustomerPublicID, PreferredTechnicianID, *PublicID, Ticket.AssetSystemID), helpers AssetsClient.* replacing the deleted AssetManagement/Part flows - mono-strangle-rewire-all.mdl, mono-strangle-keys.mdl'),
 'assoc':('resolved:association','monolith-owned association re-created local -> external (AssetsClient.*), local owner - mono-strangle-swap.mdl (e)'),
 'page':('resolved:rewired','page/snippet altered in place: widgets over unpublished slice data dropped, grids over external entities by key copy (AppointmentPublicID, WorkOrderPublicID) - mono-strangle-pages.mdl'),
 'h:planning':('handoff','planning suggested parts / tools on a work order: the slice owns SuggestedPart/SelectedTool; no REST create/delete in AssetsAPIv2 yet; monolith sections removed, read-only grids by WorkOrderPublicID remain'),
 'h:customdev':('handoff','device custom part / new inventory: part forwarded over REST; its zero-stock inventory and used part, and a NEW inventory row from the device, need an inventory-create REST action in the slice'),
 'h:pushback':('handoff','slice-side changes to used/suggested parts are no longer pushed to device copies (the push ran from the deleted commit flows; device copies keyed by the inherited SystemID, which mxcli cannot publish - captures/02)'),
 'h:orphan':('handoff','delete cascade into slice rows (used parts of an appointment, suggested parts/tools of a work order) dropped: orphans in the slice (P13); needs a REST delete-for-appointment/work-order action'),
 'h:moved-ui':('handoff','link to a slice page (asset view / overview / selection pages): the slice has its own navigation; needs a deep link'),
 'h:contract':('handoff','reads unpublished slice data (AgreementGroup, Dossier, Structure, Asset_Contract): contract warning returns false, dossier fields dropped; publish them if the monolith keeps needing them'),
 'h:xpath':('handoff','access-rule / search XPath walking local <-> external (CE0161): "My" rules [false()], technician-warehouse and BOM search filters removed - xpath-map2/3/4.tsv'),
}
def cls(t,d):
    m=d.split('.')[0]; n=d.split('.',1)[1]
    if m=='MasterData': return 'retire:admin'
    if m in('NativeModelCheck','LoadTest'): return 'retire:helper'
    if d.startswith('AppSettings.DataRemoval_'): return 'retire:retention'
    if d in {S+'OfflineUsedPartAction_Process_PartAdded',S+'UsedPart_SetSuggestedPartToUsedOrUnused',S+'UsedPart_UpdateInventory',S+'UsedPart_UpdateLastChangedBy',S+'UsedPart_UpdateQuantity'}: return 'retire:dead'
    if m=='Synchronization' and ('UsedPart' in n or 'SuggestedPart' in n): return 'h:pushback'
    if d in {S+'OfflineCustomPartAction_Process',S+'OfflineInventoryAction_Process'}: return 'h:customdev'
    if m=='Synchronization' and n.startswith('Offline'): return 'rest'
    if m=='Synchronization' and any(k in n for k in ('Asset','Part','UnitOfMeasure','Warehouse','Inventory')): return 'pull'
    if d in {'TicketManagement.WorkOrder_CommitSelectedParts','TicketManagement.WorkOrder_CommitSelectedTools','TicketManagement.Snippet_WorkOrder_Edit','TicketManagement.Snippet_WorkOrder_BulkEdit','TicketManagement.ACT_Workorder_CancelEdit'}: return 'h:planning'
    if d in {'TicketManagement.AppointmentList_Delete','TicketManagement.WorkOrderList_Delete'}: return 'h:orphan'
    if d in {'Navigation.Responsive','Dashboard.ACT_AssetDashboardNP_ShowAsset','Dashboard.DashboardExternal','TicketManagement.Ticket_View'}: return 'h:moved-ui'
    if d in {'TicketManagement.TicketNP_Asset_RequiresContractWarning','CustomerManagement.ContactPerson_Dossier','TicketManagement.Snippet_Asset_Details_TicketNP','CustomerManagement.ContactPerson_Overview','CustomerManagement.Snippet_ContactPerson_Details','FSMPublishedAPI.Asset_MapToAssetResponse'}: return 'h:contract'
    if t=='ENTITY' or d in {'NativeMobilePart.PartSearchHelper_SearchParts','NativeMobilePart.PartSearchHelper_SearchInventories','Technician.Technician_SelectWarehouse','Technician.Snippet_Technician_DataTabs'}: return 'h:xpath'
    if t=='ASSOCIATION': return 'assoc'
    if t in('PAGE','SNIPPET') and d in {'TicketManagement.Appointment_View','TicketManagement.WorkOrder_View','CustomerManagement.Snippet_SLA_Details','TicketManagement.WorkOrder_AdminDetails'}: return 'page'
    if os.path.exists('fix/'+d+'.mdl') or m in('General','CoreSeam'): return 'rewired'
    return 'rebind'
out=[];C=collections.Counter();G=collections.defaultdict(collections.Counter)
for t,d,n in rows:
    k=cls(t,d); r,ev=EV[k]; out.append((t,d,n,r,k,ev)); C[r]+=int(n); G[d.split('.')[0]][k]+=int(n)
with open('inedge-ledger.tsv','w') as f:
    f.write('source_type\tsource_doc\trefs\tresolution\tgroup\tevidence\n')
    for o in out: f.write('\t'.join(o)+'\n')
with open('cut-rules-in.tsv','w') as f:
    for t,d,n,r,k,ev in out: f.write(f'in\t{d}\t{r}\t{ev}\n')
print('refs',sum(int(o[2]) for o in out),'docs',len(out)); print(dict(C))
for g,c in sorted(G.items(),key=lambda x:-sum(x[1].values())): print(' ',g,sum(c.values()),dict(c))
