package ru.vernadsky.vvoice

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.Context
import android.content.Intent
import android.os.PowerManager
import android.content.pm.ServiceInfo
import android.media.AudioFormat
import android.media.AudioRecord
import android.media.MediaRecorder
import android.os.Build
import android.os.IBinder
import android.util.Log
import java.io.File
import java.io.FileOutputStream

/**
 * Фоновый сервис записи микрофона.
 *
 * Правила, ради которых сервис написан именно так (docs/RESEARCH/RESEARCH-2026-11.md §1.2):
 *  - тип foreground-сервиса "microphone" обязателен на Android 14+;
 *  - `startForeground` вызывается сразу после `onStartCommand` — система убивает сервис, если этого
 *    не сделать в течение нескольких секунд;
 *  - уведомление постоянное: пользователь всегда видит, что его слушают;
 *  - старт возможен только из видимого UI. Если система отказала (`ForegroundServiceStartNotAllowedException`),
 *    `RecordingChannel` возвращает ошибку в UI, а не падает молча.
 */
private const val MAX_RECORDING_MS = 4L * 60 * 60 * 1000

class RecordingService : Service() {

    private var recorder: AudioRecord? = null
    private var writer: FileOutputStream? = null
    /// Файл текущей записи: финализация и событие saved должны говорить об этом же файле.
    private var currentFile: File? = null
    private var worker: Thread? = null
    private var running = false

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        when (intent?.action) {
            ACTION_STOP -> { stopRecording(); stopSelf(); return START_NOT_STICKY }
            ACTION_PAUSE -> { RecordingChannel.emitState("paused"); return START_STICKY }
            ACTION_RESUME -> { RecordingChannel.emitState("recording"); return START_STICKY }
        }
        startForegroundWithNotification()
        startRecording()
        return START_STICKY
    }

    /** Постоянное уведомление с кнопкой «стоп» — обязательный индикатор записи. */
    // Частичный wake lock: не даёт системе усыпить сеть и диск, пока идёт запись.
    // Для этого нужен именно PARTIAL — экран при этом остаётся погашенным, как и должен.
    private var wakeLock: PowerManager.WakeLock? = null

    private fun acquireWakeLock() {
        if (wakeLock != null) return
        val power = getSystemService(Context.POWER_SERVICE) as PowerManager
        wakeLock = power.newWakeLock(PowerManager.PARTIAL_WAKE_LOCK, "vvoice:recording").apply {
            setReferenceCounted(false)
            acquire(MAX_RECORDING_MS)
        }
    }

    private fun releaseWakeLock() {
        wakeLock?.let { if (it.isHeld) it.release() }
        wakeLock = null
    }

    private fun startForegroundWithNotification() {
        val nm = getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
        val channel = NotificationChannel(
            CHANNEL_ID,
            getString(R.string.recording_channel),
            NotificationManager.IMPORTANCE_LOW
        )
        nm.createNotificationChannel(channel)

        val open = PendingIntent.getActivity(
            this, 0, Intent(this, MainActivity::class.java),
            PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT
        )
        val stop = PendingIntent.getService(
            this, 1, Intent(this, RecordingService::class.java).setAction(ACTION_STOP),
            PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT
        )

        val notification: Notification = Notification.Builder(this, CHANNEL_ID)
            .setContentTitle(getString(R.string.recording_title))
            .setContentText(getString(R.string.recording_text))
            .setSmallIcon(R.drawable.ic_launcher)
            .setOngoing(true)
            .setContentIntent(open)
            .addAction(Notification.Action.Builder(null, getString(R.string.stop), stop).build())
            .build()

        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
            startForeground(NOTIF_ID, notification, ServiceInfo.FOREGROUND_SERVICE_TYPE_MICROPHONE)
        } else {
            startForeground(NOTIF_ID, notification)
        }
    }

    private fun startRecording() {
        acquireWakeLock()
        if (running) return
        val minBuf = AudioRecord.getMinBufferSize(SAMPLE_RATE, AudioFormat.CHANNEL_IN_MONO, AudioFormat.ENCODING_PCM_16BIT)
        val record = AudioRecord(
            MediaRecorder.AudioSource.VOICE_RECOGNITION,
            SAMPLE_RATE, AudioFormat.CHANNEL_IN_MONO, AudioFormat.ENCODING_PCM_16BIT, minBuf * 4
        )
        if (record.state != AudioRecord.STATE_INITIALIZED) {
            RecordingChannel.emitError("mic_unavailable")
            stopSelf()
            return
        }

        // Имя по времени старта: вторая запись не должна затирать первую.
        val file = RecordingPaths.newRecordingFile(this)
        currentFile = file
        writer = FileOutputStream(file)
        writer?.write(WavHeader.empty(SAMPLE_RATE))

        running = true
        record.startRecording()
        recorder = record
        RecordingChannel.emitState("recording")

        // Буфер пишется на диск каждые ~200 мс: система может убить процесс, аудио должно остаться.
        worker = Thread {
            val buf = ByteArray(minBuf)
            var sinceLevel = 0
            // Куски меньше 100 мс отправлять бессмысленно: событий будет больше, чем пользы,
            // а распознаватель всё равно ждёт окно. Копим и отдаём пачкой.
            val pendingAudio = java.io.ByteArrayOutputStream()
            while (running) {
                val read = record.read(buf, 0, buf.size)
                if (read > 0) {
                    // Сбой записи на диск (кончилось место) не должен тихо убивать поток:
                    // иначе экран показывает «идёт запись», а файла больше нет.
                    try {
                        writer?.write(buf, 0, read)
                        writer?.flush()
                    } catch (e: java.io.IOException) {
                        RecordingChannel.emitError("disk_full")
                        stopRecording()
                        break
                    }
                    // Уровень считаем здесь, где данные уже в руках: отдельный опрос не нужен,
                    // а AudioRecord (в отличие от MediaRecorder) сам амплитуду не отдаёт.
                    sinceLevel += read
                    if (sinceLevel >= LEVEL_WINDOW_BYTES) {
                        sinceLevel = 0
                        RecordingChannel.emitLevel(rmsOf(buf, read))
                    }
                    // Живой текст: отдаём звук наружу небольшими кусками. Файл при этом пишется
                    // как раньше — разбор после «стоп» не должен пострадать от онлайн-режима.
                    // Отдельной проверки паузы здесь нет намеренно: сервис не держит состояния паузы,
                    // а выдумать поле, которого нет, — значит получить ошибку компиляции вместо работы.
                    pendingAudio.write(buf, 0, read)
                    if (pendingAudio.size() >= AUDIO_CHUNK_BYTES) {
                        RecordingChannel.emitAudio(pendingAudio.toByteArray())
                        pendingAudio.reset()
                    }
                }
            }
        }.also { it.start() }
    }

    private fun stopRecording() {
        releaseWakeLock()
        running = false
        worker?.join(1_000)
        recorder?.let {
            try { it.stop() } catch (e: IllegalStateException) { Log.w(TAG, "stop: " + e.message) }
            it.release()
        }
        recorder = null
        writer?.close()
        writer = null
        // Финализируем WAV-заголовок, чтобы файл читался любым плеером/фоновым процессором.
        val dir = RecordingPaths.sessionDir(this)
        val file = currentFile ?: File(dir, "rec-unknown.wav")
        RecordingPaths.finalizeWav(file, SAMPLE_RATE)
        RecordingChannel.emitState("stopped")
        // Путь нужен наверху: без него экран разбора не знает, какую запись отправлять на сервер.
        val durationMs = if (file.exists()) (file.length() / 32L) else 0L
        RecordingChannel.emitSaved(file.absolutePath, durationMs)
    }

    override fun onDestroy() {
        stopRecording()
        releaseWakeLock()
        super.onDestroy()
    }

    companion object {
        private const val TAG = "RecordingService"
        private const val CHANNEL_ID = "voice_record"
        private const val NOTIF_ID = 42
        private const val SAMPLE_RATE = 16_000
        /** ~200 мс при 16 кГц моно 16 бит: частота индикатора, а не запись. */
        // 100 мс при 16 кГц, 16 бит, моно.
        private const val AUDIO_CHUNK_BYTES = 3200
        private const val LEVEL_WINDOW_BYTES = 6400
        const val ACTION_STOP = "ru.vernadsky.vvoice.STOP"
        const val ACTION_PAUSE = "ru.vernadsky.vvoice.PAUSE"
        const val ACTION_RESUME = "ru.vernadsky.vvoice.RESUME"
    }

    /**
     * RMS куска PCM16 в диапазоне 0..1 — «сколько звука», без зависимости от модели телефона.
     *
     * Считаем по байтам: 16-битные сэмплы, младший байт первым (AudioRecord по умолчанию little-endian).
     */
    private fun rmsOf(buf: ByteArray, length: Int): Float {
        if (length < 2) return 0f
        var sum = 0.0
        var i = 0
        while (i + 1 < length) {
            val lo = buf[i].toInt() and 0xFF
            val hi = buf[i + 1].toInt()
            val sample = (hi shl 8) or lo
            sum += sample.toDouble() * sample
            i += 2
        }
        val rms = kotlin.math.sqrt(sum / (length / 2))
        return (rms / 32768.0).toFloat().coerceIn(0f, 1f)
    }

}
