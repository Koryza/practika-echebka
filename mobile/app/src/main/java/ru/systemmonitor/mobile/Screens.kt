package ru.systemmonitor.mobile

import android.content.Context
import android.content.res.ColorStateList
import android.graphics.Color
import android.graphics.Typeface
import android.graphics.drawable.GradientDrawable
import android.text.InputType
import android.view.Gravity
import android.view.View
import android.view.ViewGroup
import android.view.WindowInsets
import android.widget.Button
import android.widget.EditText
import android.widget.LinearLayout
import android.widget.ProgressBar
import android.widget.ScrollView
import android.widget.TextView
import java.time.Instant
import java.time.ZoneId
import java.time.format.DateTimeFormatter
import java.util.Locale
import kotlin.math.roundToInt

private val ink = Color.rgb(237, 242, 250)
private val muted = Color.rgb(170, 185, 206)
private val surface = Color.rgb(24, 34, 48)
private val screenBackground = Color.rgb(16, 23, 33)
private val border = Color.rgb(62, 80, 105)
private val green = Color.rgb(103, 220, 173)
private val amber = Color.rgb(255, 191, 125)
private val russian = Locale.forLanguageTag("ru-RU")
private val clock = DateTimeFormatter.ofPattern("HH:mm:ss", russian).withZone(ZoneId.systemDefault())
private val localDateTime = DateTimeFormatter.ofPattern("dd.MM.yyyy HH:mm:ss", russian)
    .withZone(ZoneId.systemDefault())

private fun Context.dp(value: Int): Int = (value * resources.displayMetrics.density).roundToInt()

private fun Context.roundBackground(color: Int, round: Int, stroke: Int? = null): GradientDrawable =
    GradientDrawable().apply {
        setColor(color)
        cornerRadius = dp(round).toFloat()
        if (stroke != null) setStroke(dp(1), stroke)
    }

private fun Context.text(label: String, size: Float, color: Int = ink, bold: Boolean = false) =
    TextView(this).apply {
        text = label
        textSize = size
        setTextColor(color)
        if (bold) setTypeface(typeface, Typeface.BOLD)
    }

private fun Context.button(label: String, primary: Boolean = false, action: () -> Unit) =
    Button(this).apply {
        text = label
        isAllCaps = false
        textSize = 14f
        setTextColor(if (primary) screenBackground else ink)
        backgroundTintList = ColorStateList.valueOf(if (primary) green else Color.rgb(38, 52, 72))
        minHeight = dp(48)
        setOnClickListener { action() }
    }

internal class ScreenLayout(private val context: Context) {
    val content = LinearLayout(context).apply {
        orientation = LinearLayout.VERTICAL
        setPadding(context.dp(20), context.dp(12), context.dp(20), context.dp(24))
    }

    val view = ScrollView(context).apply {
        isFillViewport = true
        setBackgroundColor(screenBackground)
        addView(content, ViewGroup.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT))
        setOnApplyWindowInsetsListener { view, insets ->
            val bars = insets.getInsets(WindowInsets.Type.systemBars() or WindowInsets.Type.displayCutout())
            val keyboard = insets.getInsets(WindowInsets.Type.ime())
            view.setPadding(bars.left, bars.top, bars.right, maxOf(bars.bottom, keyboard.bottom))
            WindowInsets.CONSUMED
        }
    }

    fun add(view: View, top: Int = 0) {
        content.addView(view, LinearLayout.LayoutParams(
            ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT,
        ).apply { topMargin = context.dp(top) })
    }

    fun header(title: String, action: String, onAction: () -> Unit) {
        val heading = context.text(title, 26f, bold = true)
        heading.isAccessibilityHeading = true
        val row = LinearLayout(context).apply {
            gravity = Gravity.CENTER_VERTICAL
            addView(heading, LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f))
            addView(context.button(action, action = onAction))
        }
        add(row)
    }
}

internal class MonitorScreen(context: Context, openSettings: () -> Unit, refresh: () -> Unit) {
    private val layout = ScreenLayout(context)
    val view = layout.view
    private val computer = context.text("Компьютер не подключён", 20f, bold = true)
    private val status = context.text("Подключение…", 14f, muted)
    private val updateTime = context.text("Данные ещё не получены", 13f, muted)
    private val cpu = MetricView(context, "Процессор", Color.rgb(126, 168, 255))
    private val memory = MetricView(context, "Оперативная память", Color.rgb(223, 171, 255))
    private val disk = MetricView(context, "Накопитель", green)
    private val refreshButton = context.button("Обновить", primary = true, action = refresh)

    init {
        layout.header("Мониторинг", "Настройки", openSettings)
        layout.add(computer, 14)
        layout.add(status, 5)
        layout.add(updateTime, 6)
        layout.add(cpu.view, 18)
        layout.add(memory.view, 10)
        layout.add(disk.view, 10)
        layout.add(refreshButton, 16)
    }

