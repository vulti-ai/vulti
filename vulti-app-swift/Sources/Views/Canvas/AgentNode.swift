import SwiftUI

/// Agent node — warm paper bg, role-colored border, rounded 10px.
/// Handles placed at actual node edges via overlay alignment.
struct AgentNode: View {
    let agent: GatewayClient.AgentResponse
    var isDefault: Bool = false
    var roleColor: Color = VultiTheme.violet
    var showHandles: Bool = false
    /// Reports the measured node body size (used by SquadCanvas for edge routing)
    var onNodeSize: ((CGSize) -> Void)?
    @Environment(AppState.self) private var app
    @State private var isHovered = false
    @State private var nearEdge = false
    @State private var nodeSize: CGSize = CGSize(width: 100, height: 72)

    var isSelected: Bool { app.activeAgentId == agent.id }

    /// Agent is "thinking" when actively processing
    var isThinking: Bool {
        agent.status == "active" || agent.status == "connected"
    }

    /// Handles show only near the edge or during an active connection drag
    private var handlesVisible: Bool { showHandles || nearEdge }

    private var borderWidth: CGFloat {
        if isSelected { return 2 }
        if isHovered { return 1.5 }
        return 1
    }

    var body: some View {
        nodeBody
            // Measure actual size and report to parent
            .background(
                GeometryReader { geo in
                    Color.clear
                        .onAppear { nodeSize = geo.size; onNodeSize?(geo.size) }
                        .onChange(of: geo.size) { _, s in nodeSize = s; onNodeSize?(s) }
                }
            )
            // Place handles at ACTUAL node edges via alignment
            .overlay(alignment: .top) {
                HandleDot(position: .top, isVisible: handlesVisible, isTarget: showHandles)
                    .offset(y: -4)
            }
            .overlay(alignment: .bottom) {
                HandleDot(position: .bottom, isVisible: handlesVisible, isSource: showHandles)
                    .offset(y: 4)
            }
            .overlay(alignment: .leading) {
                HandleDot(position: .left, isVisible: handlesVisible, isTarget: showHandles)
                    .offset(x: -4)
            }
            .overlay(alignment: .trailing) {
                HandleDot(position: .right, isVisible: handlesVisible, isSource: showHandles)
                    .offset(x: 4)
            }
            .onContinuousHover { phase in
                switch phase {
                case .active(let pt):
                    isHovered = true
                    // Near edge = within 14px of any side
                    let inset: CGFloat = 14
                    nearEdge = pt.x < inset || pt.y < inset
                        || pt.x > nodeSize.width - inset
                        || pt.y > nodeSize.height - inset
                case .ended:
                    isHovered = false
                    nearEdge = false
                }
            }
    }

    private var nodeBody: some View {
        VStack(spacing: 6) {
            // Avatar — role-colored gradient circle with initial, or image if generated
            AgentAvatar(agent: agent, roleColor: roleColor, size: 36)

            Text(agent.name)
                .font(.system(size: 13, weight: .medium))
                .foregroundStyle(VultiTheme.inkSoft)
                .lineLimit(1)

            if let role = agent.role, !role.isEmpty {
                Text(role)
                    .font(.system(size: 11))
                    .foregroundStyle(roleColor)
                    .lineLimit(1)
            } else {
                Text("onboarding")
                    .font(.system(size: 11))
                    .foregroundStyle(.orange)
                    .lineLimit(1)
            }
        }
        .padding(.vertical, 8)
        .padding(.horizontal, 20)
        .frame(minWidth: 100)
        .background(
            RoundedRectangle(cornerRadius: 10)
                .fill(VultiTheme.paper.opacity(0.85))
        )
        .overlay {
            ThinkingBorderEffect(cornerRadius: 10, lineWidth: 2)
        }
        .overlay(alignment: .topTrailing) {
            if app.unreadAgents.contains(agent.id) {
                Circle()
                    .fill(.red)
                    .frame(width: 10, height: 10)
                    .offset(x: 2, y: -2)
                    .transition(.scale.combined(with: .opacity))
            }
        }
        .animation(.spring(duration: 0.3), value: app.unreadAgents.contains(agent.id))
        .shadow(color: .black.opacity(isHovered ? 0.18 : 0.12), radius: isHovered ? 24 : 18, y: isHovered ? 12 : 8)
        .animation(.easeInOut(duration: 0.12), value: isHovered)
    }
}

