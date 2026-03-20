import SwiftUI

/// 5-step onboarding wizard (matches OnboardingWizard.svelte).
/// Steps: Role -> Connections -> Skills -> Actions -> Wallet
/// Steps 1-4 embed a ChatView with a channel-specific session and auto-sent initial message.
/// Step 5 embeds the existing FastVaultForm / VaultVerifyForm crypto vault creation UI.
struct OnboardingView: View {
    let agentId: String
    @Environment(AppState.self) private var app
    @State private var step = 1

    private struct StepInfo {
        let label: String
        let channel: String
        let initialMessage: String
    }

    private let steps: [(num: Int, label: String)] = [
        (1, "Role"),
        (2, "Connections"),
        (3, "Skills"),
        (4, "Actions"),
        (5, "Wallet"),
    ]

    private let chatSteps: [Int: StepInfo] = [
        1: StepInfo(
            label: "Role & Understanding",
            channel: "onboard-role",
            initialMessage: "What's my role and what should I know about you and my job?"
        ),
        2: StepInfo(
            label: "Connections",
            channel: "onboard-connections",
            initialMessage: "What services do you want me to connect to? Based on my role, I can suggest what I'll need."
        ),
        3: StepInfo(
            label: "Skills",
            channel: "onboard-skills",
            initialMessage: "What skills do you want me to have? Based on my role, here's what I'd suggest — let me check what's available and recommend the best ones for my job."
        ),
        4: StepInfo(
            label: "Actions",
            channel: "onboard-actions",
            initialMessage: "What do you want me to do each day, or what actions should I take when I see something?"
        ),
    ]

    var body: some View {
        VStack(spacing: 0) {
            // Step indicator bar
            stepIndicator

            Divider()

            // Content area
            VStack(spacing: 0) {
                if step <= 4, let cfg = chatSteps[step] {
                    ChatView(
                        agentId: agentId,
                        channel: cfg.channel,
                        initialMessage: cfg.initialMessage
                    )
                    .id("onboard-chat-\(step)") // Force new ChatView per step
                } else {
                    // Step 5: Wallet
                    walletStep
                }
            }
            .frame(maxWidth: .infinity, maxHeight: .infinity)

            Divider()

            // Footer with step counter + navigation
            footer
        }
    }

    // MARK: - Step Indicator

    private var stepIndicator: some View {
        HStack(spacing: 0) {
            // Completed "Create" checkmark
            HStack(spacing: 6) {
                ZStack {
                    Circle()
                        .fill(.tint.opacity(0.2))
                        .frame(width: 24, height: 24)
                    Image(systemName: "checkmark")
                        .font(.system(size: 10, weight: .bold))
                        .foregroundStyle(.tint)
                }
                Text(app.agent(byId: agentId)?.name ?? "Agent")
                    .font(.system(size: 11, weight: .medium))
                    .foregroundStyle(VultiTheme.inkDim)
            }

            ForEach(steps, id: \.num) { s in
                // Connector line
                Rectangle()
                    .fill(step > s.num ? Color.accentColor : step == s.num ? Color.accentColor.opacity(0.5) : VultiTheme.border)
                    .frame(width: 24, height: 1)
                    .padding(.horizontal, 4)

                // Step circle + label
                HStack(spacing: 6) {
                    ZStack {
                        Circle()
                            .fill(stepCircleFill(s.num))
                            .frame(width: 24, height: 24)
                        if step > s.num {
                            Image(systemName: "checkmark")
                                .font(.system(size: 10, weight: .bold))
                                .foregroundStyle(.tint)
                        } else {
                            Text("\(s.num)")
                                .font(.system(size: 10, weight: .bold))
                                .foregroundStyle(step == s.num ? .white : VultiTheme.inkDim)
                        }
                    }
                    Text(s.label)
                        .font(.system(size: 11, weight: .medium))
                        .foregroundStyle(step == s.num ? VultiTheme.inkSoft : VultiTheme.inkDim)
                }
            }

            Spacer()

            // Skip link
            Button("Skip") { skip() }
                .font(.system(size: 11))
                .foregroundStyle(VultiTheme.inkDim)
                .buttonStyle(.plain)
        }
        .padding(.horizontal, 16)
        .padding(.vertical, 10)
    }

    private func stepCircleFill(_ num: Int) -> some ShapeStyle {
        if step == num {
            return AnyShapeStyle(VultiTheme.rainbowGradient)
        } else if step > num {
            return AnyShapeStyle(.tint.opacity(0.2))
        } else {
            return AnyShapeStyle(VultiTheme.paperDeep)
        }
    }

    // MARK: - Wallet Step (step 5)

