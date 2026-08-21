import SwiftUI
import APIVaultCore

/// Add a key (single form or multi-line paste) or edit/rename an existing key.
struct KeyEditorView: View {
    enum Mode: Equatable {
        case add
        case edit(KeyMeta)
    }

    enum InputMode: String, CaseIterable, Identifiable {
        case single = "Single"
        case paste = "Paste multiple"
        var id: String { rawValue }
    }

    let mode: Mode
    @ObservedObject private var state = AppState.shared
    @Environment(\.dismiss) private var dismiss

    @State private var inputMode: InputMode = .single
    @State private var name = ""
    @State private var desc = ""
    @State private var value = ""
    @State private var pasteText = ""
    @State private var busy = false
    @State private var errorText: String?

    private var isEditing: Bool {
        if case .edit = mode { return true }
        return false
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            Text(title)
                .font(.headline)

            if !isEditing {
                Picker("Input mode", selection: $inputMode) {
                    ForEach(InputMode.allCases) { mode in
                        Text(mode.rawValue).tag(mode)
                    }
                }
                .pickerStyle(.segmented)
                .labelsHidden()
            }

            switch inputMode {
            case .single:
                VStack(alignment: .leading, spacing: 12) {
                    field("Name") {
                        TextField("OPENAI_API_KEY", text: $name)
                            .textFieldStyle(.roundedBorder)
                            .font(.system(.body, design: .monospaced))
                    }
                    field("Description") {
                        TextField("OpenAI key", text: $desc)
                            .textFieldStyle(.roundedBorder)
                    }
                    field("Value") {
                        SecureField("sk-…", text: $value)
                            .textFieldStyle(.roundedBorder)
                            .font(.system(.body, design: .monospaced))
                    }
                }
            case .paste:
                VStack(alignment: .leading, spacing: 8) {
                    TextEditor(text: $pasteText)
                        .font(.system(.body, design: .monospaced))
                        .scrollContentBackground(.hidden)
                        .padding(6)
                        .frame(minHeight: 130)
                        .background(.regularMaterial, in: RoundedRectangle(cornerRadius: 10, style: .continuous))
                        .overlay(
                            RoundedRectangle(cornerRadius: 10, style: .continuous)
                                .stroke(.separator)
                        )
                    Text("Paste one or more NAME=value lines, or a single value with a name.")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                    TextField("Key name (for a bare value)", text: $name)
                        .textFieldStyle(.roundedBorder)
                        .font(.system(.body, design: .monospaced))
                }
            }

            if let errorText {
                Text(errorText)
                    .font(.caption)
                    .foregroundStyle(.red)
            }

            HStack {
                Spacer()
                Button("Cancel") { dismiss() }
                    .keyboardShortcut(.cancelAction)
                Button {
                    Task { await save() }
                } label: {
                    if busy {
                        ProgressView().controlSize(.small)
                    } else {
                        Text("Save")
                    }
                }
                .keyboardShortcut(.defaultAction)
                .buttonStyle(.borderedProminent)
                .disabled(busy)
            }
        }
        .padding(20)
        .frame(width: 480)
        .onAppear {
            if case .edit(let key) = mode {
                name = key.name
                desc = key.description ?? ""
            }
        }
    }

    private var title: String {
        switch mode {
        case .add: return "Add key"
        case .edit: return "Edit key"
        }
    }

    private func field(_ label: String, @ViewBuilder content: () -> some View) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(label)
                .font(.caption)
                .foregroundStyle(.secondary)
            content()
        }
    }

    private func save() async {
        busy = true
        defer { busy = false }
        do {
            let entries: [PasteEntry]
            switch inputMode {
            case .single:
                let trimmedName = name.trimmingCharacters(in: .whitespaces)
                guard !trimmedName.isEmpty else {
                    errorText = "Name is required."
                    return
                }
                guard !value.isEmpty else {
                    errorText = "Value is required."
                    return
                }
                entries = [PasteEntry(name: trimmedName, value: value)]
            case .paste:
                entries = try parsePasted(pasteText, nameField: name.isEmpty ? nil : name)
                guard !entries.isEmpty else {
                    errorText = "Paste a key first."
                    return
                }
            }

            let description = desc.trimmingCharacters(in: .whitespaces)
            if case .edit(let key) = mode, entries[0].name != key.name {
                _ = await state.rename(
                    old: key.name,
                    to: entries[0].name,
                    description: description.isEmpty ? nil : description
                )
            } else {
                for entry in entries {
                    _ = await state.saveKey(
                        name: entry.name,
                        value: entry.value,
                        description: description.isEmpty ? nil : description
                    )
                }
            }
            dismiss()
        } catch {
            errorText = error.localizedDescription
        }
    }
}
