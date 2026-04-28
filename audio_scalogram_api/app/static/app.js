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

function metricRows(payload) {
  return (payload.metricas?.grupos || []).flatMap((group) => group.metricas || []);
}

function metricMap(payload) {
  return Object.fromEntries(metricRows(payload).map((metric) => [metric.clave, metric]));
}

function formatMetric(metric, digits = 4) {
  if (!metric) {
    return "n/a";
  }

  const value = typeof metric.valor === "number" ? formatNumber(metric.valor, digits) : metric.valor;
  return metric.unidad ? `${value} ${metric.unidad}` : String(value);
}

function appendMetricCards(node, metrics, keys) {
  keys.forEach((key) => {
    const metric = metrics[key];
    if (!metric) {
      return;
    }

    node.append(metricCard(metric.etiqueta, metric.descripcion, formatMetric(metric)));
  });
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
  const metrics = metricMap(payload);
  appendMetricCards(metadataNode, metrics, [
    "quality_flag",
    "valid_audio",
    "silence_sample_ratio",
    "active_ratio",
    "clipping_ratio",
    "snr_estimate",
  ]);
}

function populateTemporal(payload) {
  const metrics = metricMap(payload);
  appendMetricCards(temporalNode, metrics, [
    "rms_mean",
    "rms_min",
    "rms_max",
    "peak_amplitude",
    "dynamic_range_db",
    "stability_index",
    "variability_index",
    "time_to_peak_seconds",
    "silence_sample_ratio",
    "clipping_ratio",
  ]);
}

function populateSpectral(payload) {
  const metrics = metricMap(payload);
  appendMetricCards(spectralNode, metrics, [
    "dominant_frequency_hz",
    "spectral_centroid_mean_hz",
    "spectral_bandwidth_mean_hz",
    "spectral_rolloff_85_mean_hz",
    "spectral_rolloff_95_mean_hz",
    "spectral_flatness_mean",
    "spectral_flux_mean",
    "low_band_energy_ratio",
    "mid_band_energy_ratio",
    "high_band_energy_ratio",
  ]);
}

function addInsight(text) {
  const item = document.createElement("li");
  item.textContent = text;
  insightsListNode.append(item);
}

function populateInsights(payload) {
  const metrics = metricMap(payload);
  const silenceRatio = metrics.silence_sample_ratio?.valor;
  const clippingRatio = metrics.clipping_ratio?.valor;
  const flatness = metrics.spectral_flatness_mean?.valor;
  const dominantFrequency = metrics.dominant_frequency_hz?.valor;

  if (typeof silenceRatio === "number" && silenceRatio >= 0.45) {
    addInsight("El audio tiene bastante tiempo en silencio o con energia muy baja; conviene seguir este indicador en tendencias.");
  } else {
    addInsight("La señal mantiene actividad util durante buena parte del tiempo, lo que facilita comparaciones historicas.");
  }

  if (typeof clippingRatio === "number" && clippingRatio > 0) {
    addInsight("Hay indicios de clipping digital; esta captura puede distorsionar parte del analisis.");
  } else {
    addInsight("No aparecen signos relevantes de clipping, asi que la lectura espectral parece estable.");
  }

  if (typeof flatness === "number" && flatness > 0.2) {
    addInsight("La textura espectral parece relativamente ruidosa o amplia; puede ser util vigilar cambios bruscos de flatness.");
  } else {
    addInsight("La energia esta bastante concentrada en bandas concretas, lo que sugiere un patron tonal o mecanico estable.");
  }

  addInsight(`La frecuencia dominante ronda ${formatNumber(dominantFrequency, 1)} Hz y sirve como referencia base para alarmas o drift.`);
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
  const metrics = metricMap(payload);
  const file = fileInput.files?.[0];
  summaryFileNode.textContent = file?.name || "Audio analizado";
  summarySizeNode.textContent = formatBytes(file?.size || 0);
  summaryDurationNode.textContent = formatMetric(metrics.silence_sample_ratio, 3);
  summarySampleRateNode.textContent = "silencio";
  summaryDominantNode.textContent = formatMetric(metrics.dominant_frequency_hz, 1);
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
