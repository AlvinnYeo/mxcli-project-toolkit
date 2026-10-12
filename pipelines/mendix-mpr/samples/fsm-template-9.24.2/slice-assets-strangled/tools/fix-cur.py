import re,glob,os
os.makedirs('fix',exist_ok=True)
X_ASSET_SEARCH=r" or TicketManagement\.Ticket_Asset/AssetsClient\.Asset\[contains\(FullAddress, \$SearchString\) or contains\(Description, \$SearchString\) or AssetManagement\.Asset_Customer/CustomerManagement\.Customer\[contains\(CustomerName, \$SearchString\)\]\]"
SUBS=[
 (r'call microflow AssetManagement\.Asset_GetRelevantSLA\(','call microflow AssetsClient.Asset_GetRelevantSLA('),
 (r'AssetManagement\.Asset_Get_BySystemID\(','AssetsClient.Asset_Get_BySystemID('),
 (r'AssetManagement\.Asset_GetPreferredTechnician\(','AssetsClient.Asset_GetPreferredTechnician('),
 (r'AssetManagement\.Rule_Asset_RequiresNoContractNotification\(','AssetsClient.Rule_Asset_RequiresNoContractNotification('),
 (r'Part\.Part_NameIsInUse\(','AssetsClient.Part_NameIsInUse('),
 (r'\$Asset/AssetManagement\.Asset_Customer/CustomerManagement\.Customer/CustomerName','$Asset/CustomerName'),
 (r'/AssetManagement\.Asset_Technician_Preferred != empty','/PreferredTechnicianID != empty'),
 (r'/AssetManagement\.Asset_Technician_Preferred = \$Asset\]','/TechnicianID = $Asset/PreferredTechnicianID]'),
 (X_ASSET_SEARCH,''),
 (r'where AssetManagement\.Asset_Customer = \$Asset','where PublicID = $Asset/CustomerPublicID'),
]
for f in glob.glob('cur/*.mdl'):
    s=open(f).read(); o=s
    for a,b in SUBS: s=re.sub(a,b,s)
    open('fix/'+os.path.basename(f),'w').write(s)
    left=sorted(set(re.findall(r'\b(?:AssetManagement|Part|WarehouseManagement|Tool)\.[A-Za-z_]+|AssetsClient\.(?:UsedPart_Appointment|SuggestedPart_WorkOrder|SelectedTool_WorkOrder|Asset_Customer|Asset_Technician_Preferred|Asset_Contract)',s)))
    if left: print(os.path.basename(f)[:-4],':',' '.join(left))
