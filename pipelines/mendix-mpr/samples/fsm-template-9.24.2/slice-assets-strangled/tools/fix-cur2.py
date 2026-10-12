import re
def ed(name,pairs,flags=0):
    p='fix/'+name+'.mdl'; s=open(p).read()
    for a,b in pairs:
        n=len(re.findall(a,s,flags|re.M))
        if n==0: print('NO MATCH',name,a[:60])
        s=re.sub(a,b,s,flags=flags|re.M)
    open(p,'w').write(s)
RM=lambda v: (r'^\s*retrieve \$%sList from \$\w+/AssetsClient\.\w+;\n\s*add \$%sList to \$%sList_ToDelete;\n'%(v,v,v),'')
ed('TicketManagement.TicketNP_IsChoosenTechnicianAssigned',[(r'retrieve \$Technician_Preferred from Technician\.Technician\n\s*where AssetManagement\.Asset_Technician_Preferred/AssetsClient\.Asset/TicketManagement\.Ticket_Asset = \$Ticket\n\s*first;',
 'retrieve $TicketAsset from $Ticket/TicketManagement.Ticket_Asset;\n    $Technician_Preferred = call microflow AssetsClient.Asset_GetPreferredTechnician(Asset = $TicketAsset);')])
ed('Synchronization.SuggestedPart_ProcessUpdatingNativeSuggestedPart',[(r'retrieve \$WorkOrder from \$SuggestedPart/AssetsClient\.SuggestedPart_WorkOrder;',
 'retrieve $WorkOrder from TicketManagement.WorkOrder\n    where PublicID = $SuggestedPart/WorkOrderPublicID\n    first;')])
ed('Synchronization.Rule_SuggestedPart_HasChanged',[(r'where Part\.SuggestedPart_WorkOrder = \$SuggestedPart','where PublicID = $SuggestedPart/WorkOrderPublicID'),
 (r'retrieve \$Part from AssetsClient\.Part\n\s*where AssetsClient\.SuggestedPart_Part = \$SuggestedPart\n\s*first;','retrieve $Part from $SuggestedPart/AssetsClient.SuggestedPart_Part;')])
ed('TicketManagement.ACT_Workorder_CancelEdit',[(r'^\s*retrieve \$SelectedToolList from \$WorkOrder/AssetsClient\.SelectedTool_WorkOrder;\n\s*loop \$IteratorSelectedTool in \$SelectedToolList\n\s*begin\n\s*rollback \$IteratorSelectedTool;\n\s*end loop;\n',''),
 (r'^\s*retrieve \$SuggestedPartList from \$WorkOrder/AssetsClient\.SuggestedPart_WorkOrder;\n\s*loop \$IteratorSuggestedPart in \$SuggestedPartList\n\s*begin\n\s*rollback \$IteratorSuggestedPart;\n\s*end loop;\n','')])
ed('TicketManagement.AppointmentList_Delete',[(r'^\s*\$UsedPartList_ToDelete = create list of AssetsClient\.UsedPart;\n',''),RM('UsedPart'),(r'^\s*call microflow Part\.UsedPartList_Delete\(.*\n','')])
ed('TicketManagement.WorkOrderList_Delete',[(r'^\s*\$SelectedToolList_ToDelete = create list of AssetsClient\.SelectedTool;\n',''),(r'^\s*\$SuggestedPartList_ToDelete = create list of AssetsClient\.SuggestedPart;\n',''),RM('SelectedTool'),RM('SuggestedPart'),
 (r'^\s*call microflow Tool\.SelectedToolList_Delete\(.*\n',''),(r'^\s*call microflow Part\.SuggestedPartList_Delete\(.*\n','')])
for n in ['TicketManagement.WorkOrder_CommitSelectedParts','TicketManagement.WorkOrder_CommitSelectedTools']:
    ed(n,[(r'begin\n(.|\n)*?\n  return;\nend;','begin\n  -- increment 7: suggested parts / selected tools are owned by the Assets & Parts app; planning them on a\n  -- work order is a hand-off (no REST create in AssetsAPIv2 yet). Kept as a no-op so callers stay unchanged.\n  return;\nend;')])
ed('General.ASU_General',[(r'^\s*call microflow Part\.ASU_UnitOfMeasure_PrefillIfNeeded\(\);\n',''),
 (r'call microflow AssetsSeam\.ASU_EnsureJourneyAccounts\(\);','-- TEST-ONLY (journey accounts + the slice machine account); remove before real use\n  call microflow AssetsSeam.ASU_EnsureJourneyAccounts();')])
ed('Dashboard.ACT_AssetDashboardNP_ShowAsset',[(r'show page AssetManagement\.Asset_View\(Asset = \$Asset\);',"show message 'Asset details live in the Assets & Parts app.' type Information;")])
ed('FSMPublishedAPI.Asset_MapToAssetResponse',[(r'^\s*retrieve \$(Structure|Dossier|AgreementGroup) from AssetManagement\.\w+\n\s*where AssetManagement\.\w+ = \$Asset\n\s*first;\n',''),
 (r'Structure = \$Structure/Name, Dossier = \$Dossier/Name, AgreementGroup = \$AgreementGroup/Name, ','')])
