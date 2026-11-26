import Flutter
import UIKit

/// MethodChannel "vvoice/recording" — тот же контракт, что и в Android (RecordingChannel.kt).
///   start() -> "ok" | "denied" | "session_failed" | "engine_failed" | "mic_unavailable"
///   stop()  -> "ok"
///   state   -> idle | recording | paused | stopped
final class RecordingChannel {

    private let engine = RecordingEngine()
    private var channel: FlutterMethodChannel?

    init(messenger: FlutterBinaryMessenger) {
        channel = FlutterMethodChannel(name: "vvoice/recording", binaryMessenger: messenger)
        channel?.setMethodCallHandler { [weak self] call, result in
            switch call.method {
            case "start":
                guard AVAudioSession.sharedInstance().recordPermission == .granted else { result("denied"); return }
                if let reason = self?.engine.start() { result(reason) } else { result("ok") }
            case "stop":
                self?.engine.stop(); result("ok")
            case "state":
                result(RecordingChannel.state)
            default:
                result(FlutterMethodNotImplemented)
            }
        }

        let events = FlutterEventChannel(name: "vvoice/recording/events", binaryMessenger: messenger)
        events.setStreamHandler(RecordingChannel.eventHandler)
    }

    // MARK: - Мост наружу (общий для iOS и Android по имени канала)

    static var state = "idle"
    private static var sink: FlutterEventSink?
    static let eventHandler = Events()

    static func emitState(_ value: String) { state = value; sink?(["type": "state", "value": value] as [String: Any]) }
    static func emitLevel(_ rms: Float) { sink?(["type": "level", "value": rms] as [String: Any]) }
    static func emitError(code: String) { sink?(["type": "error", "code": code] as [String: Any]) }

    final class Events: NSObject, FlutterStreamHandler {
        func onListen(withArguments arguments: Any?, eventSink events: @escaping FlutterEventSink) -> FlutterError? {
            RecordingChannel.sink = events; return nil
        }
        func onCancel(withArguments arguments: Any?) -> FlutterError? {
            RecordingChannel.sink = nil; return nil
        }
    }
}
