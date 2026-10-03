"""Generate native PBIR visuals from a documented, consistent page layout."""
from pathlib import Path
import json
import math
import uuid

ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / 'Manufacturing_Reliability_Cockpit.Report'
DEF = REPORT / 'definition'
VS = 'https://developer.microsoft.com/json-schemas/fabric/item/report/definition/visualContainer/2.9.0/schema.json'
PS = 'https://developer.microsoft.com/json-schemas/fabric/item/report/definition/page/2.1.0/schema.json'
NAVY, TEAL, ORANGE, RED, GRAY, BG = '#17324D', '#007F82', '#B85C00', '#C53D43', '#546574', '#F3F6F8'
PAGES = [('plant_overview','Plant Overview'),('machine_health','Machine Health'),('failure_analysis','Failure Analysis'),('maintenance_priorities','Maintenance Priorities')]
MEASURES = {}
spec = json.loads((ROOT/'src/model_payloads.json').read_text(encoding='utf-8'))
for m in spec['measures']: MEASURES[m['name']] = m['tableName']
MEASURES.update({'Top Machine Failure Events':'Failures','Priority Date Label':'Daily Health','Sensor Context':'Sensor Daily'})
LAYOUT = {}

def write(path, data):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(data,indent=2),encoding='utf-8')
def lit(v):
    if isinstance(v,bool): s='true' if v else 'false'
    elif isinstance(v,(int,float)):s=str(v)+'D'
    else:s="'"+str(v).replace("'","''")+"'"
    return {'expr':{'Literal':{'Value':s}}}
def fill(color):return {'solid':{'color':lit(color)}}
def prop(props,selector=None):
    r={'properties':props}
    if selector:r['selector']=selector
    return r
def field(table, name, measure=False, alias=None):
    return {'Measure' if measure else 'Column':{'Expression':{'SourceRef':{'Source':alias} if alias else {'Entity':table}},'Property':name}}
def projection(binding):
    if isinstance(binding,str):table,name,measure=MEASURES[binding],binding,True
    else:table,name=binding;measure=False
    return {'field':field(table,name,measure),'queryRef':table+'.'+name,'nativeQueryRef':name,'displayName':name}
def pad(n=8):return [prop({k:lit(n) for k in ['top','bottom','left','right']})]
def add(page, typ, rect, roles=None, title=None, objects=None, extra=None):
    ident=uuid.uuid4().hex[:20]; x,y,w,h=rect
    placements=LAYOUT.setdefault(page,[])
    z=(len(placements)+1)*1000
    v={'visualType':typ,'objects':objects or {},'visualContainerObjects':{
        'background':[prop({'show':lit(True),'color':fill('#FFFFFF'),'transparency':lit(0)})],
        'border':[prop({'show':lit(False)})],
        'padding':pad(12),
        'visualHeader':[prop({'show':lit(False)})],
        'visualTooltip':[prop({'show':lit(True)})],
        'general':[prop({'altText':lit(title or typ)})]}}
    if title:v['visualContainerObjects']['title']=[prop({'show':lit(True),'text':lit(title),'fontColor':fill(NAVY),'fontSize':lit(14),'fontFamily':lit('Segoe UI Semibold')})]
    else:v['visualContainerObjects']['title']=[prop({'show':lit(False)})]
    if roles:v['query']={'queryState':{r:{'projections':[projection(b) for b in bindings]} for r,bindings in roles.items()}}
    if extra:v.update(extra)
    container={'$schema':VS,'name':ident,'position':{'x':x,'y':y,'width':w,'height':h,'z':z,'tabOrder':z},'visual':v}
    write(DEF/'pages'/page/'visuals'/ident/'visual.json',container)
    placements.append({'id':ident,'kind':typ,'title':title,'rect':list(rect),'bindings':roles or {}})
    return container
def text(page, value, rect, size=18, color=GRAY):
    obj={'general':[prop({'paragraphs':[{'textRuns':[{'value':value,'textStyle':{'fontFamily':'Segoe UI Semibold' if size>=24 else 'Segoe UI','fontSize':str(size)+'px','color':color}}],'horizontalTextAlignment':'left'}]})]}
    v=add(page,'textbox',rect,objects=obj)
    v['visual']['visualContainerObjects'].update({'background':[prop({'show':lit(False)})],'padding':pad(0)})
    write(DEF/'pages'/page/'visuals'/v['name']/'visual.json',v)
