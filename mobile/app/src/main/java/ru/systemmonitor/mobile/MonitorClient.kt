package ru.systemmonitor.mobile

import android.net.ConnectivityManager
import org.json.JSONException
import org.json.JSONObject
import java.io.ByteArrayOutputStream
import java.io.IOException
import java.net.ConnectException
import java.net.HttpURLConnection
import java.net.Proxy
import java.net.SocketTimeoutException
import java.net.UnknownHostException
import java.time.Instant
import java.time.format.DateTimeParseException

internal data class MonitorReading(
    val computerName: String,
    val sampledAt: Instant,
    val cpuPercent: Double?,
    val memoryPercent: Double?,
    val diskPercent: Double?,
    val diskName: String?,
)

internal class MonitorException(message: String) : Exception(message)

internal class MonitorClient(private val connectivity: ConnectivityManager) {
    fun check(settings: ConnectionSettings) {
        val response = request(settings, "/api/health")
        if (response.opt("status") != "ok") throw MonitorException(INVALID_RESPONSE)
    }

    fun read(settings: ConnectionSettings): MonitorReading {
        val response = request(settings, "/api/status")
        try {
            val computer = response.get("computerName") as? String ?: invalidResponse()
            if (computer.isBlank()) invalidResponse()
            val timestamp = response.get("timestamp") as? String ?: invalidResponse()
            val cpu = response.getJSONObject("cpu")
            val memory = response.getJSONObject("memory")
            val disk = when (val value = response.get("disk")) {
                JSONObject.NULL -> null
                is JSONObject -> value
                else -> invalidResponse()
            }
            val name = if (disk != null) {
                disk.get("name") as? String ?: invalidResponse()
            } else {
                null
            }
            return MonitorReading(
                computerName = computer,
                sampledAt = Instant.parse(timestamp),
                cpuPercent = cpu.readPercent(),
                memoryPercent = memory.readPercent(),
                diskPercent = disk?.readPercent(),
                diskName = name,
            )
        } catch (_: JSONException) {
            invalidResponse()
        } catch (_: DateTimeParseException) {
            invalidResponse()
        }
    }

    private fun request(settings: ConnectionSettings, path: String): JSONObject {
        if (connectivity.activeNetwork == null) throw MonitorException("Нет подключения к сети.")
        var connection: HttpURLConnection? = null
        try {
            connection = settings.endpoint(path).toURL().openConnection(Proxy.NO_PROXY) as HttpURLConnection
            connection.connectTimeout = 2500
            connection.readTimeout = 2500
            connection.instanceFollowRedirects = false
            connection.useCaches = false
            connection.setRequestProperty("Accept", "application/json")
            when (connection.responseCode) {
                200 -> Unit
                503 -> throw MonitorException("Сервер пока не получил свежий замер.")
                else -> throw MonitorException("Сервер вернул ошибку HTTP ${connection.responseCode}.")
            }
            val body = connection.inputStream.use { source ->
                val output = ByteArrayOutputStream()
                val chunk = ByteArray(4096)
                while (true) {
                    val size = source.read(chunk)
                    if (size == -1) break
                    if (output.size() + size > 32_768) invalidResponse()
                    output.write(chunk, 0, size)
                }
                output.toString(Charsets.UTF_8.name())
            }
            return JSONObject(body)
        } catch (_: SocketTimeoutException) {
            throw MonitorException("Сервер не ответил вовремя.")
        } catch (_: UnknownHostException) {
            throw MonitorException("Не удалось найти компьютер по этому адресу.")
        } catch (_: ConnectException) {
            throw MonitorException("System Monitor на Mac недоступен.")
        } catch (_: IOException) {
            throw MonitorException("Не удалось связаться с сервером.")
        } catch (_: JSONException) {
            invalidResponse()
        } finally {
            connection?.disconnect()
        }
    }

    private fun JSONObject.readPercent(): Double? = when (val value = get("usagePercent")) {
        JSONObject.NULL -> null
        is Number -> value.toDouble().takeIf { it in 0.0..100.0 } ?: invalidResponse()
        else -> invalidResponse()
    }

    private fun invalidResponse(): Nothing = throw MonitorException(INVALID_RESPONSE)

    private companion object {
        const val INVALID_RESPONSE = "Сервер вернул некорректные данные."
    }
}
