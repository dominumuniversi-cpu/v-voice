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
                "state" -> result.success(state)
                else -> result.notImplemented()
            }
        }
    }

    /**
     * Старт записи. Разрешён только из видимого UI: Android 12+ запрещает создавать
     * микрофонный foreground-сервис из фона, Android 14+ — вообще требование платформы.
     * Возвращаем причину, чтобы приложение показало человеку понятный экран, а не «ничего не произошло».
     */
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
