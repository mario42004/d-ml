const form = document.getElementById("analysis-form");
const fileInput = document.getElementById("audio_file");
const fileHintNode = document.getElementById("file-hint");
const statusNode = document.getElementById("status");
const resultsNode = document.getElementById("results");
const metadataNode = document.getElementById("metadata");
const temporalNode = document.getElementById("temporal");
const spectralNode = document.getElementById("spectral");
const plotsNode = document.getElementById("plots");
const downloadPrimaryNode = document.getElementById("download-primary");
const downloadJsonNode = document.getElementById("download-json");
const submitButton = document.getElementById("submit-button");
const audioPlayerNode = document.getElementById("audio-player");
const audioCaptionNode = document.getElementById("audio-caption");
const insightsListNode = document.getElementById("insights-list");
const spotlightTitleNode = document.getElementById("spotlight-title");
const spotlightDescriptionNode = document.getElementById("spotlight-description");
const spotlightKeyNode = document.getElementById("spotlight-key");
const spotlightImageNode = document.getElementById("spotlight-image");
const summaryFileNode = document.getElementById("summary-file");
const summarySizeNode = document.getElementById("summary-size");
const summaryDurationNode = document.getElementById("summary-duration");
const summarySampleRateNode = document.getElementById("summary-sample-rate");
const summaryDominantNode = document.getElementById("summary-dominant");
const summaryVersionNode = document.getElementById("summary-version");

let latestPayload = null;
let currentAudioUrl = null;

function formatNumber(value, digits = 4) {
  if (typeof value !== "number" || Number.isNaN(value)) {
    return "n/a";
  }

  if (Math.abs(value) >= 1000) {
    return new Intl.NumberFormat("es-ES", { maximumFractionDigits: 1 }).format(value);
  }

  return value.toFixed(digits);
}

function formatBytes(size) {
  if (!size) {
    return "0 KB";
  }

  const units = ["B", "KB", "MB", "GB"];
  let value = size;
  let unitIndex = 0;

  while (value >= 1024 && unitIndex < units.length - 1) {
    value /= 1024;
    unitIndex += 1;
  }

  return `${formatNumber(value, unitIndex === 0 ? 0 : 2)} ${units[unitIndex]}`;
}

function safeText(text) {
  return String(text)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;");
}

function metricCard(title, description, value) {
  const article = document.createElement("article");
  article.className = "metric-card";
  article.innerHTML = `
    <h3>${safeText(title)}</h3>
    <p>${safeText(description)}</p>
    <span class="metric-value">${safeText(value)}</span>
  `;
  return article;
}

function plotCard(key, plot, isActive) {
  const article = document.createElement("article");
  article.className = `plot-card${isActive ? " is-active" : ""}`;
  article.innerHTML = `
    <h3>${safeText(plot.title)}</h3>
    <p>${safeText(plot.description)}</p>
    <img alt="${safeText(plot.title)}" src="data:${plot.media_type};base64,${plot.image_base64}" />
  `;
  article.dataset.plotKey = key;
  article.addEventListener("click", () => {
    setSpotlightPlot(key, plot);
    syncActivePlot(key);
  });
  return article;
}

function resetResults() {
  metadataNode.replaceChildren();
  temporalNode.replaceChildren();
  spectralNode.replaceChildren();
  plotsNode.replaceChildren();
  insightsListNode.replaceChildren();
}

function syncActivePlot(activeKey) {
  plotsNode.querySelectorAll(".plot-card").forEach((node) => {
    node.classList.toggle("is-active", node.dataset.plotKey === activeKey);
  });
}

function setSpotlightPlot(key, plot) {
  spotlightTitleNode.textContent = plot.title;
  spotlightDescriptionNode.textContent = plot.description;
  spotlightKeyNode.textContent = key;
  spotlightImageNode.src = `data:${plot.media_type};base64,${plot.image_base64}`;
  spotlightImageNode.alt = plot.title;
}

