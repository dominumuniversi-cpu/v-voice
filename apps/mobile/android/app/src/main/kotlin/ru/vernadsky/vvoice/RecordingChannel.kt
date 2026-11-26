package ru.vernadsky.vvoice

import android.app.ForegroundServiceStartNotAllowedException
import android.content.Context
import android.content.Intent
import android.os.Build
import android.util.Log
import io.flutter.plugin.common.BinaryMessenger
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

        private var eventSink: MethodChannel.EventSink? = null

        fun attach(messenger: BinaryMessenger) {
            MethodChannel(messenger, CHANNEL + "/events").setMethodCallHandler { call, result ->
                if (call.method == "listen") { eventSink = call.arguments as MethodChannel.EventSink?; result.success(null) }
                else result.notImplemented()
            }
        }

        fun emitState(newState: String) { state = newState; eventSink?.success(mapOf("type" to "state", "value" to newState)) }
        fun emitError(code: String) { eventSink?.success(mapOf("type" to "error", "code" to code)) }
    }
}
