import SwiftUI

/// App-level onboarding — shown on first launch when no owner profile exists.
/// Four steps: (1) Identity, (2) Intelligence (AI provider, mandatory),
/// (3) Providers (speech/voice/image, optional), (4) Complete.
struct OnboardingView: View {
    @Environment(AppState.self) private var app

    @State private var step = 0

    // Step 1 — Identity
    @State private var name = "JP"
    @State private var password = "test1234"
    @State private var aboutMe = "Builder and founder living in Melbourne"

    // Step 2+3 — Providers
    @State private var providers: [GatewayClient.ProviderResponse] = []
    @State private var secrets: [GatewayClient.SecretResponse] = []
    @State private var selectedModel = ""
    @State private var selectedProviderId = ""

    // AI provider key
    @State private var showAddAIKey = false
    @State private var aiKeyName = "VENICE_API_KEY"
    @State private var aiKeyValue = ""
    @State private var isAddingAIKey = false

    // Speech provider key
    @State private var showAddSpeechKey = false
    @State private var speechKeyName = "ELEVENLABS_API_KEY"
    @State private var speechKeyValue = ""
    @State private var isAddingSpeechKey = false
    @State private var isDownloadingWhisper = false
    @State private var whisperDownloaded = false

    // Voice provider key (Bland / Twilio)
    @State private var showAddVoiceKey = false
    @State private var voiceKeyName = "BLAND_API_KEY"
    @State private var voiceKeyValue = ""
    @State private var isAddingVoiceKey = false

    // Image gen key
    @State private var showAddImageKey = false
    @State private var imageKeyName = "FAL_KEY"
    @State private var imageKeyValue = ""
    @State private var isAddingImageKey = false

    // Shared
    @State private var isSubmitting = false
    @State private var error: String?

    private static let aiKeyOptions: [(label: String, key: String)] = [
        ("Venice", "VENICE_API_KEY"),
        ("OpenRouter", "OPENROUTER_API_KEY"),
        ("Anthropic", "ANTHROPIC_API_KEY"),
        ("Claude Code OAuth", "CLAUDE_CODE_OAUTH_TOKEN"),
        ("OpenAI", "OPENAI_API_KEY"),
        ("DeepSeek", "DEEPSEEK_API_KEY"),
        ("Google AI", "GOOGLE_API_KEY"),
    ]

    private var authenticatedProviders: [GatewayClient.ProviderResponse] {
        providers.filter(\.authenticated)
    }

    private var hasElevenLabsKey: Bool {
        secrets.contains { $0.key == "ELEVENLABS_API_KEY" && ($0.isSet ?? false) }
    }

    private var hasFalKey: Bool {
        secrets.contains { $0.key == "FAL_KEY" && ($0.isSet ?? false) }
    }

    private var hasOpenAISpeechKey: Bool {
        secrets.contains { $0.key == "VOICE_TOOLS_OPENAI_KEY" && ($0.isSet ?? false) }
    }

    private var hasOpenAIImageKey: Bool {
        secrets.contains { $0.key == "OPENAI_API_KEY" && ($0.isSet ?? false) }
    }

    private var hasBlandKey: Bool {
        secrets.contains { $0.key == "BLAND_API_KEY" && ($0.isSet ?? false) }
    }

    private var hasTwilioKey: Bool {
        secrets.contains { $0.key == "TWILIO_AUTH_TOKEN" && ($0.isSet ?? false) }
    }

    private static let voiceKeyOptions: [(label: String, key: String)] = [
        ("Bland", "BLAND_API_KEY"),
        ("Twilio SID", "TWILIO_ACCOUNT_SID"),
        ("Twilio Token", "TWILIO_AUTH_TOKEN"),
        ("Twilio Phone", "TWILIO_PHONE_NUMBER"),
    ]

    private static let speechKeyOptions: [(label: String, key: String)] = [
        ("ElevenLabs", "ELEVENLABS_API_KEY"),
        ("OpenAI", "VOICE_TOOLS_OPENAI_KEY"),
    ]

    private static let imageKeyOptions: [(label: String, key: String)] = [
        ("fal.ai", "FAL_KEY"),
        ("OpenAI", "OPENAI_API_KEY"),
    ]


    // Networking + Messaging
    @State private var homeserverURL = ""
    @State private var messagingSubStep = 0  // 0 = download, 1 = sign in

    @State private var tailscaleStatus: TailscaleStatus = .checking
    @State private var tailscaleHostname = ""

    enum TailscaleStatus {
        case checking, notInstalled, notRunning, running
    }

    private static let stepCount = 7

    var body: some View {
        VStack(spacing: 0) {
            Spacer()

            if step == 0 {
                // Prerequisites splash — custom layout, no header/card
                prerequisitesStep
            } else {
                // Header
                Image(systemName: stepIcon)
                    .font(.system(size: 48))
                    .foregroundStyle(VultiTheme.primary)
                    .padding(.bottom, 8)

                Text(stepTitle)
                    .font(.title2)
                    .fontWeight(.bold)
                    .foregroundStyle(VultiTheme.inkSoft)
                    .padding(.bottom, 4)

                Text(stepSubtitle)
                    .font(.system(size: 13))
                    .foregroundStyle(VultiTheme.inkDim)
                    .multilineTextAlignment(.center)
                    .frame(maxWidth: 360)
                    .padding(.bottom, 24)

                // Step indicator
                HStack(spacing: 8) {
                    ForEach(0..<Self.stepCount, id: \.self) { i in
                        Capsule()
                            .fill(i <= step ? VultiTheme.primary : VultiTheme.paperShadow)
                            .frame(width: i == step ? 24 : 8, height: 4)
                    }
                }
                .padding(.bottom, 24)

                // Content card
                VStack(spacing: 16) {
                    switch step {
                    case 1: energyStep
                    case 2: identityStep
                    case 3: elementSignInStep
                    case 4: intelligenceStep
                    case 5: providersStep
                    case 6: completeStep
                    default: EmptyView()
                    }

                    if let error {
                        Text(error)
                            .font(.system(size: 12))
                            .foregroundStyle(VultiTheme.rose)
                    }
                }
                .padding(24)
                .background {
                    RoundedRectangle(cornerRadius: 12)
                        .fill(.ultraThinMaterial)
                        .overlay(RoundedRectangle(cornerRadius: 12).fill(VultiTheme.paperWarm.opacity(0.65)))
                }
                .overlay(RoundedRectangle(cornerRadius: 12).stroke(VultiTheme.border))
                .frame(maxWidth: 420)
            }

            Spacer()
        }
        .animation(.easeInOut(duration: 0.25), value: step)
        .task {
            providers = (try? await app.client.listProviders()) ?? []
            secrets = (try? await app.client.listSecrets()) ?? []
            autoSelectFirstModel()
            checkTailscale()
            checkWhisperInstalled()
            await fetchHomeserverURL()
        }
    }

