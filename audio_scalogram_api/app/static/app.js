const form = document.getElementById("analysis-form");
const statusNode = document.getElementById("status");
const resultsNode = document.getElementById("results");
const metadataNode = document.getElementById("metadata");
const temporalNode = document.getElementById("temporal");
const spectralNode = document.getElementById("spectral");
const plotsNode = document.getElementById("plots");
const downloadPrimaryNode = document.getElementById("download-primary");
const submitButton = document.getElementById("submit-button");

function formatNumber(value, digits = 4) {
  if (typeof value !== "number" || Number.isNaN(value)) {
    return "n/a";
  }
  if (Math.abs(value) >= 1000) {
    return new Intl.NumberFormat("es-ES", { maximumFractionDigits: 1 }).format(value);
  }
  return value.toFixed(digits);
}

function metricCard(title, description, value) {
  const article = document.createElement("article");
  article.className = "metric-card";
  article.innerHTML = `
    <h3>${title}</h3>
    <p>${description}</p>
    <span class="metric-value">${value}</span>
  `;
  return article;
}

function plotCard(key, plot) {
  const article = document.createElement("article");
  article.className = "plot-card";
  article.innerHTML = `
    <h3>${plot.title}</h3>
    <p>${plot.description}</p>
    <img alt="${plot.title}" src="data:${plot.media_type};base64,${plot.image_base64}" />
  `;
  article.dataset.plotKey = key;
  return article;
}

function resetResults() {
  metadataNode.replaceChildren();
  temporalNode.replaceChildren();
  spectralNode.replaceChildren();
  plotsNode.replaceChildren();
}

function populateMetadata(payload) {
  const meta = payload.audio_metadata;
  const config = payload.scalogram_config;
  metadataNode.append(
    metricCard("Frecuencia efectiva", "Frecuencia usada para el analisis.", `${meta.sample_rate} Hz`),
    metricCard("Frecuencia original", "Frecuencia detectada antes de resample.", `${meta.original_sample_rate} Hz`),
    metricCard("Duracion", "Duracion total del archivo.", `${formatNumber(meta.duration_seconds, 3)} s`),
    metricCard("Muestras", "Numero de muestras analizadas.", formatNumber(meta.sample_count, 0)),
    metricCard("Nyquist", "Limite superior teorico del espectro.", `${formatNumber(meta.nyquist_hz, 0)} Hz`),
    metricCard("Wavelet", "Configuracion conservada para comparabilidad.", `${config.wavelet} (${config.width_min}-${config.width_max})`)
  );
}

function populateTemporal(payload) {
  const temporal = payload.temporal_analysis;
  temporalNode.append(
    metricCard("RMS media", "Energia media del audio.", formatNumber(temporal.rms.mean, 5)),
    metricCard("Pico de amplitud", "Maximo absoluto observado.", formatNumber(temporal.peak_amplitude, 5)),
    metricCard("Silencio", "Proporcion de muestras de baja energia.", `${formatNumber(temporal.silence_ratio * 100, 2)} %`),
    metricCard("Rango dinamico", "Separacion entre zonas bajas y altas de energia.", `${formatNumber(temporal.dynamic_range_db, 2)} dB`),
    metricCard("Crest factor", "Relacion entre pico y RMS, util para transitorios.", formatNumber(temporal.crest_factor, 3)),
    metricCard("Clipping", "Fraccion de muestras cerca del maximo digital.", `${formatNumber(temporal.clipping_ratio * 100, 3)} %`)
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
    metricCard("Rolloff", "Frecuencia por debajo de la mayor parte de la energia.", `${formatNumber(spectral.rolloff_hz.mean, 1)} Hz`),
    metricCard("Flatness", "Tonalidad frente a ruido.", formatNumber(spectral.flatness.mean, 5)),
    metricCard("Frecuencia dominante", "Pico principal del espectro promedio.", `${formatNumber(spectral.dominant_frequency_hz, 1)} Hz`),
    metricCard("Top picos", "Tres bandas dominantes para seguimiento historico.", topPeaks || "n/a")
  );
}

function populatePlots(payload) {
  Object.entries(payload.plots).forEach(([key, plot]) => {
    plotsNode.append(plotCard(key, plot));
  });
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  resetResults();
  statusNode.textContent = "Analizando audio...";
  submitButton.disabled = true;

  const formData = new FormData(form);
  formData.set("output", "json");

  try {
    const response = await fetch("/scalogram", {
      method: "POST",
      body: formData,
    });

    if (!response.ok) {
      const errorPayload = await response.json().catch(() => null);
      throw new Error(errorPayload?.detail || "No se pudo analizar el audio.");
    }

    const payload = await response.json();
    populateMetadata(payload);
    populateTemporal(payload);
    populateSpectral(payload);
    populatePlots(payload);

    downloadPrimaryNode.href = `data:image/png;base64,${payload.image_base64}`;
    downloadPrimaryNode.download = payload.filename || "analysis.png";

    resultsNode.classList.remove("hidden");
    statusNode.textContent = `Analisis listo. Version ${payload.analysis_version}.`;
  } catch (error) {
    statusNode.textContent = error.message;
  } finally {
    submitButton.disabled = false;
  }
});
