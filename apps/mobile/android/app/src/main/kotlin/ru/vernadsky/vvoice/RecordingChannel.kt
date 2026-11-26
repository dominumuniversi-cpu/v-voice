package ru.vernadsky.vvoice

import android.app.ForegroundServiceStartNotAllowedException
import android.content.Context
import android.content.Intent
import android.os.Build
import android.util.Log
import io.flutter.plugin.common.BinaryMessenger
import io.flutter.plugin.common.EventChannel
import io.flutter.plugin.common.MethodCall
import io.flutter.plugin.common.MethodChannel

/**
 * MethodChannel "vvoice/recording" — единственная дверь между Flutter и нативным сервисом записи.
 *
 * Контракт (совпадает с iOS-частью, см. RecordingChannel.swift):
 *   start()  -> "ok" | "denied" | "not_allowed_in_background"
 *   stop()   -> "ok"
 *   state    -> "idle" | "recording" | "paused" | "stopped"
 *   events   -> поток состояний и ошибок в UI (state, error)
 */
class RecordingChannel(private val context: Context, messenger: BinaryMessenger) {

    private val channel = MethodChannel(messenger, CHANNEL)

    init {
        channel.setMethodCallHandler { call: MethodCall, result: MethodChannel.Result ->
            when (call.method) {
                "start" -> result.success(start())
                "stop" -> { context.stopService(Intent(context, RecordingService::class.java)); result.success("ok") }
                // Пауза обязана реально прекращать запись. Раньше действия ACTION_PAUSE/ACTION_RESUME
                // только меняли надпись состояния, микрофон продолжал писать — человек думал, что
                // запись встала, а она шла. Теперь сервис по этим действиям звук не пишет.
                "pause" -> { sendAction(RecordingService.ACTION_PAUSE); result.success("ok") }
                "resume" -> { sendAction(RecordingService.ACTION_RESUME); result.success("ok") }
                "state" -> result.success(state)
                // «Телефон разрешает нам работать в фоне» — на Xiaomi/Huawei/Oppo ответ часто нет,
                // и человек об этом не знает, пока не потеряет запись встречи.
                "batteryRestricted" -> result.success(batteryRestricted())
                "openBatterySettings" -> { openBatterySettings(); result.success("ok") }
                // Записи, лежащие на телефоне. Нужны после падения процесса: файл цел (заголовок
                // WAV обновляется на лету), но приложение о нём не знает — и разговор пропадает.
                "listRecordings" -> result.success(listRecordings())
                else -> result.notImplemented()
            }
        }
    }