    // MARK: - Step metadata

    private var stepIcon: String {
        switch step {
        case 0: return "" // prerequisites — custom layout
        case 1: return "bolt.fill"
        case 2: return "brain.head.profile"
        case 3: return "message.fill"
        case 4: return "brain"
        case 5: return "square.grid.2x2"
        case 6: return "person.2.fill"
        default: return ""
        }
    }

    private var stepTitle: String {
        switch step {
        case 0: return "" // prerequisites — custom layout
        case 1: return "Energy Settings"
        case 2: return "Welcome to Vulti"
        case 3: return "Sign In to Element X"
        case 4: return "Intelligence"
        case 5: return "Providers"
        case 6: return "Meet Hector"
        default: return ""
        }
    }

    private var stepSubtitle: String {
        switch step {
        case 0: return "" // prerequisites — custom layout
        case 1: return "Your agents run 24/7. Let\u{2019}s make sure your Mac stays awake for them."
        case 2: return "The fastest way to get multiple agents working for you at home."
        case 3: return "Sign in to Element X with your VultiHub credentials."
        case 4: return "Connect an AI provider so your agents can think. This is required."
        case 5: return "Optional providers for speech, phone calls, and image generation."
        case 6: return "Every VultiHub needs a wizard. Say hello to yours."
        default: return ""
        }
    }

    // MARK: - Step 0: Prerequisites

    // App Store URLs
    private static let tailscaleMacURL = "https://apps.apple.com/app/tailscale/id1475387142"
    private static let tailscaleIOSURL = "https://apps.apple.com/app/tailscale/id1470499037"
    private static let elementXIOSURL = "https://apps.apple.com/app/element-x-secure-messenger/id1631335820"

    private var prerequisitesStep: some View {
        VStack(spacing: 20) {
            Text("Your Private Network")
                .font(.title2)
                .fontWeight(.bold)
                .foregroundStyle(VultiTheme.inkSoft)

            Text("Set up your whole family on the same server — everyone gets their own agents, and you can even connect with friends\u{2019} agents securely. No cloud, no middlemen, just direct encrypted messaging between devices you control.")
                .font(.system(size: 13))
                .foregroundStyle(VultiTheme.inkDim)
                .multilineTextAlignment(.center)
                .frame(maxWidth: 460)

            Divider()
                .frame(maxWidth: 500)

            // ── Two-column layout: QR codes far apart ──
            HStack(alignment: .top, spacing: 120) {

                // Left column: Tailscale
                VStack(spacing: 12) {
                    ZStack {
                        Image(systemName: "network")
                            .font(.system(size: 28))
                            .foregroundStyle(.blue)
                        if tailscaleStatus == .running {
                            Image(systemName: "checkmark.circle.fill")
                                .font(.system(size: 14))
                                .foregroundStyle(VultiTheme.teal)
                                .offset(x: 16, y: -12)
                        }
                    }

                    Text("Tailscale")
                        .font(.system(size: 14, weight: .semibold))
                        .foregroundStyle(VultiTheme.inkSoft)

                    Text("Your private tunnel. Access your agents from anywhere — phone, laptop, even your family\u{2019}s devices.")
                        .font(.system(size: 11))
                        .foregroundStyle(VultiTheme.inkMuted)
                        .multilineTextAlignment(.center)
                        .frame(width: 180)
                        .fixedSize(horizontal: false, vertical: true)

                    // Status indicator
                    switch tailscaleStatus {
                    case .checking:
                        HStack(spacing: 4) {
                            ProgressView().controlSize(.mini)
                            Text("Checking...").font(.system(size: 10)).foregroundStyle(VultiTheme.inkMuted)
                        }
                    case .running:
                        HStack(spacing: 4) {
                            Image(systemName: "checkmark.circle.fill").foregroundStyle(VultiTheme.teal).font(.system(size: 11))
                            Text(tailscaleHostname.isEmpty ? "Connected" : tailscaleHostname)
                                .font(.system(size: 10, weight: .medium))
                                .foregroundStyle(VultiTheme.teal)
                                .lineLimit(1)
                        }
                    case .notRunning:
                        Text("Installed but not running \u{2014} open Tailscale")
                            .font(.system(size: 10, weight: .medium))
                            .foregroundStyle(.orange)
                            .multilineTextAlignment(.center)
                    case .notInstalled:
                        Text("Not installed")
                            .font(.system(size: 10, weight: .medium))
                            .foregroundStyle(VultiTheme.coral)
                    }

                    // Mac install link — only when not detected
                    if tailscaleStatus == .notInstalled {
                        Link("Install on this Mac", destination: URL(string: Self.tailscaleMacURL)!)
                            .font(.system(size: 11, weight: .medium))
                            .foregroundStyle(VultiTheme.primary)
                    }

                    // iPhone QR — always shown
                    qrCodeImage(for: Self.tailscaleIOSURL)
                        .interpolation(.none)
                        .resizable()
                        .scaledToFit()
                        .frame(width: 120, height: 120)
                        .padding(8)
                        .background(.white, in: RoundedRectangle(cornerRadius: 8))

                    Text("Scan with iPhone")
                        .font(.system(size: 10))
                        .foregroundStyle(VultiTheme.inkDim)
                }

                // Right column: Element X
                VStack(spacing: 12) {
                    Image(systemName: "message.fill")
                        .font(.system(size: 28))
                        .foregroundStyle(.green)

                    Text("Element X")
                        .font(.system(size: 14, weight: .semibold))
                        .foregroundStyle(VultiTheme.inkSoft)

                    Text("How you and your family message agents — fully private, no cloud servers involved.")
                        .font(.system(size: 11))
                        .foregroundStyle(VultiTheme.inkMuted)
                        .multilineTextAlignment(.center)
                        .frame(width: 180)
                        .fixedSize(horizontal: false, vertical: true)

                    // QR code for iPhone
                    qrCodeImage(for: Self.elementXIOSURL)
                        .interpolation(.none)
                        .resizable()
                        .scaledToFit()
                        .frame(width: 120, height: 120)
                        .padding(8)
                        .background(.white, in: RoundedRectangle(cornerRadius: 8))

                    Text("Scan with iPhone")
                        .font(.system(size: 10))
                        .foregroundStyle(VultiTheme.inkDim)

                    // No Mac link needed — Element X is phone only
                    Text("iPhone only")
                        .font(.system(size: 11))
                        .foregroundStyle(VultiTheme.inkDim)
                }
            }

            if tailscaleStatus == .running {
                Button {
                    withAnimation { step = 1 }
                } label: {
                    Text("Continue")
                        .font(.system(size: 13, weight: .medium))
                        .frame(maxWidth: .infinity)
                }
                .buttonStyle(.vultiPrimary)
                .controlSize(.large)
                .frame(maxWidth: 300)
            } else {
                HStack(spacing: 8) {
                    ProgressView().controlSize(.small)
                    Text("Waiting for Tailscale...")
                        .font(.system(size: 13))
                        .foregroundStyle(VultiTheme.inkMuted)
                }
            }
        }
        .task(id: "tailscale-poll") {
            // Poll every 3 seconds until Tailscale is running
            while !Task.isCancelled && tailscaleStatus != .running {
                checkTailscale()
                try? await Task.sleep(for: .seconds(3))
            }
        }
    }

