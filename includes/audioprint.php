<?php

declare(strict_types=1);

require_once __DIR__ . '/auth.php';

function audioprint_api_url(): string
{
    $newUrl = env_value('AUDIOPRINT_AUDIOANALISYS_API_URL');
    if (is_string($newUrl) && trim($newUrl) !== '') {
        return trim($newUrl);
    }

    return (string) env_value('AUDIOPRINT_SCALOGRAM_API_URL', 'http://127.0.0.1:8001/audioanalisys');
}

function audioprint_max_upload_bytes(): int
{
    return ((int) env_value('AUDIOPRINT_MAX_UPLOAD_MB', '25')) * 1024 * 1024;
}

function audioprint_timeout_seconds(): int
{
    $configured = (int) env_value('AUDIOPRINT_UPLOAD_TIMEOUT_SECONDS', '120');
    if ($configured <= 0) {
        return 120;
    }

    return min($configured, 300);
}

function audioprint_storage_dir(string $kind): string
{
    return dirname(__DIR__) . '/storage/' . $kind . '/audioprint';
}

function audioprint_public_url(string $kind, string $filename): string
{
    return '/storage/' . $kind . '/audioprint/' . $filename;
}

function ensure_directory(string $path): void
{
    if (!is_dir($path)) {
        mkdir($path, 0775, true);
    }
}

function audioprint_product(): ?array
{
    return find_product_by_code('audioprint');
}

function create_audio_job_record(int $userId, int $productId, string $originalFilename, string $mimeType, int $sizeBytes, string $audioPath, string $audioUrl): int
{
    $stmt = db()->prepare(
        'INSERT INTO audio_jobs (user_id, product_id, original_filename, mime_type, audio_size_bytes, audio_path, audio_url, status) VALUES (:user_id, :product_id, :original_filename, :mime_type, :audio_size_bytes, :audio_path, :audio_url, :status)'
    );
    $stmt->execute([
        'user_id' => $userId,
        'product_id' => $productId,
        'original_filename' => $originalFilename,
        'mime_type' => $mimeType,
        'audio_size_bytes' => $sizeBytes,
        'audio_path' => $audioPath,
        'audio_url' => $audioUrl,
        'status' => 'processing',
    ]);

    return (int) db()->lastInsertId();
}

function finalize_audio_job(int $jobId, string $status, ?string $scalogramPath = null, ?string $scalogramUrl = null, ?string $errorMessage = null): void
{
    $stmt = db()->prepare(
        'UPDATE audio_jobs SET status = :status, scalogram_path = :scalogram_path, scalogram_url = :scalogram_url, error_message = :error_message, processed_at = NOW(), updated_at = NOW() WHERE id = :id'
    );
    $stmt->execute([
        'status' => $status,
        'scalogram_path' => $scalogramPath,
        'scalogram_url' => $scalogramUrl,
        'error_message' => $errorMessage,
        'id' => $jobId,
    ]);
}

function list_audio_jobs_for_user(int $userId): array
{
    $stmt = db()->prepare(
        'SELECT id, original_filename, mime_type, audio_size_bytes, audio_url, scalogram_path, scalogram_url, status, error_message, created_at, processed_at FROM audio_jobs WHERE user_id = :user_id ORDER BY created_at DESC, id DESC'
    );
    $stmt->execute(['user_id' => $userId]);
    return $stmt->fetchAll();
}

function list_recent_audio_jobs(int $limit = 20): array
{
    $sql = <<<'SQL'
        SELECT
            j.id,
            j.original_filename,
            j.status,
            j.error_message,
            j.audio_url,
            j.scalogram_path,
            j.scalogram_url,
            j.created_at,
            j.processed_at,
            u.first_name,
            u.last_name,
            u.email
        FROM audio_jobs j
        INNER JOIN users u ON u.id = j.user_id
        ORDER BY j.created_at DESC, j.id DESC
        LIMIT :limit
    SQL;

    $stmt = db()->prepare($sql);
    $stmt->bindValue(':limit', $limit, PDO::PARAM_INT);
    $stmt->execute();
    return $stmt->fetchAll();
}