    fun render(data: ReceivedReading?, error: String?, loading: Boolean) {
        val reading = data?.reading
        computer.text = reading?.computerName ?: "Компьютер не подключён"
        status.text = error ?: if (reading == null) "Подключение…" else "Подключено"
        status.setTextColor(if (error != null) amber else if (reading != null) green else muted)
        updateTime.text = when {
            data == null -> "Данные ещё не получены"
            error != null -> "Устаревшие данные · Получены ${localDateTime.format(data.receivedAt)}"
            else -> "Получено ${localDateTime.format(data.receivedAt)} · Замер в ${clock.format(data.reading.sampledAt)}"
        }
        cpu.update(reading?.cpuPercent)
        memory.update(reading?.memoryPercent)
        disk.update(reading?.diskPercent, reading?.diskName)
        refreshButton.isEnabled = !loading
    }
}

internal data class ReceivedReading(val reading: MonitorReading, val receivedAt: Instant)

private class MetricView(context: Context, label: String, private val color: Int) {
    private val title = context.text(label, 15f, muted)
    private val value = context.text("Недоступно", 23f, bold = true)
    private val details = context.text("", 13f, muted)
    private val bar = ProgressBar(context, null, android.R.attr.progressBarStyleHorizontal).apply {
        max = 100
        progressTintList = ColorStateList.valueOf(color)
        progressBackgroundTintList = ColorStateList.valueOf(border)
        importantForAccessibility = View.IMPORTANT_FOR_ACCESSIBILITY_NO
    }
    val view = LinearLayout(context).apply {
        orientation = LinearLayout.VERTICAL
        setPadding(context.dp(15), context.dp(11), context.dp(15), context.dp(11))
        background = context.roundBackground(surface, 12, border)
        val row = LinearLayout(context).apply {
            gravity = Gravity.CENTER_VERTICAL
            addView(title, LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f))
            addView(value, LinearLayout.LayoutParams(ViewGroup.LayoutParams.WRAP_CONTENT, ViewGroup.LayoutParams.WRAP_CONTENT))
        }
        addView(row)
        addView(details)
        addView(bar, LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, context.dp(10)).apply {
            topMargin = context.dp(6)
        })
        details.visibility = View.GONE
    }

    fun update(percent: Double?, description: String? = null) {
        value.text = if (percent == null) "Недоступно" else String.format(russian, "%.1f %%", percent)
        bar.progress = percent?.roundToInt() ?: 0
        details.text = description.orEmpty()
        details.visibility = if (description.isNullOrEmpty()) View.GONE else View.VISIBLE
    }
}

internal data class SettingsInput(val host: String, val port: String, val interval: String) {
    fun validated(): ConnectionSettings = ConnectionSettings.fromInput(host, port, interval)
}

internal class SettingsScreen(
    context: Context,
    input: SettingsInput,
    onBack: () -> Unit,
    onCheck: (SettingsInput) -> Unit,
    onSave: (SettingsInput) -> Unit,
) {
    private val layout = ScreenLayout(context)
    val view = layout.view
    private val host = field(context, "IP-адрес или имя компьютера", input.host, false)
    private val port = field(context, "Порт HTTP API", input.port, true)
    private val interval = field(context, "Интервал обновления в секундах", input.interval, true)
    private val status = context.text("", 14f, muted)
    private val check = context.button("Проверить подключение", action = { onCheck(input()) })
    private val save = context.button("Сохранить", primary = true, action = { onSave(input()) })

    init {
        layout.header("Настройки", "Назад", onBack)
        layout.add(context.text("Для эмулятора на Mac используй адрес 10.0.2.2.", 14f, muted), 12)
        for ((label, field) in listOf(
            "Адрес компьютера" to host,
            "Порт HTTP API" to port,
            "Интервал обновления, с" to interval,
        )) {
            val caption = context.text(label, 14f, muted).apply { labelFor = field.id }
            layout.add(caption, 14)
            layout.add(field, 5)
        }
        layout.add(check, 14)
        layout.add(save, 2)
        layout.add(status, 8)
        layout.content.isFocusableInTouchMode = true
        layout.content.requestFocus()
    }

    fun input() = SettingsInput(host.text.toString(), port.text.toString(), interval.text.toString())

    fun showStatus(message: String, error: Boolean = false, checking: Boolean = false) {
        status.text = message
        status.setTextColor(if (error) amber else if (checking) muted else green)
        check.isEnabled = !checking
    }

    private fun field(context: Context, hintText: String, value: String, number: Boolean) =
        EditText(context).apply {
            id = View.generateViewId()
            hint = hintText
            setText(value)
            textSize = 16f
            setTextColor(ink)
            setHintTextColor(muted)
            setPadding(context.dp(12), context.dp(8), context.dp(12), context.dp(8))
            minHeight = context.dp(49)
            background = context.roundBackground(surface, 8, border)
            inputType = if (number) InputType.TYPE_CLASS_NUMBER else
                InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_VARIATION_URI
            setSingleLine()
            isSaveEnabled = false
        }
}