    /// Generate a QR code image from a string using CoreImage.
    private func qrCodeImage(for string: String) -> Image {
        let context = CIContext()
        guard let filter = CIFilter(name: "CIQRCodeGenerator") else {
            return Image(systemName: "qrcode")
        }
        filter.setValue(Data(string.utf8), forKey: "inputMessage")
        filter.setValue("M", forKey: "inputCorrectionLevel")

        guard let output = filter.outputImage,
              let cgImage = context.createCGImage(output, from: output.extent) else {
            return Image(systemName: "qrcode")
        }
        return Image(nsImage: NSImage(cgImage: cgImage, size: NSSize(width: output.extent.width, height: output.extent.height)))
    }

    // MARK: - Step 1: Energy Settings

    @State private var energyStatus: PowerManager.EnergyStatus?
    @State private var energyApplied = false
    @State private var energyApplying = false

    private var energyStep: some View {
        VStack(spacing: 16) {
            if let status = energyStatus {
                VStack(spacing: 10) {
                    energyRow("Prevent Sleep", isOptimal: status.sleepDisabled, detail: "Keeps agents running when idle")
                    energyRow("Disk Always On", isOptimal: status.diskSleepDisabled, detail: "Avoids database latency after idle")
                    energyRow("Wake for Network", isOptimal: status.wakeOnNetwork, detail: "Agents can receive messages while sleeping")
                    energyRow("Auto-Restart", isOptimal: status.autoRestart, detail: "Recovers automatically after power loss")
                }

                if status.allOptimal || energyApplied {
                    HStack(spacing: 6) {
                        Image(systemName: "checkmark.circle.fill")
                            .foregroundStyle(VultiTheme.teal)
                            .font(.system(size: 13))
                        Text("All set")
                            .font(.system(size: 12))
                            .foregroundStyle(VultiTheme.teal)
                    }
                    .padding(.top, 4)
                } else {
                    Button {
                        energyApplying = true
                        let success = app.power.applyOptimalSettings()
                        energyApplying = false
                        if success {
                            energyApplied = true
                            energyStatus = app.power.currentEnergyStatus()
                        }
                    } label: {
                        if energyApplying {
                            ProgressView()
                                .controlSize(.small)
                                .frame(maxWidth: .infinity)
                        } else {
                            Text("Optimize Settings")
                                .font(.system(size: 13, weight: .medium))
                                .frame(maxWidth: .infinity)
                        }
                    }
                    .buttonStyle(.vultiPrimary)
                    .controlSize(.large)
                    .disabled(energyApplying)
                }
            } else {
                ProgressView("Checking energy settings...")
                    .font(.system(size: 12))
            }

            Button {
                withAnimation { step = 2 }
            } label: {
                Text(energyStatus?.allOptimal == true || energyApplied ? "Continue" : "Skip")
                    .font(.system(size: 13, weight: .medium))
                    .frame(maxWidth: .infinity)
            }
            .buttonStyle(.vultiSecondary)
            .controlSize(.large)
        }
        .onAppear {
            energyStatus = app.power.currentEnergyStatus()
        }
    }

