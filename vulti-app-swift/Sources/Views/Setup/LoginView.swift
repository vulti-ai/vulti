import SwiftUI

/// Token entry screen — shown when ~/.vulti/web_token is missing or empty.
struct LoginView: View {
    @Environment(AppState.self) private var app
    @State private var token = ""
    @State private var error: String?
    @State private var isSubmitting = false

    var body: some View {
        ZStack {
            VStack(spacing: 24) {
                Spacer()

                Image(systemName: "key.fill")
                    .font(.system(size: 48))
                    .foregroundStyle(VultiTheme.primary)

                Text("Vulti")
                    .font(.largeTitle)
                    .fontWeight(.bold)
                    .foregroundStyle(VultiTheme.inkSoft)

                Text("Paste the token shown in your terminal when you ran vulti gateway")
                    .multilineTextAlignment(.center)
                    .foregroundStyle(VultiTheme.inkDim)
                    .frame(maxWidth: 340)

                VStack(spacing: 12) {
                    VStack(alignment: .leading, spacing: 6) {
                        Text("Connection Token")
                            .font(.system(size: 13, weight: .medium))
                            .foregroundStyle(VultiTheme.inkSoft)
                        SecureField("Paste token here", text: $token)
                            .textFieldStyle(.vulti)
                    }

                    if let error {
                        Text(error)
                            .foregroundStyle(VultiTheme.rose)
                            .font(.system(size: 13))
                    }

                    Button {
                        submit()
                    } label: {
                        if isSubmitting {
                            ProgressView()
                                .controlSize(.small)
                                .frame(maxWidth: .infinity)
                        } else {
                            Text("Connect")
                                .font(.system(size: 13, weight: .medium))
                                .frame(maxWidth: .infinity)
                        }
                    }
                    .buttonStyle(.vultiPrimary)
                    .tint(VultiTheme.primary)
                    .controlSize(.large)
                    .disabled(token.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty || isSubmitting)
                }
                .padding(24)
                .background {
                    RoundedRectangle(cornerRadius: 12)
                        .fill(.ultraThinMaterial)
                        .overlay(RoundedRectangle(cornerRadius: 12).fill(VultiTheme.paperWarm.opacity(0.65)))
                }
                .overlay(RoundedRectangle(cornerRadius: 12).stroke(VultiTheme.border))
                .frame(maxWidth: 400)

                Spacer()
            }
            .frame(maxWidth: 448)
        }
    }

    private func submit() {
        let trimmed = token.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else { return }

        isSubmitting = true
        error = nil

        do {
            try VultiHome.atomicWriteString(trimmed, to: VultiHome.webTokenPath)
            // Re-check token and reboot the app state
            app.hasToken = true
            Task {
                await app.boot()
            }
        } catch {
            self.error = "Failed to save token: \(error.localizedDescription)"
        }

        isSubmitting = false
    }
}
