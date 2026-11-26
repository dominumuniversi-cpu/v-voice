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
            do {
                try self?.file?.write(from: buffer)
            } catch {
                // Место кончилось или файл недоступен: честно останавливаемся, иначе экран врёт.
                RecordingChannel.emitError(code: "disk_full")
                DispatchQueue.main.async { self?.stop() }
                return
            }
            RecordingChannel.emitLevel(RecordingEngine.rms(buffer))
        }

        engine.prepare()
        do { try engine.start() } catch {
            input.removeTap(onBus: 0)
            return "engine_failed"
        }

        observeSystemEvents()
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

    /// Подписка на события системы, которые МОГУТ остановить запись.
    ///
    /// Почему это обязательно: звонок или выдёргивание наушников останавливает ввод, а без подписки
    /// приложение об этом не узнаёт. Человек уверен, что пишет совещание, а записи уже нет.
    private func observeSystemEvents() {
        let center = NotificationCenter.default
        center.addObserver(self, selector: #selector(handleInterruption(_:)),
                           name: AVAudioSession.interruptionNotification, object: nil)
        center.addObserver(self, selector: #selector(handleRouteChange(_:)),
                           name: AVAudioSession.routeChangeNotification, object: nil)
    }

    @objc private func handleInterruption(_ note: Notification) {
        guard isRecording,
              let raw = note.userInfo?[AVAudioSessionInterruptionTypeKey] as? UInt,
              let kind = AVAudioSession.InterruptionType(rawValue: raw) else { return }
        switch kind {
        case .began:
            // Говорим правду: запись стоит, человек должен это увидеть, а не догадываться.
            RecordingChannel.emitError(code: "recording_interrupted")
        case .ended:
            // Продолжаем только если система разрешает — без согласия она отберёт микрофон снова.
            let options = (note.userInfo?[AVAudioSessionInterruptionOptionKey] as? UInt)
                .map { AVAudioSession.InterruptionOptions(rawValue: $0) }
            if options?.contains(.shouldResume) ?? false {
                do {
                    try AVAudioSession.sharedInstance().setActive(true)
                    if !engine.isRunning { try engine.start() }
                    RecordingChannel.emitState("recording")
                } catch {
                    RecordingChannel.emitError(code: "resume_failed")
                }
            } else {
                RecordingChannel.emitState("paused")
            }
        @unknown default:
            return
        }
    }

    @objc private func handleRouteChange(_ note: Notification) {
        guard isRecording,
              let raw = note.userInfo?[AVAudioSessionRouteChangeReasonKey] as? UInt,
              let reason = AVAudioSession.RouteChangeReason(rawValue: raw) else { return }
        // Потеря устройства ввода — не повод притворяться, что пишем: сообщаем наверх.
        if reason == .oldDeviceUnavailable {
            let inputs = AVAudioSession.sharedInstance().currentRoute.inputs
            if inputs.isEmpty { RecordingChannel.emitError(code: "input_lost") }
        }
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