function get_audio_job_by_id(int $jobId): ?array
{
    $stmt = db()->prepare(
        'SELECT id, user_id, original_filename, audio_path, audio_url, scalogram_path, scalogram_url, status FROM audio_jobs WHERE id = :id LIMIT 1'
    );
    $stmt->execute(['id' => $jobId]);
    $job = $stmt->fetch();

    return $job ?: null;
}

function delete_audio_job_record(int $jobId): array
{
    $job = get_audio_job_by_id($jobId);
    if ($job === null) {
        return ['ok' => false, 'message' => 'El registro ya no existe o fue eliminado.'];
    }

    $audioPath = (string) ($job['audio_path'] ?? '');
    $scalogramPath = (string) ($job['scalogram_path'] ?? '');
    $analysisPath = audioprint_analysis_path_from_scalogram_path($scalogramPath);

    $stmt = db()->prepare('DELETE FROM audio_jobs WHERE id = :id');
    $stmt->execute(['id' => $jobId]);

    foreach ([$audioPath, $scalogramPath, $analysisPath] as $path) {
        if ($path !== '' && is_file($path)) {
            @unlink($path);
        }
    }

    return ['ok' => true];
}

function audioprint_analysis_path_from_scalogram_path(?string $scalogramPath): ?string
{
    if (!is_string($scalogramPath) || $scalogramPath === '') {
        return null;
    }

    return preg_replace('/\.png$/i', '.json', $scalogramPath) ?: null;
}

function audioprint_analysis_url_from_scalogram_url(?string $scalogramUrl): ?string
{
    if (!is_string($scalogramUrl) || $scalogramUrl === '') {
        return null;
    }

    return preg_replace('/\.png$/i', '.json', $scalogramUrl) ?: null;
}

function audioprint_enrich_job_record(array $job): array
{
    $analysisPath = audioprint_analysis_path_from_scalogram_path((string) ($job['scalogram_path'] ?? ''));
    $analysisUrl = audioprint_analysis_url_from_scalogram_url((string) ($job['scalogram_url'] ?? ''));
    $job['analysis_path'] = $analysisPath;
    $job['analysis_url'] = $analysisUrl;
    $job['analysis_available'] = $analysisPath !== null && is_file($analysisPath);

    return $job;
}

function audioprint_load_analysis_for_job(array $job): ?array
{
    $analysisPath = $job['analysis_path'] ?? audioprint_analysis_path_from_scalogram_path((string) ($job['scalogram_path'] ?? ''));
    if (!is_string($analysisPath) || $analysisPath === '' || !is_file($analysisPath)) {
        return null;
    }

    $contents = file_get_contents($analysisPath);
    if (!is_string($contents) || $contents === '') {
        return null;
    }

    $decoded = json_decode($contents, true);
    return is_array($decoded) ? $decoded : null;
}

function audioprint_analysis_metric(array $analysis, array $path): ?float
{
    $value = $analysis;
    foreach ($path as $segment) {
        if (!is_array($value) || !array_key_exists($segment, $value)) {
            return null;
        }
        $value = $value[$segment];
    }

    return is_numeric($value) ? (float) $value : null;
}

function audioprint_analysis_metric_any(array $analysis, array $paths): ?float
{
    foreach ($paths as $path) {
        if (!is_array($path)) {
            continue;
        }

        $metric = audioprint_analysis_metric($analysis, $path);
        if ($metric !== null) {
            return $metric;
        }
    }

    return null;
}

function audioprint_job_datetime_label(array $job): string
{
    $raw = (string) ($job['processed_at'] ?? $job['created_at'] ?? '');
    if ($raw === '') {
        return '';
    }

    try {
        $date = new DateTimeImmutable($raw);
        return $date->format('d/m H:i');
    } catch (Throwable $exception) {
        return $raw;
    }
}

