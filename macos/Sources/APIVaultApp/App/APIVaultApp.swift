import AppKit
import SwiftUI
import APIVaultCore

@main
struct APIVaultApp: App {
    @NSApplicationDelegateAdaptor(AppDelegate.self) private var appDelegate

    var body: some Scene {
        WindowGroup {
            ContentView()
                .frame(minWidth: 760, minHeight: 520)
        }
        .windowResizability(.contentMinSize)
        .commands {
            CommandMenu("Vault") {
                Button("Lock") {
                    Task { @MainActor in
                        await AppState.shared.lock()
                    }
                }
                .keyboardShortcut("l", modifiers: [.command])
                .disabled(AppState.shared.phase != .unlocked)
            }
        }
    }
}

final class AppDelegate: NSObject, NSApplicationDelegate {
    func applicationDidFinishLaunching(_ notification: Notification) {
        // Make sure the window comes to the foreground when launched from a bundle.
        NSApp.setActivationPolicy(.regular)
        NSApp.activate(ignoringOtherApps: true)
    }

    func applicationWillTerminate(_ notification: Notification) {
        Task { @MainActor in
            AppState.shared.backend.stop()
        }
    }
}
