import SwiftUI

struct MenuBarView: View {
    @Environment(AppState.self) private var app

    var body: some View {
        VStack {
            if app.isGatewayRunning {
                Label("Gateway Running", systemImage: "circle.fill")
                    .foregroundStyle(.green)
            } else {
                Label("Gateway Stopped", systemImage: "circle")
                    .foregroundStyle(VultiTheme.inkDim)
            }

            Divider()

            Button("Show Window") {
                NSApplication.shared.activate(ignoringOtherApps: true)
                if let window = NSApplication.shared.windows.first {
                    window.makeKeyAndOrderFront(nil)
                }
            }
            .keyboardShortcut("o")

            Divider()

            Button("Quit Vulti") {
                Task {
                    await app.stopGateway()
                    NSApplication.shared.terminate(nil)
                }
            }
            .keyboardShortcut("q")
        }
    }
}