function audioprint_job_datetime_sort_value(array $job): int
{
    $raw = (string) ($job['processed_at'] ?? $job['created_at'] ?? '');
    if ($raw === '') {
        return 0;
    }

    try {
        return (new DateTimeImmutable($raw))->getTimestamp();
    } catch (Throwable $exception) {
        return 0;
    }
}

function audioprint_trend_definitions(): array
{
    return [
        'dominant_frequency_hz' => [
            'label' => 'Frecuencia dominante',
            'unit' => 'Hz',
            'description' => 'Sirve para detectar drift o desplazamientos en la banda principal.',
            'color' => '#ffc74d',
            'paths' => [
                ['analysis_engine', 'spectral_summary', 'dominant_frequency'],
                ['spectral_analysis', 'dominant_frequency_hz'],
            ],
        ],
        'dynamic_range_db' => [
            'label' => 'Rango dinamico',
            'unit' => 'dB',
            'description' => 'Resume cambios entre zonas de baja y alta energia del audio.',
            'color' => '#f26a21',
            'paths' => [
                ['analysis_engine', 'global_features', 'basic_features', 'dynamic_range_db'],
                ['temporal_analysis', 'dynamic_range_db'],
            ],
        ],
        'silence_ratio' => [
            'label' => 'Silencio',
            'unit' => '',
            'description' => 'Permite vigilar inactividad o degradacion de captura.',
            'color' => '#46c797',
            'paths' => [
                ['analysis_engine', 'quality', 'silence_ratio'],
                ['temporal_analysis', 'silence_ratio'],
            ],
        ],
        'stability_index' => [
            'label' => 'Estabilidad',
            'unit' => '',
            'description' => 'Resume la consistencia temporal del audio a partir de frames internos.',
            'color' => '#7cc7ff',
            'paths' => [
                ['analysis_engine', 'temporal_summary', 'stability_index'],
            ],
        ],
    ];
}

function audioprint_build_trend_series(array $jobs): array
{
    $definitions = audioprint_trend_definitions();
    $series = [];

    foreach ($definitions as $key => $definition) {
        $series[$key] = [
            'key' => $key,
            'label' => $definition['label'],
            'unit' => $definition['unit'],
            'description' => $definition['description'],
            'color' => $definition['color'],
            'points' => [],
        ];
    }

    foreach ($jobs as $job) {
        if (($job['analysis_available'] ?? false) !== true) {
            continue;
        }

        $analysis = audioprint_load_analysis_for_job($job);
        if (!is_array($analysis)) {
            continue;
        }

        $sortValue = audioprint_job_datetime_sort_value($job);
        $label = audioprint_job_datetime_label($job);
        foreach ($definitions as $key => $definition) {
            $paths = is_array($definition['paths'] ?? null) ? $definition['paths'] : [];
            $metric = audioprint_analysis_metric_any($analysis, $paths);
            if ($metric === null) {
                continue;
            }

            $series[$key]['points'][] = [
                'x' => $sortValue,
                'x_label' => $label,
                'y' => $metric,
                'job_id' => (int) ($job['id'] ?? 0),
            ];
        }
    }

    foreach ($series as $key => $definition) {
        usort(
            $series[$key]['points'],
            static fn (array $left, array $right): int => ($left['x'] ?? 0) <=> ($right['x'] ?? 0)
        );
    }

    return $series;
}

