import SwiftUI
import APIVaultCore

/// First-run: create the vault with a master password.
struct InitView: View {
    @ObservedObject private var state = AppState.shared
    @State private var password = ""
    @State private var confirm = ""
    @State private var busy = false

    var body: some View {
        GlassCard {
            VStack(spacing: 14) {
                Image(systemName: "key.horizontal")
                    .font(.system(size: 36))
                    .foregroundStyle(.tint)
                Text("Initialize vault")
                    .font(.title2.weight(.semibold))
                Text("No vault found yet. Every key is encrypted with this password — nothing is stored in plain text.")
                    .font(.callout)
                    .foregroundStyle(.secondary)
                    .multilineTextAlignment(.center)
                    .frame(maxWidth: 360)

                SecureField("Master password", text: $password)
                    .textFieldStyle(.roundedBorder)
                SecureField("Confirm master password", text: $confirm)
                    .textFieldStyle(.roundedBorder)

                Button(action: create) {
                    if busy { ProgressView().controlSize(.small) } else { Text("Create vault") }
                }
                .buttonStyle(.borderedProminent)
                .disabled(busy || password.isEmpty || confirm.isEmpty)
            }
            .frame(width: 340)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }

    private func create() {
        guard password == confirm else {
            state.noticeIsError = true
            state.notice = "Passwords do not match."
            return
        }
        busy = true
        Task {
            await state.createVault(password: password)
            busy = false
        }
    }
}

/// Unlock an existing vault with the master password or a bearer token.
struct UnlockView: View {
    @ObservedObject private var state = AppState.shared
    @State private var password = ""
    @State private var token = ""
    @State private var useToken = false
    @State private var busy = false

    var body: some View {
        GlassCard {
            VStack(spacing: 14) {
                Image(systemName: "lock.fill")
                    .font(.system(size: 36))
                    .foregroundStyle(.tint)
                Text("Vault locked")
                    .font(.title2.weight(.semibold))
                Text(unlockHint)
                    .font(.callout)
                    .foregroundStyle(.secondary)
                    .multilineTextAlignment(.center)

                if useToken {
                    SecureField("Bearer token", text: $token)
                        .textFieldStyle(.roundedBorder)
                        .onSubmit { submit() }
                } else {
                    SecureField("Master password", text: $password)
                        .textFieldStyle(.roundedBorder)
                        .onSubmit { submit() }
                }

                Button {
                    submit()
                } label: {
                    if busy {
                        ProgressView().controlSize(.small)
                    } else {
                        Text(actionTitle)
                    }
                }
                .buttonStyle(.borderedProminent)
                .disabled(isDisabled)

                Button(useToken ? "Use the master password" : "Use a bearer token instead") {
                    useToken.toggle()
                }
                .buttonStyle(.link)
            }
            .frame(width: 340)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }

    private var actionTitle: String {
        useToken ? "Connect" : "Unlock"
    }

    private var isDisabled: Bool {
        busy || (useToken ? token.isEmpty : password.isEmpty)
    }

    private var unlockHint: String {
        useToken
            ? "Connect with a bearer token from 'apivault serve --token'."
            : "Enter the master password to unlock this vault."
    }

    private func submit() {
        if useToken {
            connect()
        } else {
            unlock()
        }
    }

    private func unlock() {
        busy = true
        Task {
            await state.unlock(password: password)
            busy = false
        }
    }

    private func connect() {
        busy = true
        Task {
            await state.connect(token: token)
            busy = false
        }
    }
}
