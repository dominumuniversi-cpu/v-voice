package ru.vernadsky.vvoice

import android.Manifest
import android.content.Context
import android.content.pm.PackageManager
import androidx.core.content.ContextCompat

/** Проверка runtime-разрешений до старта сервиса: без микрофона запись бессмысленна. */
object RecordingPermissions {
    fun hasMicrophone(context: Context): Boolean =
        ContextCompat.checkSelfPermission(context, Manifest.permission.RECORD_AUDIO) == PackageManager.PERMISSION_GRANTED
}
