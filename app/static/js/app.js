// Microsoft Presidio Web UI Client Application
document.addEventListener("DOMContentLoaded", () => {
  initTheme();
  initTabs();
  initAnalyzer();
  initAnonymizer();
  initImageRedactor();
  initStructured();
  initTestDataHub();
});

// --- Swiss Technical Theme Switching ---
function initTheme() {
  const toggleBtn = document.getElementById("theme-toggle-btn");
  const themeLabel = document.getElementById("theme-label");
  if (!toggleBtn) return;

  const currentTheme = localStorage.getItem("presidio_theme") || "dark";
  document.documentElement.setAttribute("data-theme", currentTheme);
  themeLabel.textContent = `MODE: ${currentTheme.toUpperCase()}`;

  toggleBtn.addEventListener("click", () => {
    const isDark = document.documentElement.getAttribute("data-theme") === "dark";
    const nextTheme = isDark ? "light" : "dark";
    document.documentElement.setAttribute("data-theme", nextTheme);
    localStorage.setItem("presidio_theme", nextTheme);
    themeLabel.textContent = `MODE: ${nextTheme.toUpperCase()}`;
  });
}


// --- Tab Switching ---
function initTabs() {
  const tabs = document.querySelectorAll(".tab-btn");
  const panels = document.querySelectorAll(".tab-panel");

  tabs.forEach(tab => {
    tab.addEventListener("click", () => {
      tabs.forEach(t => t.classList.remove("active"));
      panels.forEach(p => p.classList.remove("active"));

      tab.classList.add("active");
      const targetId = tab.getAttribute("data-tab");
      document.getElementById(targetId).classList.add("active");
    });
  });
}

// --- 1. Presidio Analyzer ---
function initAnalyzer() {
  const input = document.getElementById("analyzer-input");
  const btn = document.getElementById("analyzer-submit-btn");
  const spinner = document.getElementById("analyzer-spinner");
  const resultText = document.getElementById("analyzer-highlighted-text");
  const jsonViewer = document.getElementById("analyzer-json-viewer");
  const entityCount = document.getElementById("analyzer-entity-count");

  // Load sample texts
  document.querySelectorAll(".analyzer-sample-btn").forEach(btn => {
    btn.addEventListener("click", async () => {
      const scenario = btn.getAttribute("data-scenario");
      try {
        const res = await fetch(`/api/test-data/text/${scenario}`);
        const data = await res.json();
        input.value = data.text;
      } catch (e) {
        console.error("Failed to load sample text", e);
      }
    });
  });

  btn.addEventListener("click", async () => {
    const text = input.value.trim();
    if (!text) {
      alert("분석할 텍스트를 입력해주세요.");
      return;
    }

    spinner.style.display = "inline-block";
    btn.disabled = true;

    try {
      const res = await fetch("/api/analyze", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          text: text,
          language: "ko",
          score_threshold: 0.35,
        }),
      });
      const data = await res.json();

      entityCount.textContent = `${data.total_entities}개 탐지됨`;
      jsonViewer.textContent = JSON.stringify(data.entities, null, 2);

      // Render highlighted text
      let highlighted = "";
      let lastIdx = 0;
      const sortedEntities = [...data.entities].sort((a, b) => a.start - b.start);

      sortedEntities.forEach(ent => {
        if (ent.start >= lastIdx) {
          highlighted += escapeHtml(text.substring(lastIdx, ent.start));
          highlighted += `<mark class="pii-highlight" data-entity="${ent.entity_type} (${Math.round(ent.score * 100)}%)">${escapeHtml(text.substring(ent.start, ent.end))}</mark>`;
          lastIdx = ent.end;
        }
      });
      highlighted += escapeHtml(text.substring(lastIdx));
      resultText.innerHTML = highlighted || "탐지된 개인정보가 없습니다.";

    } catch (e) {
      alert("분석 중 오류 발생: " + e.message);
    } finally {
      spinner.style.display = "none";
      btn.disabled = false;
    }
  });
}

// --- 2. Presidio Anonymizer & Deanonymizer ---
let currentDeanonymizePayload = null;

