// DOM unit tests execute the shipped HTML/JS. They do not control a browser.
const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const {JSDOM} = require('jsdom');
const root = path.resolve(__dirname, '..');
const example = JSON.parse(fs.readFileSync(path.join(__dirname, 'fixtures/aqueduct_example.json'), 'utf8'));
const html = fs.readFileSync(path.join(root, 'medspeech/web/index.html'), 'utf8');
const script = fs.readFileSync(path.join(root, 'medspeech/web/app.js'), 'utf8');
const tick = () => new Promise(resolve => setImmediate(resolve));

async function page(runResponse = example) {
  const dom = new JSDOM(html, {url:'http://localhost/demo/aqueduct', runScripts:'outside-only'});
  const w = dom.window;
  let saved = null;
  w.structuredClone = structuredClone;
  w.Blob = Blob;
  w.URL.createObjectURL = blob => {saved = blob; return 'blob:test-only';};
  w.URL.revokeObjectURL = () => {};
  w.HTMLAnchorElement.prototype.click = () => {};
  w.fetch = async url => {
    if (url.endsWith('/run') && runResponse instanceof Error) throw runResponse;
    return {ok:true, json:async () => structuredClone(url.endsWith('/run') ? runResponse : example)};
  };
  w.eval(script);
  await tick();
  return {dom, id:id => w.document.getElementById(id), saved:() => saved};
}

test('initial obstruction stops the downstream arrow and expands upstream nodes', async () => {
  const {dom,id} = await page();
  assert.equal(id('flow-diagram').dataset.state, 'blocked');
  assert.equal(id('blocked-button').getAttribute('aria-pressed'), 'true');
  assert.equal(id('obstruction-marker').hasAttribute('hidden'), false);
  assert.equal(id('downstream-flow').hasAttribute('hidden'), true);
  assert.equal(id('aqueduct-flow').getAttribute('d'), 'M628 180 H670');
  assert.equal(id('lateral-node').dataset.expanded, 'true');
  assert.equal(id('third-node').dataset.expanded, 'true');
  assert.match(id('execution-status').textContent, /예시 전사문 · 모델 미실행/);
  assert.equal(JSON.parse(id('structured-json').textContent).audio.symptoms.length, 2);
  assert.doesNotMatch(id('structured-json').textContent, /germinoma|생식세포종/);
  dom.window.close();
});

test('normal flow reaches fourth ventricle; switching back restores all obstruction signs', async () => {
  const {dom,id} = await page();
  id('normal-button').click();
  assert.equal(id('flow-diagram').dataset.state, 'normal');
  assert.equal(id('obstruction-marker').hasAttribute('hidden'), true);
  assert.equal(id('downstream-flow').hasAttribute('hidden'), false);
  assert.equal(id('aqueduct-flow').getAttribute('d'), 'M628 180 H732');
  assert.equal(id('lateral-node').dataset.expanded, 'false');
  assert.equal(id('third-node').dataset.expanded, 'false');
  assert.equal(id('third-shape').getAttribute('rx'), '28');
  assert.match(id('aqueduct-caption').textContent, /흐름 통과/);
  id('blocked-button').click();
  assert.equal(id('downstream-flow').hasAttribute('hidden'), true);
  assert.equal(id('third-shape').getAttribute('rx'), '46');
  assert.equal(id('obstruction-marker').hasAttribute('hidden'), false);
  dom.window.close();
});

test('hiding MRI removes raw text, findings, evidence and exported imaging, not scenario', async () => {
  const {dom,id,saved} = await page();
  assert.match(id('imaging-findings').textContent, /중뇌수도관/);
  id('mri-toggle').click();
  assert.equal(id('mri-toggle').getAttribute('aria-expanded'), 'false');
  assert.equal(id('mri-report').textContent, '');
  assert.equal(id('mri-empty').hidden, false);
  assert.equal(id('imaging-findings').textContent, '영상 정보 없음');
  assert.equal(JSON.parse(id('structured-json').textContent).imaging, null);
  assert.equal(id('flow-diagram').dataset.state, 'blocked');
  assert.match(id('scenario-diagnosis').textContent, /germinoma/);
  assert.match(id('symptoms').textContent, /구토/);
  id('download-case').click();
  const data = JSON.parse(await saved().text());
  assert.equal(data.case.stt_transcript, null);
  assert.equal(data.case.simulated_mri_report, null);
  assert.equal(data.imaging_findings, null);
  id('mri-toggle').click();
  assert.match(id('mri-report').textContent, /송과체 부위 종괴/);
  assert.match(id('imaging-findings').textContent, /제3뇌실/);
  dom.window.close();
});

test('schema failure preserves STT and shows failure rather than example/success', async () => {
  const failed = structuredClone(example);
  failed.case.stt_transcript = '실제 STT 테스트 출력';
  failed.audio_findings = null;
  failed.execution.stt = 'completed';
  failed.execution.structure = 'schema_error';
  failed.execution.message = '실제 STT 완료 · 구조화 실패 — JSON 스키마 오류';
  const {dom,id} = await page(failed);
  id('run-models').click(); await tick();
  assert.match(id('stt-transcript').textContent, /실제 STT 테스트 출력/);
  assert.match(id('execution-status').textContent, /구조화 실패/);
  assert.equal(id('execution-status').classList.contains('error'), true);
  assert.equal(JSON.parse(id('structured-json').textContent).audio, null);
  assert.match(id('symptoms').textContent, /성공으로 처리하지 않습니다/);
  assert.equal(id('run-models').disabled, false);
  id('reset-example').click(); await tick();
  assert.equal(id('stt-transcript').textContent, '미실행 · null');
  assert.match(id('symptom-method').textContent, /예시 주석/);
  dom.window.close();
});

test('model unavailable and network failure leave the demo usable', async () => {
  const missing = structuredClone(example);
  missing.audio_findings = null;
  missing.execution.stt = 'unavailable'; missing.execution.structure = 'not_run';
  missing.execution.message = '예시 전사문 · 모델 미실행 — 합성 음성을 먼저 생성하세요.';
  let view = await page(missing);
  view.id('run-models').click(); await tick();
  assert.match(view.id('execution-status').textContent, /모델 미실행/);
  assert.equal(view.id('stt-transcript').textContent, '미실행 · null');
  assert.equal(view.id('run-models').disabled, false);
  view.dom.window.close();
  view = await page(new Error('서버 연결 실패'));
  view.id('run-models').click(); await tick();
  assert.match(view.id('execution-status').textContent, /서버 연결 실패/);
  assert.equal(view.id('run-models').disabled, false);
  view.id('normal-button').click();
  assert.equal(view.id('flow-diagram').dataset.state, 'normal');
  view.dom.window.close();
});
