import SwiftUI

/// App-level onboarding — shown on first launch when no owner profile exists.
/// Four steps: (1) Identity, (2) Intelligence (AI provider, mandatory),
/// (3) Providers (speech/voice/image, optional), (4) Complete.
struct OnboardingView: View {
    @Environment(AppState.self) private var app

    @State private var step = 0

    // Step 1 — Identity
    @State private var name = ""
    @State private var password = ""
    @State private var aboutMe = ""

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
    @State private var speechKeyValue = ""
    @State private var isAddingSpeechKey = false
    @State private var isDownloadingWhisper = false
    @State private var whisperDownloaded = false

    // Voice provider key (Bland)
    @State private var showAddVoiceKey = false
    @State private var voiceKeyValue = ""
    @State private var isAddingVoiceKey = false

    // Image gen key
    @State private var showAddFalKey = false
    @State private var falKeyValue = ""
    @State private var isAddingFalKey = false

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

    private var hasBlandKey: Bool {
        secrets.contains { $0.key == "BLAND_API_KEY" && ($0.isSet ?? false) }
    }


    // Step 4 — Messaging
    @State private var homeserverURL = ""

    private static let stepCount = 5

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
                case 1: messagingStep
                case 2: intelligenceStep
                case 3: providersStep
                case 4: completeStep
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
            await fetchHomeserverURL()
        }
    }

    // MARK: - Step metadata

    private var stepIcon: String {
        switch step {
        case 0: return "brain.head.profile"
        case 1: return "message.fill"
        case 2: return "brain"
        case 3: return "square.grid.2x2"
        case 4: return "person.2.fill"
        default: return ""
        }
    }

    private var stepTitle: String {
        switch step {
        case 0: return "Welcome to Vulti"
        case 1: return "Messaging"
        case 2: return "Intelligence"
        case 3: return "Providers"
        case 4: return "Create Agents"
        default: return ""
        }
    }

    private var stepSubtitle: String {
        switch step {
        case 0: return "The fastest way to get multiple agents working for you at home."
        case 1: return "Vulti works best with Element X — all your messaging with your agents in one server controlled by you."
        case 2: return "Connect an AI provider so your agents can think. This is required."
        case 3: return "Optional providers for speech, phone calls, and image generation."
        case 4: return "Set up your system agent and create your first assistant."
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
                Button("Back") { step = 1 }
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

                    // ElevenLabs
                    if hasElevenLabsKey {
                        HStack(spacing: 10) {
                            Image(systemName: "checkmark.circle.fill")
                                .foregroundStyle(VultiTheme.teal)
                                .font(.system(size: 14))
                            Text("ElevenLabs")
                                .font(.system(size: 12, weight: .medium))
                                .foregroundStyle(VultiTheme.inkSoft)
                            Spacer()
                            Text("Connected")
                                .font(.system(size: 11))
                                .foregroundStyle(VultiTheme.inkMuted)
                        }
                    }

                    inlineSecretEntry(
                        showBinding: $showAddSpeechKey,
                        keyValue: $speechKeyValue,
                        isAdding: $isAddingSpeechKey,
                        secretKey: "ELEVENLABS_API_KEY",
                        placeholder: "Paste ElevenLabs API key",
                        buttonLabel: "+ Add speech provider API key"
                    )
                }

                // ── Voice Provider ──
                providerSection(
                    icon: "phone.arrow.up.right",
                    title: "Voice",
                    subtitle: "Phone calls and voice AI via Bland"
                ) {
                    if hasBlandKey {
                        HStack(spacing: 10) {
                            Image(systemName: "checkmark.circle.fill")
                                .foregroundStyle(VultiTheme.teal)
                                .font(.system(size: 14))
                            Text("Bland")
                                .font(.system(size: 12, weight: .medium))
                                .foregroundStyle(VultiTheme.inkSoft)
                            Spacer()
                            Text("Connected")
                                .font(.system(size: 11))
                                .foregroundStyle(VultiTheme.inkMuted)
                        }
                    }

                    inlineSecretEntry(
                        showBinding: $showAddVoiceKey,
                        keyValue: $voiceKeyValue,
                        isAdding: $isAddingVoiceKey,
                        secretKey: "BLAND_API_KEY",
                        placeholder: "Paste Bland API key",
                        buttonLabel: "+ Add Bland key"
                    )
                }

                // ── Image Gen Provider ──
                providerSection(
                    icon: "photo.artframe",
                    title: "Image Generation",
                    subtitle: "Let agents create images"
                ) {
                    if hasFalKey {
                        HStack(spacing: 10) {
                            Image(systemName: "checkmark.circle.fill")
                                .foregroundStyle(VultiTheme.teal)
                                .font(.system(size: 14))
                            Text("fal.ai")
                                .font(.system(size: 12, weight: .medium))
                                .foregroundStyle(VultiTheme.inkSoft)
                            Spacer()
                            Text("Connected")
                                .font(.system(size: 11))
                                .foregroundStyle(VultiTheme.inkMuted)
                        }
                    }

                    inlineSecretEntry(
                        showBinding: $showAddFalKey,
                        keyValue: $falKeyValue,
                        isAdding: $isAddingFalKey,
                        secretKey: "FAL_KEY",
                        placeholder: "Paste fal.ai API key",
                        buttonLabel: "+ Add fal.ai key"
                    )
                }

                // ── Navigation ──
                HStack {
                    Button("Back") { step = 2 }
                        .font(.system(size: 13))
                        .foregroundStyle(VultiTheme.inkMuted)
                        .buttonStyle(.plain)

                    Spacer()

                    Button("Skip") { step = 4 }
                        .font(.system(size: 13))
                        .foregroundStyle(VultiTheme.inkMuted)
                        .buttonStyle(.plain)

                    Button("Next") { step = 4 }
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

    // MARK: - Step 4: Messaging

    private var messagingStep: some View {
        VStack(spacing: 16) {

            // Element X download
            VStack(alignment: .leading, spacing: 10) {
                HStack(spacing: 10) {
                    Image(systemName: "arrow.down.app.fill")
                        .font(.system(size: 20))
                        .foregroundStyle(VultiTheme.primary)
                    VStack(alignment: .leading, spacing: 2) {
                        Text("Download Element X")
                            .font(.system(size: 13, weight: .semibold))
                            .foregroundStyle(VultiTheme.inkSoft)
                        Text("Available on iOS and Android. Search \"Element X\" on the App Store.")
                            .font(.system(size: 11))
                            .foregroundStyle(VultiTheme.inkMuted)
                            .fixedSize(horizontal: false, vertical: true)
                    }
                }

                // QR code linking to iOS app
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

            // Connection details
            VStack(alignment: .leading, spacing: 10) {
                Text("CONNECTION DETAILS")
                    .font(.system(size: 11, weight: .bold))
                    .foregroundStyle(VultiTheme.inkDim)

                connectionRow(label: "Server", value: homeserverURL.isEmpty ? "Loading..." : homeserverURL)
                connectionRow(label: "Username", value: name.lowercased().replacingOccurrences(of: " ", with: "_"))
                connectionRow(label: "Password", value: password)
            }
            .padding(14)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(VultiTheme.paperDeep.opacity(0.5), in: RoundedRectangle(cornerRadius: 8))

            Text("Sign in to Element X with these credentials to message your agents from any device.")
                .font(.system(size: 11))
                .foregroundStyle(VultiTheme.inkMuted)
                .multilineTextAlignment(.center)

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

    @ViewBuilder
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
            Spacer()
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

    // MARK: - Step 5: Create Agents

    @State private var janitorEnabled = false
    @State private var isActivatingJanitor = false

    private var janitorExists: Bool {
        app.agentList.contains { $0.id == "janitor" && $0.status == "active" }
    }

    private var completeStep: some View {
        VStack(spacing: 20) {

            // ── Janitor ──
            VStack(alignment: .leading, spacing: 10) {
                HStack(spacing: 8) {
                    Text("⚙")
                        .font(.system(size: 20))
                    VStack(alignment: .leading, spacing: 2) {
                        Text("Janitor")
                            .font(.system(size: 13, weight: .semibold))
                            .foregroundStyle(VultiTheme.inkSoft)
                        Text("System agent that keeps your workspace healthy — runs daily checks, cleans up sessions, and reports issues.")
                            .font(.system(size: 11))
                            .foregroundStyle(VultiTheme.inkMuted)
                            .fixedSize(horizontal: false, vertical: true)
                    }
                }

                if janitorEnabled || janitorExists {
                    HStack(spacing: 6) {
                        Image(systemName: "checkmark.circle.fill")
                            .foregroundStyle(VultiTheme.teal)
                            .font(.system(size: 13))
                        Text("Active")
                            .font(.system(size: 12))
                            .foregroundStyle(VultiTheme.teal)
                    }
                    .padding(.leading, 28)
                } else {
                    Button {
                        activateJanitor()
                    } label: {
                        if isActivatingJanitor {
                            ProgressView()
                                .controlSize(.small)
                                .frame(width: 80)
                        } else {
                            Text("Turn On")
                                .font(.system(size: 12, weight: .medium))
                        }
                    }
                    .buttonStyle(.vultiSecondary)
                    .disabled(isActivatingJanitor)
                    .padding(.leading, 28)
                }
            }
            .padding(14)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(VultiTheme.paperDeep.opacity(0.5), in: RoundedRectangle(cornerRadius: 8))

            // ── Create first agent ──
            VStack(spacing: 8) {
                Text("Now create your first agent.")
                    .font(.system(size: 13))
                    .foregroundStyle(VultiTheme.inkSoft)

                Button {
                    Persistence.onboardingComplete = true
                    app.onboardingComplete = true
                    Task {
                        await app.refreshAgents()
                        await MainActor.run {
                            app.openCreate()
                        }
                    }
                } label: {
                    Text("Create Agent")
                        .font(.system(size: 13, weight: .medium))
                        .frame(maxWidth: .infinity)
                }
                .buttonStyle(.vultiPrimary)
                .controlSize(.large)
            }
        }
    }

    // MARK: - Actions

    private func activateJanitor() {
        isActivatingJanitor = true
        Task {
            do {
                // Janitor is auto-seeded by the registry, just needs Matrix onboarding
                _ = try? await app.client.updateAgent("janitor", updates: [
                    "allowedConnections": "matrix"
                ])
                try? await app.client.installSkill(agentId: "janitor", name: "matrix")
                try? await app.client.onboardAgentToMatrix(agentId: "janitor")
                try? await app.client.finalizeOnboarding(agentId: "janitor", role: "ops")
                await app.refreshAgents()
                await MainActor.run {
                    janitorEnabled = true
                    isActivatingJanitor = false
                }
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
        step = 3
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

    private func downloadWhisper() {
        isDownloadingWhisper = true
        Task {
            // pip install faster-whisper in the gateway's Python environment
            let process = Process()
            process.executableURL = URL(fileURLWithPath: "/usr/bin/env")
            process.arguments = ["pip", "install", "-U", "faster-whisper", "--quiet"]
            do {
                try process.run()
                process.waitUntilExit()
                await MainActor.run {
                    whisperDownloaded = process.terminationStatus == 0
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