function audioprint_render_trend_chart(array $series): string
{
    $points = $series['points'] ?? [];
    if (!is_array($points) || $points === []) {
        return '';
    }

    $width = 560;
    $height = 220;
    $paddingLeft = 62;
    $paddingRight = 18;
    $paddingTop = 18;
    $paddingBottom = 34;
    $plotWidth = $width - $paddingLeft - $paddingRight;
    $plotHeight = $height - $paddingTop - $paddingBottom;

    $values = array_map(static fn (array $point): float => (float) ($point['y'] ?? 0), $points);
    $minValue = min($values);
    $maxValue = max($values);
    if (abs($maxValue - $minValue) < 0.000001) {
        $minValue -= 1.0;
        $maxValue += 1.0;
    }

    $count = count($points);
    $coordinates = [];
    foreach ($points as $index => $point) {
        $x = $paddingLeft + ($count === 1 ? $plotWidth / 2 : ($plotWidth * $index / ($count - 1)));
        $normalized = (((float) $point['y']) - $minValue) / ($maxValue - $minValue);
        $y = $paddingTop + $plotHeight - ($normalized * $plotHeight);
        $coordinates[] = ['x' => $x, 'y' => $y, 'label' => (string) ($point['x_label'] ?? '')];
    }

    $path = '';
    foreach ($coordinates as $index => $point) {
        $path .= ($index === 0 ? 'M' : ' L') . round($point['x'], 2) . ' ' . round($point['y'], 2);
    }

    $gridLines = 4;
    $gridMarkup = '';
    $yLabelsMarkup = '';
    for ($step = 0; $step <= $gridLines; $step++) {
        $y = $paddingTop + ($plotHeight * $step / $gridLines);
        $value = $maxValue - (($maxValue - $minValue) * $step / $gridLines);
        $valueText = rtrim(rtrim(number_format($value, 3, '.', ''), '0'), '.');
        $gridMarkup .= '<line x1="' . $paddingLeft . '" y1="' . round($y, 2) . '" x2="' . ($width - $paddingRight) . '" y2="' . round($y, 2) . '" stroke="rgba(255,255,255,0.08)" stroke-width="1" />';
        $yLabelsMarkup .= '<text x="' . ($paddingLeft - 8) . '" y="' . round($y + 4, 2) . '" text-anchor="end" fill="#bbaea0" font-size="11">' . htmlspecialchars($valueText, ENT_QUOTES, 'UTF-8') . '</text>';
    }

    $circlesMarkup = '';
    foreach ($coordinates as $index => $point) {
        $circlesMarkup .= '<circle cx="' . round($point['x'], 2) . '" cy="' . round($point['y'], 2) . '" r="4" fill="' . htmlspecialchars((string) ($series['color'] ?? '#ffc74d'), ENT_QUOTES, 'UTF-8') . '" />';
        if ($count <= 8 || $index === 0 || $index === $count - 1) {
            $circlesMarkup .= '<text x="' . round($point['x'], 2) . '" y="' . ($height - 10) . '" text-anchor="middle" fill="#bbaea0" font-size="11">' . htmlspecialchars($point['label'], ENT_QUOTES, 'UTF-8') . '</text>';
        }
    }

    $latestValue = (float) end($values);
    $latestValueText = rtrim(rtrim(number_format($latestValue, 3, '.', ''), '0'), '.');

    return
        '<svg viewBox="0 0 ' . $width . ' ' . $height . '" class="audioprint-trend-svg" role="img" aria-label="' . htmlspecialchars((string) ($series['label'] ?? 'Tendencia'), ENT_QUOTES, 'UTF-8') . '">' .
        '<rect x="0" y="0" width="' . $width . '" height="' . $height . '" rx="18" fill="rgba(255,255,255,0.02)" />' .
        $gridMarkup .
        $yLabelsMarkup .
        '<line x1="' . $paddingLeft . '" y1="' . $paddingTop . '" x2="' . $paddingLeft . '" y2="' . ($height - $paddingBottom) . '" stroke="rgba(255,255,255,0.12)" stroke-width="1" />' .
        '<path d="' . trim($path) . '" fill="none" stroke="' . htmlspecialchars((string) ($series['color'] ?? '#ffc74d'), ENT_QUOTES, 'UTF-8') . '" stroke-width="3" stroke-linecap="round" stroke-linejoin="round" />' .
        $circlesMarkup .
        '<text x="' . $paddingLeft . '" y="14" fill="#f5efe5" font-size="12" font-weight="700">Ultimo valor: ' . htmlspecialchars($latestValueText . ((string) ($series['unit'] ?? '') !== '' ? ' ' . (string) $series['unit'] : ''), ENT_QUOTES, 'UTF-8') . '</text>' .
        '<text x="14" y="' . ($paddingTop + 8) . '" fill="#bbaea0" font-size="11">' . htmlspecialchars((string) (($series['unit'] ?? '') !== '' ? $series['unit'] : 'valor'), ENT_QUOTES, 'UTF-8') . '</text>' .
        '</svg>';
}

