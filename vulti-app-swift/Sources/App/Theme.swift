import SwiftUI

// MARK: - Adaptive color helper

private extension Color {
    /// Creates a color that adapts to light/dark mode using NSColor's dynamic provider.
    static func adaptive(light: Color, dark: Color) -> Color {
        Color(nsColor: NSColor(name: nil) { appearance in
            let isDark = appearance.bestMatch(from: [.darkAqua, .aqua]) == .darkAqua
            return isDark ? NSColor(dark) : NSColor(light)
        })
    }
}

/// Vulti design system — Rainbow Paper (light) / Rainbow Charcoal (dark).
/// Dark mode uses warm charcoal tones (brown-gray), never cool purple-gray.
enum VultiTheme {

    // MARK: - Paper (backgrounds)
    static let paper       = Color.adaptive(light: Color(hex: "#F5F0E8"), dark: Color(hex: "#1E1C1A"))
    static let paperWarm   = Color.adaptive(light: Color(hex: "#EDE7DB"), dark: Color(hex: "#262422"))
    static let paperDeep   = Color.adaptive(light: Color(hex: "#E3DCD0"), dark: Color(hex: "#302D2A"))
    static let paperShadow = Color.adaptive(light: Color(hex: "#D4CCC0"), dark: Color(hex: "#3A3530"))

    // MARK: - Ink (text)
    static let ink       = Color.adaptive(light: Color(hex: "#1A1A1A"), dark: Color(hex: "#F5F0E8"))
    static let inkSoft   = Color.adaptive(light: Color(hex: "#3A3530"), dark: Color(hex: "#E0DBD3"))
    static let inkDim    = Color.adaptive(light: Color(hex: "#6B6460"), dark: Color(hex: "#C8C2B8"))
    static let inkMuted  = Color.adaptive(light: Color(hex: "#9A938D"), dark: Color(hex: "#6B6460"))
    static let inkFaint  = Color.adaptive(light: Color(hex: "#B8B0A8"), dark: Color(hex: "#504A44"))

    // MARK: - Primary
    static let primary      = Color.adaptive(light: Color(hex: "#9D7AEA"), dark: Color(hex: "#B094EF"))
    static let primaryHover = Color.adaptive(light: Color(hex: "#B094EF"), dark: Color(hex: "#C4AEF5"))

    // MARK: - Border
    static let border = Color.adaptive(
        light: Color(red: 26/255, green: 26/255, blue: 26/255, opacity: 0.10),
        dark: Color(red: 255/255, green: 255/255, blue: 255/255, opacity: 0.06)
    )

    // MARK: - Rainbow role colors (slightly brighter in dark mode for legibility)
    static let rose   = Color.adaptive(light: Color(hex: "#E8607A"), dark: Color(hex: "#F07A90"))
    static let coral  = Color.adaptive(light: Color(hex: "#F28B6D"), dark: Color(hex: "#F5A088"))
    static let amber  = Color.adaptive(light: Color(hex: "#F0A84A"), dark: Color(hex: "#F4BC6E"))
    static let lime   = Color.adaptive(light: Color(hex: "#8BC867"), dark: Color(hex: "#A0D880"))
    static let teal   = Color.adaptive(light: Color(hex: "#4AC6B7"), dark: Color(hex: "#66D4C8"))
    static let sky    = Color.adaptive(light: Color(hex: "#5AADE0"), dark: Color(hex: "#78C0EA"))
    static let blue   = Color.adaptive(light: Color(hex: "#6B8BEB"), dark: Color(hex: "#89A4F2"))
    static let violet = Color.adaptive(light: Color(hex: "#9D7AEA"), dark: Color(hex: "#B094EF"))
    static let pink   = Color.adaptive(light: Color(hex: "#D96BA8"), dark: Color(hex: "#E488BC"))

    // MARK: - Status dots
    static let statusActive  = Color.adaptive(light: Color(hex: "#8BC867"), dark: Color(hex: "#A0D880"))
    static let statusWarning = Color.adaptive(light: Color(hex: "#F0A84A"), dark: Color(hex: "#F4BC6E"))
    static let statusError   = Color.adaptive(light: Color(hex: "#E8607A"), dark: Color(hex: "#F07A90"))
    static let statusDefault = Color.adaptive(light: Color(hex: "#9A938D"), dark: Color(hex: "#6D6878"))

    // MARK: - Rainbow gradient (for primary buttons & active pickers)
    // Tauri CSS: linear-gradient(135deg, #E8607A..#9D7AEA) at 300% size,
    // centered — only the middle third is visible: coral → amber → teal.
    static let rainbowGradient = LinearGradient(
        colors: [
            Color(hex: "#F28B6D"),  // coral
            Color(hex: "#F0A84A"),  // amber
            Color(hex: "#4AC6B7"),  // teal
        ],
        startPoint: .topLeading,
        endPoint: .bottomTrailing
    )

    // MARK: - Noise texture overlay
    /// Generates a subtle grain texture matching the SVG feTurbulence effect.
    /// Light: warm brown multiply at 35% · Dark: warm cream soft-light at 25%
    static func noiseOverlay() -> some View {
        AdaptiveNoiseOverlay()
    }