    private func energyRow(_ label: String, isOptimal: Bool, detail: String) -> some View {
        HStack(spacing: 10) {
            Image(systemName: isOptimal ? "checkmark.circle.fill" : "exclamationmark.circle")
                .foregroundStyle(isOptimal ? VultiTheme.teal : .orange)
                .font(.system(size: 14))
            VStack(alignment: .leading, spacing: 2) {
                Text(label)
                    .font(.system(size: 13, weight: .medium))
                    .foregroundStyle(VultiTheme.inkSoft)
                Text(detail)
                    .font(.system(size: 11))
                    .foregroundStyle(VultiTheme.inkMuted)
            }
            Spacer()
        }
        .padding(10)
        .background(
            RoundedRectangle(cornerRadius: 8)
                .fill(isOptimal ? VultiTheme.teal.opacity(0.06) : Color.orange.opacity(0.06))
        )
    }

    // MARK: - Step 2: Identity

    private var identityStep: some View {
        VStack(spacing: 14) {
            VStack(alignment: .leading, spacing: 6) {
                Text("Name")
                    .font(.system(size: 13, weight: .medium))
                    .foregroundStyle(VultiTheme.inkSoft)
                TextField("Your name", text: $name)
                    .textFieldStyle(.vulti)
                Text("This will be your username and Matrix identity.")
                    .font(.system(size: 11))
                    .foregroundStyle(VultiTheme.inkMuted)
            }

            VStack(alignment: .leading, spacing: 6) {
                Text("Password")
                    .font(.system(size: 13, weight: .medium))
                    .foregroundStyle(VultiTheme.inkSoft)
                TextField("Choose a password", text: $password)
                    .textFieldStyle(.vulti)
                Text("Keep it simple — this is a local homeserver.")
                    .font(.system(size: 11))
                    .foregroundStyle(VultiTheme.inkMuted)
            }

            VStack(alignment: .leading, spacing: 6) {
                Text("About Me")
                    .font(.system(size: 13, weight: .medium))
                    .foregroundStyle(VultiTheme.inkSoft)
                TextEditor(text: $aboutMe)
                    .font(.system(size: 13))
                    .scrollContentBackground(.hidden)
                    .padding(8)
                    .frame(height: 80)
                    .background(VultiTheme.paperDeep.opacity(0.5), in: RoundedRectangle(cornerRadius: 8))
                    .overlay(RoundedRectangle(cornerRadius: 8).stroke(VultiTheme.border))
                Text("Basic information your agents should know about you.")
                    .font(.system(size: 11))
                    .foregroundStyle(VultiTheme.inkMuted)
            }

            Button {
                submitIdentity()
            } label: {
                if isSubmitting {
                    ProgressView()
                        .controlSize(.small)
                        .frame(maxWidth: .infinity)
                } else {
                    Text("Next")
                        .font(.system(size: 13, weight: .medium))
                        .frame(maxWidth: .infinity)
                }
            }
            .buttonStyle(.vultiPrimary)
            .controlSize(.large)
            .disabled(name.trimmingCharacters(in: .whitespaces).isEmpty
                      || password.trimmingCharacters(in: .whitespaces).isEmpty
                      || isSubmitting)
        }
    }

    // MARK: - Step 2: Intelligence (AI provider — mandatory)

    private var selectedProviderObj: GatewayClient.ProviderResponse? {
        authenticatedProviders.first { $0.id == selectedProviderId }
    }

    private var intelligenceStep: some View {
        VStack(spacing: 14) {
            if authenticatedProviders.isEmpty {
                HStack(spacing: 8) {
                    Image(systemName: "exclamationmark.triangle")
                        .foregroundStyle(.orange)
                    Text("No AI provider configured yet.")
                        .font(.system(size: 12))
                        .foregroundStyle(VultiTheme.inkDim)
                }
                .padding(10)
                .frame(maxWidth: .infinity, alignment: .leading)
                .background(Color.orange.opacity(0.08), in: RoundedRectangle(cornerRadius: 6))

            } else if selectedProviderId.isEmpty {
                // Step 1: Pick a provider
                Text("Choose your AI provider")
                    .font(.system(size: 12))
                    .foregroundStyle(VultiTheme.inkMuted)

                VStack(alignment: .leading, spacing: 6) {
                    ForEach(authenticatedProviders, id: \.id) { provider in
                        HStack(spacing: 10) {
                            Image(systemName: "circle")
                                .font(.system(size: 14))
                                .foregroundStyle(VultiTheme.inkDim)
                            Text(provider.name)
                                .font(.system(size: 13, weight: .medium))
                                .foregroundStyle(VultiTheme.inkSoft)
                            Spacer()
                            Text("\(provider.models?.count ?? 0) models")
                                .font(.system(size: 11))
                                .foregroundStyle(VultiTheme.inkMuted)
                            Image(systemName: "chevron.right")
                                .font(.system(size: 11))
                                .foregroundStyle(VultiTheme.inkMuted)
                        }
                        .padding(.vertical, 8)
                        .padding(.horizontal, 12)
                        .background(VultiTheme.paperDeep.opacity(0.5), in: RoundedRectangle(cornerRadius: 8))
                        .contentShape(Rectangle())
                        .onTapGesture {
                            selectedProviderId = provider.id
                            // Auto-select first model
                            if let first = provider.models?.first {
                                selectedModel = first.strippingProviderPrefix()
                            }
                        }
                    }
                }

            } else if let provider = selectedProviderObj {
                // Step 2: Pick a model from the selected provider
                VStack(alignment: .leading, spacing: 8) {
                    HStack(spacing: 8) {
                        Button {
                            selectedProviderId = ""
                            selectedModel = ""
                        } label: {
                            Image(systemName: "chevron.left")
                                .font(.system(size: 11, weight: .medium))
                                .foregroundStyle(VultiTheme.primary)
                        }
                        .buttonStyle(.plain)

                        Text(provider.name)
                            .font(.system(size: 11, weight: .semibold))
                            .foregroundStyle(VultiTheme.inkDim)
                            .textCase(.uppercase)
                    }

                    ModelPicker(
                        style: .radioList,
                        selectedModel: $selectedModel,
                        providers: [provider]
                    )
                }
                .padding(12)
                .frame(maxWidth: .infinity, alignment: .topLeading)
                .background(VultiTheme.paperDeep.opacity(0.5), in: RoundedRectangle(cornerRadius: 8))
            }

            inlineKeyEntry(
                showBinding: $showAddAIKey,
                keyName: $aiKeyName,
                keyValue: $aiKeyValue,
                isAdding: $isAddingAIKey,
                options: Self.aiKeyOptions,
                buttonLabel: "+ Add AI provider key"
            ) {
                addSecret(key: aiKeyName, value: aiKeyValue) {
                    aiKeyValue = ""
                    showAddAIKey = false
                    isAddingAIKey = false
                }
            }

            HStack {
                Button("Back") { step = 3 }
                    .font(.system(size: 13))
                    .foregroundStyle(VultiTheme.inkMuted)
                    .buttonStyle(.plain)

                Spacer()

                Button("Next") { submitIntelligence() }
                    .buttonStyle(.vultiPrimary)
                    .disabled(authenticatedProviders.isEmpty || selectedModel.isEmpty)
            }
        }
        .animation(.easeInOut(duration: 0.2), value: selectedProviderId)
    }

