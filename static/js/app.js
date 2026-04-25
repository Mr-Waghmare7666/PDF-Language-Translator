const data = window.APP_DATA || { languages: [], fontMap: [], defaultLang: null };

const state = {
    activeJobId: null,
    pollTimer: null,
};

const elements = {
    translateForm: document.getElementById("translateForm"),
    pdfInput: document.getElementById("pdfInput"),
    targetLang: document.getElementById("targetLang"),
    chunkSize: document.getElementById("chunkSize"),
    chunkValue: document.getElementById("chunkValue"),
    fallbackEngine: document.getElementById("fallbackEngine"),
    startBtn: document.getElementById("startBtn"),

    metricFile: document.getElementById("metricFile"),
    metricSize: document.getElementById("metricSize"),
    metricStatus: document.getElementById("metricStatus"),

    statusPill: document.getElementById("statusPill"),
    progressBar: document.getElementById("progressBar"),
    statusMessage: document.getElementById("statusMessage"),
    downloadBtn: document.getElementById("downloadBtn"),

    statTotalPages: document.getElementById("statTotalPages"),
    statTextPages: document.getElementById("statTextPages"),
    statTotalChunks: document.getElementById("statTotalChunks"),
    statGoogle: document.getElementById("statGoogle"),
    statDeep: document.getElementById("statDeep"),
    statFallback: document.getElementById("statFallback"),
    statFont: document.getElementById("statFont"),
    statLanguage: document.getElementById("statLanguage"),

    resultPreview: document.getElementById("resultPreview"),

    sampleForm: document.getElementById("sampleForm"),
    sampleInput: document.getElementById("sampleInput"),
    sampleOutput: document.getElementById("sampleOutput"),
    sampleEngine: document.getElementById("sampleEngine"),

    languageSearch: document.getElementById("languageSearch"),
    languageTableBody: document.getElementById("languageTableBody"),
};

function humanFileSize(bytes) {
    if (!Number.isFinite(bytes) || bytes <= 0) {
        return "0 MB";
    }
    return `${(bytes / (1024 * 1024)).toFixed(2)} MB`;
}

function setStatus(label, type) {
    elements.statusPill.textContent = label;
    elements.statusPill.className = `status-pill status-${type}`;
    elements.metricStatus.textContent = label;
}

function setProgress(value) {
    const clamped = Math.max(0, Math.min(100, Number(value) || 0));
    elements.progressBar.style.width = `${clamped}%`;
}

function setLoading(isLoading) {
    elements.startBtn.disabled = isLoading;
    elements.startBtn.textContent = isLoading ? "Translating..." : "Start Translation";
}

function resetStats() {
    elements.statTotalPages.textContent = "0";
    elements.statTextPages.textContent = "0";
    elements.statTotalChunks.textContent = "0";
    elements.statGoogle.textContent = "0";
    elements.statDeep.textContent = "0";
    elements.statFallback.textContent = "0";
    elements.statFont.textContent = "-";
    elements.statLanguage.textContent = "-";
}

function applyStats(dataPoint) {
    const stats = dataPoint.stats || {};
    elements.statTotalPages.textContent = String(stats.total_pages ?? 0);
    elements.statTextPages.textContent = String(stats.text_pages ?? 0);
    elements.statTotalChunks.textContent = String(stats.total_chunks ?? 0);
    elements.statGoogle.textContent = String(stats.google_chunks ?? 0);
    elements.statDeep.textContent = String(stats.deep_chunks ?? 0);
    elements.statFallback.textContent = String(stats.fallback_chunks ?? 0);
    elements.statFont.textContent = dataPoint.font || "-";
    const langName = dataPoint.target_language_name || dataPoint.target_language || "-";
    elements.statLanguage.textContent = langName;
}

function populateLanguages() {
    const fragment = document.createDocumentFragment();
    data.languages.forEach((lang) => {
        const option = document.createElement("option");
        option.value = lang.code;
        option.textContent = `${lang.name} (${lang.code})`;
        fragment.appendChild(option);
    });
    elements.targetLang.appendChild(fragment);

    if (data.defaultLang) {
        elements.targetLang.value = data.defaultLang;
    }
}

function renderLanguageTable(query = "") {
    const text = query.trim().toLowerCase();
    elements.languageTableBody.innerHTML = "";

    const rows = data.fontMap.filter((row) => {
        if (!text) {
            return true;
        }
        return (
            row.name.toLowerCase().includes(text) ||
            row.code.toLowerCase().includes(text) ||
            row.font.toLowerCase().includes(text)
        );
    });

    const fragment = document.createDocumentFragment();
    rows.forEach((row) => {
        const tr = document.createElement("tr");
        const tdName = document.createElement("td");
        const tdCode = document.createElement("td");
        const tdFont = document.createElement("td");
        tdName.textContent = row.name;
        tdCode.textContent = row.code;
        tdFont.textContent = row.font;
        tr.appendChild(tdName);
        tr.appendChild(tdCode);
        tr.appendChild(tdFont);
        fragment.appendChild(tr);
    });

    elements.languageTableBody.appendChild(fragment);
}

