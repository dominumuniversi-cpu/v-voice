import Foundation

/// Сегменты записи лежат во внутренней папке приложения: не требует разрешений и живёт при сбоях.
enum RecordingPaths {
    static func sessionDirectory() -> URL {
        let base = FileManager.default.urls(for: .documentDirectory, in: .userDomainMask)[0]
        let dir = base.appendingPathComponent("recordings", isDirectory: true)
        if !FileManager.default.fileExists(atPath: dir.path) {
            try? FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
        }
        return dir
    }

    /// Новый файл фрагмента. Имя — по времени, чтобы порядок восстанавливался без метаданных.
    static func nextSegmentURL() -> URL {
        let stamp = Int(Date().timeIntervalSince1970 * 1000)
        return sessionDirectory().appendingPathComponent("segment-\(stamp).caf")
    }
}
