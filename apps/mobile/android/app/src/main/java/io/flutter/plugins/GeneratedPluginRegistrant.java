package io.flutter.plugins;

import androidx.annotation.Keep;
import androidx.annotation.NonNull;
import io.flutter.embedding.engine.FlutterEngine;
import io.flutter.plugin.common.PluginRegistry;

/**
 * Файл, по которому Flutter определяет, что проект использует embedding v2.
 * При добавлении плагинов (pubspec) его перезаписывает флаттер-тулчейн при сборке.
 */
@Keep
public final class GeneratedPluginRegistrant {
  private static final String TAG = "GeneratedPluginRegistrant";

  public static void registerWith(@NonNull FlutterEngine flutterEngine) {
    // Плагинов не подключено: канал записи регистрируется вручную в MainActivity.
  }
}