// MARK: - Add Agent Node (placeholder card)

/// "+" card that sits in the agent grid as a placeholder to create a new agent.
struct AddAgentNode: View {
    @State private var isHovered = false

    var body: some View {
        VStack(spacing: 4) {
            Image(systemName: "plus")
                .font(.system(size: 14, weight: .ultraLight))
                .foregroundStyle(VultiTheme.rainbowGradient)
                .frame(width: 24, height: 24)

            Text("New Agent")
                .font(.system(size: 9, weight: .ultraLight))
                .foregroundStyle(VultiTheme.rainbowGradient)
                .lineLimit(1)
        }
        .padding(.vertical, 6)
        .padding(.horizontal, 12)
        .background(
            RoundedRectangle(cornerRadius: 8)
                .fill(VultiTheme.paper.opacity(0.3))
        )
        .overlay(
            RoundedRectangle(cornerRadius: 8)
                .strokeBorder(VultiTheme.rainbowGradient, lineWidth: isHovered ? 1 : 0.5)
        )
        .shadow(color: .black.opacity(isHovered ? 0.12 : 0.06), radius: isHovered ? 12 : 8, y: isHovered ? 6 : 4)
        .scaleEffect(isHovered ? 1.06 : 1.0)
        .animation(.easeInOut(duration: 0.12), value: isHovered)
        .onHover { isHovered = $0 }
    }
}

// MARK: - Handle

enum HandlePosition: Hashable {
    case top, bottom, left, right
}

struct HandleDot: View {
    let position: HandlePosition
    var isVisible: Bool = false
    var isConnecting: Bool = false
    var isSource: Bool = false
    var isTarget: Bool = false

    private var size: CGFloat { (isSource || isTarget) ? 10 : 8 }

    var body: some View {
        Circle()
            .fill(isSource ? VultiTheme.paperWarm.opacity(0.9) : VultiTheme.paperWarm)
            .frame(width: size, height: size)
            .overlay(
                Circle().stroke(
                    isSource ? VultiTheme.inkSoft : VultiTheme.inkMuted,
                    lineWidth: isSource ? 2 : 1.5
                )
            )
            .opacity(isConnecting ? 1.0 : isVisible ? 0.6 : 0)
            .animation(.easeInOut(duration: 0.15), value: isVisible)
            .animation(.easeInOut(duration: 0.15), value: isConnecting)
            .allowsHitTesting(false)
    }
}

/// Owner node — 80x80 circle with source handles at edges.
/// Border highlights on hover; handles only appear near the circle edge.
struct OwnerNode: View {
    let name: String
    var color: Color = VultiTheme.rose
    var showHandles: Bool = false
    @Environment(AppState.self) private var app
    @State private var isHovered = false
    @State private var nearEdge = false

    var isSelected: Bool { app.panelMode == .owner }
    private var handlesVisible: Bool { showHandles || nearEdge }

    private var borderWidth: CGFloat {
        if isSelected { return 2 }
        if isHovered { return 1.5 }
        return 1
    }

    private var ownerAvatar: String? {
        app.ownerInfo?.avatar
    }

