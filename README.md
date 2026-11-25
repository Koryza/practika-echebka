# System Monitor

System Monitor собирает показатели Mac и передаёт их Android-приложению. Настольная часть также позволяет работать с файлами в выбранной папке, запускать и завершать дочерние процессы и просматривать историю замеров и журнал событий.

## Запуск на Mac

Нужны macOS 13 или новее и Python 3.12. Настольное приложение использует PySide6, psutil, SQLite и Flask.

Выполните команды из корня репозитория.

```sh
python3.12 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m desktop
```

Вкладка «История и настройки» показывает адрес API и активный порт. База SQLite создаётся при запуске в `~/Library/Application Support/System Monitor`.

## Сборка Android-приложения

Нужны Android SDK Platform 37, Build Tools 36.0.0 и JDK 17 или новее. Приложение написано на Kotlin и устанавливается на Android 13 или новее. Для проверки на Mac откройте каталог `mobile` в Android Studio или выполните сборку через Gradle Wrapper.

```sh
cd mobile
export JAVA_HOME="/Applications/Android Studio.app/Contents/jbr/Contents/Home"
export ANDROID_HOME="$HOME/Library/Android/sdk"
./gradlew assembleDebug
```

Пути в примере подходят для стандартной установки Android Studio и SDK на Mac. Собранный файл находится в `mobile/app/build/outputs/apk/debug/app-debug.apk` относительно корня репозитория. При запущенном эмуляторе выполните установку из каталога `mobile`.

```sh
"$ANDROID_HOME/platform-tools/adb" -e install -r app/build/outputs/apk/debug/app-debug.apk
```

Запустите настольный System Monitor и задайте в мобильном приложении адрес `10.0.2.2` и порт, показанный на Mac. Начальное значение порта — `8080`. Кнопка «Проверить подключение» проверяет доступность сервера. Экран мониторинга обновляет данные по таймеру и по кнопке «Обновить». [Сетевые адреса Android Emulator](https://developer.android.com/studio/run/emulator-networking-address)

## Проверки

```sh
.venv/bin/python -m unittest discover -s tests -v
```

Для модульных тестов и статической проверки Android выполните `./gradlew testDebugUnitTest lintDebug` из каталога `mobile`.

## Ограничения

- API слушает локальный интерфейс Mac. В конфигурации для защиты Android-клиент запускается в эмуляторе на том же компьютере.
- Объекты файлового менеджера должны находиться в выбранной рабочей папке. Между томами используйте копирование.
- Диспетчер процессов запускает исполняемые файлы. Завершение доступно только для дочерних процессов, запущенных из текущего экземпляра System Monitor.

[Архитектура, схема базы и алгоритмы](docs/design.md) · [Протокол испытаний](docs/test-results.pdf) · [Результаты оптимизации и регрессии](docs/optimization-results.pdf) · [Заметки по отладке](docs/debugging.md)

## Документы для сдачи

- [Техническое задание](docs/technical-specification.pdf)
- [Описание программы](docs/program-description.pdf)
- [Программа и методика испытаний](docs/testing-methodology.pdf)
- [Руководство оператора](docs/operator-manual.pdf)
- [Отчёт о прохождении учебной практики](docs/practice-report.pdf)
