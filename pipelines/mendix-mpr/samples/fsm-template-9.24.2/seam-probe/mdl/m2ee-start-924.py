import json,os,sys,base64,urllib.request
# Probe recipe: configure + start a Mendix 9.24 runtime started by start-runtime-924.sh (M2EE admin API).
# 'python3 m2ee-start-924.py' = first start; any argument = re-send config + start only.
def call(action,params=None,port=8390,pw=None):
    req=urllib.request.Request('http://127.0.0.1:%d/'%port,data=json.dumps({'action':action,'params':params or {}}).encode(),
        headers={'Content-Type':'application/json','X-M2EE-Authentication':base64.b64encode((pw or os.environ['M2EE_ADMIN_PASS']).encode()).decode()})
    op=urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try: r=op.open(req,timeout=600).read().decode()
    except urllib.error.HTTPError as e: r=e.read().decode()
    print(action,'->',r[:1500]); return json.loads(r)
D='<lab>/seam/mono9/deployment'; R='<home>/.mxcli/runtime/9.24.2.6130/runtime'
import secrets
consts={c['Name']:c.get('DefaultValue','') for c in json.load(open(D+'/model/metadata.json')).get('Constants',[])}
consts['MendixSSO.TokenEncryptionKey']=secrets.token_hex(8)  # local probe only, never stored
if len(sys.argv)<2: call('update_appcontainer_configuration',{'runtime_port':8380,'runtime_listen_addresses':'127.0.0.1'})
call('update_configuration',{'BasePath':D,'RuntimePath':R,'DTAPMode':'D','DatabaseType':'HSQLDB','DatabaseName':'default',
  'DatabaseJdbcUrl':'jdbc:hsqldb:file:%s/data/database/hsqldb/default/default'%D,'ApplicationRootUrl':'http://127.0.0.1:8380/',
  'MicroflowConstants':consts})
r=call('start',{'autocreatedb':True})
if r.get('result')==2 or 'database' in json.dumps(r).lower():
    call('execute_ddl_commands'); call('start',{'autocreatedb':True})