    // MARK: - Ambient glow orbs
    /// Two drifting gradient orbs that bleed through frosted-glass surfaces.
    /// Light: subtle (12%/10% opacity) · Dark: vivid (18%/15% opacity)
    static func ambientGlows() -> some View {
        AdaptiveGlowOrbs()
    }
}

/// Noise overlay that adapts blend mode per color scheme.
private struct AdaptiveNoiseOverlay: View {
    @Environment(\.colorScheme) private var colorScheme

    var body: some View {
        Canvas { context, size in
            // Dense grain with varied particle sizes for a 200gsm paper feel.
            // Mix warm browns/tans at different opacities to mimic fiber texture.
            let area = size.width * size.height
            let count = Int(area * 0.008)  // 0.8% density — visible grain

            for _ in 0..<count {
                let x = CGFloat.random(in: 0..<size.width)
                let y = CGFloat.random(in: 0..<size.height)
                let w = CGFloat.random(in: 1...2)
                let h = CGFloat.random(in: 1...2)
                let alpha = CGFloat.random(in: 0.02...0.08)
                let rect = CGRect(x: x, y: y, width: w, height: h)
                context.fill(Path(rect), with: .color(.brown.opacity(alpha)))
            }
        }
        .blendMode(colorScheme == .dark ? .softLight : .multiply)
        .opacity(colorScheme == .dark ? 0.30 : 0.45)
        .allowsHitTesting(false)
    }
}

/// Two animated glow orbs — warm (rose/coral/amber) top-left, cool (teal/sky/violet) bottom-right.
private struct AdaptiveGlowOrbs: View {
    @Environment(\.colorScheme) private var colorScheme
    @State private var phase: Bool = false

    private var warmOpacity: Double { colorScheme == .dark ? 0.18 : 0.12 }
    private var coolOpacity: Double { colorScheme == .dark ? 0.15 : 0.10 }

    var body: some View {
        ZStack {
            // Glow 1 — warm (top-left)
            Ellipse()
                .fill(
                    LinearGradient(
                        colors: [Color(hex: "#E8607A"), Color(hex: "#F28B6D"), Color(hex: "#F0A84A")],
                        startPoint: .topLeading,
                        endPoint: .bottomTrailing
                    )
                )
                .frame(width: 800, height: 800)
                .blur(radius: 180)
                .opacity(warmOpacity)
                .offset(
                    x: phase ? -190 : -250,
                    y: phase ? -260 : -300
                )
                .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)

            // Glow 2 — cool (bottom-right)
            Ellipse()
                .fill(
                    LinearGradient(
                        colors: [Color(hex: "#4AC6B7"), Color(hex: "#5AADE0"), Color(hex: "#9D7AEA")],
                        startPoint: .topLeading,
                        endPoint: .bottomTrailing
                    )
                )
                .frame(width: 700, height: 700)
                .blur(radius: 180)
                .opacity(coolOpacity)
                .offset(
                    x: phase ? 150 : 200,
                    y: phase ? 170 : 200
                )
                .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .bottomTrailing)
        }
        .allowsHitTesting(false)
        .onAppear {
            withAnimation(.easeInOut(duration: 20).repeatForever(autoreverses: true)) {
                phase = true
            }
        }
    }
}

// MARK: - Theme preference

enum ThemePreference: String, CaseIterable {
    case light  = "light"
    case dark   = "dark"
    case system = "system"

    var label: String {
        switch self {
        case .light:  "Light"
        case .dark:   "Dark"
        case .system: "System"
        }
    }

    var colorScheme: ColorScheme? {
        switch self {
        case .light:  .light
        case .dark:   .dark
        case .system: nil
        }
    }
}

// MARK: - Reusable styled components

/// Frosted glass surface card — semi-transparent bg with backdrop vibrancy,
/// matching Tauri's `bg-surface` (75% opacity + blur(20px) saturate(1.4)).
struct VultiCard<Content: View>: View {
    let content: Content
    init(@ViewBuilder content: () -> Content) { self.content = content() }
    var body: some View {
        content
            .padding(16)
            .background {
                RoundedRectangle(cornerRadius: 12)
                    .fill(.ultraThinMaterial)
                    .overlay(
                        RoundedRectangle(cornerRadius: 12)
                            .fill(VultiTheme.paperWarm.opacity(0.65))
                    )
            }
            .overlay(RoundedRectangle(cornerRadius: 12).stroke(VultiTheme.border))
            .shadow(color: .black.opacity(0.06), radius: 15, y: 8)
    }
}

/// Rainbow gradient button (matches the "+ Add" style)
struct VultiGradientButton: View {
    let label: String
    let action: () -> Void
    var body: some View {
        Button(action: action) {
            Text(label)
                .font(.system(size: 13, weight: .semibold))
                .foregroundStyle(.white)
                .padding(.horizontal, 20)
                .padding(.vertical, 10)
                .background(VultiTheme.rainbowGradient, in: RoundedRectangle(cornerRadius: 10))
        }
        .buttonStyle(.plain)
    }
}