    /**
     * Старт записи. Разрешён только из видимого UI: Android 12+ запрещает создавать
     * микрофонный foreground-сервис из фона, Android 14+ — вообще требование платформы.
     * Возвращаем причину, чтобы приложение показало человеку понятный экран, а не «ничего не произошло».
     */
    /**
     * Передаёт действие сервису записи. Без этого вызова команда из Dart никого не достигает.
     *
     * Пауза законна и из фона: сервис уже работает, поэтому startService безопасен.
     * На Android 12+ startForegroundService из фона даёт исключение — не ловим им паузу.
     */
    private fun sendAction(action: String) {
        val intent = Intent(context, RecordingService::class.java).setAction(action)
        try {
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) context.startForegroundService(intent)
            else context.startService(intent)
        } catch (e: Exception) {
            // Сервис не работает — паузе нечего останавливать. Молча: нечего чинить человеку.
            Log.w(TAG, "action " + action + " not delivered: " + e.message)
        }
    }

    /** true — система ограничивает фон, запись может оборваться без предупреждения. */
    /** Все записи на телефоне, свежие сверху. Только имя, путь, размер и время — без чтения звука. */
    private fun listRecordings(): List<Map<String, Any>> {
        val dir = RecordingPaths.sessionDir(context)
        val files = dir.listFiles() ?: return emptyList()
        return files.filter { it.isFile && it.name.endsWith(".wav") && it.length() > 44 }
            .sortedByDescending { it.lastModified() }
            .map {
                mapOf("path" to it.absolutePath, "name" to it.name,
                      "bytes" to it.length(), "modified_ms" to it.lastModified())
            }
    }

    private fun batteryRestricted(): Boolean {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.M) return false
        val pm = context.getSystemService(Context.POWER_SERVICE) as android.os.PowerManager
        return !pm.isIgnoringBatteryOptimizations(context.packageName)
    }

    /** Открывает системный экран, где человек снимает ограничение. Сам ничего не разрешает. */
    private fun openBatterySettings() {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.M) return
        val intent = Intent(android.provider.Settings.ACTION_IGNORE_BATTERY_OPTIMIZATION_SETTINGS)
        intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
        try {
            context.startActivity(intent)
        } catch (e: Exception) {
            // Некоторые прошивки не имеют этого экрана — молча падать нельзя, но и падать незачем.
            Log.w(TAG, "battery settings unavailable: " + e.message)
        }
    }

    private fun start(): String {
        if (!RecordingPermissions.hasMicrophone(context)) return "denied"
        val intent = Intent(context, RecordingService::class.java)
        return try {
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) context.startForegroundService(intent)
            else context.startService(intent)
            state = "recording"
            "ok"
        } catch (e: ForegroundServiceStartNotAllowedException) {
            Log.w(TAG, "start denied by system: " + e.message)
            emitError("not_allowed_in_background")
            "not_allowed_in_background"
        } catch (e: Exception) {
            // На Android 8–11 этого исключения нет, но бывают SecurityException и лимит сервисов.
            // Без общего перехвата метод падал бы целиком, и человек видел бы «ничего не произошло».
            Log.w(TAG, "start failed: " + e.message)
            emitError("start_failed")
            "start_failed"
        }
    }

    companion object {
        private const val TAG = "RecordingChannel"
        const val CHANNEL = "vvoice/recording"
        var state: String = "idle"
            private set

        private var eventSink: EventChannel.EventSink? = null
        private var eventsChannel: EventChannel? = null

        fun attach(messenger: BinaryMessenger) {
            // ВАЖНО: это EventChannel, а не MethodChannel. Flutter при подписке присылает метод
            // listen/onListen и ждёт onListen-событие — на MethodChannel события не придут никогда.
            eventsChannel = EventChannel(messenger, CHANNEL + "/events")
            eventsChannel?.setStreamHandler(object : EventChannel.StreamHandler {
                override fun onListen(arguments: Any?, events: EventChannel.EventSink?) {
                    eventSink = events
                    events?.success(mapOf("type" to "state", "value" to state))
                }

                override fun onCancel(arguments: Any?) {
                    eventSink = null
                }
            })
        }

        fun emitState(newState: String) { state = newState; eventSink?.success(mapOf("type" to "state", "value" to newState)) }
        fun emitError(code: String) { eventSink?.success(mapOf("type" to "error", "code" to code)) }

        /** Уровень 0..1 для индикатора — тот же формат и имя поля, что в iOS. */
        fun emitLevel(rms: Float) { eventSink?.success(mapOf("type" to "level", "value" to rms)) }

        /**
         * Запись сохранена: путь к файлу и длительность.
         * Зачем событием, а не возвратом из stop(): stop() уже отдаёт "ok" и эту форму знает iOS;
         * ломать общий контракт ради пути дороже, чем добавить ещё одно событие.
         */
        /**
         * Кусок звука для онлайн-распознавания (PCM 16 бит, 16 кГц, моно).
         *
         * Почему через EventChannel, а не через поток Flutter: звук идёт десятки раз в секунду,
         * а канал событий уже используется для состояния — второй механизм добавил бы стык,
         * которого нет смысла проверять отдельно.
         */
        fun emitAudio(pcm: ByteArray) {
            eventSink?.success(mapOf("type" to "audio", "pcm" to pcm))
        }

        fun emitSaved(path: String, durationMs: Long) {
            eventSink?.success(mapOf("type" to "saved", "path" to path, "duration_ms" to durationMs))
        }
    }
}