function audioprint_call_scalogram_api(string $audioPath, string $mimeType, string $originalFilename): array
{
    if (!function_exists('curl_init')) {
        return ['ok' => false, 'message' => 'La extension cURL no esta disponible en PHP.'];
    }

    $ch = curl_init(audioprint_api_url());
    if ($ch === false) {
        return ['ok' => false, 'message' => 'No fue posible inicializar la conexion con la API.'];
    }

    $payload = [
        'audio_file' => new CURLFile($audioPath, $mimeType, $originalFilename),
        'output' => 'json',
        'visualization' => 'dashboard',
    ];

    curl_setopt_array($ch, [
        CURLOPT_POST => true,
        CURLOPT_POSTFIELDS => $payload,
        CURLOPT_RETURNTRANSFER => true,
        CURLOPT_CONNECTTIMEOUT => 10,
        CURLOPT_TIMEOUT => audioprint_timeout_seconds(),
        CURLOPT_HTTPHEADER => ['Expect:'],
    ]);

    $response = curl_exec($ch);
    $httpCode = (int) curl_getinfo($ch, CURLINFO_RESPONSE_CODE);
    $error = curl_error($ch);
    curl_close($ch);

    if ($response === false) {
        $message = $error !== '' ? $error : 'La API no devolvio respuesta.';

        if (stripos($message, 'timed out') !== false) {
            $message = 'La generacion del analisis tardo demasiado y el servidor cancelo la espera. Prueba con un audio mas corto.';
        }

        return ['ok' => false, 'message' => $message];
    }

    if ($httpCode < 200 || $httpCode >= 300) {
        $decodedError = json_decode((string) $response, true);
        $detail = is_array($decodedError) ? (string) ($decodedError['detail'] ?? '') : '';
        $message = $detail !== '' ? $detail : 'La API devolvio un error HTTP ' . $httpCode . '.';
        return ['ok' => false, 'message' => $message];
    }

    $decoded = json_decode((string) $response, true);
    if (!is_array($decoded)) {
        return ['ok' => false, 'message' => 'La API devolvio una respuesta JSON no valida.'];
    }

    if (!isset($decoded['image_base64']) || !is_string($decoded['image_base64'])) {
        return ['ok' => false, 'message' => 'La API no devolvio la imagen principal del analisis.'];
    }

    return ['ok' => true, 'payload' => $decoded];
}

