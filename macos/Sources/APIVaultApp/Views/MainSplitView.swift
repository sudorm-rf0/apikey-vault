import SwiftUI
import APIVaultCore

struct MainSplitView: View {
    @ObservedObject private var state = AppState.shared
    @State private var showAdd = false
    @State private var showChangePassword = false
    @State private var showImport = false
    @State private var showExport = false
    @State private var exportDocument: VaultDataDocument?

    var body: some View {
        NavigationSplitView {
            SidebarView()
                .navigationSplitViewColumnWidth(min: 220, ideal: 260, max: 360)
        } detail: {
            DetailView()
        }
        .searchable(text: $state.searchText, placement: .toolbar, prompt: "Filter keys")
        .toolbar {
            ToolbarItemGroup(placement: .primaryAction) {
                Button {
                    showAdd = true
                } label: {
                    Label("Add key", systemImage: "plus")
                }
                .help("Add a key")

                Spacer()

                Button {
                    Task { await state.lock() }
                } label: {
                    Label("Lock", systemImage: "lock")
                }
                .help("Lock the vault")

                Menu {
                    Button("Change password…", systemImage: "key.horizontal") {
                        showChangePassword = true
                    }
                    Divider()
                    Button("Export encrypted vault…", systemImage: "square.and.arrow.up") {
                        exportVault()
                    }
                    Button("Import encrypted vault…", systemImage: "square.and.arrow.down") {
                        showImport = true
                    }
                } label: {
                    Label("More", systemImage: "ellipsis.circle")
                }
            }
        }
        .sheet(isPresented: $showAdd) {
            KeyEditorView(mode: .add)
        }
        .sheet(isPresented: $showChangePassword) {
            ChangePasswordView()
        }
        .fileImporter(isPresented: $showImport, allowedContentTypes: [.data]) { result in
            if case .success(let url) = result {
                if let data = try? Data(contentsOf: url) {
                    Task { await state.importData(data) }
                }
            }
        }
        .fileExporter(
            isPresented: $showExport,
            document: exportDocument,
            contentType: .data,
            defaultFilename: Self.defaultExportName()
        ) { _ in }
    }

    private func exportVault() {
        Task {
            guard let data = await state.exportData() else { return }
            exportDocument = VaultDataDocument(data: data)
            showExport = true
        }
    }

    private static func defaultExportName() -> String {
        let formatter = DateFormatter()
        formatter.dateFormat = "yyyyMMdd-HHmmss"
        return "apikey-vault-\(formatter.string(from: Date())).db"
    }
}

struct SidebarView: View {
    @ObservedObject private var state = AppState.shared

    var body: some View {
        List(selection: $state.selection) {
            ForEach(state.filteredKeys) { key in
                VStack(alignment: .leading, spacing: 2) {
                    Text(key.name)
                        .font(.system(.body, design: .monospaced))
                        .lineLimit(1)
                    if let description = key.description, !description.isEmpty {
                        Text(description)
                            .font(.caption)
                            .foregroundStyle(.secondary)
                            .lineLimit(1)
                    }
                }
                .tag(key.name)
            }
        }
        .navigationTitle("Key library")
        .overlay {
            if state.keys.isEmpty {
                ContentUnavailableView(
                    "No keys yet",
                    systemImage: "key",
                    description: Text("Paste or add a key to start.")
                )
            } else if state.filteredKeys.isEmpty {
                ContentUnavailableView.search(text: state.searchText)
            }
        }
    }
}
