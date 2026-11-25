package ru.systemmonitor.mobile

import android.content.Context
import java.net.URI
import java.net.URISyntaxException

internal data class ConnectionSettings(
    val host: String = "10.0.2.2",
    val port: Int = 8080,
    val intervalSeconds: Int = 5,
) {
    fun endpoint(path: String): URI = URI("http", null, host, port, path, null, null)

    companion object {
        fun fromInput(hostText: String, portText: String, intervalText: String): ConnectionSettings {
            val host = hostText.trim()
            val address = try {
                URI("http", null, host, -1, null, null, null)
            } catch (_: URISyntaxException) {
                null
            }
            require(address?.host != null && address.rawUserInfo == null && address.port == -1) {
                "Введите IP-адрес или имя компьютера без порта и пути."
            }
            val port = portText.trim().toIntOrNull()
            require(port != null && port in 1..65535) { "Введите порт от 1 до 65535." }
            val interval = intervalText.trim().toIntOrNull()
            require(interval != null && interval in 1..3600) {
                "Введите интервал от 1 до 3600 секунд."
            }
            return ConnectionSettings(host, port, interval)
        }
    }
}

internal class SettingsStore(context: Context) {
    private val preferences = context.getSharedPreferences("connection", Context.MODE_PRIVATE)

    fun load(): ConnectionSettings = try {
        ConnectionSettings.fromInput(
            preferences.getString("host", "10.0.2.2").orEmpty(),
            preferences.getInt("port", 8080).toString(),
            preferences.getInt("interval", 5).toString(),
        )
    } catch (_: IllegalArgumentException) {
        ConnectionSettings()
    }

    fun save(settings: ConnectionSettings) {
        preferences.edit()
            .putString("host", settings.host)
            .putInt("port", settings.port)
            .putInt("interval", settings.intervalSeconds)
            .apply()
    }
}
