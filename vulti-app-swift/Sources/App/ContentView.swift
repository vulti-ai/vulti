import SwiftUI

struct ContentView: View {
    @Environment(AppState.self) private var app

    var body: some View {
        ZStack {
            // Warm paper base
            VultiTheme.paper.ignoresSafeArea()

            // Ambient rainbow glow orbs (bleed through frosted surfaces)
            VultiTheme.ambientGlows().ignoresSafeArea()

            // 200gsm paper grain — global noise texture (matches Tauri feTurbulence)
            VultiTheme.noiseOverlay().ignoresSafeArea()

            if !app.hasToken {
                LoginView()
            } else if app.isGatewayRunning {
                MainView()
            } else {
                SetupView()
            }

            // Notifications overlay (top-right, max 3)
            VStack(alignment: .trailing, spacing: 8) {
                ForEach(Array(app.notifications.prefix(3))) { notif in
                    NotificationBanner(notification: notif)
                        .transition(.move(edge: .trailing).combined(with: .opacity))
                }
                Spacer()
            }
            .frame(maxWidth: .infinity, alignment: .trailing)
            .padding()
        }
        .animation(.easeInOut(duration: 0.2), value: app.hasToken)
        .animation(.easeInOut(duration: 0.2), value: app.isGatewayRunning)
        .animation(.easeInOut(duration: 0.15), value: app.notifications.count)
    }
}

struct NotificationBanner: View {
    let notification: AppNotification
    @Environment(AppState.self) private var app

    var body: some View {
        HStack(alignment: .top, spacing: 8) {
            VStack(alignment: .leading, spacing: 4) {
                Text(notification.source.uppercased())
                    .font(.system(size: 10, weight: .bold))
                    .foregroundStyle(VultiTheme.primary)
                Text(notification.summary)
                    .font(.caption)
                    .foregroundStyle(VultiTheme.inkSoft.opacity(0.8))
                    .lineLimit(2)
            }
            Spacer()
            Button {
                app.dismissNotification(notification.id)
            } label: {
                Image(systemName: "xmark")
                    .font(.system(size: 10))
                    .foregroundStyle(VultiTheme.inkMuted)
            }
            .buttonStyle(.plain)
        }
        .padding(12)
        .background(VultiTheme.paperWarm, in: RoundedRectangle(cornerRadius: 8))
        .overlay(RoundedRectangle(cornerRadius: 8).stroke(VultiTheme.border))
        .shadow(color: .black.opacity(0.08), radius: 12, y: 6)
        .frame(maxWidth: 300)
    }
}
