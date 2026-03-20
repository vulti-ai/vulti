import SwiftUI

@main
struct VultiApp: App {
    @State private var appState = AppState()
    @AppStorage("vulti_theme") private var themeRaw: String = "system"

    private var colorScheme: ColorScheme? {
        ThemePreference(rawValue: themeRaw)?.colorScheme
    }

    var body: some Scene {
        WindowGroup {
            ContentView()
                .environment(appState)
                .vultiAppearance()
                .frame(minWidth: 900, minHeight: 660)
                .preferredColorScheme(colorScheme)
                .onAppear {
                    Task { await appState.boot() }
                }
        }
        .windowStyle(.titleBar)
        .defaultSize(width: 1200, height: 860)

        MenuBarExtra("Vulti", systemImage: "brain.head.profile") {
            MenuBarView()
                .environment(appState)
                .preferredColorScheme(colorScheme)
        }
    }
}
