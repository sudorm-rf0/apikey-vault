import SwiftUI

/// A system-material card. The system provides Liquid Glass treatment to the
/// window chrome and standard controls on macOS 26 automatically; this card
/// uses the adaptive system material so it follows Light/Dark mode.
struct GlassCard<Content: View>: View {
    @ViewBuilder var content: Content

    var body: some View {
        content
            .padding(28)
            .background(.regularMaterial, in: RoundedRectangle(cornerRadius: 22, style: .continuous))
    }
}

/// Copy a string to the pasteboard.
func copyToPasteboard(_ string: String) {
    let pasteboard = NSPasteboard.general
    pasteboard.clearContents()
    pasteboard.setString(string, forType: .string)
}
