import SwiftUI
import APIVaultCore

struct DetailView: View {
    @ObservedObject private var state = AppState.shared
    @State private var revealed = false
    @State private var value: String?
    @State private var editing = false
    @State private var confirmDelete = false
    @State private var hideTimer: Timer?

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
                copyValue(key)
            } label: {
                Label("Copy", systemImage: "doc.on.doc")
            }
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

    private func copyValue(_ key: KeyMeta) {
        Task {
            do {
                let value = try await state.api.value(for: key.name)
                copyToPasteboard(value)
                state.notice = "Copied \(key.name) to clipboard."
            } catch {
                state.noticeIsError = true
                state.notice = error.localizedDescription
            }
        }
    }
}