    var body: some View {
        VStack(spacing: 4) {
            // Avatar or initial
            if let avatarStr = ownerAvatar, !avatarStr.isEmpty,
               let data = Data(base64Encoded: avatarStr),
               let nsImage = NSImage(data: data) {
                Image(nsImage: nsImage)
                    .resizable()
                    .scaledToFill()
                    .frame(width: 40, height: 40)
                    .clipShape(Circle())
            } else {
                Text(String(name.prefix(1)).uppercased())
                    .font(.system(size: 16, weight: .semibold))
                    .foregroundStyle(VultiTheme.inkDim)
                    .frame(width: 40, height: 40)
                    .background(Circle().fill(VultiTheme.paperWarm))
            }

            Text(name)
                .font(.system(size: 11, weight: .semibold))
                .foregroundStyle(VultiTheme.inkSoft)
                .lineLimit(1)
        }
        .frame(width: 80, height: 80)
        .background(Circle().fill(VultiTheme.paper.opacity(0.85)))
        .overlay(Circle().stroke(color, lineWidth: borderWidth).animation(.easeInOut(duration: 0.12), value: borderWidth))
        .shadow(color: .black.opacity(isHovered ? 0.18 : 0.12), radius: isHovered ? 24 : 18, y: isHovered ? 12 : 8)
        .animation(.easeInOut(duration: 0.12), value: isHovered)
        .overlay(alignment: .bottom) {
            HandleDot(position: .bottom, isVisible: handlesVisible, isSource: showHandles)
                .offset(y: 4)
        }
        .overlay(alignment: .leading) {
            HandleDot(position: .left, isVisible: handlesVisible, isSource: showHandles)
                .offset(x: -4)
        }
        .overlay(alignment: .trailing) {
            HandleDot(position: .right, isVisible: handlesVisible, isSource: showHandles)
                .offset(x: 4)
        }
        .onContinuousHover { phase in
            switch phase {
            case .active(let pt):
                isHovered = true
                // Circle: 80x80, center at (40,40), radius 40
                // Show handles when cursor is within 12px of the perimeter
                let dx = pt.x - 40, dy = pt.y - 40
                nearEdge = hypot(dx, dy) > 28  // 40 - 12
            case .ended:
                isHovered = false
                nearEdge = false
            }
        }
    }
}

// MARK: - Thinking Border Effect

/// A clockwise-spinning rainbow arc on the border — indicates the agent is processing.
struct ThinkingBorderEffect: View {
    var cornerRadius: CGFloat = 10
    var lineWidth: CGFloat = 2
    @State private var rotation: Double = 0

    private var gradient: AngularGradient {
        AngularGradient(
            gradient: Gradient(colors: [
                Color(hex: "#E8607A"),
                Color(hex: "#F28B6D"),
                Color(hex: "#F0A84A"),
                Color(hex: "#4AC6B7"),
                Color(hex: "#6B8BEB"),
                Color(hex: "#9D7AEA"),
                Color(hex: "#E8607A"),
            ]),
            center: .center,
            angle: .degrees(rotation)
        )
    }

    var body: some View {
        RoundedRectangle(cornerRadius: cornerRadius)
            .stroke(gradient, lineWidth: lineWidth)
            .onAppear {
                withAnimation(.linear(duration: 2).repeatForever(autoreverses: false)) {
                    rotation = 360
                }
            }
    }
}

// MARK: - Agent Avatar

/// Flat avatar — paperWarm rounded rect with image, emoji, or initial letter.
/// No circle, no extra shadow — sits flat on the card surface.
struct AgentAvatar: View {
    let agent: GatewayClient.AgentResponse
    var roleColor: Color = VultiTheme.violet
    var size: CGFloat = 36

    private var initial: String {
        String(agent.name.prefix(1)).uppercased()
    }

    var body: some View {
        ZStack {
            RoundedRectangle(cornerRadius: size * 0.17)
                .fill(VultiTheme.paperWarm)
                .frame(width: size, height: size)

            if let avatarStr = agent.avatar, !avatarStr.isEmpty {
                if avatarStr.count <= 2, avatarStr.unicodeScalars.allSatisfy({ $0.properties.isEmoji }) {
                    Text(avatarStr)
                        .font(.system(size: size * 0.5))
                } else if let data = Data(base64Encoded: avatarStr),
                          let nsImage = NSImage(data: data) {
                    Image(nsImage: nsImage)
                        .resizable()
                        .scaledToFill()
                        .frame(width: size - 4, height: size - 4)
                        .clipShape(RoundedRectangle(cornerRadius: size * 0.12))
                } else {
                    initialView
                }
            } else {
                initialView
            }
        }
    }

    private var initialView: some View {
        Text(initial)
            .font(.system(size: size * 0.38, weight: .semibold))
            .foregroundStyle(VultiTheme.inkDim)
    }
}