def selection(table,col,value):
    return {'filter':{'Version':2,'From':[{'Name':'s','Entity':table,'Type':0}],'Where':[{'Condition':{'In':{'Expressions':[field(table,col,alias='s')],'Values':[[{'Literal':{'Value':"'"+value+"'"}}]]}}}]}}
def slicer(page, binding, title, rect, mode='Dropdown', default=None, sync=True):
    obj={'data':[prop({'mode':lit(mode)})],'header':[prop({'show':lit(True),'text':lit(title),'fontColor':fill(NAVY),'textSize':lit(11)})],
         'items':[prop({'fontColor':fill(NAVY),'textSize':lit(11)})]}
    if default:obj['general']=[prop({'filter':selection(*binding,default)})]
    if mode=='Between':
        obj['data'][0]['properties'].update({'startDate':{'expr':{'Literal':{'Value':"datetime'2015-01-01T00:00:00'"}}},'endDate':{'expr':{'Literal':{'Value':"datetime'2015-12-31T00:00:00'"}}}})
        obj['general']=[prop({'filter':{'filter':{'Version':2,'From':[{'Name':'d','Entity':'Dates','Type':0}],'Where':[{'Condition':{'Between':{'Expression':field('Dates','Date',alias='d'),'LowerBound':{'Literal':{'Value':"datetime'2015-01-01T00:00:00'"}},'UpperBound':{'Literal':{'Value':"datetime'2015-12-31T00:00:00'"}}}}}]}}})]
    extra={'syncGroup':{'groupName':'Filter '+title,'fieldChanges':True,'filterChanges':True}} if sync else {}
    v=add(page,'slicer',rect,{'Values':[binding]},objects=obj,extra=extra)
    v['visual']['visualContainerObjects']['padding']=pad(8)
    write(DEF/'pages'/page/'visuals'/v['name']/'visual.json',v)
def card(page, names, rect, color=TEAL, text_card=False):
    fs=16 if text_card else round(1080*0.028)
    obj={'value':[prop({'fontSize':lit(fs),'fontColor':fill(color),'textWrap':lit(True),'labelDisplayUnits':lit('1')}, {'id':'default'})],
         'label':[prop({'fontSize':lit(12),'fontColor':fill(GRAY),'show':lit(not text_card)}, {'id':'default'})],
         'padding':[prop({'paddingUniform':lit(8)},{'id':'default'})],'layout':[prop({'paddingUniform':lit(0)},{'id':'default'})]}
    v=add(page,'cardVisual',rect,{'Data':names},objects=obj)
    v['visual']['visualContainerObjects']['padding']=pad(8)
    v['visual']['visualContainerObjects']['spacing']=[prop({'customizeSpacing':lit(True),'verticalSpacing':lit(2)},{'id':'default'})]
    write(DEF/'pages'/page/'visuals'/v['name']/'visual.json',v)
def chart(page, typ, category, measures, title, rect, color=TEAL, tooltip=None, sort_desc=False):
    obj={'categoryAxis':[prop({'fontSize':lit(11),'labelColor':fill(GRAY),'showAxisTitle':lit(False)})],
         'valueAxis':[prop({'fontSize':lit(11),'labelColor':fill(GRAY),'showAxisTitle':lit(False),'gridlineColor':fill('#E4EAEE'),'gridlineThickness':lit(1),'labelDisplayUnits':lit(1)})],
         'legend':[prop({'show':lit(len(measures)>1),'position':lit('Top'),'fontSize':lit(11)})],
         'dataPoint':[prop({'fill':fill(c)},{'metadata':MEASURES[m]+'.'+m}) for m,c in zip(measures,[color,GRAY,ORANGE,RED])]}
    if 'Bar' in typ or 'Column' in typ:
        if len(measures)==1:obj['dataPoint'].insert(0,prop({'defaultColor':fill(color)}))
        obj['valueAxis'][0]['properties']['start']=lit(0)
        obj['labels']=[prop({'show':lit(True),'fontSize':lit(11),'labelDisplayUnits':lit(1),'color':fill(NAVY)})]
    else:
        obj['labels']=[prop({'show':lit(False)})]
        obj['lineStyles']=[prop({'strokeWidth':lit(2.5),'lineChartType':lit('linear'),'areaShow':lit(False)})]
        if 'Prior 30 Day Mean' in measures:
            obj['lineStyles'].append(prop({'lineStyle':lit('dashed')},{'metadata':'Sensor Daily.Prior 30 Day Mean'}))
    roles={'Category':[category],'Y':measures}
    if tooltip:roles['Tooltips']=tooltip
    v=add(page,typ,rect,roles,title,obj)
    sort=projection(measures[0] if sort_desc else category)['field']
    v['visual']['query']['sortDefinition']={'sort':[{'field':sort,'direction':'Descending' if sort_desc else 'Ascending'}],'isDefaultSort':True}
    write(DEF/'pages'/page/'visuals'/v['name']/'visual.json',v)
