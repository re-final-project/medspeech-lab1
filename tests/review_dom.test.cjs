const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const {JSDOM}=require('jsdom');
const root=path.resolve(__dirname,'..');
const read=name=>JSON.parse(fs.readFileSync(path.join(__dirname,'fixtures',name),'utf8'));
const fixture=read('review_example.json'), comparison=read('transcription_comparison.json'), example=read('aqueduct_example.json');
const html=fs.readFileSync(path.join(root,'medspeech/web/index.html'),'utf8');
const scripts=['app.js','comparison.js','review.js'].map(n=>fs.readFileSync(path.join(root,'medspeech/web',n),'utf8'));
const tick=()=>new Promise(resolve=>setImmediate(resolve));
async function page(responder,session=fixture.session){
  const dom=new JSDOM(html,{url:'http://localhost/demo/aqueduct',runScripts:'outside-only'});
  const w=dom.window;w.structuredClone=structuredClone;
  const calls=[];
  w.fetch=async(url,options={})=>{
    if(url.includes('/review/reanalyse')){
      const body=JSON.parse(options.body);calls.push(body);
      const value=responder ? await responder(body,calls.length) : structuredClone(body.corrected_transcript.includes('안')?fixture.negative:fixture.positive);
      if(value instanceof Error)throw value;
      return {ok:true,json:async()=>structuredClone(value)};
    }
    const value=url.includes('/review')?session:url.includes('/compare')?comparison:example;
    return {ok:true,json:async()=>structuredClone(value)};
  };
  scripts.forEach(s=>w.eval(s));await tick();
  const id=name=>w.document.getElementById(name);
  const edit=text=>{id('review-editor').value=text;id('review-editor').dispatchEvent(new w.Event('input',{bubbles:true}));};
  return {dom,id,edit,calls};
}

test('initial text is copied; only corrected text is submitted; vomiting change is highlighted',async()=>{
  const {dom,id,calls}=await page();
  const original=id('review-initial').textContent, initialResult=id('review-initial-result').textContent;
  assert.equal(id('review-editor').value,original);
  assert.equal(id('review-source').textContent,'모의 전사문 · STT 미실행');
  id('review-fill').click();id('review-analyse').click();await tick();
  assert.match(id('review-transitions').textContent,/두통: 있음 → 있음/);
  assert.match(id('review-transitions').textContent,/구토: 있음 → 없음/);
  assert.equal(id('review-transitions').querySelectorAll('.changed').length,1);
  assert.equal(id('review-transitions').querySelector('.changed').dataset.symptom,'vomiting');
  assert.match(id('review-transitions').textContent,/초기 근거: 구토를 했어요/);
  assert.match(id('review-transitions').textContent,/수정 근거: 구토는 안 했어요/);
  assert.match(id('review-corrected-result').textContent,/예시 결과/);
  assert.equal(id('review-initial').textContent,original);
  assert.equal(id('review-initial-result').textContent,initialResult);
  assert.deepEqual(Object.keys(calls[0]).sort(),['analysis_mode','corrected_transcript','include_mri']);
  dom.window.close();
});

test('editing after analysis retains results marked previous-draft basis until reanalysed',async()=>{
  const {dom,id,edit}=await page();
  id('review-analyse').click();await tick();
  const previous=id('review-corrected-result').textContent;
  edit(fixture.negative.side.text);
  assert.match(id('review-result-basis').textContent,/이전 수정문 기준/);
  assert.equal(id('review-corrected-result').textContent,previous);
  assert.match(id('review-transitions').textContent,/구토: 있음 → 있음/);
  id('review-analyse').click();await tick();
  assert.match(id('review-result-basis').textContent,/현재 수정문 기준/);
  assert.match(id('review-transitions').textContent,/구토: 있음 → 없음/);
  dom.window.close();
});

test('blank or whitespace input disables reanalysis without replacing prior results',async()=>{
  const {dom,id,edit,calls}=await page();
  id('review-analyse').click();await tick();
  for(const value of ['','  ']){
    edit(value);assert.equal(id('review-analyse').disabled,true);
    assert.match(id('review-status').textContent,/빈 수정문/);
    assert.match(id('review-result-basis').textContent,/이전 수정문 기준/);
    id('review-analyse').click();await tick();
  }
  assert.equal(calls.length,1);
  dom.window.close();
});

test('real schema failure shows reanalysis failure, permits retry, and never fabricates examples',async()=>{
  const session=structuredClone(fixture.session);session.analysis_mode='model';session.initial.example_answer=null;
  const failure=structuredClone(fixture.negative);failure.status='failed';failure.message='재분석 실패 · schema_error · 재시도하세요.';
  failure.side.example_answer=null;failure.side.structure_status='schema_error';
  const success=structuredClone(fixture.negative);success.status='completed';success.message='수정문 재분석 완료';
  success.side.model_states=success.side.example_answer;success.side.example_answer=null;success.side.structure_status='completed';
  const {dom,id,calls}=await page((body,n)=>n===1?failure:success,session);
  const initial=id('review-initial').textContent;
  id('review-fill').click();id('review-analyse').click();await tick();
  assert.match(id('review-status').textContent,/재분석 실패/);
  assert.doesNotMatch(id('review-corrected-result').textContent,/예시 결과/);
  assert.equal(id('review-analyse').disabled,false);
  id('review-analyse').click();await tick();
  assert.equal(calls.length,2);assert.match(id('review-corrected-result').textContent,/실제 모델 결과/);
  assert.equal(id('review-initial').textContent,initial);
  dom.window.close();
});

test('typing during an in-flight analysis does not overwrite draft and marks returned result stale',async()=>{
  let release;const pending=new Promise(resolve=>{release=resolve;});
  const {dom,id,edit}=await page(()=>pending);
  id('review-fill').click();id('review-analyse').click();
  assert.equal(id('review-analyse').disabled,true);
  edit(fixture.positive.side.text);
  release(fixture.negative);await tick();
  assert.equal(id('review-editor').value,fixture.positive.side.text);
  assert.match(id('review-result-basis').textContent,/이전 수정문 기준/);
  dom.window.close();
});

test('review leaves MRI findings and normal/blocked controls independent; hidden MRI clears review JSON',async()=>{
  const {dom,id}=await page();const findings=id('imaging-findings').textContent;
  id('review-fill').click();id('review-analyse').click();await tick();
  assert.equal(id('imaging-findings').textContent,findings);
  id('normal-button').click();assert.equal(id('flow-diagram').dataset.state,'normal');
  id('blocked-button').click();assert.equal(id('flow-diagram').dataset.state,'blocked');
  id('mri-toggle').click();
  assert.equal(id('imaging-findings').textContent,'영상 정보 없음');
  const value=JSON.parse(id('review-json').textContent);
  assert.equal(value.initial_snapshot.imaging_findings,null);
  assert.equal(value.last_analysis.imaging_findings,null);
  id('mri-toggle').click();assert.equal(id('imaging-findings').textContent,findings);
  dom.window.close();
});
