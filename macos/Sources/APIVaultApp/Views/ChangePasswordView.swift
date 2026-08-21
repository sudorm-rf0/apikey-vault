import SwiftUI

struct ChangePasswordView: View {
    @ObservedObject private var state = AppState.shared
    @Environment(\.dismiss) private var dismiss
    @State private var old = ""
    @State private var new = ""
    @State private var confirm = ""
    @State private var busy = false
    @State private var errorText: String?

    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            Text("Change master password")
                .font(.headline)

            SecureField("Old password", text: $old)
                .textFieldStyle(.roundedBorder)
            SecureField("New password", text: $new)
                .textFieldStyle(.roundedBorder)
            SecureField("Confirm new password", text: $confirm)
                .textFieldStyle(.roundedBorder)

            if let errorText {
                Text(errorText).font(.caption).foregroundStyle(.red)
            }

            HStack {
                Spacer()
                Button("Cancel") { dismiss() }
                    .keyboardShortcut(.cancelAction)
                Button {
                    change()
                } label: {
                    if busy {
                        ProgressView().controlSize(.small)
                    } else {
                        Text("Change")
                    }
                }
                .keyboardShortcut(.defaultAction)
                .buttonStyle(.borderedProminent)
                .disabled(busy)
            }
        }
        .padding(20)
        .frame(width: 380)
    }

    private func change() {
        guard new == confirm else {
            errorText = "New passwords do not match."
            return
        }
        guard !new.isEmpty else {
            errorText = "New password must not be empty."
            return
        }
        busy = true
        Task {
            await state.changePassword(old: old, new: new)
            busy = false
            if state.noticeIsError == false {
                dismiss()
            }
        }
    }
}
