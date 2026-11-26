import Flutter
import UIKit

/// Точка входа iOS-приложения.
///
/// Без этого файла канал записи на iOS не регистрируется вообще: приложение собралось бы,
/// но кнопка «Слушаю» молча ничего не делала бы — Dart видит «канал не найден» и получает
/// невнятную ошибку. Android-половина регистрирует канал в MainActivity, iOS должен здесь.
@main
@objc class AppDelegate: FlutterAppDelegate {
    /// Держим ссылку: канал обязан жить, пока живо приложение, иначе обработчик вызовов умирает.
    private var recordingChannel: RecordingChannel?

    override func application(
        _ application: UIApplication,
        didFinishLaunchingWithOptions launchOptions: [UIApplication.LaunchOptionsKey: Any]?
    ) -> Bool {
        let controller = window?.rootViewController as? FlutterViewController
        if let controller = controller {
            recordingChannel = RecordingChannel(messenger: controller.binaryMessenger)
        }
        GeneratedPluginRegistrant.register(with: self)
        return super.application(application, didFinishLaunchingWithOptions: launchOptions)
    }
}
