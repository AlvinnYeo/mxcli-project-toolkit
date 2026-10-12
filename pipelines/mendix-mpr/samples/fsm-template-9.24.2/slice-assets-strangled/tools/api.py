# tiny helper: call the slice/monolith services with the machine accounts from the local constant stores (never printed)
import json,base64,urllib.request,sys
mono=json.load(open('<lab>/web-assets/mono/.mxcli/constants.json'))['constants']
ACC={'slice':('fsm_monolith',mono['AssetsSeam.APIUserPassword']),'mono':('assets_slice',mono['CoreSeam.SliceAPIUserPassword']),'none':None}
def call(method,url,acc='slice',data=None):
    r=urllib.request.Request(url,method=method,data=data)
    a=ACC[acc]
    if a: r.add_header('Authorization','Basic '+base64.b64encode(f'{a[0]}:{a[1]}'.encode()).decode())
    try:
        with urllib.request.urlopen(r,timeout=60) as f: return f.status,f.read().decode()
    except urllib.error.HTTPError as e: return e.code,e.read().decode()[:300]
if __name__=='__main__':
    m,u,a=sys.argv[1],sys.argv[2],sys.argv[3] if len(sys.argv)>3 else 'slice'
    st,b=call(m,u,a); print('HTTP',st); print(b if len(sys.argv)<5 else b[:int(sys.argv[4])])
