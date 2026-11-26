#!/bin/sh
set -eu

root=$(CDPATH='' cd -- "$(dirname -- "$0")/.." && pwd)
destination="$HOME/Library/Application Support/System Monitor"
app_name='System Monitor Notifications.app'
mkdir -p "$destination"
staging=$(mktemp -d "$destination/.notifier.XXXXXXXX")
trap 'rm -rf "$staging"' EXIT
bundle="$staging/$app_name"

mkdir -p "$bundle/Contents/MacOS"
cp "$root/desktop/macos/Info.plist" "$bundle/Contents/Info.plist"
xcrun swiftc -target "$(uname -m)-apple-macos13.0" -O "$root/desktop/macos/NotificationSender.swift" \
    -o "$bundle/Contents/MacOS/NotificationSender"
codesign --force --sign - "$bundle"
ditto "$bundle" "$destination/$app_name"
printf '%s\n' 'Установлены системные уведомления System Monitor.'
