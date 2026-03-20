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
                VStack(spacing: 2) {
                    ToolbarButton(icon: "gear", tooltip: "Settings") {
                        app.openSettings()
                    }
                    ToolbarButton(icon: "plus", tooltip: "New Agent") {
                        app.openCreate()
                    }
                    ToolbarButton(icon: "clock.arrow.circlepath", tooltip: "Audit Log") {
                        app.openAudit()
                    }
                    Spacer()
                }
                .padding(.leading, 20)
                .padding(.top, 20)
                .frame(maxWidth: .infinity, alignment: .leading)
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

    var body: some View {
        Button(action: action) {
            Image(systemName: icon)
                .font(.system(size: 14))
                .foregroundStyle(VultiTheme.inkDim)
                .frame(width: 36, height: 36)
                .background {
                    RoundedRectangle(cornerRadius: 10)
                        .fill(.ultraThinMaterial)
                        .overlay(
                            RoundedRectangle(cornerRadius: 10)
                                .fill(VultiTheme.paperWarm.opacity(0.6))
                        )
                }
                .overlay(RoundedRectangle(cornerRadius: 10).stroke(VultiTheme.border))
        }
        .buttonStyle(.plain)
        .help(tooltip)
        .shadow(color: .black.opacity(0.06), radius: 8, y: 4)
    }
}