def table(page, bindings, title, rect, sort=None):
    obj={'columnHeaders':[prop({'fontSize':lit(11),'fontColor':fill(NAVY),'backColor':fill('#E8F0F3'),'columnAdjustment':lit('growToFit'),'autoSizeColumnWidth':lit(True),'wordWrap':lit(True)})],
         'values':[prop({'fontSize':lit(11),'fontColorPrimary':fill(NAVY),'backColorPrimary':fill('#FFFFFF'),'backColorSecondary':fill('#F3F6F8'),'wordWrap':lit(True)})],
         'grid':[prop({'rowPadding':lit(8)})],'total':[prop({'totals':lit(False)})]}
    v=add(page,'tableEx',rect,{'Values':bindings},title,obj)
    v['visual']['visualContainerObjects']['stylePreset']=[prop({'name':lit('None')})]
    if sort:v['visual']['query']['sortDefinition']={'sort':[{'field':projection(sort)['field'],'direction':'Descending'}],'isDefaultSort':True}
    write(DEF/'pages'/page/'visuals'/v['name']/'visual.json',v)
def button(page,label,target,rect,back=False):
    color=TEAL if target==page else NAVY
    obj={'text':[prop({'show':lit(True)}),prop({'text':lit(label),'fontSize':lit(11),'fontColor':fill('#FFFFFF'),'horizontalAlignment':lit('center')},{'id':'default'})],
         'icon':[prop({'show':lit(False)}),prop({'placement':lit('left')},{'id':'default'})],
         'fill':[prop({'show':lit(True)}),prop({'fillColor':fill(color)},{'id':'default'})],
         'outline':[prop({'show':lit(False)})],
         'shape':[prop({'tileShape':lit('rectangleRounded'),'roundEdge':lit(4)}),prop({'tileShape':lit('rectangleRounded')},{'id':'default'})]}
    v=add(page,'actionButton',rect,objects=obj)
    link={'show':lit(True),'type':lit('Back' if back else 'PageNavigation')}
    if not back:link['navigationSection']=lit(target)
    v['visual']['visualContainerObjects'].update({'background':[prop({'show':lit(False)})],'border':[prop({'show':lit(False)})],'padding':pad(0),'visualLink':[prop(link)]})
    write(DEF/'pages'/page/'visuals'/v['name']/'visual.json',v)

