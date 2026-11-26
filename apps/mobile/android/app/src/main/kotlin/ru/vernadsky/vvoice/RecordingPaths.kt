package ru.vernadsky.vvoice

import android.content.Context
import java.io.File
import java.io.RandomAccessFile

/** Куда пишем аудио: внутренняя память приложения (не требует разрешений, доступна всегда). */
object RecordingPaths {
    /**
     * Новый файл для новой записи: имя включает время старта.
     *
     * Почему не одно имя на всех: раньше каждая запись писалась в segment.wav, и вторая
     * молча уничтожала первую. Человек узнавал об этом, когда пытался открыть вчерашнее совещание.
     */
    fun newRecordingFile(context: Context, startedAtMs: Long = System.currentTimeMillis()): File {
        val stamp = java.text.SimpleDateFormat("yyyyMMdd-HHmmss", java.util.Locale.US)
            .format(java.util.Date(startedAtMs))
        return File(sessionDir(context), "rec-" + stamp + ".wav")
    }

    fun sessionDir(context: Context): File {
        val dir = File(context.filesDir, "recordings")
        if (!dir.exists()) dir.mkdirs()
        return dir
    }

    /** Заранее пишем пустой WAV-заголовок, чтобы после падения процесса файл уже был валидным. */
    /**
     * Дописывает WAV-заголовок под фактическую длину файла.
     *
     * Файл передаётся аргументом: после перехода на имена по времени зашитое «segment.wav»
     * чинило бы несуществующий файл, и запись оставалась бы битой.
     */
    fun finalizeWav(file: File, sampleRate: Int) {
        if (!file.exists()) return
        val dataLen = (file.length() - 44).coerceAtLeast(0).toInt()
        RandomAccessFile(file, "rw").use { raf ->
            raf.seek(4); raf.write(WavHeader.intLE(36 + dataLen))
            raf.seek(40); raf.write(WavHeader.intLE(dataLen))
        }
    }
}

/** Минимальный RIFF/WAVE-заголовок для LPCM 16 kHz mono 16 bit. */
object WavHeader {
    const val SAMPLE_RATE = 16000
    fun empty(sampleRate: Int): ByteArray = header(sampleRate, 0)
    fun intLE(v: Int) = byteArrayOf((v and 0xFF).toByte(), ((v shr 8) and 0xFF).toByte(), ((v shr 16) and 0xFF).toByte(), ((v shr 24) and 0xFF).toByte())
    private fun header(sampleRate: Int, dataLen: Int): ByteArray {
        val bytes = ByteArray(44)
        var i = 0
        fun put(s: String) { for (c in s.toByteArray()) bytes[i++] = c }
        fun putInt(v: Int) { intLE(v).forEach { bytes[i++] = it } }
        fun putShort(v: Int) { bytes[i++] = (v and 0xFF).toByte(); bytes[i++] = ((v shr 8) and 0xFF).toByte() }
        put("RIFF"); putInt(36 + dataLen); put("WAVE")
        put("fmt "); putInt(16); putShort(1); putShort(1)
        putInt(sampleRate); putInt(sampleRate * 2); putShort(2); putShort(16)
        put("data"); putInt(dataLen)
        return bytes
    }
}
