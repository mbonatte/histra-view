import { test } from 'node:test';
import assert from 'node:assert/strict';
import { AnalysesPage } from '../static/analyses.js';

test('stage pill displays the selected scour extent and requested value', () => {
  const oldDocument = globalThis.document;
  globalThis.document = { createElement: tag => ({ tagName: tag, textContent: '', title: '' }), getElementById: () => null };
  try {
    const page = new AnalysesPage();
    const [pill] = page.buildStagePills([{ key: 28, name: 'scour_4', status: 'completed', scourExtent: {
      ratio: 619 / 1100, requestedRatio: .55, widthCm: 619, foundationWidthCm: 1100, interfaceCount: 48,
    }}]);
    assert.match(pill.textContent, /selected extent 56\.27%/);
    assert.match(pill.title, /Requested 55\.00%/);
  } finally { globalThis.document = oldDocument; }
});

test('sends the λ target only for its selected analysis', async () => {
  const oldDocument = globalThis.document, oldFetch = globalThis.fetch;
  globalThis.document = { getElementById: () => null };
  const requests = [];
  globalThis.fetch = async (_url, options) => {
    requests.push(JSON.parse(options.body));
    return { ok: true, json: async () => ({ status: 'completed', logs: [] }) };
  };
  try {
    const page = new AnalysesPage();
    page.render = () => {}; page.schedulePoll = () => {};
    page.arcLambdaTarget = { analysisKey: '23', enabled: true, value: '0' };
    await page.runAnalysis({ key: '23', name: 'scour_1' });
    await page.runAnalysis({ key: '24', name: 'scour_2' });
    assert.equal(requests[0].arcLambdaTarget, 0);
    assert.equal(requests[1].arcLambdaTarget, null);
  } finally { globalThis.document = oldDocument; globalThis.fetch = oldFetch; }
});

test('sends total scour ratios and ordered stages with a modal run', async () => {
  const previousDocument = globalThis.document, previousFetch = globalThis.fetch;
  globalThis.document = { getElementById: () => null };
  let request;
  globalThis.fetch = async (_url, options) => {
    request = JSON.parse(options.body);
    return {ok:true, json:async()=>({status:'completed', logs:[]})};
  };
  try {
    const page = new AnalysesPage(null, {getSource:()=>({source:'abc',modelName:'bridge.hrx'})});
    page.render=()=>{}; page.schedulePoll=()=>{};
    page.analyses=[{key:'1',name:'Vert'},{key:'23',name:'scour_1'},{key:'24',name:'scour_2'},{key:'40',name:'Modal_2'}];
    page.scourWorkflow={enabled:true,pier:'1',intactMaterial:'146',scouredMaterial:'147',direction:'-Y',ratios:{23:'20',24:'40'}};
    await page.runAnalysis(page.analyses[3]);
    assert.deepEqual(request.scourWorkflow,{pier:1,intactMaterial:146,scouredMaterial:147,direction:'-Y',stages:[{analysisKey:23,ratio:.2},{analysisKey:24,ratio:.4}],skipEquilibriumAudit:false});
  } finally { globalThis.document=previousDocument; globalThis.fetch=previousFetch; }
});

test('uses all masonry material names, including unassigned materials', async () => {
  const { masonryMaterialOptions } = await import('../static/analyses.js');
  const model={materialLibrary:[
    {key:'18',name:'Pier masonry',attributes:{PurposeType:'MasonryMaterial'}},
    {key:'146',name:'Intact soil',attributes:{PurposeType:'MasonryMaterial'},quadCount:0},
    {key:'147',name:'Scoured soil',attributes:{TypeOf:'HiStrA.Objects.MasonryMaterial'},quadCount:0},
    {key:'60',name:'Other',attributes:{PurposeType:'GeotecnicalMaterial'}},
  ]};
  assert.deepEqual(masonryMaterialOptions(model),[
    {value:'18',label:'Pier masonry'}, {value:'146',label:'Intact soil'}, {value:'147',label:'Scoured soil'}
  ]);
});