    private var walletStep: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 20) {
                Text("Set up a crypto vault for your agent")
                    .font(.system(size: 15, weight: .medium))

                Text("Create a Fast Vault to give your agent the ability to hold and transact with crypto assets. You can skip this and set it up later.")
                    .font(.system(size: 13))
                    .foregroundStyle(VultiTheme.inkDim)

                OnboardingWalletForm(agentId: agentId) {
                    handleWalletSaved()
                }
            }
            .padding(24)
        }
    }

    // MARK: - Footer

    private var footer: some View {
        HStack {
            Text("Step \(step) of 5")
                .font(.system(size: 11))
                .foregroundStyle(VultiTheme.inkDim)

            Spacer()

            if step <= 4 {
                Button("Next") { advance() }
                    .buttonStyle(.vultiPrimary)
            }
        }
        .padding(.horizontal, 16)
        .padding(.vertical, 10)
    }

    // MARK: - Actions

    private func advance() {
        if step == 1 {
            finalizeAndReload()
        }

        if step == 5 {
            finalizeAndReload()
            generateAvatarInBackground()
            app.openAgent(agentId)
        } else {
            step += 1
        }
    }

    private func skip() {
        if step == 5 {
            finalizeAndReload()
            generateAvatarInBackground()
            app.openAgent(agentId)
        } else {
            step += 1
        }
    }

    private func handleWalletSaved() {
        generateAvatarInBackground()
        finalizeAndReload()
        app.openAgent(agentId)
    }

    private func finalizeAndReload() {
        Task {
            try? await app.client.finalizeOnboarding(agentId: agentId)
            await app.refreshAgents()
        }
    }

    private func generateAvatarInBackground() {
        Task {
            try? await app.client.generateAvatar(agentId: agentId)
            app.invalidateAvatar(agentId)
            await app.refreshAgents()
        }
    }
}

/// Wallet form for onboarding step 5 — wraps FastVaultForm with onboarding-specific completion.
struct OnboardingWalletForm: View {
    let agentId: String
    let onSave: () -> Void
    @Environment(AppState.self) private var app
    @State private var phase: VaultPhase = .form
    @State private var vault: GatewayClient.VaultResponse?
    @State private var vaultName = ""
    @State private var vaultEmail = ""
    @State private var vaultPassword = ""
    @State private var vaultId = ""
    @State private var verifyCode = ""
    @State private var error: String?

    enum VaultPhase {
        case form, creating, verify, verifying
    }

    var body: some View {
        if let vault, vault.vaultId != nil {
            VStack(alignment: .leading, spacing: 12) {
                Label("Vault connected", systemImage: "checkmark.shield.fill")
                    .foregroundStyle(.green)
                LabeledContent("Name") { Text(vault.name ?? "Vault") }
                LabeledContent("Vault ID") {
                    Text(vault.vaultId ?? "")
                        .font(.system(size: 11)).monospaced().lineLimit(1)
                }
                Button("Continue") { onSave() }
                    .buttonStyle(.vultiPrimary)
            }
            .font(.system(size: 12))
        } else {
            switch phase {
            case .form:
                VStack(alignment: .leading, spacing: 12) {
                    TextField("Vault name", text: $vaultName).textFieldStyle(.vulti)
                    TextField("Email", text: $vaultEmail).textFieldStyle(.vulti)
                    SecureField("Password", text: $vaultPassword).textFieldStyle(.vulti)
                    Button("Create") { createVault() }
                        .buttonStyle(.vultiPrimary)
                        .disabled(vaultName.isEmpty || vaultEmail.isEmpty || vaultPassword.isEmpty)
                }
            case .creating:
                ProgressView("Creating vault...")
            case .verify:
                VStack(alignment: .leading, spacing: 12) {
                    Text("Enter the verification code sent to \(vaultEmail)")
                        .font(.system(size: 12)).foregroundStyle(VultiTheme.inkDim)
                    TextField("6-digit code", text: $verifyCode).textFieldStyle(.vulti)
                    HStack {
                        Button("Verify") { verifyVault() }
                            .buttonStyle(.vultiPrimary)
                            .disabled(verifyCode.trimmingCharacters(in: .whitespaces).isEmpty)
                        Button("Resend Code") { resendCode() }
                            .font(.system(size: 12))
                    }
                }
            case .verifying:
                ProgressView("Verifying...")
            }

            if let error {
                Text(error).font(.system(size: 11)).foregroundStyle(.red).padding(.top, 4)
            }
        }
    }

    private func createVault() {
        error = nil; phase = .creating
        Task {
            do {
                vaultId = try await app.vultisig.createFastVault(
                    name: vaultName.trimmingCharacters(in: .whitespaces),
                    email: vaultEmail.trimmingCharacters(in: .whitespaces),
                    password: vaultPassword
                )
                phase = .verify
            } catch { self.error = error.localizedDescription; phase = .form }
        }
    }

    private func verifyVault() {
        error = nil; phase = .verifying
        Task {
            do {
                _ = try await app.vultisig.verifyVault(
                    vaultId: vaultId,
                    code: verifyCode.trimmingCharacters(in: .whitespaces),
                    agentId: agentId
                )
                vault = try? await app.client.getVault(agentId: agentId)
                phase = .form
            } catch { self.error = error.localizedDescription; phase = .verify }
        }
    }

    private func resendCode() {
        error = nil
        Task {
            do {
                try await app.vultisig.resendVerification(
                    vaultId: vaultId, email: vaultEmail, password: vaultPassword
                )
            } catch { self.error = error.localizedDescription }
        }
    }
}
