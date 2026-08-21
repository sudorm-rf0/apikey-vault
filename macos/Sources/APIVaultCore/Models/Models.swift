import Foundation

/// Non-secret metadata about a stored key.
public struct KeyMeta: Codable, Identifiable, Hashable, Sendable {
    public let name: String
    public let description: String?
    public let created_at: String
    public let updated_at: String

    public var id: String { name }

    public init(name: String, description: String?, created_at: String, updated_at: String) {
        self.name = name
        self.description = description
        self.created_at = created_at
        self.updated_at = updated_at
    }
}

public struct Health: Codable, Sendable {
    public let status: String
    public let initialized: Bool
    public let unlocked: Bool
    public let api: String?
}

public struct UnlockResponse: Codable, Sendable {
    public let token: String
    public let ttl_seconds: Int
    public let expires_at: String
}

public struct KeyValue: Codable, Sendable {
    public let name: String
    public let value: String
}

public struct KeyListResponse: Codable, Sendable {
    public let keys: [KeyMeta]
}

public struct StatusResponse: Codable, Sendable {
    public let status: String
}

public enum APIError: Error, LocalizedError, Sendable {
    case transport(String)
    case badStatus(Int, String?)
    case decoding(String)

    public var errorDescription: String? {
        switch self {
        case .transport(let message): return message
        case .badStatus(let code, let message):
            return message ?? "HTTP \(code)"
        case .decoding(let message): return "decode error: \(message)"
        }
    }
}

/// One parsed line from the paste box (NAME=value or bare value).
public struct PasteEntry: Sendable {
    public let name: String
    public let value: String

    public init(name: String, value: String) {
        self.name = name
        self.value = value
    }
}

public enum PasteError: Error, LocalizedError, Sendable {
    case missingName(String)
    case needName

    public var errorDescription: String? {
        switch self {
        case .missingName(let line): return "line has no NAME= prefix: \(line.prefix(40))"
        case .needName: return "enter a key name for the pasted value"
        }
    }
}

/// Parse pasted text into key/value entries.
/// Accepts one or more `NAME=value` lines (optionally `export `-prefixed and
/// quoted), or a single bare value combined with a name field.
public func parsePasted(_ text: String, nameField: String?) throws -> [PasteEntry] {
    let lines = text
        .split(whereSeparator: \.isNewline)
        .map { $0.trimmingCharacters(in: .whitespaces) }
        .filter { !$0.isEmpty }

    guard !lines.isEmpty else { return [] }

    var entries: [PasteEntry] = []
    for line in lines {
        if let eq = line.firstIndex(of: "=") {
            var name = String(line[..<eq]).trimmingCharacters(in: .whitespaces)
            if name.hasPrefix("export ") {
                name = String(name.dropFirst("export ".count)).trimmingCharacters(in: .whitespaces)
            }
            var value = String(line[line.index(after: eq)...]).trimmingCharacters(in: .whitespaces)
            if (value.hasPrefix("\"") && value.hasSuffix("\"")) ||
                (value.hasPrefix("'") && value.hasSuffix("'")) {
                value = String(value.dropFirst().dropLast())
            }
            entries.append(PasteEntry(name: name, value: value))
        } else {
            if lines.count > 1 {
                throw PasteError.missingName(line)
            }
            guard let nameField, !nameField.isEmpty else {
                throw PasteError.needName
            }
            entries.append(PasteEntry(name: nameField, value: line))
        }
    }
    return entries
}
