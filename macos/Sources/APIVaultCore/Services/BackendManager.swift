import Foundation

/// Spawns (or connects to) the local Python apikey-vault backend.
///
/// The app bundle ships with an embedded Python virtualenv at
/// `Contents/Resources/venv/bin/python`. If that is missing we fall back to
/// `python3 -m apivault` from the PATH so development builds keep working.
public enum BackendPhase: Sendable, Equatable {
    case idle
    case starting
    case running
    case failed(String)
}

@MainActor
public final class BackendManager {
    public let port: Int
    public let vaultDirectory: String?
    public private(set) var phase: BackendPhase = .idle
    public private(set) var health: Health?

    private var process: Process?

    public init(
        port: Int = UserDefaults.standard.integer(forKey: "backendPort") == 0
            ? 8417
            : UserDefaults.standard.integer(forKey: "backendPort"),
        vaultDirectory: String? = nil
    ) {
        self.port = port
        self.vaultDirectory = vaultDirectory
    }

    public var baseURL: URL {
        URL(string: "http://127.0.0.1:\(port)")!
    }

    // MARK: - lifecycle

    /// Make sure a backend is reachable; spawn one if necessary.
    public func ensureRunning() async throws {
        if await isHealthy() {
            phase = .running
            return
        }
        try startProcess()
        // poll health until the server responds
        for _ in 0..<60 {
            try? await Task.sleep(nanoseconds: 500_000_000)
            if await isHealthy() {
                phase = .running
                return
            }
        }
        phase = .failed("backend did not become healthy in time")
        throw APIError.transport("local backend did not start (see ~/.apikey-vault/app.log)")
    }

    public func stop() {
        if let process, process.isRunning {
            process.terminate()
        }
        process = nil
        phase = .idle
    }

    // MARK: - internals

    private func isHealthy() async -> Bool {
        let client = APIClient(baseURL: baseURL)
        do {
            let health = try await client.health()
            self.health = health
            return health.status == "ok"
        } catch {
            return false
        }
    }

    private func startProcess() throws {
        let (python, prefix) = BackendManager.pythonExecutable()
        guard python != nil else {
            phase = .failed("no Python runtime found (bundled venv or python3)")
            throw APIError.transport("no Python runtime found")
        }
        let pythonURL = python!

        let logURL = FileManager.default.homeDirectoryForCurrentUser
            .appendingPathComponent(".apikey-vault")
        try? FileManager.default.createDirectory(at: logURL, withIntermediateDirectories: true)
        let logFile = logURL.appendingPathComponent("app.log")

        let pipe = Pipe()
        let proc = Process()
        proc.executableURL = pythonURL
        proc.arguments = prefix + [
            "-m", "apivault", "serve",
            "--host", "127.0.0.1",
            "--port", "\(port)",
        ]
        if let vaultDirectory {
            var env = ProcessInfo.processInfo.environment
            env["APIVAULT_DIR"] = vaultDirectory
            proc.environment = env
        }
        proc.standardOutput = pipe
        proc.standardError = pipe

        // Capture backend output into ~/.apikey-vault/app.log
        let handle = pipe.fileHandleForReading
        handle.readabilityHandler = { [weak self] handler in
            let data = handler.availableData
            if !data.isEmpty {
                if let fh = FileHandle(forWritingAtPath: logFile.path) {
                    fh.seekToEndOfFile()
                    fh.write(data)
                    try? fh.close()
                }
            } else {
                handler.readabilityHandler = nil
            }
            _ = self
        }

        phase = .starting
        do {
            try proc.run()
        } catch {
            phase = .failed(error.localizedDescription)
            throw APIError.transport("failed to launch backend: \(error.localizedDescription)")
        }
        process = proc
    }

    /// Prefer the embedded venv shipped inside the .app bundle, then fall back
    /// to `python3` from PATH (dev builds).
    static func pythonExecutable() -> (URL?, [String]) {
        if let resource = Bundle.main.resourceURL {
            let bundled = resource.appendingPathComponent("venv/bin/python")
            if FileManager.default.isExecutableFile(atPath: bundled.path) {
                return (bundled, [])
            }
        }
        // `/usr/bin/env python3` resolves python3 from PATH.
        let env = URL(fileURLWithPath: "/usr/bin/env")
        if FileManager.default.isExecutableFile(atPath: env.path) {
            return (env, ["python3"])
        }
        for path in ["/usr/local/bin/python3", "/opt/homebrew/bin/python3"]
        where FileManager.default.isExecutableFile(atPath: path) {
            return (URL(fileURLWithPath: path), [])
        }
        return (nil, [])
    }
}
