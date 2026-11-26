import AVFoundation
import UIKit

/// Движок записи: AVAudioEngine + запись на диск фрагментами.
///
/// Почему так:
///  - сессия .record + фоновый режим audio даёт запись при погашенном экране, пока приложение живо;
///  - данные пишутся на диск каждые пару секунд, поэтому убийство процесса не съедает запись;
///  - когда система приостанавливает процесс ( фоновая квота ), буфер сохраняется и догружается.
final class RecordingEngine {

    enum EngineError: Error { case sessionFailed(Error), engineFailed(Error), fileFailed(Error) }

    private let engine = AVAudioEngine()
    private var file: AVAudioFile?
    private var backgroundTask: UIBackgroundTaskIdentifier = .invalid
    private(set) var isRecording = false

    /// Старт записи. Возвращает nil при успехе, иначе человекочитаемую причину.
    func start() -> String? {
        do {
            let session = AVAudioSession.sharedInstance()
            try session.setCategory(.playAndRecord, mode: .measurement, options: [.defaultToSpeaker, .allowBluetooth])
            try session.setActive(true)
        } catch {
            return "session_failed"
        }

        let input = engine.inputNode
        let format = input.outputFormat(forBus: 0)
        guard format.sampleRate > 0 else { return "mic_unavailable" }

        let url = RecordingPaths.nextSegmentURL()
        do {
            file = try AVAudioFile(forWriting: url, settings: format.settings)
        } catch {
            return "file_failed"
        }

        input.installTap(onBus: 0, bufferSize: 4096, format: format) { [weak self] buffer, _ in
            do { try self?.file?.write(from: buffer) } catch { RecordingChannel.emitError(code: "write_failed") }
            RecordingChannel.emitLevel(RecordingEngine.rms(buffer))
        }

        engine.prepare()
        do { try engine.start() } catch {
            input.removeTap(onBus: 0)
            return "engine_failed"
        }

        beginBackgroundBudget()
        isRecording = true
        RecordingChannel.emitState("recording")
        return nil
    }

    func stop() {
        guard isRecording else { return }
        isRecording = false
        engine.inputNode.removeTap(onBus: 0)
        engine.stop()
        file = nil
        endBackgroundBudget()
        try? AVAudioSession.sharedInstance().setActive(false, options: [.notifyOthersOnDeactivation])
        RecordingChannel.emitState("stopped")
    }

    /// Короткое продление жизни в фоне: покупаем время на закрытие файлов и досыл сегментов.
    private func beginBackgroundBudget() {
        backgroundTask = UIApplication.shared.beginBackgroundTask(withName: "vvoice.record") { [weak self] in
            self?.file = nil
            self?.endBackgroundBudget()
        }
    }

    private func endBackgroundBudget() {
        if backgroundTask != .invalid {
            UIApplication.shared.endBackgroundTask(backgroundTask)
            backgroundTask = .invalid
        }
    }

    private static func rms(_ buffer: AVAudioPCMBuffer) -> Float {
        guard let data = buffer.floatChannelData?[0] else { return 0 }
        let n = Int(buffer.frameLength)
        guard n > 0 else { return 0 }
        var sum: Float = 0
        for i in 0..<n { sum += data[i] * data[i] }
        return (sum / Float(n)).squareRoot()
    }
}
