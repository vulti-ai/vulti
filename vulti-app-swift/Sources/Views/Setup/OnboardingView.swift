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

    private static let stepCount = 6

    var body: some View {
        VStack(spacing: 0) {
            Spacer()

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
                case 0: identityStep
                case 1: networkingStep
                case 2: messagingStep
                case 3: intelligenceStep
                case 4: providersStep
                case 5: completeStep
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
        case 0: return "brain.head.profile"
        case 1: return "network"
        case 2: return "message.fill"
        case 3: return "brain"
        case 4: return "square.grid.2x2"
        case 5: return "person.2.fill"
        default: return ""
        }
    }

    private var stepTitle: String {
        switch step {
        case 0: return "Welcome to Vulti"
        case 1: return "Networking"
        case 2: return messagingSubStep == 0 ? "Download Element X" : "Sign In"
        case 3: return "Intelligence"
        case 4: return "Providers"
        case 5: return "Meet Hector"
        default: return ""
        }
    }

    private var stepSubtitle: String {
        switch step {
        case 0: return "The fastest way to get multiple agents working for you at home."
        case 1: return "Tailscale connects your devices so you can reach your agents from anywhere."
        case 2: return messagingSubStep == 0
            ? "VultiHub's Matrix server works with any Matrix client. We recommend Element X."
            : "Sign in manually to Element X with your credentials."
        case 3: return "Connect an AI provider so your agents can think. This is required."
        case 4: return "Optional providers for speech, phone calls, and image generation."
        case 5: return "Hector is your wizard — he manages connections, keeps agents healthy, and maintains system integrity."
        default: return ""
        }
    }

    // MARK: - Step 1: Identity

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
            } else {
                // Model picker grouped by provider
                VStack(alignment: .leading, spacing: 12) {
                    ForEach(authenticatedProviders, id: \.id) { provider in
                        VStack(alignment: .leading, spacing: 4) {
                            Text(provider.name)
                                .font(.system(size: 11, weight: .semibold))
                                .foregroundStyle(VultiTheme.inkDim)
                                .textCase(.uppercase)

                            ForEach(provider.models ?? [], id: \.self) { m in
                                let modelId = stripProviderPrefix(m)
                                HStack(spacing: 8) {
                                    Image(systemName: selectedModel == modelId ? "circle.inset.filled" : "circle")
                                        .font(.system(size: 13))
                                        .foregroundStyle(selectedModel == modelId ? VultiTheme.primary : VultiTheme.inkDim)
                                    Text(modelId)
                                        .font(.system(size: 12, design: .monospaced))
                                        .foregroundStyle(selectedModel == modelId ? VultiTheme.inkSoft : VultiTheme.inkDim)
                                }
                                .padding(.vertical, 4)
                                .padding(.horizontal, 8)
                                .frame(maxWidth: .infinity, alignment: .leading)
                                .background(
                                    selectedModel == modelId
                                        ? VultiTheme.primary.opacity(0.08)
                                        : Color.clear,
                                    in: RoundedRectangle(cornerRadius: 6)
                                )
                                .contentShape(Rectangle())
                                .onTapGesture { selectedModel = modelId }
                            }
                        }
                    }
                }
                .padding(12)
                .frame(maxWidth: .infinity, maxHeight: 240, alignment: .topLeading)
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
                Button("Back") { step = 2 }
                    .font(.system(size: 13))
                    .foregroundStyle(VultiTheme.inkMuted)
                    .buttonStyle(.plain)

                Spacer()

                Button("Next") { submitIntelligence() }
                    .buttonStyle(.vultiPrimary)
                    .disabled(authenticatedProviders.isEmpty || selectedModel.isEmpty)
            }
        }
    }

    /// Strip provider routing prefix (e.g. "openrouter/anthropic/claude-opus-4" → "anthropic/claude-opus-4")
    private func stripProviderPrefix(_ model: String) -> String {
        let prefixes = ["openrouter/", "openai/openai/", "anthropic/anthropic/"]
        for prefix in prefixes {
            if model.hasPrefix(prefix) {
                return String(model.dropFirst(prefix.count))
            }
        }
        return model
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
                    Button("Back") { step = 3 }
                        .font(.system(size: 13))
                        .foregroundStyle(VultiTheme.inkMuted)
                        .buttonStyle(.plain)

                    Spacer()

                    Button("Skip") { step = 5 }
                        .font(.system(size: 13))
                        .foregroundStyle(VultiTheme.inkMuted)
                        .buttonStyle(.plain)

                    Button("Next") { step = 5 }
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

    // MARK: - Step 2: Networking (Tailscale)

    private var networkingStep: some View {
        VStack(spacing: 16) {

            // Mac status
            VStack(alignment: .leading, spacing: 10) {
                Text("THIS MAC")
                    .font(.system(size: 11, weight: .bold))
                    .foregroundStyle(VultiTheme.inkDim)

                switch tailscaleStatus {
                case .checking:
                    HStack(spacing: 8) {
                        ProgressView().controlSize(.small)
                        Text("Checking Tailscale...")
                            .font(.system(size: 12))
                            .foregroundStyle(VultiTheme.inkDim)
                    }
                case .running:
                    HStack(spacing: 8) {
                        Image(systemName: "checkmark.circle.fill")
                            .foregroundStyle(VultiTheme.teal)
                            .font(.system(size: 14))
                        VStack(alignment: .leading, spacing: 2) {
                            Text("Tailscale is running")
                                .font(.system(size: 12, weight: .medium))
                                .foregroundStyle(VultiTheme.inkSoft)
                            if !tailscaleHostname.isEmpty {
                                Text(tailscaleHostname)
                                    .font(.system(size: 11, design: .monospaced))
                                    .foregroundStyle(VultiTheme.inkMuted)
                                    .textSelection(.enabled)
                            }
                        }
                    }
                case .notRunning:
                    HStack(spacing: 8) {
                        Image(systemName: "exclamationmark.circle.fill")
                            .foregroundStyle(.orange)
                            .font(.system(size: 14))
                        VStack(alignment: .leading, spacing: 2) {
                            Text("Tailscale is installed but not connected.")
                                .font(.system(size: 12))
                                .foregroundStyle(VultiTheme.inkDim)
                            Text("Open the Tailscale app and sign in.")
                                .font(.system(size: 11))
                                .foregroundStyle(VultiTheme.inkMuted)
                        }
                    }
                    Button("Open Tailscale") {
                        if let url = NSWorkspace.shared.urlForApplication(withBundleIdentifier: "io.tailscale.ipn.macos") {
                            NSWorkspace.shared.openApplication(at: url, configuration: .init())
                        } else if let url = NSWorkspace.shared.urlForApplication(withBundleIdentifier: "io.tailscale.ipn.macsys") {
                            NSWorkspace.shared.openApplication(at: url, configuration: .init())
                        }
                    }
                    .font(.system(size: 12, weight: .medium))
                    .buttonStyle(.vultiSecondary)
                case .notInstalled:
                    HStack(spacing: 8) {
                        Image(systemName: "xmark.circle.fill")
                            .foregroundStyle(VultiTheme.rose)
                            .font(.system(size: 14))
                        VStack(alignment: .leading, spacing: 2) {
                            Text("Tailscale is not installed.")
                                .font(.system(size: 12))
                                .foregroundStyle(VultiTheme.inkDim)
                            Text("Get it free from the Mac App Store — no terminal needed.")
                                .font(.system(size: 11))
                                .foregroundStyle(VultiTheme.inkMuted)
                        }
                    }
                    Button("Open Mac App Store") {
                        NSWorkspace.shared.open(URL(string: "macappstore://apps.apple.com/app/tailscale/id1475387142")!)
                    }
                    .font(.system(size: 12, weight: .medium))
                    .buttonStyle(.vultiSecondary)
                }

                Button("Refresh") { checkTailscale() }
                    .font(.system(size: 11))
                    .foregroundStyle(VultiTheme.primary)
                    .buttonStyle(.plain)
            }
            .padding(14)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(VultiTheme.paperDeep.opacity(0.5), in: RoundedRectangle(cornerRadius: 8))

            // iPhone instructions
            VStack(alignment: .leading, spacing: 10) {
                Text("YOUR IPHONE")
                    .font(.system(size: 11, weight: .bold))
                    .foregroundStyle(VultiTheme.inkDim)

                HStack(alignment: .top, spacing: 8) {
                    Text("1.")
                        .font(.system(size: 12, weight: .medium))
                        .foregroundStyle(VultiTheme.inkDim)
                    Text("Install Tailscale from the App Store")
                        .font(.system(size: 12))
                        .foregroundStyle(VultiTheme.inkSoft)
                }
                HStack(alignment: .top, spacing: 8) {
                    Text("2.")
                        .font(.system(size: 12, weight: .medium))
                        .foregroundStyle(VultiTheme.inkDim)
                    Text("Sign in with the same account as this Mac")
                        .font(.system(size: 12))
                        .foregroundStyle(VultiTheme.inkSoft)
                }
                HStack(alignment: .top, spacing: 8) {
                    Text("3.")
                        .font(.system(size: 12, weight: .medium))
                        .foregroundStyle(VultiTheme.inkDim)
                    Text("Both devices will appear on your private network")
                        .font(.system(size: 12))
                        .foregroundStyle(VultiTheme.inkSoft)
                }

                if let qrImage = generateQRCode(from: "https://apps.apple.com/app/tailscale/id1470499037") {
                    HStack {
                        Spacer()
                        VStack(spacing: 4) {
                            Image(nsImage: qrImage)
                                .interpolation(.none)
                                .resizable()
                                .scaledToFit()
                                .frame(width: 160, height: 160)
                                .clipShape(RoundedRectangle(cornerRadius: 8))
                            Text("Scan to download Tailscale for iOS")
                                .font(.system(size: 10))
                                .foregroundStyle(VultiTheme.inkMuted)
                        }
                        Spacer()
                    }
                }
            }
            .padding(14)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(VultiTheme.paperDeep.opacity(0.5), in: RoundedRectangle(cornerRadius: 8))

            // Navigation
            HStack {
                Button("Back") { step = 0 }
                    .font(.system(size: 13))
                    .foregroundStyle(VultiTheme.inkMuted)
                    .buttonStyle(.plain)

                Spacer()

                Button("Next") { step = 2 }
                    .buttonStyle(.vultiPrimary)
            }
        }
    }

    // MARK: - Step 3: Messaging

    private var messagingStep: some View {
        VStack(spacing: 16) {
            if messagingSubStep == 0 {
                // Page 1: Download Element X
                VStack(alignment: .leading, spacing: 10) {
                    HStack(spacing: 10) {
                        Image(systemName: "arrow.down.app.fill")
                            .font(.system(size: 20))
                            .foregroundStyle(VultiTheme.primary)
                        Text("Download Element X")
                            .font(.system(size: 13, weight: .semibold))
                            .foregroundStyle(VultiTheme.inkSoft)
                    }

                    if let qrImage = generateQRCode(from: "https://apps.apple.com/app/element-x-secure-messenger/id1631335820") {
                        HStack {
                            Spacer()
                            Image(nsImage: qrImage)
                                .interpolation(.none)
                                .resizable()
                                .scaledToFit()
                                .frame(width: 120, height: 120)
                                .clipShape(RoundedRectangle(cornerRadius: 8))
                            Spacer()
                        }

                        Text("Scan to download Element X for iOS")
                            .font(.system(size: 10))
                            .foregroundStyle(VultiTheme.inkMuted)
                            .frame(maxWidth: .infinity, alignment: .center)
                    }
                }
                .padding(14)
                .frame(maxWidth: .infinity, alignment: .leading)
                .background(VultiTheme.paperDeep.opacity(0.5), in: RoundedRectangle(cornerRadius: 8))

                HStack {
                    Button("Back") { step = 1 }
                        .font(.system(size: 13))
                        .foregroundStyle(VultiTheme.inkMuted)
                        .buttonStyle(.plain)
                    Spacer()
                    Button("Next") { messagingSubStep = 1 }
                        .buttonStyle(.vultiPrimary)
                }

            } else {
                // Page 2: Sign in instructions + credentials

                // Step-by-step instructions
                VStack(alignment: .leading, spacing: 12) {
                    Text("SIGN IN MANUALLY")
                        .font(.system(size: 11, weight: .bold))
                        .foregroundStyle(VultiTheme.inkDim)

                    signInStep(number: "1", text: "Open Element X on your phone")
                    signInStep(number: "2", text: "Tap \"Change account provider\"")
                    signInStep(number: "3", text: "Enter your homeserver URL below")
                    signInStep(number: "4", text: "Sign in with your username and password")
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

                Text("Your server URL is also available to copy in your iOS Tailscale app.")
                    .font(.system(size: 11))
                    .foregroundStyle(VultiTheme.inkMuted)
                    .multilineTextAlignment(.center)

                HStack {
                    Button("Back") { messagingSubStep = 0 }
                        .font(.system(size: 13))
                        .foregroundStyle(VultiTheme.inkMuted)
                        .buttonStyle(.plain)
                    Spacer()
                    Button("Next") { step = 3 }
                        .buttonStyle(.vultiPrimary)
                }
            }
        }
        .animation(.easeInOut(duration: 0.2), value: messagingSubStep)
    }

    @ViewBuilder
    private func signInStep(number: String, text: String) -> some View {
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
                    Text("He'll set up your first connections — email, files, calendar — and help you create your first agent.")
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

    private func checkTailscale() {
        tailscaleStatus = .checking
        Task {
            let process = Process()
            process.executableURL = URL(fileURLWithPath: "/usr/bin/env")
            process.arguments = ["tailscale", "status", "--self", "--json"]
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
                    // Check if tailscale binary exists but daemon isn't running
                    await MainActor.run { tailscaleStatus = .notRunning }
                }
            } catch {
                await MainActor.run { tailscaleStatus = .notInstalled }
            }
        }
    }

    private func fetchHomeserverURL() async {
        // Fetch from .well-known/matrix/client endpoint
        let url = URL(string: "http://localhost:8080/.well-known/matrix/client")!
        var request = URLRequest(url: url)
        if let token = VultiHome.webToken() {
            request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        }
        if let (data, _) = try? await URLSession.shared.data(for: request),
           let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
           let hs = json["m.homeserver"] as? [String: Any],
           let baseURL = hs["base_url"] as? String {
            homeserverURL = baseURL
        } else {
            homeserverURL = "http://localhost:6167"
        }
    }

    private func autoSelectFirstModel() {
        guard selectedModel.isEmpty else { return }
        if let first = authenticatedProviders.first,
           let firstModel = first.models?.first {
            selectedModel = stripProviderPrefix(firstModel)
        }
    }

    private func submitIntelligence() {
        guard !selectedModel.isEmpty else { return }
        // Save selected model as the system default via env
        Task {
            try? await app.client.addSecret(key: "VULTI_DEFAULT_MODEL", value: selectedModel)
        }
        step = 4
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
                    step = 1
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
