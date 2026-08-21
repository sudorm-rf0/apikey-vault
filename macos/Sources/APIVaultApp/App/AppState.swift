import Foundation
import SwiftUI
import APIVaultCore

@MainActor
final class AppState: ObservableObject {
    /// Single shared instance (the backend child process must be stopped at
    /// app termination, which the AppDelegate reaches through this).
    static let shared = AppState()

    enum Phase: Equatable {
        case connecting
        case createVault
        case locked
        case unlocked
        case failed(String)
    }

    @Published var phase: Phase = .connecting
    @Published var health: Health?
    @Published var keys: [KeyMeta] = []
    @Published var selection: String?
    @Published var searchText = ""
    @Published var notice: String?
    @Published var noticeIsError = false

    let backend: BackendManager
    let api: APIClient

    init() {
        let backend = BackendManager()
        self.backend = backend
        self.api = APIClient(baseURL: backend.baseURL)
    }

    var filteredKeys: [KeyMeta] {
        let query = searchText.trimmingCharacters(in: .whitespaces).lowercased()
        guard !query.isEmpty else { return keys }
        return keys.filter {
            $0.name.lowercased().contains(query) ||
            ($0.description ?? "").lowercased().contains(query)
        }
    }

    // MARK: - lifecycle

    func startup() async {
        do {
            try await backend.ensureRunning()
            health = backend.health
            if let health {
                if health.initialized {
                    phase = .locked
                } else {
                    phase = .createVault
                }
            } else {
                phase = .failed("backend health check returned no data")
            }
        } catch {
            phase = .failed(error.localizedDescription)
        }
    }

    // MARK: - auth

    func createVault(password: String) async {
        do {
            try await api.initVault(password: password)
            _ = try await api.unlock(password: password)
            phase = .unlocked
            notice = "Vault created and unlocked."
            await refreshKeys()
        } catch {
            noticeIsError = true
            notice = error.localizedDescription
        }
    }

    func unlock(password: String) async {
        do {
            _ = try await api.unlock(password: password)
            health = try await api.health()
            phase = .unlocked
            await refreshKeys()
        } catch {
            noticeIsError = true
            notice = error.localizedDescription
        }
    }

    func connect(token: String) async {
        await api.setToken(token)
        do {
            let keys = try await api.listKeys()
            self.keys = keys
            health = try await api.health()
            phase = .unlocked
        } catch let APIError.badStatus(code, message) {
            if code == 423 {
                noticeIsError = true
                notice = "Vault is locked on the server — unlock with the master password first."
            } else {
                noticeIsError = true
                notice = message ?? "Invalid token."
            }
            await api.setToken(nil)
        } catch {
            noticeIsError = true
            notice = error.localizedDescription
            await api.setToken(nil)
        }
    }

    func lock() async {
        do {
            try await api.lock()
        } catch {
            // lock is best-effort; still return to the lock screen
        }
        phase = .locked
        keys = []
        selection = nil
    }

    // MARK: - keys

    func refreshKeys() async {
        do {
            keys = try await api.listKeys()
            if let selection, !keys.contains(where: { $0.name == selection }) {
                self.selection = nil
            }
        } catch {
            noticeIsError = true
            notice = error.localizedDescription
        }
    }

    @discardableResult
    func saveKey(name: String, value: String, description: String?) async -> Bool {
        do {
            let created = try await api.putKey(name: name, value: value, description: description)
            await refreshKeys()
            selection = name
            notice = created ? "Stored \(name)." : "Updated \(name)."
            return true
        } catch {
            noticeIsError = true
            notice = error.localizedDescription
            return false
        }
    }

    func rename(old: String, to new: String, description: String?) async -> Bool {
        do {
            let value = try await api.value(for: old)
            _ = try await api.putKey(name: new, value: value, description: description)
            try await api.deleteKey(name: old)
            await refreshKeys()
            selection = new
            notice = "Renamed \(old) → \(new)."
            return true
        } catch {
            noticeIsError = true
            notice = error.localizedDescription
            return false
        }
    }

    func deleteKey(name: String) async {
        do {
            try await api.deleteKey(name: name)
            await refreshKeys()
            notice = "Deleted \(name)."
        } catch {
            noticeIsError = true
            notice = error.localizedDescription
        }
    }

    func changePassword(old: String, new: String) async {
        do {
            try await api.changePassword(old: old, new: new)
            notice = "Master password changed."
        } catch {
            noticeIsError = true
            notice = error.localizedDescription
        }
    }

    // MARK: - export / import

    func exportData() async -> Data? {
        do {
            return try await api.exportData()
        } catch {
            noticeIsError = true
            notice = error.localizedDescription
            return nil
        }
    }

    func importData(_ data: Data) async {
        do {
            try await api.importData(data)
            health = try await api.health()
            phase = .locked
            keys = []
            selection = nil
            notice = "Vault imported — unlock with its master password."
        } catch {
            noticeIsError = true
            notice = error.localizedDescription
        }
    }

    func clearNotice() {
        notice = nil
        noticeIsError = false
    }
}
