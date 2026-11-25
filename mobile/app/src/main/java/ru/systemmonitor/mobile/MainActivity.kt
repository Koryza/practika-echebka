package ru.systemmonitor.mobile

import android.app.Activity
import android.net.ConnectivityManager
import android.os.Build
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.window.OnBackInvokedCallback
import android.window.OnBackInvokedDispatcher
import java.time.Instant
import java.util.concurrent.Executors
import java.util.concurrent.Future

class MainActivity : Activity() {
    private val handler = Handler(Looper.getMainLooper())
    private val executor = Executors.newSingleThreadExecutor()
    private val poll = Runnable { refresh() }
    private lateinit var store: SettingsStore
    private lateinit var client: MonitorClient
    private lateinit var settings: ConnectionSettings
    private var monitor: MonitorScreen? = null
    private var settingsScreen: SettingsScreen? = null
    private val returnToMonitor = OnBackInvokedCallback { showMonitor() }
    private var inForeground = false
    private var generation = 0
    private var task: Future<*>? = null
    private var lastReading: ReceivedReading? = null
    private var lastError: String? = null

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        configureWindow()
        store = SettingsStore(this)
        client = MonitorClient(getSystemService(ConnectivityManager::class.java))
        settings = store.load()
        if (savedInstanceState?.getBoolean("editing") == true) {
            showSettings(SettingsInput(
                savedInstanceState.getString("host").orEmpty(),
                savedInstanceState.getString("port").orEmpty(),
                savedInstanceState.getString("interval").orEmpty(),
            ))
        } else {
            showMonitor()
        }
    }

    override fun onStart() {
        super.onStart()
        inForeground = true
        if (monitor != null) {
            if (lastReading != null) lastError = "Проверяем подключение…"
            refresh()
        }
    }

    override fun onStop() {
        inForeground = false
        cancelRequests()
        settingsScreen?.showStatus("")
        super.onStop()
    }

    override fun onSaveInstanceState(outState: Bundle) {
        settingsScreen?.input()?.let {
            outState.putBoolean("editing", true)
            outState.putString("host", it.host)
            outState.putString("port", it.port)
            outState.putString("interval", it.interval)
        }
        super.onSaveInstanceState(outState)
    }

    override fun onDestroy() {
        if (settingsScreen != null) onBackInvokedDispatcher.unregisterOnBackInvokedCallback(returnToMonitor)
        executor.shutdownNow()
        super.onDestroy()
    }

    @Suppress("DEPRECATION")
    private fun configureWindow() {
        if (Build.VERSION.SDK_INT < 35) window.setDecorFitsSystemWindows(false)
    }

    private fun showMonitor() {
        cancelRequests()
        if (settingsScreen != null) onBackInvokedDispatcher.unregisterOnBackInvokedCallback(returnToMonitor)
        settingsScreen = null
        val screen = MonitorScreen(this, { showSettings() }, ::refresh)
        monitor = screen
        setContentView(screen.view)
        screen.view.requestApplyInsets()
        if (lastReading != null) lastError = "Проверяем подключение…"
        screen.render(lastReading, lastError, loading = false)
        if (inForeground) refresh()
    }

    private fun showSettings(draft: SettingsInput? = null) {
        cancelRequests()
        monitor = null
        val input = draft ?: SettingsInput(
            settings.host, settings.port.toString(), settings.intervalSeconds.toString(),
        )
        val screen = SettingsScreen(this, input, ::showMonitor, ::checkConnection, ::saveSettings)
        settingsScreen = screen
        setContentView(screen.view)
        screen.view.requestApplyInsets()
        onBackInvokedDispatcher.registerOnBackInvokedCallback(
            OnBackInvokedDispatcher.PRIORITY_DEFAULT, returnToMonitor,
        )
    }

    private fun refresh() {
        val screen = monitor ?: return
        if (!inForeground || task != null) return
        handler.removeCallbacks(poll)
        val target = settings
        val currentGeneration = generation
        screen.render(lastReading, lastError, loading = true)
        task = executor.submit {
            val result = try {
                ReceivedReading(client.read(target), Instant.now()) to null
            } catch (error: MonitorException) {
                null to error.message
            }
            handler.post {
                if (currentGeneration != generation) return@post
                task = null
                if (result.first != null) lastReading = result.first
                lastError = result.second
                screen.render(lastReading, lastError, loading = false)
                handler.postDelayed(poll, target.intervalSeconds * 1000L)
            }
        }
    }

    private fun checkConnection(input: SettingsInput) {
        val screen = settingsScreen ?: return
        val target = validate(input, screen) ?: return
        if (task != null) return
        val currentGeneration = generation
        screen.showStatus("Проверяем подключение…", checking = true)
        task = executor.submit {
            val error = try {
                client.check(target)
                null
            } catch (failure: MonitorException) {
                failure.message
            }
            handler.post {
                if (currentGeneration != generation) return@post
                task = null
                screen.showStatus(error ?: "Сервер отвечает.", error = error != null)
            }
        }
    }

    private fun saveSettings(input: SettingsInput) {
        val screen = settingsScreen ?: return
        val updated = validate(input, screen) ?: return
        if (updated.host != settings.host || updated.port != settings.port) {
            lastReading = null
            lastError = null
        }
        settings = updated
        store.save(settings)
        showMonitor()
    }

    private fun validate(input: SettingsInput, screen: SettingsScreen): ConnectionSettings? =
        try {
            input.validated()
        } catch (error: IllegalArgumentException) {
            screen.showStatus(error.message.orEmpty(), error = true)
            null
        }

    private fun cancelRequests() {
        generation++
        handler.removeCallbacks(poll)
        task?.cancel(true)
        task = null
    }
}
