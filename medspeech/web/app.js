"use strict";
(() => {
  const byId = id => document.getElementById(id);
  let response = null;
  let includeMRI = true;
  let busy = false;
  let flow = "blocked";
  const visibleCase = () => {
    const value = structuredClone(response);
    if (!includeMRI) {
      value.case.simulated_mri_report = null;
      value.imaging_findings = null;
      value.imaging_status = "no_information";
    }
    return value;
  };
  function setFlow(next) {
    flow = next;
    const blocked = next === "blocked";
    byId("flow-diagram").dataset.state = next;
    for (const id of ["normal-button", "blocked-button"]) {
      const selected = id === `${next}-button`;
      byId(id).classList.toggle("selected", selected);
      byId(id).setAttribute("aria-pressed", String(selected));
    }
    for (const id of ["lateral-node", "third-node"]) byId(id).dataset.expanded = String(blocked);
    for (const id of ["lateral-left", "lateral-right", "third-shape"]) {
      const shape = byId(id);
      shape.classList.toggle("expanded", blocked);
      shape.setAttribute("rx", blocked ? (id === "third-shape" ? "46" : "42") : "28");
      shape.setAttribute("ry", blocked ? "62" : "42");
    }
    byId("obstruction-marker").toggleAttribute("hidden", !blocked);
    byId("downstream-flow").toggleAttribute("hidden", blocked);
    byId("aqueduct-flow").setAttribute("d", blocked ? "M628 180 H670" : "M628 180 H732");
    byId("fourth-shape").classList.toggle("downstream", blocked);
    for (const id of ["lateral-caption", "third-caption"]) byId(id).textContent = blocked ? "상류 확장" : "기준 크기 (개념)";
    byId("aqueduct-caption").textContent = blocked ? "흐름 중단" : "흐름 통과";
    byId("flow-tag").classList.toggle("blocked", blocked);
    byId("flow-tag").textContent = blocked ? "수도관 폐쇄" : "정상 흐름";
    byId("flow-title").textContent = blocked ? "좁은 통로에서 흐름이 멈춥니다." : "연결된 통로를 따라 흐릅니다.";
    byId("flow-description").textContent = blocked ? "종괴의 압박 지점에서 흐름을 중단하고, 상류인 측뇌실과 제3뇌실의 확장을 강조했습니다." : "측뇌실, 제3뇌실, 중뇌수도관, 제4뇌실 순서로 흐름을 연결합니다. 종괴·폐쇄·상류 확장 표시는 제거됩니다.";
    byId("svg-title").textContent = blocked ? "수도관 폐쇄 개념도" : "정상 뇌척수액 흐름 개념도";
    byId("svg-desc").textContent = blocked ? "종괴가 중뇌수도관을 압박하고 상류 뇌실이 확장된 시나리오. 화살표는 압박 지점에서 멈춥니다." : "측뇌실에서 제3뇌실, 중뇌수도관을 지나 제4뇌실로 이어집니다. 폐쇄와 확장 표시가 없습니다.";
  }
  function finding(container, item, label) {
    const row = document.createElement("div");
    row.className = "finding";
    if (label) {
      const name = document.createElement("span"); name.className = "finding-label"; name.textContent = label; row.append(name);
    }
    const value = document.createElement("strong"); value.textContent = item.value;
    const evidence = document.createElement("p"); evidence.className = "evidence"; evidence.textContent = `근거: ${item.evidence}`;
    row.append(value, evidence); container.append(row);
  }
  function empty(container, message) {
    const p = document.createElement("p"); p.className = "empty-state"; p.textContent = message; container.append(p);
  }
  function render() {
    if (!response) return;
    const value = visibleCase();
    const state = value.execution;
    byId("scenario-diagnosis").textContent = value.case.scenario_diagnosis;
    byId("reference-transcript").textContent = value.case.reference_transcript;
    byId("stt-transcript").textContent = value.case.stt_transcript === null ? "미실행 · null" : value.case.stt_transcript;
    byId("execution-status").textContent = busy ? "실제 모델 실행 중 · 완료 전까지 결과를 확정하지 않습니다." : state.message;
    byId("execution-status").classList.toggle("running", busy);
    byId("execution-status").classList.toggle("error", !busy && (state.stt === "failed" || ["schema_error", "grounding_error", "content_error", "failed"].includes(state.structure)));
    byId("mri-toggle").textContent = includeMRI ? "가상 MRI 판독문 숨기기" : "가상 MRI 판독문 표시하기";
    byId("mri-toggle").setAttribute("aria-expanded", String(includeMRI));
    byId("mri-report").textContent = value.case.simulated_mri_report || "";
    byId("mri-report").hidden = !includeMRI;
    byId("mri-empty").hidden = includeMRI;
    const symptoms = byId("symptoms"); symptoms.replaceChildren();
    byId("symptom-method").textContent = state.structure === "example_annotation" ? "예시 주석 · 모델 미실행" : state.structure === "completed" ? "실제 LLM 출력 · 전사문 근거 검증 통과" : `모델 결과 없음 · ${state.structure}`;
    if (value.audio_findings) {
      value.audio_findings.symptoms.forEach(item => finding(symptoms, item));
      if (!value.audio_findings.symptoms.length) empty(symptoms, "추출된 증상 없음");
    } else empty(symptoms, state.structure === "schema_error" ? "JSON 스키마 오류 · 구조화 성공으로 처리하지 않습니다." : "유효한 음성 구조화 결과 없음");
    const imaging = byId("imaging-findings"); imaging.replaceChildren();
    byId("imaging-method").textContent = includeMRI ? value.imaging_method : "영상 정보 없음";
    if (value.imaging_findings) {
      if (value.imaging_findings.obstruction_site) finding(imaging, value.imaging_findings.obstruction_site, "폐쇄 관련 위치 · 판독문은 '압박'을 기술");
      value.imaging_findings.enlarged_ventricles.forEach(item => finding(imaging, item, "확장된 뇌실"));
    } else empty(imaging, "영상 정보 없음");
    byId("structured-json").textContent = JSON.stringify({audio: value.audio_findings, imaging: value.imaging_findings}, null, 2);
    byId("run-models").disabled = busy;
    byId("run-models").textContent = busy ? "실제 모델 실행 중…" : "합성 음성으로 STT·LLM 실행";
    byId("reset-example").disabled = busy;
    const modelDetails = [];
    if (state.stt_model) modelDetails.push(`STT: ${state.stt_model}`);
    if (state.llm_model) modelDetails.push(`LLM: ${state.llm_model}`);
    if (state.stt_seconds !== null) modelDetails.push(`전사 ${state.stt_seconds.toFixed(2)}초 · RTF ${state.rtf.toFixed(3)}`);
    if (state.structure_seconds !== null) modelDetails.push(`구조화 ${state.structure_seconds.toFixed(2)}초`);
    byId("model-detail").textContent = modelDetails.join(" / ");
    byId("case-audio").hidden = !value.audio_available;
    if (value.audio_available && !byId("case-audio").getAttribute("src")) byId("case-audio").src = "/demo/audio";
    byId("audio-note").textContent = value.audio_available ? "MMS TTS 합성 음성 · 실환자 녹취 아님" : "합성 음성 미생성 · 예시 전사문으로 확인할 수 있습니다.";
  }
  async function loadExample() {
    const result = await fetch("/demo/api/case");
    if (!result.ok) throw new Error("가상 사례를 불러오지 못했습니다.");
    response = await result.json(); render();
  }
  byId("normal-button").addEventListener("click", () => setFlow("normal"));
  byId("blocked-button").addEventListener("click", () => setFlow("blocked"));
  byId("mri-toggle").addEventListener("click", () => { includeMRI = !includeMRI; render(); });
  byId("reset-example").addEventListener("click", () => loadExample().catch(showError));
  function showError(error) {
    byId("execution-status").textContent = error.message;
    byId("execution-status").classList.add("error");
  }
  byId("run-models").addEventListener("click", async () => {
    busy = true; render();
    try {
      // Always return both source fields; visibility remains a separate UI choice.
      const result = await fetch("/demo/api/run", {method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify({include_mri:true})});
      if (!result.ok) throw new Error(`모델 요청 실패 (HTTP ${result.status}) · 예시 전사를 모델 출력으로 사용하지 않습니다.`);
      response = await result.json();
    } catch (error) {
      busy = false; render(); showError(error); return;
    }
    busy = false; render();
  });
  byId("download-case").addEventListener("click", () => {
    if (!response) return;
    const value = visibleCase();
    const blob = new Blob([JSON.stringify({...value, scenario_view:flow}, null, 2)], {type:"application/json"});
    const url = URL.createObjectURL(blob); const link = document.createElement("a");
    link.href = url; link.download = "aqueduct-fictional-case.json"; link.click(); URL.revokeObjectURL(url);
  });
  setFlow("blocked");
  loadExample().catch(showError);
})();
