import Foundation
import APIVaultCore

/// End-to-end self-test of the Swift client against the real Python backend.
/// Runs without any UI: spawns an isolated backend on a temp vault, exercises
/// the full API, prints SELFTEST OK, and exits.
@main
struct SelfTest {
    @MainActor
    static func main() async {
        let dir = FileManager.default.temporaryDirectory
            .appendingPathComponent("apivault-selftest-\(UUID().uuidString)")
        try? FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)

        let backend = BackendManager(port: 18431, vaultDirectory: dir.path)
        do {
            try await backend.ensureRunning()
            let api = APIClient(baseURL: backend.baseURL)

            // first run: vault not initialized
            let health = try await api.health()
            guard health.initialized == false else {
                throw APIError.transport("expected an uninitialized vault")
            }

            // init + unlock
            try await api.initVault(password: "selftest-pw")
            _ = try await api.unlock(password: "selftest-pw")

            // CRUD
            let created = try await api.putKey(name: "OPENAI_API_KEY", value: "sk-selftest-1", description: "OpenAI")
            guard created else { throw APIError.transport("expected create") }
            _ = try await api.putKey(name: "GITHUB_TOKEN", value: "ghp_selftest", description: nil)

            var keys = try await api.listKeys()
            guard keys.count == 2 else { throw APIError.transport("expected 2 keys, got \(keys.count)") }
            let got = try await api.value(for: "OPENAI_API_KEY")
            guard got == "sk-selftest-1" else {
                throw APIError.transport("value mismatch")
            }

            // change password + lock + old password rejected
            try await api.changePassword(old: "selftest-pw", new: "selftest-pw2")
            try await api.lock()
            do {
                _ = try await api.unlock(password: "selftest-pw")
                throw APIError.transport("old password was accepted")
            } catch APIError.badStatus(401, _) {
                // expected: the old password must be rejected
            }
            _ = try await api.unlock(password: "selftest-pw2")

            // delete
            try await api.deleteKey(name: "GITHUB_TOKEN")
            keys = try await api.listKeys()
            guard keys.count == 1 else { throw APIError.transport("delete failed") }

            // export / import roundtrip (import re-locks the vault)
            let exported = try await api.exportData()
            try await api.importData(exported)
            let afterImport = try await api.health()
            guard afterImport.unlocked == false else {
                throw APIError.transport("vault should be locked after import")
            }
            _ = try await api.unlock(password: "selftest-pw2")
            keys = try await api.listKeys()
            guard keys.count == 1 else { throw APIError.transport("import lost keys") }

            backend.stop()
            print("SELFTEST OK")
            exit(0)
        } catch {
            backend.stop()
            print("SELFTEST FAILED: \(error)")
            exit(1)
        }
    }
}