function initAnonymizer() {
  const input = document.getElementById("anon-input");
  const anonBtn = document.getElementById("anon-submit-btn");
  const anonSpinner = document.getElementById("anon-spinner");
  const anonOutput = document.getElementById("anon-output-text");
  const anonItemsTbody = document.getElementById("anon-items-tbody");

  const deanonBtn = document.getElementById("deanon-submit-btn");
  const deanonSpinner = document.getElementById("deanon-spinner");
  const deanonOutput = document.getElementById("deanon-output-text");
  const deanonKeyInput = document.getElementById("deanon-key-input");
  const deanonCard = document.getElementById("deanon-card");

  // Sample load
  document.querySelectorAll(".anon-sample-btn").forEach(btn => {
    btn.addEventListener("click", async () => {
      const scenario = btn.getAttribute("data-scenario");
      try {
        const res = await fetch(`/api/test-data/text/${scenario}`);
        const data = await res.json();
        input.value = data.text;
      } catch (e) {
        console.error(e);
      }
    });
  });

  anonBtn.addEventListener("click", async () => {
    const text = input.value.trim();
    if (!text) {
      alert("비식별화할 텍스트를 입력해주세요.");
      return;
    }

    const rrnOp = document.getElementById("op-rrn").value;
    const phoneOp = document.getElementById("op-phone").value;
    const emailOp = document.getElementById("op-email").value;
    const personOp = document.getElementById("op-person").value;
    const aesKey = document.getElementById("anon-aes-key").value.trim() || "1234567890123456";

    const operators = {
      KR_RRN: getOperatorConfig(rrnOp, aesKey, { chars_to_mask: 7, from_end: true, new_value: "<주민번호_삭제>" }),
      KR_PHONE_NUMBER: getOperatorConfig(phoneOp, aesKey, { chars_to_mask: 4, from_end: true, new_value: "<연락처_삭제>" }),
      EMAIL_ADDRESS: getOperatorConfig(emailOp, aesKey, { chars_to_mask: 5, from_end: false, new_value: "<이메일_삭제>" }),
      PERSON: getOperatorConfig(personOp, aesKey, { chars_to_mask: 1, from_end: true, new_value: "<고객명_삭제>" }),
    };

    anonSpinner.style.display = "inline-block";
    anonBtn.disabled = true;

    try {
      const res = await fetch("/api/anonymize", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          text: text,
          language: "ko",
          operators: operators,
          score_threshold: 0.35,
        }),
      });
      const data = await res.json();

      anonOutput.textContent = data.anonymized_text;
      currentDeanonymizePayload = data.deanonymize_payload;

      // Populate Items Table
      anonItemsTbody.innerHTML = "";
      data.items.forEach(it => {
        const tr = document.createElement("tr");
        tr.innerHTML = `
          <td><span class="badge badge-primary">${it.entity_type}</span></td>
          <td><span class="badge badge-cyan">${it.operator}</span></td>
          <td style="color: #f87171;">${escapeHtml(it.original_text)}</td>
          <td style="color: #34d399;">${escapeHtml(it.anonymized_text)}</td>
        `;
        anonItemsTbody.appendChild(tr);
      });

      // Show Deanonymize Section if reversible
      if (data.is_reversible && data.deanonymize_payload) {
        deanonCard.style.display = "flex";
        deanonKeyInput.value = data.deanonymize_payload.encryption_key_used || aesKey;
        deanonOutput.textContent = "아래 '복원 실행 (Deanonymize)' 버튼을 누르면 원문이 복원됩니다.";
      } else {
        deanonCard.style.display = "none";
      }

    } catch (e) {
      alert("비식별화 실패: " + e.message);
    } finally {
      anonSpinner.style.display = "none";
      anonBtn.disabled = false;
    }
  });

  deanonBtn.addEventListener("click", async () => {
    if (!currentDeanonymizePayload || !currentDeanonymizePayload.items.length) {
      alert("복원할 암호화 데이터(deanonymize_payload)가 없습니다.");
      return;
    }

    const key = deanonKeyInput.value.trim();
    if (!key) {
      alert("복호화에 필요한 대칭키(AES Key)를 입력해주세요.");
      return;
    }

    deanonSpinner.style.display = "inline-block";
    deanonBtn.disabled = true;

    try {
      const res = await fetch("/api/deanonymize", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          text: currentDeanonymizePayload.text,
          items: currentDeanonymizePayload.items,
          encryption_key: key,
        }),
      });
      const data = await res.json();

      deanonOutput.textContent = data.restored_text;
    } catch (e) {
      alert("복원 실패: " + e.message);
    } finally {
      deanonSpinner.style.display = "none";
      deanonBtn.disabled = false;
    }
  });
}

