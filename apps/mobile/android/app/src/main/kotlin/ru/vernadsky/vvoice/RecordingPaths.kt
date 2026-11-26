package ru.vernadsky.vvoice

import android.content.Context
import java.io.File
import java.io.RandomAccessFile

/** Куда пишем аудио: внутренняя память приложения (не требует разрешений, доступна всегда). */
object RecordingPaths {
    fun sessionDir(context: Context): File {
        val dir = File(context.filesDir, "recordings")
        if (!dir.exists()) dir.mkdirs()
        return dir
    }

    /** Заранее пишем пустой WAV-заголовок, чтобы после падения процесса файл уже был валидным. */
    fun finalizeWav(dir: File, sampleRate: Int) {
        val file = File(dir, "segment.wav")
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