function stopPolling() {
    if (state.pollTimer) {
        window.clearInterval(state.pollTimer);
        state.pollTimer = null;
    }
}

async function fetchJobStatus(jobId) {
    const response = await fetch(`/api/jobs/${jobId}`);
    const payload = await response.json();
    if (!response.ok) {
        throw new Error(payload.error || "Could not fetch job status.");
    }
    return payload;
}

function handleJobUpdate(payload) {
    setProgress(payload.progress ?? 0);
    elements.statusMessage.textContent = payload.message || "Working...";
    applyStats(payload);

    if (payload.preview) {
        elements.resultPreview.value = payload.preview;
    }

    if (payload.status === "queued") {
        setStatus("Queued", "idle");
    } else if (payload.status === "running") {
        setStatus("Running", "running");
    } else if (payload.status === "completed") {
        setStatus("Completed", "completed");
        setLoading(false);
        stopPolling();
        elements.downloadBtn.classList.remove("disabled");
        elements.downloadBtn.href = payload.download_url || "#";
        elements.downloadBtn.download = payload.output_name || "translated.pdf";
    } else if (payload.status === "failed") {
        setStatus("Failed", "failed");
        setLoading(false);
        stopPolling();
        elements.statusMessage.textContent = payload.error || "Translation failed.";
    }
}

async function startJobPolling(jobId) {
    state.activeJobId = jobId;
    stopPolling();

    const poll = async () => {
        if (!state.activeJobId) {
            return;
        }

        try {
            const payload = await fetchJobStatus(state.activeJobId);
            handleJobUpdate(payload);
        } catch (error) {
            setStatus("Failed", "failed");
            elements.statusMessage.textContent = error.message;
            setLoading(false);
            stopPolling();
        }
    };

    await poll();
    state.pollTimer = window.setInterval(poll, 1300);
}

async function createTranslationJob(formData) {
    const response = await fetch("/api/jobs", {
        method: "POST",
        body: formData,
    });
    const payload = await response.json();
    if (!response.ok) {
        throw new Error(payload.error || "Could not create translation job.");
    }
    return payload;
}

async function handleTranslateSubmit(event) {
    event.preventDefault();
    const file = elements.pdfInput.files?.[0];
    if (!file) {
        setStatus("Failed", "failed");
        elements.statusMessage.textContent = "Please select a PDF file first.";
        return;
    }

    elements.metricFile.textContent = file.name;
    elements.metricSize.textContent = humanFileSize(file.size);
    elements.metricStatus.textContent = "Uploading";
    elements.resultPreview.value = "Preparing translation...";

    setProgress(0);
    setStatus("Uploading", "running");
    elements.statusMessage.textContent = "Uploading PDF and creating translation job...";
    elements.downloadBtn.classList.add("disabled");
    elements.downloadBtn.href = "#";
    resetStats();
    setLoading(true);

    const formData = new FormData();
    formData.append("pdf", file);
    formData.append("target_lang", elements.targetLang.value);
    formData.append("chunk_size", elements.chunkSize.value);
    formData.append("use_fallback_engine", String(elements.fallbackEngine.checked));

    try {
        const created = await createTranslationJob(formData);
        await startJobPolling(created.job_id);
    } catch (error) {
        setStatus("Failed", "failed");
        elements.statusMessage.textContent = error.message;
        setLoading(false);
    }
}

async function handleSampleSubmit(event) {
    event.preventDefault();
    const text = elements.sampleInput.value.trim();
    if (!text) {
        elements.sampleOutput.value = "Please type some sample text.";
        return;
    }

    elements.sampleOutput.value = "Translating sample text...";

    try {
        const response = await fetch("/api/sample-translate", {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
            },
            body: JSON.stringify({
                text,
                target_lang: elements.targetLang.value,
                use_fallback_engine: elements.fallbackEngine.checked,
            }),
        });

        const payload = await response.json();
        if (!response.ok) {
            throw new Error(payload.error || "Sample translation failed.");
        }

        elements.sampleOutput.value = payload.translated_text || "";
        elements.sampleEngine.textContent = `Engine: ${payload.engine}`;
    } catch (error) {
        elements.sampleOutput.value = error.message;
        elements.sampleEngine.textContent = "Engine: error";
    }
}

function initialize() {
    populateLanguages();
    renderLanguageTable();

    elements.chunkValue.textContent = elements.chunkSize.value;

    elements.chunkSize.addEventListener("input", () => {
        elements.chunkValue.textContent = elements.chunkSize.value;
    });

    elements.languageSearch.addEventListener("input", () => {
        renderLanguageTable(elements.languageSearch.value);
    });

    elements.translateForm.addEventListener("submit", handleTranslateSubmit);
    elements.sampleForm.addEventListener("submit", handleSampleSubmit);
}

initialize();