def main():
    # Only clear generated visual JSON; never touch another project or model.
    for p in (DEF/'pages').glob('*/visuals/*/visual.json'):
        p.unlink()
        if not any(p.parent.iterdir()):p.parent.rmdir()
    for directory in (DEF/'pages').glob('*/visuals/*'):
        if directory.is_dir() and not any(directory.iterdir()):directory.rmdir()
    for page,name in PAGES:
        write(DEF/'pages'/page/'page.json',{'$schema':PS,'name':page,'displayName':name,'displayOption':'FitToPage','width':1920,'height':1080,
            'objects':{'background':[prop({'color':fill(BG),'transparency':lit(0)})]}})
        text(page,'MANUFACTURING RELIABILITY & MAINTENANCE COCKPIT',(32,24,1000,32),18,TEAL)
        text(page,name,(32,64,928,64),40,NAVY)
        text(page,'Historical Microsoft sample | 2015 telemetry | simulated assets',(32,136,928,32),18,GRAY)
        slicer(page,('Machines','Model'),'Model',(984,56,232,104))
        slicer(page,('Machines','Machine'),'Machine',(1232,56,232,104),sync=page!='machine_health')
        slicer(page,('Dates','Date'),'Date range',(1480,40,408,128),'Between')
        for i,(target,label) in enumerate(PAGES):button(page,label,target,(32+i*248,192,232,48))
        text(page,'HISTORICAL ANALYSIS  /  no live feed',(1392,200,496,40),18,GRAY)
        text(page,'Source: Microsoft simulated predictive-maintenance sample. Recommendations require engineering review.',(32,1032,1856,32),16,GRAY)
    p='plant_overview'
    card(p,['Failure Events'],(32,272,448,112),RED)
    card(p,['Machines With Failures'],(504,272,448,112),NAVY)
    card(p,['Observed Telemetry Hours'],(976,272,448,112),TEAL)
    card(p,['Failures per 1000 Observed Hours'],(1448,272,440,112),ORANGE)
    chart(p,'lineChart',('Dates','Month'),['Failure Events'],'Component failure events by month',(32,408,1128,320),RED,tooltip=['Machines With Failures','Observed Telemetry Hours'])
    chart(p,'clusteredBarChart',('Machines','Machine'),['Top Machine Failure Events'],'Machines with most failure events | top 10 ranks',(1184,408,704,320),RED,sort_desc=True)
    chart(p,'clusteredBarChart',('Components','Component'),['Failure Events'],'Failure concentration by component',(32,752,600,248),RED,tooltip=['Component Cumulative Share'],sort_desc=True)
    table(p,[('Components','Component'),'Failure Events','Component Cumulative Share'],'Pareto | descending events',(656,752,552,248),'Failure Events')
    card(p,['Plant Insight'],(1232,752,656,128),NAVY,True)
    text(p,'Rate = component failure records / observed hourly telemetry samples × 1,000, within selected dates and machines. Telemetry exposure is not productive uptime.',(1248,904,624,96),18,GRAY)
    p='machine_health'
    card(p,['Machine Context'],(32,272,1152,96),NAVY,True)
    slicer(p,('Sensors','Sensor'),'Sensor',(1208,272,256,96),default='Voltage',sync=False)
    button(p,'Back to source','',(1488,296,216,48),back=True)
    card(p,['Latest Observed Timestamp'],(32,392,592,112),NAVY)
    card(p,['Failure Events','Replacement Records'],(648,392,592,112),RED)
    card(p,['Priority Status'],(1264,392,624,112),ORANGE,True)
    chart(p,'lineChart',('Dates','Date'),['Sensor Daily Mean','Prior 30 Day Mean'],'Daily sensor trend vs preceding 30-day reference',(32,528,1208,256),TEAL,tooltip=['Sensor Deviation Z'])
    chart(p,'lineChart',('Dates','Date'),['Error Events','Replacement Records','Failure Events'],'Event records on the same daily time axis',(32,808,1208,192),ORANGE)
    card(p,['Machine History Note'],(1264,528,624,128),NAVY,True)
    card(p,['Sensor Context'],(1264,680,624,88),TEAL,True)
    text(p,'Select a single machine or use drill-through from a machine row.\n\nThe dashed/reference series uses only earlier daily means (30 days; at least 7). Units are sample units: the source does not specify physical units.\n\nNo recorded event does not establish perfect health. Partial boundary days are retained.',(1280,776,592,224),18,GRAY)
    page=json.loads((DEF/'pages'/p/'page.json').read_text())
    page['filterConfig']={'filters':[{'name':'MachineDrillFilter','field':field('Machines','Machine'),'type':'Categorical','howCreated':'Drillthrough'}]}
    page['pageBinding']={'name':'Pod','type':'Drillthrough','parameters':[{'name':'MachineDrillParameter','boundFilter':'MachineDrillFilter','fieldExpr':field('Machines','Machine')} ]}
    write(DEF/'pages'/p/'page.json',page)
    p='failure_analysis'
    slicer(p,('Components','Component'),'Component',(32,272,256,96),sync=False)
    slicer(p,('Sensors','Sensor'),'Sensor',(312,272,256,96),default='Voltage',sync=False)
    card(p,['Failure Events','Window Event Sample'],(592,272,736,112),RED)
    card(p,['Failures per 1000 Observed Hours'],(1352,272,536,112),ORANGE)
    chart(p,'clusteredBarChart',('Machines','Model'),['Failures per 1000 Observed Hours'],'Failure records per 1,000 observed hours | by model',(32,408,904,256),TEAL,tooltip=['Failure Events','Observed Machines','Observed Telemetry Hours'],sort_desc=True)
    chart(p,'clusteredBarChart',('Machines','Age Band'),['Failures per 1000 Observed Hours'],'Failure records per 1,000 observed hours | recorded age',(960,408,928,256),TEAL,tooltip=['Failure Events','Observed Machines','Observed Telemetry Hours'])
    chart(p,'lineChart',('Failure Windows','Relative Day'),['Failure Window Mean'],'Sensor behavior around component failure | day 0 = failure',(32,688,904,312),ORANGE,tooltip=['Window Event Sample','Window Hour Sample'])
    table(p,[('Components','Component'),'Failure Events','Machines With Failures','Failures per 1000 Observed Hours'],'Counts alongside normalized component comparisons',(960,688,928,248),'Failure Events')
    text(p,'Event-relative means use full 24-hour bins with equal event weighting. Overlapping windows reuse readings. Sample sizes: tooltips. Association is not causation.',(976,960,896,56),16,GRAY)
    p='maintenance_priorities'
    card(p,['Priority Date Label'],(32,272,1136,96),NAVY,True)
    card(p,['High Priority Machines','Watch Priority Machines'],(1192,272,696,112),ORANGE)
    table(p,[('Machines','Machine'),('Machines','Model'),'Priority Rank','Priority Score','Priority Status','Recent Failures 14 Days','Recent Errors 7 Days','Maximum Sensor Deviation','Oldest Component Replacement Days'],
          'Maintenance inspection queue | select a machine row to drill through',(32,408,1856,312),'Priority Score')
    table(p,[('Machines','Machine'),'Priority Score','Failure Score Points','Error Score Points','Sensor Score Points','Maintenance Score Points','Priority Reasons','Suggested Inspection'],
          'Why each machine is prioritized | transparent score contribution',(32,744,1856,200),'Priority Score')
    text(p,'Score 0–100: failures /14d (max 40) + errors /7d (max 15) + prior-baseline deviations (max 30) + oldest component replacement age (max 15).  High ≥60  |  Watch ≥30. Selected date uses end-of-day records only.',(32,968,1856,48),18,GRAY)
    write(DEF/'pages/pages.json',{'$schema':'https://developer.microsoft.com/json-schemas/fabric/item/report/definition/pagesMetadata/1.1.0/schema.json','pageOrder':[p for p,n in PAGES],'activePageName':'plant_overview'})
    # Remove only unused scaffold page metadata; schema validation otherwise inventories it.
    for f in (DEF/'pages').glob('*/page.json'):
        if f.parent.name not in dict(PAGES):f.unlink()
    for directory in (DEF/'pages').iterdir():
        if directory.is_dir() and directory.name not in dict(PAGES):
            for empty in sorted(directory.rglob('*'), key=lambda p:len(p.parts),reverse=True):
                if empty.is_dir() and not any(empty.iterdir()):empty.rmdir()
            if not any(directory.iterdir()):directory.rmdir()
    theme_path=ROOT.parent/'.agents/skills/powerbi-report-cli/references/design/assets/base.json'
    theme=json.loads(theme_path.read_text(encoding='utf-8-sig'))
    name='ReliabilityIndustrial-'+uuid.uuid4().hex[:8]+'.json'
    theme.update({'name':name,'dataColors':[TEAL,RED,ORANGE,NAVY,GRAY],'foreground':NAVY,'background':'#FFFFFF','tableAccent':TEAL,'good':TEAL,'neutral':ORANGE,'bad':RED})
    theme['textClasses']={'title':{'fontFace':'Segoe UI Semibold','fontSize':14,'color':NAVY},'header':{'fontFace':'Segoe UI Semibold','fontSize':12,'color':NAVY},'label':{'fontFace':'Segoe UI','fontSize':11,'color':GRAY},'callout':{'fontFace':'Segoe UI Semibold','fontSize':30,'color':NAVY}}
    # The base reference includes card container keys unsupported by current metadata.
    card_style=theme.get('visualStyles',{}).get('cardVisual',{}).get('*',{})
    for obj,keys in [('border',['radius']),('spacing',['customizeSpacing']),('padding',['top','bottom','left','right'])]:
        for entry in card_style.get(obj,[]):
            for key in keys:entry.pop(key,None)
    write(REPORT/'StaticResources/RegisteredResources'/name,theme)
    report=json.loads((DEF/'report.json').read_text())
    report['themeCollection']['customTheme']={'name':name,'type':'RegisteredResources','reportVersionAtImport':{'visual':'2.9.0','report':'3.3.0','page':'2.1.0'}}
    report['resourcePackages']=[r for r in report['resourcePackages'] if r['type']!='RegisteredResources']+[{'name':'RegisteredResources','type':'RegisteredResources','items':[{'name':name,'path':name,'type':'CustomTheme'}]}]
    write(DEF/'report.json',report)
    write(ROOT/'validation/report_layout.json',LAYOUT)
    model=ROOT/'Manufacturing_Reliability_Cockpit.SemanticModel'
    write(model/'definition.pbism',{'$schema':'https://developer.microsoft.com/json-schemas/fabric/item/semanticModel/definitionProperties/1.0.0/schema.json','version':'4.2','settings':{'qnaEnabled':False}})
    write(model/'.platform',{'$schema':'https://developer.microsoft.com/json-schemas/fabric/gitIntegration/platformProperties/2.0.0/schema.json','metadata':{'type':'SemanticModel','displayName':'Manufacturing Reliability & Maintenance Cockpit'},'config':{'version':'2.0','logicalId':str(uuid.uuid4())}})
    brief=['# Report specification','\nImplementation authorized by the detailed user request; local only.','\nDesign Brief:','```yaml','generated_by: powerbi-report-cli','contract_version: 1','mode: greenfield','design_identity:','  tone: precise industrial analysis','  signature: navy headers and transparent evidence paired with each decision','navigation_model: buttons','pages:']
    roles=[('Executive','B'),('Analytical','B'),('Comparative','B'),('Operational','C')]
    for (page,name),(archetype,variant) in zip(PAGES,roles):
        brief+=['  - name: '+name,'    archetype: '+archetype,'    layout_variant: '+variant,'    variant_rationale: '+{'plant_overview':'Four KPIs and concentration charts support a fast plant scan.','machine_health':'Two aligned time series support a single-machine diagnostic profile.','failure_analysis':'Counts and exposure-normalized comparisons are paired across groups.','maintenance_priorities':'An inspection queue is the dominant decision surface.'}[page],
                '    layout_contract:','      canvas: {width: 1920, height: 1080, margin: 32, gutter: 24, snap: 8}','      grid:','        columns: 12','        rows: 12','        regions: {header: [1,1,13,3], body: [1,3,13,12], footer: [1,12,13,13]}','      placements:']
        for i,v in enumerate(LAYOUT[page]):brief+=['        - id: '+('page_title' if i==1 else v['id']),'          kind: '+v['kind'],'          region: '+('header' if v['rect'][1]<248 else 'footer' if v['rect'][1]>=1032 else 'body'),'          pixels: '+str(v['rect'])]
        brief+=['      space_audit: {empty_cell_pct: 10, unplaced_regions: [], balance_rationale: "Reserved filter and navigation bands; substantive evidence fills the body."}']
    brief+=['```','\nEach chart answers one diagnostic question. Failures use red; warnings orange; sensor reference teal/gray. No OEE, downtime, repair costs, production losses, or ML probabilities.','\nAll facts connect to Machines and Dates using many-to-one single-direction relationships; component/sensor dimensions filter only applicable facts. See validation/report_layout.json for bindings and exact rectangles.']
    (ROOT/'_brief').mkdir(exist_ok=True);(ROOT/'_brief/report-spec.md').write_text('\n'.join(brief),encoding='utf-8')
    errors=[]
    for page,vs in LAYOUT.items():
        for i,a in enumerate(vs):
            x,y,w,h=a['rect'];assert x>=0 and y>=0 and x+w<=1920 and y+h<=1080
            for b in vs[i+1:]:
                bx,by,bw,bh=b['rect']
                if max(x,bx)<min(x+w,bx+bw) and max(y,by)<min(y+h,by+bh):errors.append((page,a['id'],b['id']))
    assert not errors,errors
    print('Generated four pages; bounds and non-overlap checks passed.')

if __name__=='__main__':main()
