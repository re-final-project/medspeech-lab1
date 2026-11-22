"use strict";
(() => {
  const id = name => document.getElementById(name);
  let comparison = null;
  let busy = false;
  const showMRI = () => id("mri-toggle").getAttribute("aria-expanded") === "true";
  function visible() {
    const copy = structuredClone(comparison);
    if (!showMRI()) {
      copy.simulated_mri_report = null;
      copy.imaging_findings = null;
      copy.imaging_status = "no_information";
    }
    return copy;
  }
  function drawDifferences(value) {
    const left = id("comparison-reference"), right = id("comparison-transcript");
    left.replaceChildren(); right.replaceChildren();
    for (const part of value.differences) {
      for (const [node, text] of [[left, part.reference], [right, part.transcript]]) {
        if (part.kind === "equal") node.append(document.createTextNode(text));
        else {
          const mark = document.createElement(text ? "mark" : "span");
          mark.textContent = text || "∅";
          mark.dataset.kind = part.kind;
          if (!text) {mark.className = "diff-absent"; mark.setAttribute("aria-label", "해당 쪽에 문자가 없는 구간");}
          node.append(mark);
        }
      }
    }
    if (!value.transcript.text.trim()) right.textContent = "빈 전사문 · 평가 불가";
  }
  function states(container, values) {
    for (const [key, name] of [["headache", "두통"], ["vomiting", "구토"]]) {
      const row = document.createElement("div"); row.className = "mention-row";
      row.dataset.symptom = key;
      const title = document.createElement("span"); title.className = "mention-label"; title.textContent = name;
      const status = document.createElement("span"); status.className = "mention-state";
      status.classList.toggle("absent", values[key].status === "없음");
      status.classList.toggle("unmentioned", values[key].status === "언급 없음");
      status.textContent = values[key].status;
      const evidence = document.createElement("p"); evidence.className = "mention-evidence";
      evidence.textContent = values[key].evidence ? `근거: ${values[key].evidence}` : "근거 없음 · 해당 증상 언급 없음";
      row.append(title, status, evidence); container.append(row);
    }
  }
  function renderSide(container, side) {
    container.replaceChildren();
    const source = document.createElement("p"); source.className = "state-source";
    source.textContent = "예시 정답 · 한정 문자열 주석 · 모델 결과 아님"; container.append(source);
    if (side.example_answer) states(container, side.example_answer);
    else {const p = document.createElement("p"); p.className = "empty-state"; p.textContent = "빈 전사문 · 예시 정답도 평가하지 않습니다."; container.append(p);}
    const model = document.createElement("div"); model.className = "model-result";
    const label = document.createElement("p"); label.className = "model-state";
    const labels = {not_run:"구조화 모델 미실행", completed:"실제 LLM 결과 · 스키마/전사 근거 검증 통과", schema_error:"JSON 스키마 오류 · 모델 결과 없음", grounding_error:"전사 근거 오류 · 모델 결과 없음", content_error:"구조화 내용 오류 · 모델 결과 없음", failed:"구조화 실행 실패 · 모델 결과 없음", empty_transcript:"빈 전사문 · 구조화 미실행"};
    label.textContent = labels[side.structure_status] || "구조화 상태 확인 필요";
    label.classList.toggle("error", ["schema_error", "grounding_error", "content_error", "failed", "empty_transcript"].includes(side.structure_status));
    model.append(label);
    if (side.structure_status === "completed" && side.model_states) states(model, side.model_states);
    container.append(model);
  }
  function render() {
    if (!comparison) return;
    const value = visible();
    id("comparison-status").textContent = busy ? "비교 모델 실행 중 · 완료 전까지 결과 미확정" : value.label;
    id("comparison-status").classList.toggle("running", busy);
    id("comparison-status").classList.toggle("error", !busy && (!value.transcript.text.trim() || [value.reference.structure_status, value.transcript.structure_status].some(x => ["schema_error","grounding_error","content_error","failed"].includes(x))));
    id("comparison-transcript-source").textContent = ({simulated:"모의 전사문 · 실제 STT 출력 아님", actual_stt:"실제 STT 전사문", edited:"직접 수정한 전사문 · 실제 STT 출력 아님"})[value.source];
    drawDifferences(value);
    renderSide(id("comparison-reference-states"), value.reference);
    renderSide(id("comparison-transcript-states"), value.transcript);
    const left = value.reference.example_answer, right = value.transcript.example_answer;
    id("negation-summary").textContent = left && right ? `예시 정답 기준 · 구토: 원본 「${left.vomiting.status}」 / 전사문 「${right.vomiting.status}」${left.vomiting.status !== right.vomiting.status ? " — 언급 상태가 달라졌습니다." : " — 언급 상태가 같습니다."}` : "빈 전사문 · 증상 상태 비교 불가";
    id("comparison-json").textContent = JSON.stringify(value, null, 2);
    id("comparison-models").textContent = [value.stt_model && `STT: ${value.stt_model}`, value.llm_model && `LLM: ${value.llm_model}`, value.stored_result && "저장된 실행 결과이며 이 페이지 요청에서는 모델을 재실행하지 않았습니다."].filter(Boolean).join(" / ");
    for (const key of ["comparison-run", "comparison-apply", "comparison-simulated", "comparison-editor"]) id(key).disabled = busy;
  }
  async function request(url, body) {
    if (busy) return;
    busy = true;
    if (comparison) render();
    try {
      const result = await fetch(url, body === undefined ? {} : {method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify(body)});
      if (!result.ok) throw new Error(`비교 요청 실패 (HTTP ${result.status})`);
      comparison = await result.json();
      id("comparison-editor").value = comparison.transcript.text;
      busy = false; render();
    } catch (error) {
      busy = false; if (comparison) render();
      id("comparison-status").textContent = `${error.message} · 모델 성공으로 처리하지 않습니다.`;
      id("comparison-status").classList.add("error");
    }
  }
  id("comparison-run").addEventListener("click", () => request("/demo/api/compare/run", {include_mri:true}));
  id("comparison-apply").addEventListener("click", () => request("/demo/api/compare", {transcript:id("comparison-editor").value, include_mri:true}));
  id("comparison-simulated").addEventListener("click", () => request("/demo/api/compare?source=simulated"));
  // Source MRI data is independent of transcript editing. Hide both its text
  // and findings in the comparison view/JSON when the shared toggle is off.
  id("mri-toggle").addEventListener("click", render);
  request("/demo/api/compare");
})();