function handle_audioprint_upload(int $userId, array $file): array
{
    $product = audioprint_product();
    if ($product === null) {
        return ['ok' => false, 'message' => 'Audioprint no esta configurado en la base de datos.'];
    }

    if (($file['error'] ?? UPLOAD_ERR_NO_FILE) !== UPLOAD_ERR_OK) {
        return ['ok' => false, 'message' => 'No fue posible recibir el archivo de audio.'];
    }

    $tmpPath = (string) ($file['tmp_name'] ?? '');
    $originalFilename = trim((string) ($file['name'] ?? 'audio'));
    $sizeBytes = (int) ($file['size'] ?? 0);
    $mimeType = trim((string) ($file['type'] ?? 'application/octet-stream'));

    if ($sizeBytes <= 0) {
        return ['ok' => false, 'message' => 'El archivo de audio esta vacio.'];
    }

    if ($sizeBytes > audioprint_max_upload_bytes()) {
        return ['ok' => false, 'message' => 'El archivo supera el tamano maximo permitido.'];
    }

    $uploadsDir = audioprint_storage_dir('uploads');
    $resultsDir = audioprint_storage_dir('results');
    ensure_directory($uploadsDir);
    ensure_directory($resultsDir);

    $extension = strtolower((string) pathinfo($originalFilename, PATHINFO_EXTENSION));
    $safeExtension = $extension !== '' ? preg_replace('/[^a-z0-9]/', '', $extension) : 'bin';
    $baseName = 'audio_' . date('Ymd_His') . '_' . bin2hex(random_bytes(6));
    $audioFilename = $baseName . '.' . ($safeExtension !== '' ? $safeExtension : 'bin');
    $audioPath = $uploadsDir . '/' . $audioFilename;
    $audioUrl = audioprint_public_url('uploads', $audioFilename);

    if (!move_uploaded_file($tmpPath, $audioPath)) {
        return ['ok' => false, 'message' => 'No fue posible guardar el audio subido.'];
    }

    $jobId = create_audio_job_record($userId, (int) $product['id'], $originalFilename, $mimeType, $sizeBytes, $audioPath, $audioUrl);
    $apiResult = audioprint_call_scalogram_api($audioPath, $mimeType, $originalFilename);
    if (($apiResult['ok'] ?? false) !== true) {
        finalize_audio_job($jobId, 'failed', null, null, (string) ($apiResult['message'] ?? 'La API devolvio un error.'));
        return ['ok' => false, 'message' => (string) ($apiResult['message'] ?? 'La API devolvio un error.')];
    }

    $analysisPayload = $apiResult['payload'] ?? null;
    if (!is_array($analysisPayload)) {
        finalize_audio_job($jobId, 'failed', null, null, 'La API no devolvio un analisis interpretable.');
        return ['ok' => false, 'message' => 'La API no devolvio un analisis interpretable.'];
    }

    $scalogramFilename = $baseName . '.png';
    $scalogramPath = $resultsDir . '/' . $scalogramFilename;
    $scalogramUrl = audioprint_public_url('results', $scalogramFilename);
    $analysisFilename = $baseName . '.json';
    $analysisPath = $resultsDir . '/' . $analysisFilename;

    $primaryImageBase64 = (string) ($analysisPayload['image_base64'] ?? '');
    $primaryImageBytes = base64_decode($primaryImageBase64, true);
    if (!is_string($primaryImageBytes) || $primaryImageBytes === '') {
        finalize_audio_job($jobId, 'failed', null, null, 'La API devolvio una imagen principal no valida.');
        return ['ok' => false, 'message' => 'La API devolvio una imagen principal no valida.'];
    }

    if (file_put_contents($scalogramPath, $primaryImageBytes) === false) {
        finalize_audio_job($jobId, 'failed', null, null, 'No fue posible guardar la imagen principal del analisis.');
        return ['ok' => false, 'message' => 'No fue posible guardar la imagen principal del analisis.'];
    }

    $analysisJson = json_encode($analysisPayload, JSON_PRETTY_PRINT | JSON_UNESCAPED_SLASHES);
    if (!is_string($analysisJson) || file_put_contents($analysisPath, $analysisJson) === false) {
        @unlink($scalogramPath);
        finalize_audio_job($jobId, 'failed', null, null, 'No fue posible guardar el analisis generado.');
        return ['ok' => false, 'message' => 'No fue posible guardar el analisis generado.'];
    }

    finalize_audio_job($jobId, 'completed', $scalogramPath, $scalogramUrl, null);

    return ['ok' => true, 'job_id' => $jobId];
}
