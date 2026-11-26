package ru.vernadsky.vvoice

import android.Manifest
import androidx.annotation.NonNull
import androidx.core.app.ActivityCompat
import io.flutter.embedding.android.FlutterActivity
import io.flutter.embedding.engine.FlutterEngine

/**
 * Единственная Activity: хостит Flutter и регистрирует канал записи.
 *
 * Важно для Android 12+: старт сервиса записи возможен только пока Activity видима
 * (после `onPause` — уже фон). Поэтому кнопка «Слушаю» живёт именно здесь.
 */
class MainActivity : FlutterActivity() {

    override fun configureFlutterEngine(@NonNull flutterEngine: FlutterEngine) {
        super.configureFlutterEngine(flutterEngine)
        RecordingChannel(this, flutterEngine.dartExecutor.binaryMessenger)
        RecordingChannel.attach(flutterEngine.dartExecutor.binaryMessenger)
        ActivityCompat.requestPermissions(
            this,
            arrayOf(Manifest.permission.RECORD_AUDIO, Manifest.permission.POST_NOTIFICATIONS),
            REQ_PERMISSIONS
        )
    }

    companion object { private const val REQ_PERMISSIONS = 1001 }
}
