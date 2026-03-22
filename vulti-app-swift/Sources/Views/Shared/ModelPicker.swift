import SwiftUI

// MARK: - Provider prefix stripping

extension String {
    /// Strip routing prefixes like "openrouter/" or "anthropic/anthropic/".
    func strippingProviderPrefix() -> String {
        let prefixes = ["openrouter/", "openai/openai/", "anthropic/anthropic/"]
        for prefix in prefixes {
            if self.hasPrefix(prefix) {
                return String(self.dropFirst(prefix.count))
            }
        }
        return self
    }
}

// MARK: - ModelPicker

/// Unified model/provider picker used across onboarding, agent creation,
/// agent detail header, and settings.
struct ModelPicker: View {
    enum Style { case radioList, dropdownMenu }

    let style: Style
    @Binding var selectedModel: String
    let providers: [GatewayClient.ProviderResponse]
    var defaultModel: String? = nil
    var defaultProvider: String? = nil
    var onSelect: ((String, String) -> Void)? = nil

    var body: some View {
        switch style {
        case .radioList:
            radioListBody
        case .dropdownMenu:
            dropdownMenuBody
        }
    }

    // MARK: - Radio List

    @ViewBuilder
    private var radioListBody: some View {
        let authenticated = providers.filter(\.authenticated)
        if authenticated.isEmpty {
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
            VStack(alignment: .leading, spacing: 12) {
                ForEach(authenticated, id: \.id) { provider in
                    VStack(alignment: .leading, spacing: 4) {
                        Text(provider.name)
                            .font(.system(size: 11, weight: .semibold))
                            .foregroundStyle(VultiTheme.inkDim)
                            .textCase(.uppercase)

                        ForEach(provider.models ?? [], id: \.self) { m in
                            let modelId = m.strippingProviderPrefix()
                            let isSelected = selectedModel == modelId
                            let isDefault = defaultModel == modelId && defaultProvider == provider.id

                            HStack(spacing: 8) {
                                Image(systemName: isSelected ? "circle.inset.filled" : "circle")
                                    .font(.system(size: 13))
                                    .foregroundStyle(isSelected
                                        ? (isDefault ? AnyShapeStyle(VultiTheme.rainbowGradient) : AnyShapeStyle(VultiTheme.primary))
                                        : AnyShapeStyle(VultiTheme.inkDim))
                                Text(modelId)
                                    .font(.system(size: 12, design: .monospaced))
                                    .foregroundStyle(isSelected ? VultiTheme.inkSoft : VultiTheme.inkDim)
                                if isDefault {
                                    Text("default")
                                        .font(.system(size: 9, weight: .medium))
                                        .foregroundStyle(VultiTheme.rainbowGradient)
                                        .padding(.horizontal, 5)
                                        .padding(.vertical, 1)
                                        .background(VultiTheme.paperDeep, in: Capsule())
                                }
                            }
                            .padding(.vertical, 4)
                            .padding(.horizontal, 8)
                            .frame(maxWidth: .infinity, alignment: .leading)
                            .background(
                                isSelected
                                    ? VultiTheme.primary.opacity(0.08)
                                    : Color.clear,
                                in: RoundedRectangle(cornerRadius: 6)
                            )
                            .contentShape(Rectangle())
                            .onTapGesture {
                                selectedModel = modelId
                                onSelect?(modelId, provider.id)
                            }
                        }
                    }
                }
            }
        }
    }

    // MARK: - Dropdown Menu

    @ViewBuilder
    private var dropdownMenuBody: some View {
        let authenticated = providers.filter(\.authenticated)
        if authenticated.isEmpty {
            Text("No providers connected")
        }
        ForEach(authenticated, id: \.id) { provider in
            let models = provider.models ?? []
            if models.isEmpty {
                Menu(provider.name) {
                    Text("No models available")
                }
            } else {
                Menu(provider.name) {
                    ForEach(models, id: \.self) { m in
                        let modelId = m.strippingProviderPrefix()
                        Button {
                            selectedModel = modelId
                            onSelect?(modelId, provider.id)
                        } label: {
                            HStack {
                                Text(modelId)
                                if selectedModel == modelId || selectedModel == m {
                                    Image(systemName: "checkmark")
                                }
                            }
                        }
                    }
                }
            }
        }
    }
}
