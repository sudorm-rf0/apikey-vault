import Foundation

/// Async HTTP client for the local apikey-vault REST API.
public actor APIClient {
    public let baseURL: URL
    private var token: String?

    public init(baseURL: URL, token: String? = nil) {
        self.baseURL = baseURL
        self.token = token
    }

    public func setToken(_ newToken: String?) {
        token = newToken
    }

    // MARK: - core calls

    public func health() async throws -> Health {
        try await get("/v1/health", auth: false)
    }

    public func initVault(password: String) async throws {
        _ = try await send("POST", "/v1/init", body: ["password": password], auth: false, expect: 201)
    }

    @discardableResult
    public func unlock(password: String) async throws -> String {
        let data = try await send("POST", "/v1/unlock", body: ["password": password], auth: false)
        let response = try decode(UnlockResponse.self, from: data)
        token = response.token
        return response.token
    }

    public func lock() async throws {
        token = nil
        _ = try await send("POST", "/v1/lock", auth: false)
    }

    public func listKeys() async throws -> [KeyMeta] {
        let data = try await send("GET", "/v1/keys")
        return try decode(KeyListResponse.self, from: data).keys
    }

    public func value(for name: String) async throws -> String {
        let data = try await send("GET", "/v1/keys/\(name.addingPercentEncoding(withAllowedCharacters: .urlPathAllowed) ?? name)")
        return try decode(KeyValue.self, from: data).value
    }

    /// Returns true when the key was created, false when it was updated.
    @discardableResult
    public func putKey(name: String, value: String, description: String?) async throws -> Bool {
        var body: [String: String] = ["value": value]
        if let description { body["description"] = description }
        let data = try await send("PUT", "/v1/keys/\(name.addingPercentEncoding(withAllowedCharacters: .urlPathAllowed) ?? name)", body: body)
        let status = try decode(StatusResponse.self, from: data)
        return status.status == "created"
    }

    public func deleteKey(name: String) async throws {
        _ = try await send("DELETE", "/v1/keys/\(name.addingPercentEncoding(withAllowedCharacters: .urlPathAllowed) ?? name)")
    }

    public func changePassword(old: String, new: String) async throws {
        _ = try await send("POST", "/v1/password", body: ["old_password": old, "new_password": new])
    }

    public func exportData() async throws -> Data {
        try await send("GET", "/v1/export")
    }

    public func importData(_ data: Data) async throws {
        // The import request itself must be authenticated; the server revokes
        // all tokens after a successful import, so clear ours afterwards.
        _ = try await send("POST", "/v1/import", raw: data, contentType: "application/octet-stream")
        token = nil
    }

    // MARK: - transport

    private func get<T: Decodable>(_ path: String, auth: Bool) async throws -> T {
        let data = try await send("GET", path, auth: auth)
        return try decode(T.self, from: data)
    }

    private func decode<T: Decodable>(_ type: T.Type, from data: Data) throws -> T {
        do {
            return try JSONDecoder().decode(type, from: data)
        } catch {
            throw APIError.decoding(error.localizedDescription)
        }
    }

    private func send(
        _ method: String,
        _ path: String,
        body: [String: String]? = nil,
        raw: Data? = nil,
        contentType: String = "application/json",
        auth: Bool = true,
        expect: Int = 200
    ) async throws -> Data {
        guard let url = URL(string: path, relativeTo: baseURL) else {
            throw APIError.transport("bad URL: \(path)")
        }
        var request = URLRequest(url: url)
        request.httpMethod = method
        request.timeoutInterval = 30
        if auth, let token {
            request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        }
        if let raw {
            request.httpBody = raw
            request.setValue(contentType, forHTTPHeaderField: "Content-Type")
        } else if let body {
            request.httpBody = try JSONSerialization.data(withJSONObject: body)
            request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        }

        let data: Data
        let response: URLResponse
        do {
            (data, response) = try await URLSession.shared.data(for: request)
        } catch {
            throw APIError.transport(error.localizedDescription)
        }
        guard let http = response as? HTTPURLResponse else {
            throw APIError.transport("no HTTP response")
        }
        guard http.statusCode == expect || (expect == 200 && (200...299).contains(http.statusCode)) else {
            let message = (try? JSONSerialization.jsonObject(with: data) as? [String: Any])?["error"] as? String
            throw APIError.badStatus(http.statusCode, message)
        }
        return data
    }
}
