import SwiftUI
import APIVaultCore

struct ContentView: View {
    @ObservedObject private var state = AppState.shared

    var body: some View {
        Group {
            switch state.phase {
            case .connecting:
                ConnectingView()
            case .createVault:
                InitView()
            case .locked:
                UnlockView()
            case .unlocked:
                MainSplitView()
            case .failed(let message):
                FailedView(message: message)
            }
        }
        .alert(state.notice ?? "Error", isPresented: noticeBinding) {
            Button("OK") { state.clearNotice() }
        }
        .task {
            if case .connecting = state.phase {
                await state.startup()
            }
        }
    }

    private var noticeBinding: Binding<Bool> {
        Binding(
            get: { state.notice != nil },
            set: { if !$0 { state.clearNotice() } }
        )
    }
}

private struct ConnectingView: View {
    var body: some View {
        VStack(spacing: 12) {
            ProgressView()
            Text("Starting local vault…")
                .foregroundStyle(.secondary)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }
}

private struct FailedView: View {
    let message: String
    @ObservedObject private var state = AppState.shared

    var body: some View {
        VStack(spacing: 14) {
            Image(systemName: "exclamationmark.triangle")
                .font(.system(size: 36))
                .foregroundStyle(.orange)
            Text("Backend failed to start").font(.title3.weight(.semibold))
            Text(message)
                .font(.callout)
                .foregroundStyle(.secondary)
                .multilineTextAlignment(.center)
                .frame(maxWidth: 420)
            Button("Retry") {
                state.phase = .connecting
                Task { await state.startup() }
            }
            .buttonStyle(.borderedProminent)
        }
        .padding(40)
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }
}