test('scour and modal analyses use only their required earlier scour stages', async () => {
  const { scourStagesForAnalysis } = await import('../static/analyses.js');
  const analyses=[{key:'23',name:'scour_1'},{key:'24',name:'scour_2'},{key:'26',name:'scour_3'},{key:'28',name:'scour_4'},
    {key:'31',name:'Modal_1',analysisType:'5'},{key:'40',name:'Modal_4',analysisType:'5'}];
  assert.deepEqual(scourStagesForAnalysis(analyses,analyses[0]).map(a=>a.name),['scour_1']);
  assert.deepEqual(scourStagesForAnalysis(analyses,analyses[1]).map(a=>a.name),['scour_1','scour_2']);
  assert.deepEqual(scourStagesForAnalysis(analyses,analyses[4]).map(a=>a.name),['scour_1']);
  assert.deepEqual(scourStagesForAnalysis(analyses,analyses[5]).map(a=>a.name),['scour_1','scour_2','scour_3','scour_4']);
});

test('scour analysis displays its own editable ratio and named material selectors', () => {
  const oldDocument=globalThis.document, oldOption=globalThis.Option;
  class Element {
    constructor(tag){this.tagName=tag;this.children=[];this.style={};this.classList={add(){},remove(){}};this.value='';this.textContent='';}
    append(...nodes){this.children.push(...nodes);} prepend(...nodes){this.children.unshift(...nodes);}
    add(option){this.children.push(option);} addEventListener(){} setAttribute(){}
  }
  globalThis.document={createElement:tag=>new Element(tag),getElementById:()=>null};
  globalThis.Option=class {constructor(label,value){this.label=label;this.value=value;}};
  try {
    const page=new AnalysesPage();
    page.analyses=[{key:'23',name:'scour_1',analysisType:'2'},{key:'24',name:'scour_2',analysisType:'2'}];
    page.scourMaterials=[{value:'146',label:'Intact soil'},{value:'147',label:'Scoured soil'}];
    page.scourWorkflow.enabled=true;
    const panel=page.renderSolverPanel(page.analyses[0]);
    const scour=panel.children.find(c=>c.tagName==='details' && c.children[0]?.textContent==='Staged foundation scour');
    const labels=scour.children.filter(c=>c.tagName==='label');
    assert.equal(labels.filter(l=>l.textContent.includes('Total scour')).length,1);
    assert.ok(!labels.some(l=>/scour_2/i.test(l.textContent)));
    assert.deepEqual(labels.filter(l=>l.textContent.endsWith('soil material')).map(l=>l.children[0].tagName),['select','select']);
    assert.ok(labels.find(l=>l.textContent==='Intact soil material').children[0].children.some(o=>o.label==='Intact soil'));
  } finally {globalThis.document=oldDocument;globalThis.Option=oldOption;}
});

test('running an earlier modal ignores ratios configured for later stages', async () => {
  const oldDocument=globalThis.document, oldFetch=globalThis.fetch;
  globalThis.document={getElementById:()=>null};
  let request;
  globalThis.fetch=async (_url,options)=>{request=JSON.parse(options.body);return {ok:true,json:async()=>({status:'completed',logs:[]})};};
  try {
    const page=new AnalysesPage(null,{getSource:()=>({source:'test',modelName:'bridge'})});
    page.render=()=>{};page.schedulePoll=()=>{};
    page.analyses=[{key:'23',name:'scour_1'},{key:'24',name:'scour_2'},{key:'31',name:'Modal_1',analysisType:'5'}];
    page.scourWorkflow={enabled:true,pier:'1',intactMaterial:'146',scouredMaterial:'147',direction:'-Y',ratios:{23:'20',24:'40'}};
    await page.runAnalysis(page.analyses[2]);
    assert.deepEqual(request.scourWorkflow.stages,[{analysisKey:23,ratio:.2}]);
  } finally {globalThis.document=oldDocument;globalThis.fetch=oldFetch;}
});

test('stop requests a graceful stop and keeps polling the active job', async () => {
  const oldDocument = globalThis.document, oldFetch = globalThis.fetch;
  globalThis.document = { getElementById: () => null };
  let request;
  globalThis.fetch = async (url, options) => {
    request = { url, body: JSON.parse(options.body) };
    return { ok: true, json: async () => ({ status: 'running', stopRequested: true }) };
  };
  try {
    const page = new AnalysesPage();
    page.solverJob = { jobId: 'abc', status: 'running' };
    page.render = () => {};
    await page.stopRun();
    assert.deepEqual(request, { url: '/api/solver/stop', body: { jobId: 'abc' } });
    assert.equal(page.solverJob.status, 'running');
    assert.equal(page.solverJob.stopRequested, true);
  } finally { globalThis.document = oldDocument; globalThis.fetch = oldFetch; }
});