function getOperatorConfig(type, aesKey, defaults) {
  if (type === "encrypt") {
    return { operator: "encrypt", params: { key: aesKey } };
  } else if (type === "mask") {
    return { operator: "mask", params: { masking_char: "*", chars_to_mask: defaults.chars_to_mask, from_end: defaults.from_end } };
  } else if (type === "hash") {
    return { operator: "hash", params: { hash_type: "sha256", salt: "privacy_salt" } };
  } else if (type === "redact") {
    return { operator: "redact", params: {} };
  } else {
    return { operator: "replace", params: { new_value: defaults.new_value } };
  }
}

// --- 3. Presidio Image Redactor ---
function initImageRedactor() {
  const fileInput = document.getElementById("image-file-input");
  const loadSampleImgBtn = document.getElementById("load-sample-image-btn");
  const loadSampleDcmBtn = document.getElementById("load-sample-dicom-btn");
  const redactBtn = document.getElementById("image-redact-submit-btn");
  const spinner = document.getElementById("image-spinner");
  const origPreview = document.getElementById("orig-image-preview");
  const redactedPreview = document.getElementById("redacted-image-preview");
  const bboxesViewer = document.getElementById("image-bboxes-viewer");
  const dicomMetaCard = document.getElementById("dicom-meta-card");
  const dicomTagsList = document.getElementById("dicom-tags-list");
  const dicomDownloadBtn = document.getElementById("dicom-download-btn");

  let currentImageDataUri = null;
  let currentDicomFile = null;
  let currentDicomDownloadUrl = null;

  // File upload handler
  fileInput.addEventListener("change", (e) => {
    const file = e.target.files[0];
    if (!file) return;

    if (file.name.toLowerCase().endsWith(".dcm")) {
      currentDicomFile = file;
      currentImageDataUri = null;
      origPreview.src = "";
      origPreview.alt = `DICOM 파일 선택됨: ${file.name}`;
      redactedPreview.src = "";
      dicomMetaCard.style.display = "none";
    } else {
      currentDicomFile = null;
      const reader = new FileReader();
      reader.onload = (evt) => {
        currentImageDataUri = evt.target.result;
        origPreview.src = currentImageDataUri;
        redactedPreview.src = "";
        dicomMetaCard.style.display = "none";
      };
      reader.readAsDataURL(file);
    }
  });

  // Load sample image
  loadSampleImgBtn.addEventListener("click", async () => {
    try {
      const res = await fetch("/api/test-data/image");
      const data = await res.json();
      currentImageDataUri = data.image_base64;
      currentDicomFile = null;
      origPreview.src = currentImageDataUri;
      redactedPreview.src = "";
      dicomMetaCard.style.display = "none";
    } catch (e) {
      alert("샘플 이미지 로드 실패: " + e.message);
    }
  });

  // Load sample DICOM
  loadSampleDcmBtn.addEventListener("click", async () => {
    try {
      const res = await fetch("/api/test-data/dicom");
      const blob = await res.blob();
      currentDicomFile = new File([blob], "sample_medical_scan.dcm", { type: "application/dicom" });
      currentImageDataUri = null;
      origPreview.src = "";
      origPreview.alt = "의료용 샘플 DICOM (sample_medical_scan.dcm) 로드 완료. 아래 마스킹 버튼을 누르세요.";
      redactedPreview.src = "";
      dicomMetaCard.style.display = "none";
      alert("합성 의료 DICOM 파일이 로드되었습니다. '이미지 마스킹 실행' 버튼을 누르세요.");
    } catch (e) {
      alert("샘플 DICOM 로드 실패: " + e.message);
    }
  });

  // Execute Redaction
  redactBtn.addEventListener("click", async () => {
    if (!currentImageDataUri && !currentDicomFile) {
      alert("먼저 이미지를 업로드하거나 샘플을 로드해주세요.");
      return;
    }

    const redactionType = document.querySelector('input[name="redaction_style"]:checked').value;
    spinner.style.display = "inline-block";
    redactBtn.disabled = true;

    try {
      if (currentDicomFile) {
        // Redact DICOM
        const formData = new FormData();
        formData.append("file", currentDicomFile);
        formData.append("redaction_type", redactionType);
        formData.append("blur_radius", "15");
        formData.append("redact_metadata", "true");

        const res = await fetch("/api/image/redact-dicom", {
          method: "POST",
          body: formData,
        });
        const data = await res.json();

        origPreview.src = data.preview_original_base64;
        redactedPreview.src = data.preview_redacted_base64;
        bboxesViewer.textContent = JSON.stringify(data.pixel_bboxes, null, 2);

        // Show DICOM metadata info
        dicomMetaCard.style.display = "flex";
        dicomTagsList.innerHTML = data.redacted_tags.map(t => `<span class="badge badge-emerald">${t}</span>`).join(" ");
        currentDicomDownloadUrl = data.download_url;
      } else {
        // Redact standard image
        const res = await fetch("/api/image/redact", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            image_base64: currentImageDataUri,
            redaction_type: redactionType,
            fill_color: [0, 0, 0],
            blur_radius: 15,
            language: "kor+eng",
          }),
        });
        const data = await res.json();

        redactedPreview.src = data.redacted_image_base64;
        bboxesViewer.textContent = JSON.stringify(data.bboxes, null, 2);
        dicomMetaCard.style.display = "none";
      }
    } catch (e) {
      alert("이미지 마스킹 실패: " + e.message);
    } finally {
      spinner.style.display = "none";
      redactBtn.disabled = false;
    }
  });

  dicomDownloadBtn.addEventListener("click", () => {
    if (currentDicomDownloadUrl) {
      window.location.href = currentDicomDownloadUrl;
    }
  });
}

