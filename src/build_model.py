"""Rebuild the separate offline semantic model using Power BI Authoring MCP."""
from pathlib import Path
import argparse
import json
import queue
import shutil
import subprocess
import threading
from model_spec import ROOT, create_payloads

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--accept-eula',action='store_true',help='Use only after reviewing the Microsoft MCP EULA at https://go.microsoft.com/fwlink/?LinkId=2381247')
    args=parser.parse_args()
    if not args.accept_eula:parser.error('Review the MCP EULA, then explicitly pass --accept-eula to authorize acceptance.')
    create_payloads()
    spec=json.loads((ROOT/'src/model_payloads.json').read_text(encoding='utf-8'))
    npx=shutil.which('npx.cmd') or shutil.which('npx')
    if not npx:raise RuntimeError('Install Node.js 20+ with npm/npx.')
    process=subprocess.Popen([npx,'-y','@microsoft/powerbi-modeling-mcp@latest','--start','--accept-eula'],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,encoding='utf-8')
    responses=queue.Queue();logs=[]
    def read_stdout():
        for line in process.stdout:
            try:responses.put(json.loads(line))
            except json.JSONDecodeError:logs.append(line.strip())
    def read_stderr():
        for line in process.stderr:logs.append(line.strip())
    threading.Thread(target=read_stdout,daemon=True).start();threading.Thread(target=read_stderr,daemon=True).start()
    request_id=0
    def rpc(method,params):
        nonlocal request_id
        request_id+=1
        process.stdin.write(json.dumps({'jsonrpc':'2.0','id':request_id,'method':method,'params':params})+'\n');process.stdin.flush()
        while True:
            response=responses.get(timeout=120)
            if response.get('id')==request_id:
                if 'error' in response or response.get('result',{}).get('isError'):raise RuntimeError(json.dumps(response))
                return response
    def tool(name,request):
        response=rpc('tools/call',{'name':name,'arguments':{'request':request}})
        logs.append({'tool':name,'result':response});return response
    connection='CockpitOfflineRebuild'
    try:
        rpc('initialize',{'protocolVersion':'2024-11-05','capabilities':{},'clientInfo':{'name':'manufacturing-cockpit-rebuild','version':'1.0'}})
        process.stdin.write(json.dumps({'jsonrpc':'2.0','method':'notifications/initialized'})+'\n');process.stdin.flush()
        tool('database_operations',{'operation':'Create','connectionName':connection,'createDefinition':{'name':'Manufacturing Reliability & Maintenance Cockpit','isOffline':True,'compatibilityLevel':1702}})
        tool('model_operations',{'operation':'Update','connectionName':connection,'definition':{'culture':'en-US','sourceQueryCulture':'en-US','discourageImplicitMeasures':True,'defaultPowerBIDataSourceVersion':'PowerBI_V3','annotations':[{'key':'__PBI_TimeIntelligenceEnabled','value':'0'}]}})
        expression=json.dumps((ROOT/'data/processed').as_posix())+' meta [IsParameterQuery=true, Type="Text", IsParameterQueryRequired=true]'
        tool('named_expression_operations',{'operation':'Create','connectionName':connection,'definitions':[{'name':'Data Folder','kind':'M','expression':expression,'description':'Processed CSV folder; generated from the current project root.'}]})
        for name,key in [('table_operations','tables'),('relationship_operations','relationships'),('measure_operations','measures')]:
            tool(name,{'operation':'Create','connectionName':connection,'definitions':spec[key],'options':{'continueOnError':False,'useTransaction':True}})
        tool('table_operations',{'operation':'MarkAsDateTable','connectionName':connection,'markAsDateTableDefinitions':[{'tableName':'Dates','dateColumnName':'Date'}]})
        tool('database_operations',{'operation':'ExportToTmdlFolder','connectionName':connection,'tmdlFolderPath':str(ROOT/'Manufacturing_Reliability_Cockpit.SemanticModel/definition')})
        (ROOT/'validation/model_build.json').write_text(json.dumps({'status':'passed','tables':len(spec['tables']),'relationships':len(spec['relationships']),'measures':len(spec['measures']),'log':logs},indent=2),encoding='utf-8')
        print('Model built and exported by MCP. Open the PBIP and Refresh to load the CSVs.')
    finally:process.terminate()

if __name__=='__main__':main()
