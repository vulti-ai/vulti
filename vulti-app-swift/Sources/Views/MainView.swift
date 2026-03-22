import SwiftUI

/// Main app view — canvas with left toolbar and left-sliding panel.
/// Warm paper background, toolbar buttons in paperWarm material.
struct MainView: View {
    @Environment(AppState.self) private var app

    var body: some View {
        ZStack {
            // Full-screen canvas (has its own paper background)
            SquadCanvas()

            // Left toolbar (matches screenshot: top-left, stacked, paper material)
            if app.panelMode == nil {
                // Top toolbar — settings left, activity right
                HStack {
                    ToolbarButton(icon: "gear", tooltip: "Settings") {
                        app.openSettings()
                    }
                    Spacer()
                    ToolbarButton(icon: "clock.arrow.circlepath", tooltip: "Activity") {
                        app.openAudit()
                    }
                }
                .padding(.horizontal, 20)
                .padding(.top, 20)
                .frame(maxHeight: .infinity, alignment: .top)
            }
        }
        .overlay {
            // Panel as an overlay — keeps it out of the ZStack safe area chain
            if app.panelMode != nil {
                // Scrim
                Color.black.opacity(0.15)
                    .ignoresSafeArea()
                    .onTapGesture { app.closePanel() }
                    .transition(.opacity)
            }
        }
        .overlay {
            if let mode = app.panelMode {
                SlideOutPanel(mode: mode)
                    .transition(mode.isBottomPanel
                        ? .move(edge: .bottom)
                        : .move(edge: .leading))
            }
        }
        .animation(.spring(duration: 0.25), value: app.panelMode)
    }
}

/// Toolbar button — warm paper circle, matching screenshot.
struct ToolbarButton: View {
    let icon: String
    let tooltip: String
    let action: () -> Void
    @State private var isHovered = false

    var body: some View {
        Button(action: action) {
            Image(systemName: icon)
                .font(.system(size: 14))
                .foregroundStyle(VultiTheme.rainbowGradient)
                .frame(width: 36, height: 36)
                .background {
                    RoundedRectangle(cornerRadius: 10)
                        .fill(.ultraThinMaterial)
                        .overlay(
                            RoundedRectangle(cornerRadius: 10)
                                .fill(VultiTheme.paperWarm.opacity(isHovered ? 0.9 : 0.6))
                        )
                }
                .overlay(
                    RoundedRectangle(cornerRadius: 10)
                        .stroke(VultiTheme.rainbowGradient, lineWidth: isHovered ? 1.5 : 1)
                )
                .scaleEffect(isHovered ? 1.08 : 1.0)
                .shadow(color: .black.opacity(isHovered ? 0.12 : 0.06), radius: isHovered ? 12 : 8, y: isHovered ? 6 : 4)
        }
        .buttonStyle(.plain)
        .help(tooltip)
        .onHover { isHovered = $0 }
        .animation(.easeOut(duration: 0.15), value: isHovered)
    }
}