/// Primary button style with rainbow gradient background.
/// Use in place of `.buttonStyle(.borderedProminent).tint(VultiTheme.primary)`.
struct VultiPrimaryButtonStyle: ButtonStyle {
    @Environment(\.controlSize) private var controlSize
    @Environment(\.isEnabled) private var isEnabled

    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .font(font)
            .foregroundStyle(.white)
            .padding(.horizontal, hPad)
            .padding(.vertical, vPad)
            .background(
                VultiTheme.rainbowGradient
                    .opacity(isEnabled ? (configuration.isPressed ? 0.8 : 1.0) : 0.4),
                in: RoundedRectangle(cornerRadius: radius)
            )
    }

    private var font: Font {
        switch controlSize {
        case .mini:  .system(size: 10, weight: .semibold)
        case .small: .system(size: 12, weight: .semibold)
        default:     .system(size: 13, weight: .semibold)
        }
    }
    private var hPad: CGFloat { controlSize == .small ? 12 : 16 }
    private var vPad: CGFloat { controlSize == .small ? 5 : 8 }
    private var radius: CGFloat { controlSize == .small ? 6 : 8 }
}

extension ButtonStyle where Self == VultiPrimaryButtonStyle {
    static var vultiPrimary: VultiPrimaryButtonStyle { VultiPrimaryButtonStyle() }
}

/// Secondary button — bold rainbow gradient text, no background fill.
/// Used for "+ New Job", "+ Add Skills", etc.
struct VultiSecondaryButtonStyle: ButtonStyle {
    @Environment(\.isEnabled) private var isEnabled

    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .font(.system(size: 13, weight: .semibold))
            .foregroundStyle(VultiTheme.rainbowGradient)
            .opacity(isEnabled ? (configuration.isPressed ? 0.6 : 1.0) : 0.4)
    }
}

extension ButtonStyle where Self == VultiSecondaryButtonStyle {
    static var vultiSecondary: VultiSecondaryButtonStyle { VultiSecondaryButtonStyle() }
}

/// Embossed segmented picker — matches Tauri's `rounded-lg border border-border p-0.5` container
/// with `rounded-md bg-primary` active tab. Looks like a pill pressed into paper.
struct VultiPicker: View {
    let options: [String]
    @Binding var selection: String

    var body: some View {
        HStack(spacing: 4) {
            ForEach(options, id: \.self) { option in
                Button {
                    selection = option
                } label: {
                    Text(option)
                        .font(.system(size: 12, weight: .medium))
                        .padding(.horizontal, 12)
                        .padding(.vertical, 6)
                        .background(
                            selection == option
                                ? AnyShapeStyle(VultiTheme.rainbowGradient)
                                : AnyShapeStyle(.clear),
                            in: RoundedRectangle(cornerRadius: 6)
                        )
                        .foregroundStyle(selection == option ? .white : VultiTheme.inkMuted)
                }
                .buttonStyle(.plain)
            }
        }
        .padding(2)
        .background(
            RoundedRectangle(cornerRadius: 8)
                .fill(VultiTheme.paperDeep)
                .overlay(RoundedRectangle(cornerRadius: 8).stroke(VultiTheme.border))
        )
    }
}

/// Tag pill (for "API Key", "image", "generation" etc.)
struct VultiTag: View {
    let text: String
    var color: Color = VultiTheme.inkMuted
    var body: some View {
        Text(text)
            .font(.system(size: 10, weight: .medium))
            .padding(.horizontal, 8)
            .padding(.vertical, 3)
            .background(color.opacity(0.1), in: RoundedRectangle(cornerRadius: 4))
            .foregroundStyle(color)
    }
}

// MARK: - Custom text field style (fixes dark-mode system rendering)

/// Custom text field style that always uses VultiTheme colors.
/// Replaces .textFieldStyle(.roundedBorder) which inherits system dark appearance.
struct VultiTextFieldStyle: TextFieldStyle {
    func _body(configuration: TextField<Self._Label>) -> some View {
        configuration
            .textFieldStyle(.plain)
            .font(.system(size: 13))
            .foregroundStyle(VultiTheme.inkSoft)
            .padding(.horizontal, 16)
            .padding(.vertical, 12)
            .background(VultiTheme.paperWarm, in: RoundedRectangle(cornerRadius: 8))
            .overlay(RoundedRectangle(cornerRadius: 8).stroke(VultiTheme.border))
    }
}

extension TextFieldStyle where Self == VultiTextFieldStyle {
    static var vulti: VultiTextFieldStyle { VultiTextFieldStyle() }
}

/// View modifier to force VultiTheme on any view tree — fixes all child system controls.
struct VultiAppearance: ViewModifier {
    func body(content: Content) -> some View {
        content
            .foregroundStyle(VultiTheme.inkSoft)
            .tint(VultiTheme.primary)
    }
}

extension View {
    func vultiAppearance() -> some View {
        modifier(VultiAppearance())
    }
}
