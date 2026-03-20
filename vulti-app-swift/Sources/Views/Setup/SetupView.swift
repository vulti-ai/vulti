import SwiftUI

/// Gateway setup — warm paper background, centered content.
struct SetupView: View {
    @Environment(AppState.self) private var app
    @State private var isStarting = false
    @State private var error: String?

    var body: some View {
        ZStack {
            VStack(spacing: 24) {
                Spacer()

                Image(systemName: "brain.head.profile")
                    .font(.system(size: 64))
                    .foregroundStyle(VultiTheme.primary)

                Text("Vulti")
                    .font(.largeTitle)
                    .fontWeight(.bold)
                    .foregroundStyle(VultiTheme.inkSoft)

                Text("Start the gateway to connect your agents")
                    .foregroundStyle(VultiTheme.inkDim)

                if let error {
                    Text(error)
                        .foregroundStyle(VultiTheme.rose)
                        .font(.caption)
                }

                Button {
                    isStarting = true
                    error = nil
                    Task {
                        do {
                            try await app.startGateway()
                        } catch {
                            self.error = error.localizedDescription
                        }
                        isStarting = false
                    }
                } label: {
                    if isStarting {
                        ProgressView()
                            .controlSize(.small)
                            .frame(width: 140)
                    } else {
                        Text("Start Gateway")
                            .frame(width: 140)
                    }
                }
                .buttonStyle(.vultiPrimary)
                .tint(VultiTheme.primary)
                .controlSize(.large)
                .disabled(isStarting)

                Spacer()
            }
            .frame(maxWidth: 448)
        }
    }
}