function populateMetadata(payload) {
  const meta = payload.audio_metadata;
  const config = payload.scalogram_config;

  metadataNode.append(
    metricCard("Frecuencia efectiva", "Frecuencia usada para el analisis.", `${meta.sample_rate} Hz`),
    metricCard("Frecuencia original", "Frecuencia detectada antes del resample.", `${meta.original_sample_rate} Hz`),
    metricCard("Duracion", "Duracion total del audio.", `${formatNumber(meta.duration_seconds, 3)} s`),
    metricCard("Muestras", "Numero de muestras finalmente analizadas.", formatNumber(meta.sample_count, 0)),
    metricCard("Nyquist", "Limite superior teorico del espectro.", `${formatNumber(meta.nyquist_hz, 0)} Hz`),
    metricCard("Wavelet", "Configuracion guardada para comparabilidad.", `${config.wavelet} (${config.width_min}-${config.width_max})`)
  );
}

function populateTemporal(payload) {
  const temporal = payload.temporal_analysis;

  temporalNode.append(
    metricCard("RMS media", "Energia media agregada del audio.", formatNumber(temporal.rms.mean, 5)),
    metricCard("Pico de amplitud", "Maximo absoluto observado.", formatNumber(temporal.peak_amplitude, 5)),
    metricCard("Silencio", "Fraccion del audio con amplitud muy baja.", `${formatNumber(temporal.silence_ratio * 100, 2)} %`),
    metricCard("Rango dinamico", "Separacion entre zonas bajas y altas de energia.", `${formatNumber(temporal.dynamic_range_db, 2)} dB`),
    metricCard("Crest factor", "Relacion entre picos y energia RMS.", formatNumber(temporal.crest_factor, 3)),
    metricCard("Clipping", "Muestras cercanas al maximo digital.", `${formatNumber(temporal.clipping_ratio * 100, 3)} %`)
  );
}

function populateSpectral(payload) {
  const spectral = payload.spectral_analysis;
  const topPeaks = spectral.top_spectral_peaks
    .slice(0, 3)
    .map((peak) => `${formatNumber(peak.frequency_hz, 1)} Hz`)
    .join(", ");

  spectralNode.append(
    metricCard("Centroide", "Brillo espectral medio.", `${formatNumber(spectral.centroid_hz.mean, 1)} Hz`),
    metricCard("Bandwidth", "Anchura media del contenido frecuencial.", `${formatNumber(spectral.bandwidth_hz.mean, 1)} Hz`),
    metricCard("Rolloff", "Frecuencia bajo la que cae gran parte de la energia.", `${formatNumber(spectral.rolloff_hz.mean, 1)} Hz`),
    metricCard("Flatness", "Cuanto se acerca el audio a ruido frente a tono.", formatNumber(spectral.flatness.mean, 5)),
    metricCard("Frecuencia dominante", "Pico principal del espectro promedio.", `${formatNumber(spectral.dominant_frequency_hz, 1)} Hz`),
    metricCard("Top picos", "Bandas mas relevantes para seguimiento historico.", topPeaks || "n/a")
  );
}

function addInsight(text) {
  const item = document.createElement("li");
  item.textContent = text;
  insightsListNode.append(item);
}

function populateInsights(payload) {
  const temporal = payload.temporal_analysis;
  const spectral = payload.spectral_analysis;

  if (temporal.silence_ratio >= 0.45) {
    addInsight("El audio tiene bastante tiempo en silencio o con energia muy baja; conviene seguir este indicador en tendencias.");
  } else {
    addInsight("La señal mantiene actividad util durante buena parte del tiempo, lo que facilita comparaciones historicas.");
  }

  if (temporal.clipping_ratio > 0) {
    addInsight("Hay indicios de clipping digital; esta captura puede distorsionar parte del analisis.");
  } else {
    addInsight("No aparecen signos relevantes de clipping, asi que la lectura espectral parece estable.");
  }

  if (spectral.flatness.mean > 0.2) {
    addInsight("La textura espectral parece relativamente ruidosa o amplia; puede ser util vigilar cambios bruscos de flatness.");
  } else {
    addInsight("La energia esta bastante concentrada en bandas concretas, lo que sugiere un patron tonal o mecanico estable.");
  }

  addInsight(`La frecuencia dominante ronda ${formatNumber(spectral.dominant_frequency_hz, 1)} Hz y sirve como referencia base para alarmas o drift.`);
}