// --- 4. Presidio Structured ---
let currentTableRecords = [];
let currentAnonymizedRecords = [];

function initStructured() {
  const loadSampleBtn = document.getElementById("struct-load-sample-btn");
  const analyzeBtn = document.getElementById("struct-analyze-btn");
  const anonymizeBtn = document.getElementById("struct-anonymize-btn");
  const deanonBtn = document.getElementById("struct-deanon-btn");
  const downloadCsvBtn = document.getElementById("struct-download-csv-btn");
  const spinner = document.getElementById("struct-spinner");

  const tableHead = document.getElementById("struct-table-head");
  const tableBody = document.getElementById("struct-table-body");
  const colRulesContainer = document.getElementById("struct-col-rules");

  loadSampleBtn.addEventListener("click", async () => {
    try {
      const res = await fetch("/api/test-data/structured");
      const data = await res.json();
      currentTableRecords = data.records;
      renderTable(currentTableRecords);
      colRulesContainer.innerHTML = '<span style="color: var(--text-dim);">먼저 [컬럼 PII 정밀 분석] 버튼을 눌러 컬럼별 개인정보 유형을 판별해주세요.</span>';
    } catch (e) {
      alert("샘플 로드 실패: " + e.message);
    }
  });

  // Step 1: Analyze Columns
  analyzeBtn.addEventListener("click", async () => {
    if (!currentTableRecords.length) {
      alert("먼저 샘플 데이터를 로드하거나 테이블 데이터를 준비해주세요.");
      return;
    }

    spinner.style.display = "inline-block";
    analyzeBtn.disabled = true;

    try {
      const res = await fetch("/api/structured/analyze", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          data: currentTableRecords,
          language: "ko",
          sample_size: 20,
        }),
      });
      const data = await res.json();

      // Render column rule configurations
      colRulesContainer.innerHTML = "";
      data.columns.forEach(col => {
        const div = document.createElement("div");
        div.className = "entity-pill";
        div.style.display = "flex";
        div.style.gap = "0.6rem";
        div.style.alignItems = "center";

        const recOp = data.recommended_operators[col.column_name] || { operator: "replace" };
        const detectedBadge = col.detected_entity
          ? `<span class="badge badge-rose">${col.detected_entity} (${Math.round(col.confidence_score * 100)}%)</span>`
          : `<span class="badge badge-primary">일반 데이터</span>`;

        div.innerHTML = `
          <strong>${col.column_name}</strong>
          ${detectedBadge}
          <select class="input-field col-operator-select" data-col="${col.column_name}" style="padding: 0.2rem 0.5rem; font-size: 0.8rem;">
            <option value="none">유지 (None)</option>
            <option value="mask" ${recOp.operator === "mask" ? "selected" : ""}>마스킹 (Mask)</option>
            <option value="encrypt" ${recOp.operator === "encrypt" ? "selected" : ""}>암호화 (AES Encrypt)</option>
            <option value="replace" ${recOp.operator === "replace" ? "selected" : ""}>대체 (Replace)</option>
            <option value="hash" ${recOp.operator === "hash" ? "selected" : ""}>해싱 (SHA256)</option>
            <option value="redact" ${recOp.operator === "redact" ? "selected" : ""}>삭제 (Redact)</option>
          </select>
        `;
        colRulesContainer.appendChild(div);
      });

    } catch (e) {
      alert("컬럼 분석 실패: " + e.message);
    } finally {
      spinner.style.display = "none";
      analyzeBtn.disabled = false;
    }
  });

  // Step 2: Anonymize Table
  anonymizeBtn.addEventListener("click", async () => {
    if (!currentTableRecords.length) {
      alert("데이터가 없습니다.");
      return;
    }

    const selects = document.querySelectorAll(".col-operator-select");
    const columnOps = {};
    const aesKey = "1234567890123456";

    selects.forEach(sel => {
      const col = sel.getAttribute("data-col");
      const val = sel.value;
      if (val !== "none") {
        if (val === "encrypt") {
          columnOps[col] = { operator: "encrypt", params: { key: aesKey } };
        } else if (val === "mask") {
          columnOps[col] = { operator: "mask", params: { masking_char: "*", chars_to_mask: 4, from_end: true } };
        } else if (val === "hash") {
          columnOps[col] = { operator: "hash", params: { hash_type: "sha256" } };
        } else if (val === "redact") {
          columnOps[col] = { operator: "redact", params: {} };
        } else {
          columnOps[col] = { operator: "replace", params: { new_value: "<비식별화>" } };
        }
      }
    });

    spinner.style.display = "inline-block";
    anonymizeBtn.disabled = true;

    try {
      const res = await fetch("/api/structured/anonymize", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          data: currentTableRecords,
          column_operators: columnOps,
          language: "ko",
        }),
      });
      const data = await res.json();
      currentAnonymizedRecords = data.anonymized_data;
      renderTable(currentAnonymizedRecords);
      downloadCsvBtn.style.display = "inline-flex";
    } catch (e) {
      alert("테이블 비식별화 실패: " + e.message);
    } finally {
      spinner.style.display = "none";
      anonymizeBtn.disabled = false;
    }
  });

  // Step 3: Deanonymize Table
  deanonBtn.addEventListener("click", async () => {
    if (!currentAnonymizedRecords.length) {
      alert("먼저 테이블을 비식별화(암호화)해주세요.");
      return;
    }

    const selects = document.querySelectorAll(".col-operator-select");
    const columnKeys = {};
    selects.forEach(sel => {
      if (sel.value === "encrypt") {
        columnKeys[sel.getAttribute("data-col")] = "1234567890123456";
      }
    });

    if (Object.keys(columnKeys).length === 0) {
      alert("암호화(AES Encrypt)된 컬럼이 없습니다.");
      return;
    }

    spinner.style.display = "inline-block";
    deanonBtn.disabled = true;

    try {
      const res = await fetch("/api/structured/deanonymize", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          anonymized_data: currentAnonymizedRecords,
          column_keys: columnKeys,
        }),
      });
      const data = await res.json();
      renderTable(data.restored_data);
      alert("암호화된 컬럼이 원문으로 성공적으로 복원되었습니다!");
    } catch (e) {
      alert("테이블 복원 실패: " + e.message);
    } finally {
      spinner.style.display = "none";
      deanonBtn.disabled = false;
    }
  });

  // Download CSV
  downloadCsvBtn.addEventListener("click", () => {
    if (!currentAnonymizedRecords.length) return;
    const keys = Object.keys(currentAnonymizedRecords[0]);
    let csv = "\uFEFF" + keys.join(",") + "\n";
    currentAnonymizedRecords.forEach(row => {
      csv += keys.map(k => `"${String(row[k] || "").replace(/"/g, '""')}"`).join(",") + "\n";
    });
    const blob = new Blob([csv], { type: "text/csv;charset=utf-8;" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "presidio_anonymized_table.csv";
    a.click();
    URL.revokeObjectURL(url);
  });

  function renderTable(records) {
    if (!records.length) return;
    const cols = Object.keys(records[0]);
    tableHead.innerHTML = "<tr>" + cols.map(c => `<th>${c}</th>`).join("") + "</tr>";
    tableBody.innerHTML = records.map(row => {
      return "<tr>" + cols.map(c => `<td>${escapeHtml(String(row[c] || ""))}</td>`).join("") + "</tr>";
    }).join("");
  }
}

// --- 5. Test Data Hub ---
function initTestDataHub() {
  // Hub buttons are directly wired with href links or API calls
}

// Utility
function escapeHtml(str) {
  if (!str) return "";
  return str
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}
