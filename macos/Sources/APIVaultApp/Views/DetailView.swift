import SwiftUI
import APIVaultCore

struct DetailView: View {
    @ObservedObject private var state = AppState.shared
    @State private var revealed = false
    @State private var value: String?
    @State private var editing = false
    @State private var confirmDelete = false
    @State private var confirmPlaintext = false
    @State private var hideTimer: Timer?
    @State private var clipboardTimer: Timer?

    private var selectedKey: KeyMeta? {
        guard let name = state.selection else { return nil }
        return state.keys.first { $0.name == name }
    }

    var body: some View {
        if let key = selectedKey {
            ScrollView {
                VStack(alignment: .leading, spacing: 18) {
                    header(key)
                    valueBox
                    Divider()
                    metadata(key)
                }
                .padding(24)
            }
            .sheet(isPresented: $editing) {
                KeyEditorView(mode: .edit(key))
            }
            .confirmationDialog("Delete \(key.name)?", isPresented: $confirmDelete, titleVisibility: .visible) {
                Button("Delete", role: .destructive) {
                    Task { await state.deleteKey(name: key.name) }
                }
                Button("Cancel", role: .cancel) {}
            } message: {
                Text("This cannot be undone.")
            }
            .confirmationDialog(
                "Copy plaintext key?",
                isPresented: $confirmPlaintext,
                titleVisibility: .visible
            ) {
                Button("Copy plaintext (clears in 30s)", role: .destructive) {
                    if let key = selectedKey {
                        copyPlaintext(key)
                    }
                }
                Button("Cancel", role: .cancel) {}
            } message: {
                Text("The real key will be put on the clipboard. Never paste it into an AI chat — the placeholder {{NAME}} is the safe choice.")
            }
        } else {
            ContentUnavailableView(
                "Select a key",
                systemImage: "key",
                description: Text("Choose a key from the library.")
            )
        }
    }

    private func header(_ key: KeyMeta) -> some View {
        HStack(alignment: .firstTextBaseline) {
            Text(key.name)
                .font(.title2.weight(.semibold))
                .textSelection(.enabled)
            Spacer()
            Button {
                Task { await reveal(key) }
            } label: {
                Label(revealed ? "Hide" : "Reveal", systemImage: revealed ? "eye.slash" : "eye")
            }
            Button {
                copyPlaceholder(key)
            } label: {
                Label("Copy", systemImage: "doc.on.doc")
            }
            .help("Copy the safe placeholder {{NAME}} — never paste the real key into an AI chat")
            Button {
                confirmPlaintext = true
            } label: {
                Label("Plaintext…", systemImage: "doc.on.doc.fill")
            }
            .help("Copy the real key (warned) — trusted locations only")
            Button {
                editing = true
            } label: {
                Label("Edit", systemImage: "pencil")
            }
            Button(role: .destructive) {
                confirmDelete = true
            } label: {
                Label("Delete", systemImage: "trash")
            }
        }
    }

    private var valueBox: some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack {
                Text(revealed ? (value ?? "") : String(repeating: "•", count: 24))
                    .font(.system(.body, design: .monospaced))
                    .textSelection(.enabled)
                    .lineLimit(1)
                    .truncationMode(.middle)
                Spacer()
            }
            .padding(14)
            .background(.regularMaterial, in: RoundedRectangle(cornerRadius: 10, style: .continuous))

            if revealed {
                Label("Plaintext shown on screen — never paste it into an AI chat.", systemImage: "exclamationmark.triangle")
                    .font(.caption)
                    .foregroundStyle(.orange)
            }
        }
    }

    private func metadata(_ key: KeyMeta) -> some View {
        Grid(alignment: .leading, horizontalSpacing: 24, verticalSpacing: 8) {
            GridRow {
                Text("Description").foregroundStyle(.secondary).gridColumnAlignment(.leading)
                Text(key.description ?? "—").textSelection(.enabled)
            }
            GridRow {
                Text("Created").foregroundStyle(.secondary)
                Text(key.created_at).font(.system(.callout, design: .monospaced))
            }
            GridRow {
                Text("Updated").foregroundStyle(.secondary)
                Text(key.updated_at).font(.system(.callout, design: .monospaced))
            }
        }
        .font(.callout)
    }

    private func reveal(_ key: KeyMeta) async {
        if revealed {
            revealed = false
            value = nil
            hideTimer?.invalidate()
            return
        }
        do {
            value = try await state.api.value(for: key.name)
            revealed = true
            hideTimer?.invalidate()
            hideTimer = Timer.scheduledTimer(withTimeInterval: 60, repeats: false) { _ in
                Task { @MainActor in
                    self.revealed = false
                    self.value = nil
                }
            }
        } catch {
            state.noticeIsError = true
            state.notice = error.localizedDescription
        }
    }

    /// Safe copy: put `{{NAME}}` on the clipboard so the real key can never be
    /// pasted into an AI chat by accident.
    private func copyPlaceholder(_ key: KeyMeta) {
        copyToPasteboard("{{\(key.name)}}")
        state.notice = "Copied placeholder {{\(key.name)}}. Use Plaintext… only for trusted locations."
    }

    /// Warned plaintext copy; the clipboard is cleared again after 30 seconds.
    private func copyPlaintext(_ key: KeyMeta) {
        Task {
            do {
                let value = try await state.api.value(for: key.name)
                copyToPasteboard(value)
                clipboardTimer?.invalidate()
                clipboardTimer = Timer.scheduledTimer(withTimeInterval: 30, repeats: false) { _ in
                    Task { @MainActor in
                        if NSPasteboard.general.string(forType: .string) == value {
                            NSPasteboard.general.clearContents()
                            self.state.notice = "Clipboard cleared (30s auto-expire)."
                        }
                    }
                }
                state.noticeIsError = true
                state.notice = "Plaintext \(key.name) copied — do not paste it into AI chats. Clipboard clears in 30s."
            } catch {
                state.noticeIsError = true
                state.notice = error.localizedDescription
            }
        }
    }
}