    // MARK: - Step 3: Providers (speech, voice, image — optional)

    private var providersStep: some View {
        ScrollView {
            VStack(spacing: 20) {

                // ── Speech Provider ──
                providerSection(
                    icon: "waveform",
                    title: "Speech",
                    subtitle: "Voice transcription and text-to-speech"
                ) {
                    // Whisper local
                    HStack(spacing: 10) {
                        Image(systemName: whisperDownloaded ? "checkmark.circle.fill" : "arrow.down.circle")
                            .foregroundStyle(whisperDownloaded ? VultiTheme.teal : VultiTheme.inkDim)
                            .font(.system(size: 14))
                        VStack(alignment: .leading, spacing: 2) {
                            Text("Whisper Local")
                                .font(.system(size: 12, weight: .medium))
                                .foregroundStyle(VultiTheme.inkSoft)
                            Text("Free, on-device speech-to-text")
                                .font(.system(size: 11))
                                .foregroundStyle(VultiTheme.inkMuted)
                        }
                        Spacer()
                        Button(isDownloadingWhisper ? "Installing..." : (whisperDownloaded ? "Installed" : "Download")) {
                            downloadWhisper()
                        }
                        .font(.system(size: 11, weight: .medium))
                        .buttonStyle(.vultiSecondary)
                        .disabled(isDownloadingWhisper || whisperDownloaded)
                    }

                    // Connected speech providers
                    if hasElevenLabsKey {
                        connectedRow(name: "ElevenLabs")
                    }
                    if hasOpenAISpeechKey {
                        connectedRow(name: "OpenAI")
                    }

                    inlineKeyEntry(
                        showBinding: $showAddSpeechKey,
                        keyName: $speechKeyName,
                        keyValue: $speechKeyValue,
                        isAdding: $isAddingSpeechKey,
                        options: Self.speechKeyOptions,
                        buttonLabel: "+ Add speech provider key"
                    ) {
                        addSecret(key: speechKeyName, value: speechKeyValue) {
                            speechKeyValue = ""
                            showAddSpeechKey = false
                            isAddingSpeechKey = false
                        }
                    }
                }

                // ── Voice Provider ──
                providerSection(
                    icon: "phone.arrow.up.right",
                    title: "Voice",
                    subtitle: "Phone calls and voice AI"
                ) {
                    if hasBlandKey {
                        connectedRow(name: "Bland")
                    }
                    if hasTwilioKey {
                        connectedRow(name: "Twilio")
                    }

                    inlineKeyEntry(
                        showBinding: $showAddVoiceKey,
                        keyName: $voiceKeyName,
                        keyValue: $voiceKeyValue,
                        isAdding: $isAddingVoiceKey,
                        options: Self.voiceKeyOptions,
                        buttonLabel: "+ Add voice provider key"
                    ) {
                        addSecret(key: voiceKeyName, value: voiceKeyValue) {
                            voiceKeyValue = ""
                            showAddVoiceKey = false
                            isAddingVoiceKey = false
                        }
                    }
                }

                // ── Image Gen Provider ──
                providerSection(
                    icon: "photo.artframe",
                    title: "Image Generation",
                    subtitle: "Let agents create images"
                ) {
                    if hasFalKey {
                        connectedRow(name: "fal.ai")
                    }
                    if hasOpenAIImageKey {
                        connectedRow(name: "OpenAI")
                    }

                    inlineKeyEntry(
                        showBinding: $showAddImageKey,
                        keyName: $imageKeyName,
                        keyValue: $imageKeyValue,
                        isAdding: $isAddingImageKey,
                        options: Self.imageKeyOptions,
                        buttonLabel: "+ Add image gen key"
                    ) {
                        addSecret(key: imageKeyName, value: imageKeyValue) {
                            imageKeyValue = ""
                            showAddImageKey = false
                            isAddingImageKey = false
                        }
                    }
                }

                // ── Navigation ──
                HStack {
                    Button("Back") { step = 4 }
                        .font(.system(size: 13))
                        .foregroundStyle(VultiTheme.inkMuted)
                        .buttonStyle(.plain)

                    Spacer()

                    Button("Skip") { step = 6 }
                        .font(.system(size: 13))
                        .foregroundStyle(VultiTheme.inkMuted)
                        .buttonStyle(.plain)

                    Button("Next") { step = 6 }
                        .buttonStyle(.vultiPrimary)
                }
            }
        }
        .frame(maxHeight: 480)
    }

