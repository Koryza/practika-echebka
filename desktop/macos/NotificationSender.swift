import Foundation
import UserNotifications

final class NotificationDelegate: NSObject, UNUserNotificationCenterDelegate {
    func userNotificationCenter(
        _ center: UNUserNotificationCenter,
        willPresent notification: UNNotification,
        withCompletionHandler completionHandler: @escaping (UNNotificationPresentationOptions) -> Void
    ) {
        completionHandler([.banner, .list])
    }
}

let arguments = CommandLine.arguments
guard arguments.count == 4 else { exit(64) }
let resultURL = URL(fileURLWithPath: arguments[3])

func finish(_ result: String) -> Never {
    try? Data(result.utf8).write(to: resultURL, options: .atomic)
    exit(result == "sent" ? 0 : 1)
}

func report(_ error: Error) -> Never {
    let error = error as NSError
    let denied = error.domain == UNError.errorDomain
        && error.code == UNError.Code.notificationsNotAllowed.rawValue
    finish(denied ? "denied" : "error")
}

let delegate = NotificationDelegate()
let center = UNUserNotificationCenter.current()
center.delegate = delegate
DispatchQueue.main.asyncAfter(deadline: .now() + 90) { finish("timeout") }
center.requestAuthorization(options: [.alert]) { allowed, error in
    if let error { report(error) }
    guard allowed else { finish("denied") }

    let content = UNMutableNotificationContent()
    content.title = arguments[1]
    content.body = arguments[2]
    let request = UNNotificationRequest(identifier: UUID().uuidString, content: content, trigger: nil)
    center.add(request) { error in
        if let error { report(error) }
        finish("sent")
    }
}

withExtendedLifetime(delegate) { RunLoop.main.run() }
