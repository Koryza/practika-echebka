package ru.systemmonitor.mobile

import org.junit.Assert.assertEquals
import org.junit.Assert.assertThrows
import org.junit.Test

class ConnectionSettingsTest {
    @Test
    fun rejectsAddressComponentsOutsideTheHost() {
        for (host in listOf("bad/path", "bad?query", "bad#fragment", "10.0.2.2:8080", "http://mac.local")) {
            assertThrows(host, IllegalArgumentException::class.java) {
                ConnectionSettings.fromInput(host, "8080", "5")
            }
        }
    }

    @Test
    fun acceptsEmulatorAddressAndHostname() {
        val emulator = ConnectionSettings.fromInput(" 10.0.2.2 ", "8080", "5")
        assertEquals("http://10.0.2.2:8080/api/status", emulator.endpoint("/api/status").toString())
        val namedHost = ConnectionSettings.fromInput("mac.local", "9090", "10")
        assertEquals("http://mac.local:9090/api/health", namedHost.endpoint("/api/health").toString())
    }

    @Test
    fun rejectsPortsAndIntervalsOutsideSupportedRanges() {
        for (port in listOf("0", "65536", "abc")) {
            assertThrows(IllegalArgumentException::class.java) {
                ConnectionSettings.fromInput("10.0.2.2", port, "5")
            }
        }
        for (interval in listOf("0", "3601", "abc")) {
            assertThrows(IllegalArgumentException::class.java) {
                ConnectionSettings.fromInput("10.0.2.2", "8080", interval)
            }
        }
    }
}