    // MARK: - Provider section container

    @ViewBuilder
    private func providerSection(
        icon: String,
        title: String,
        subtitle: String,
        @ViewBuilder content: () -> some View
    ) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack(spacing: 8) {
                Image(systemName: icon)
                    .font(.system(size: 14))
                    .foregroundStyle(VultiTheme.primary)
                VStack(alignment: .leading, spacing: 1) {
                    Text(title)
                        .font(.system(size: 13, weight: .semibold))
                        .foregroundStyle(VultiTheme.inkSoft)
                    Text(subtitle)
                        .font(.system(size: 11))
                        .foregroundStyle(VultiTheme.inkMuted)
                }
            }

            VStack(alignment: .leading, spacing: 8) {
                content()
            }
            .padding(12)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(VultiTheme.paperDeep.opacity(0.5), in: RoundedRectangle(cornerRadius: 8))
        }
    }

    // MARK: - Inline key entry (multi-provider picker)

    @ViewBuilder
    private func inlineKeyEntry(
        showBinding: Binding<Bool>,
        keyName: Binding<String>,
        keyValue: Binding<String>,
        isAdding: Binding<Bool>,
        options: [(label: String, key: String)],
        buttonLabel: String,
        onSave: @escaping () -> Void
    ) -> some View {
        if showBinding.wrappedValue {
            HStack(spacing: 8) {
                Picker("", selection: keyName) {
                    ForEach(options, id: \.key) { opt in
                        Text(opt.label).tag(opt.key)
                    }
                }
                .labelsHidden()
                .frame(width: 130)

                SecureField("Paste API key", text: keyValue)
                    .textFieldStyle(.vulti)

                Button(isAdding.wrappedValue ? "Saving..." : "Save") {
                    isAdding.wrappedValue = true
                    onSave()
                }
                .buttonStyle(.vultiPrimary)
                .font(.system(size: 11, weight: .medium))
                .disabled(isAdding.wrappedValue || keyValue.wrappedValue.trimmingCharacters(in: .whitespaces).isEmpty)

                Button("Cancel") {
                    showBinding.wrappedValue = false
                    keyValue.wrappedValue = ""
                }
                .font(.system(size: 11))
                .foregroundStyle(VultiTheme.inkMuted)
                .buttonStyle(.plain)
            }
        } else {
            Button(buttonLabel) {
                showBinding.wrappedValue = true
            }
            .font(.system(size: 12))
            .foregroundStyle(VultiTheme.primary)
            .buttonStyle(.plain)
        }
    }

    // MARK: - Inline secret entry (single key)

    @ViewBuilder
    private func inlineSecretEntry(
        showBinding: Binding<Bool>,
        keyValue: Binding<String>,
        isAdding: Binding<Bool>,
        secretKey: String,
        placeholder: String,
        buttonLabel: String
    ) -> some View {
        if showBinding.wrappedValue {
            HStack(spacing: 8) {
                SecureField(placeholder, text: keyValue)
                    .textFieldStyle(.vulti)

                Button(isAdding.wrappedValue ? "Saving..." : "Save") {
                    isAdding.wrappedValue = true
                    addSecret(key: secretKey, value: keyValue.wrappedValue) {
                        keyValue.wrappedValue = ""
                        showBinding.wrappedValue = false
                        isAdding.wrappedValue = false
                    }
                }
                .buttonStyle(.vultiPrimary)
                .font(.system(size: 11, weight: .medium))
                .disabled(isAdding.wrappedValue || keyValue.wrappedValue.trimmingCharacters(in: .whitespaces).isEmpty)

                Button("Cancel") {
                    showBinding.wrappedValue = false
                    keyValue.wrappedValue = ""
                }
                .font(.system(size: 11))
                .foregroundStyle(VultiTheme.inkMuted)
                .buttonStyle(.plain)
            }
        } else {
            Button(buttonLabel) {
                showBinding.wrappedValue = true
            }
            .font(.system(size: 12))
            .foregroundStyle(VultiTheme.primary)
            .buttonStyle(.plain)
        }
    }

    // MARK: - Step 2: Sign In to Element X

    private var elementSignInStep: some View {
        VStack(spacing: 16) {
            // Step-by-step instructions
            VStack(alignment: .leading, spacing: 12) {
                signInStepRow(number: "1", text: "Open Element X on your phone")
                signInStepRow(number: "2", text: "Tap \"Change account provider\"")
                signInStepRow(number: "3", text: "Enter your homeserver URL below")
                signInStepRow(number: "4", text: "Sign in with your username and password")
            }
            .padding(14)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(VultiTheme.paperDeep.opacity(0.5), in: RoundedRectangle(cornerRadius: 8))

            // Connection details
            VStack(alignment: .leading, spacing: 10) {
                Text("YOUR CREDENTIALS")
                    .font(.system(size: 11, weight: .bold))
                    .foregroundStyle(VultiTheme.inkDim)

                connectionRow(label: "Server", value: homeserverURL.isEmpty ? "Loading..." : homeserverURL)
                connectionRow(label: "Username", value: name.lowercased().replacingOccurrences(of: " ", with: "_"))
                connectionRow(label: "Password", value: password)
            }
            .padding(14)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(VultiTheme.paperDeep.opacity(0.5), in: RoundedRectangle(cornerRadius: 8))

            Text("You can find your server URL in the Tailscale app on iOS under your machine name.")
                .font(.system(size: 11))
                .foregroundStyle(VultiTheme.inkDim)

            HStack {
                Button("Back") { step = 2 }
                    .font(.system(size: 13))
                    .foregroundStyle(VultiTheme.inkMuted)
                    .buttonStyle(.plain)
                Spacer()
                Button("Next") { step = 4 }
                    .buttonStyle(.vultiPrimary)
            }
        }
    }

    @ViewBuilder
    private func signInStepRow(number: String, text: String) -> some View {
        HStack(alignment: .top, spacing: 10) {
            Text(number)
                .font(.system(size: 10, weight: .bold, design: .monospaced))
                .foregroundStyle(VultiTheme.paperWarm)
                .frame(width: 18, height: 18)
                .background(VultiTheme.primary, in: Circle())
            Text(text)
                .font(.system(size: 12))
                .foregroundStyle(VultiTheme.inkSoft)
        }
    }

    @ViewBuilder
    private func connectedRow(name: String) -> some View {
        HStack(spacing: 10) {
            Image(systemName: "checkmark.circle.fill")
                .foregroundStyle(VultiTheme.teal)
                .font(.system(size: 14))
            Text(name)
                .font(.system(size: 12, weight: .medium))
                .foregroundStyle(VultiTheme.inkSoft)
            Spacer()
            Text("Connected")
                .font(.system(size: 11))
                .foregroundStyle(VultiTheme.inkMuted)
        }
    }

    private func connectionRow(label: String, value: String) -> some View {
        HStack {
            Text(label)
                .font(.system(size: 12, weight: .medium))
                .foregroundStyle(VultiTheme.inkDim)
                .frame(width: 80, alignment: .leading)
            Text(value)
                .font(.system(size: 12, design: .monospaced))
                .foregroundStyle(VultiTheme.inkSoft)
                .textSelection(.enabled)
                .fixedSize(horizontal: false, vertical: true)
        }
    }

    private func generateQRCode(from string: String) -> NSImage? {
        guard let data = string.data(using: .utf8),
              let filter = CIFilter(name: "CIQRCodeGenerator") else { return nil }
        filter.setValue(data, forKey: "inputMessage")
        filter.setValue("M", forKey: "inputCorrectionLevel")
        guard let ciImage = filter.outputImage else { return nil }
        let scaled = ciImage.transformed(by: CGAffineTransform(scaleX: 10, y: 10))
        let rep = NSCIImageRep(ciImage: scaled)
        let nsImage = NSImage(size: rep.size)
        nsImage.addRepresentation(rep)
        return nsImage
    }

    // MARK: - Step 5: Meet Hector

    @State private var hectorEnabled = false
    @State private var isActivatingHector = false

    private var hectorExists: Bool {
        app.agentList.contains { $0.id == "hector" && $0.status == "active" }
    }

    private var completeStep: some View {
        VStack(spacing: 20) {

            // ── Hector ──
            HStack(spacing: 8) {
                Text("🧙")
                    .font(.system(size: 20))
                VStack(alignment: .leading, spacing: 2) {
                    Text("Hector")
                        .font(.system(size: 13, weight: .semibold))
                        .foregroundStyle(VultiTheme.inkSoft)
                    Text("Hector guards your system — patching security, watching connections, managing files, and keeping every agent in line. He\u{2019}ll also help you create your first one.")
                        .font(.system(size: 11))
                        .foregroundStyle(VultiTheme.inkMuted)
                        .fixedSize(horizontal: false, vertical: true)
                }
            }
            .padding(14)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(VultiTheme.paperDeep.opacity(0.5), in: RoundedRectangle(cornerRadius: 8))

            if hectorEnabled || hectorExists {
                HStack(spacing: 6) {
                    Image(systemName: "checkmark.circle.fill")
                        .foregroundStyle(VultiTheme.teal)
                        .font(.system(size: 13))
                    Text("Active")
                        .font(.system(size: 12))
                        .foregroundStyle(VultiTheme.teal)
                }
            } else {
                Button {
                    activateHector()
                } label: {
                    if isActivatingHector {
                        ProgressView()
                            .controlSize(.small)
                            .frame(maxWidth: .infinity)
                    } else {
                        Text("Start Hector")
                            .font(.system(size: 13, weight: .medium))
                            .frame(maxWidth: .infinity)
                    }
                }
                .buttonStyle(.vultiPrimary)
                .controlSize(.large)
                .disabled(isActivatingHector)
            }
        }
    }

    // MARK: - Actions

    private func activateHector() {
        isActivatingHector = true
        Task {
            do {
                // Hector is auto-seeded by the registry, just needs Matrix onboarding
                _ = try? await app.client.updateAgent("hector", updates: [
                    "allowedConnections": "matrix"
                ])
                try? await app.client.installSkill(agentId: "hector", name: "matrix")
                try? await app.client.onboardAgentToMatrix(agentId: "hector")
                try? await app.client.finalizeOnboarding(agentId: "hector", role: "wizard")

                // Send Hector's introduction prompt so he greets the owner
                let introPrompt = """
                Introduce yourself to the owner. This is their first time using VultiHub. \
                Tell them who you are (Hector, the system wizard), what you do (manage security, \
                system integrity, connections, and the file system), and what you're about to do \
                right now (run a status check on the system, verify connections, and make sure \
                everything is healthy). Keep it warm but brief — 2-3 sentences max.
                """
                let session = try? await app.client.createSession(agentId: "hector", name: "Welcome")
                if let session {
                    // Send via gateway REST API so Hector responds through the normal flow
                    _ = try? await app.gateway.postRaw(
                        path: "sessions/\(session.id)/chat",
                        body: ["content": introPrompt, "agent_id": "hector"]
                    )
                }

                await app.refreshAgents()
                await MainActor.run {
                    hectorEnabled = true
                    isActivatingHector = false
                    // Complete onboarding and open a chat with Hector
                    Persistence.onboardingComplete = true
                    app.onboardingComplete = true
                    app.openAgent("hector")
                }
            }
        }
    }

    /// Find the tailscale CLI binary. Mac App Store version lives inside the .app bundle.
    private static let tailscaleCLIPaths = [
        "/Applications/Tailscale.app/Contents/MacOS/Tailscale",
        "/usr/local/bin/tailscale",
        "/opt/homebrew/bin/tailscale",
    ]

    private func checkTailscale() {
        tailscaleStatus = .checking
        Task {
            // Find tailscale binary
            let binary = Self.tailscaleCLIPaths.first { FileManager.default.isExecutableFile(atPath: $0) }

            guard let binary else {
                await MainActor.run { tailscaleStatus = .notInstalled }
                return
            }

            let process = Process()
            process.executableURL = URL(fileURLWithPath: binary)
            process.arguments = ["status", "--self", "--json"]
            let pipe = Pipe()
            process.standardOutput = pipe
            process.standardError = Pipe()

            do {
                try process.run()
                process.waitUntilExit()

                if process.terminationStatus == 0 {
                    let data = pipe.fileHandleForReading.readDataToEndOfFile()
                    if let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
                       let selfNode = json["Self"] as? [String: Any],
                       let dnsName = selfNode["DNSName"] as? String, !dnsName.isEmpty {
                        let hostname = dnsName.hasSuffix(".") ? String(dnsName.dropLast()) : dnsName
                        await MainActor.run {
                            tailscaleHostname = hostname
                            tailscaleStatus = .running
                        }
                        return
                    }
                    await MainActor.run { tailscaleStatus = .notRunning }
                } else {
                    await MainActor.run { tailscaleStatus = .notRunning }
                }
            } catch {
                await MainActor.run { tailscaleStatus = .notInstalled }
            }
        }
    }

    private func fetchHomeserverURL() async {
        // Use Tailscale MagicDNS hostname so Element X can reach the server from any device.
        // Fallback to localhost only if Tailscale hostname isn't available.
        let host = tailscaleHostname.isEmpty ? "localhost" : tailscaleHostname

        // Try .well-known first to get the actual port
        let url = URL(string: "http://localhost:8080/.well-known/matrix/client")!
        var request = URLRequest(url: url)
        if let token = VultiHome.webToken() {
            request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        }
        homeserverURL = host
    }

    private func autoSelectFirstModel() {
        guard selectedModel.isEmpty else { return }
        if let first = authenticatedProviders.first,
           let firstModel = first.models?.first {
            selectedModel = firstModel.strippingProviderPrefix()
        }
    }

    private func submitIntelligence() {
        guard !selectedModel.isEmpty else { return }
        // Save selected model as the system default via env
        Task {
            try? await app.client.addSecret(key: "VULTI_DEFAULT_MODEL", value: selectedModel)
        }
        step = 5
    }

    private func submitIdentity() {
        let trimmedName = name.trimmingCharacters(in: .whitespaces)
        let trimmedPassword = password.trimmingCharacters(in: .whitespaces)
        guard !trimmedName.isEmpty, !trimmedPassword.isEmpty else { return }

        isSubmitting = true
        error = nil

        Task {
            do {
                // Save owner profile
                try await app.client.updateOwner(name: trimmedName, about: aboutMe.trimmingCharacters(in: .whitespacesAndNewlines))

                // Register Matrix account with the same name/password
                try await app.client.registerMatrix(
                    username: trimmedName.lowercased().replacingOccurrences(of: " ", with: "_"),
                    password: trimmedPassword
                )

                await app.refreshOwner()

                await MainActor.run {
                    step = 3
                    isSubmitting = false
                }
            } catch {
                await MainActor.run {
                    self.error = error.localizedDescription
                    isSubmitting = false
                }
            }
        }
    }

    private func addSecret(key: String, value: String, completion: @escaping () -> Void) {
        let trimmed = value.trimmingCharacters(in: .whitespaces)
        guard !trimmed.isEmpty else { return }
        Task {
            try? await app.client.addSecret(key: key, value: trimmed)
            providers = (try? await app.client.listProviders()) ?? []
            secrets = (try? await app.client.listSecrets()) ?? []
            autoSelectFirstModel()
            await MainActor.run { completion() }
        }
    }

    private func checkWhisperInstalled() {
        Task.detached {
            let process = Process()
            process.executableURL = URL(fileURLWithPath: "/bin/zsh")
            process.arguments = ["-lc", "python3 -c 'import faster_whisper' 2>/dev/null"]
            process.standardOutput = Pipe()
            process.standardError = Pipe()
            try? process.run()
            process.waitUntilExit()
            await MainActor.run {
                whisperDownloaded = process.terminationStatus == 0
            }
        }
    }

    private func downloadWhisper() {
        isDownloadingWhisper = true
        Task.detached {
            // Use login shell so the gateway's venv pip is on PATH
            let process = Process()
            process.executableURL = URL(fileURLWithPath: "/bin/zsh")
            process.arguments = ["-lc", "pip3 install -U faster-whisper --quiet"]
            do {
                try process.run()
                process.waitUntilExit()
                await MainActor.run {
                    whisperDownloaded = process.terminationStatus == 0
                    if !whisperDownloaded {
                        self.error = "Whisper install failed (exit \(process.terminationStatus))"
                    }
                    isDownloadingWhisper = false
                }
            } catch {
                await MainActor.run {
                    self.error = "Failed to install whisper: \(error.localizedDescription)"
                    isDownloadingWhisper = false
                }
            }
        }
    }
}