function populatePlots(payload) {
  const primaryKey = payload.primary_visualization;

  Object.entries(payload.plots).forEach(([key, plot]) => {
    plotsNode.append(plotCard(key, plot, key === primaryKey));
  });

  const primaryPlot = payload.plots[primaryKey];
  if (primaryPlot) {
    setSpotlightPlot(primaryKey, primaryPlot);
  }
}

function updateSummary(payload) {
  const meta = payload.audio_metadata;
  const file = fileInput.files?.[0];
  summaryFileNode.textContent = file?.name || "Audio analizado";
  summarySizeNode.textContent = formatBytes(file?.size || meta.file_size_bytes);
  summaryDurationNode.textContent = `${formatNumber(meta.duration_seconds, 3)} s`;
  summarySampleRateNode.textContent = `${meta.sample_rate} Hz`;
  summaryDominantNode.textContent = `${formatNumber(payload.spectral_analysis.dominant_frequency_hz, 1)} Hz`;
  summaryVersionNode.textContent = `v${payload.analysis_version}`;
}

function setupAudioPreview() {
  const file = fileInput.files?.[0];

  if (currentAudioUrl) {
    URL.revokeObjectURL(currentAudioUrl);
    currentAudioUrl = null;
  }

  if (!file) {
    audioPlayerNode.removeAttribute("src");
    audioPlayerNode.load();
    audioCaptionNode.textContent = "La reproduccion ayuda a contrastar lo que ves en las graficas.";
    return;
  }

  currentAudioUrl = URL.createObjectURL(file);
  audioPlayerNode.src = currentAudioUrl;
  audioCaptionNode.textContent = `Escuchando ${file.name} para contrastar hallazgos visuales y auditivos.`;
}

function setFileHint() {
  const file = fileInput.files?.[0];
  fileHintNode.textContent = file
    ? `${file.name} · ${formatBytes(file.size)}`
    : "Acepta cualquier formato soportado por `librosa`.";
}

function downloadJson() {
  if (!latestPayload) {
    return;
  }

  const blob = new Blob([JSON.stringify(latestPayload, null, 2)], {
    type: "application/json",
  });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = "audio-analysis.json";
  anchor.click();
  URL.revokeObjectURL(url);
}

fileInput.addEventListener("change", () => {
  setFileHint();
  setupAudioPreview();
});

downloadJsonNode.addEventListener("click", downloadJson);

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  resetResults();
  statusNode.textContent = "Analizando audio...";
  submitButton.disabled = true;

  const formData = new FormData(form);
  formData.set("output", "json");

  try {
    const response = await fetch("/audioanalisys", {
      method: "POST",
      body: formData,
    });

    if (!response.ok) {
      const errorPayload = await response.json().catch(() => null);
      throw new Error(errorPayload?.detail || "No se pudo analizar el audio.");
    }

    const payload = await response.json();
    latestPayload = payload;

    updateSummary(payload);
    populateMetadata(payload);
    populateTemporal(payload);
    populateSpectral(payload);
    populateInsights(payload);
    populatePlots(payload);

    downloadPrimaryNode.href = `data:image/png;base64,${payload.image_base64}`;
    downloadPrimaryNode.download = payload.filename || "analysis.png";

    resultsNode.classList.remove("hidden");
    statusNode.textContent = `Analisis listo. Version ${payload.analysis_version}.`;
    resultsNode.scrollIntoView({ behavior: "smooth", block: "start" });
  } catch (error) {
    statusNode.textContent = error.message;
  } finally {
    submitButton.disabled = false;
  }
});
