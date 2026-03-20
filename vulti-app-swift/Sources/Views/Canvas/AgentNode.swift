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

    var statusColor: Color {
        switch agent.status ?? "" {
        case "active", "connected", "ready": VultiTheme.statusActive
        case "disconnected", "stopped", "setting_up": VultiTheme.statusWarning
        case "error": VultiTheme.statusError
        default: VultiTheme.statusDefault
        }
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
        VStack(spacing: 4) {
            ZStack {
                RoundedRectangle(cornerRadius: 6)
                    .fill(VultiTheme.paperWarm)
                    .frame(width: 32, height: 32)

                if let avatarStr = agent.avatar, !avatarStr.isEmpty {
                    if avatarStr.count <= 2, avatarStr.unicodeScalars.allSatisfy({ $0.properties.isEmoji }) {
                        Text(avatarStr)
                            .font(.system(size: 18))
                    } else if let data = Data(base64Encoded: avatarStr),
                              let nsImage = NSImage(data: data) {
                        Image(nsImage: nsImage)
                            .resizable()
                            .frame(width: 28, height: 28)
                            .clipShape(RoundedRectangle(cornerRadius: 4))
                    } else {
                        Text(String(agent.name.prefix(1)).uppercased())
                            .font(.system(size: 14, weight: .semibold))
                            .foregroundStyle(VultiTheme.inkDim)
                    }
                } else {
                    Text(String(agent.name.prefix(1)).uppercased())
                        .font(.system(size: 14, weight: .semibold))
                        .foregroundStyle(VultiTheme.inkDim)
                }
            }

            Text(agent.name)
                .font(.system(size: 13, weight: .medium))
                .foregroundStyle(VultiTheme.inkSoft)
                .lineLimit(1)

            if let role = agent.role, !role.isEmpty {
                Text(role)
                    .font(.system(size: 11))
                    .foregroundStyle(roleColor)
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
        .overlay(
            RoundedRectangle(cornerRadius: 10)
                .stroke(roleColor, lineWidth: borderWidth)
                .animation(.easeInOut(duration: 0.12), value: borderWidth)
        )
        .overlay(
            Circle()
                .fill(statusColor)
                .frame(width: 7, height: 7)
                .offset(x: -4, y: 4),
            alignment: .topTrailing
        )
        .shadow(color: .black.opacity(isHovered ? 0.10 : 0.06), radius: isHovered ? 18 : 15, y: 8)
        .animation(.easeInOut(duration: 0.12), value: isHovered)
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
        if isHovered { return 2 }
        return 1.5
    }

    var body: some View {
        VStack(spacing: 1) {
            Text(name)
                .font(.system(size: 14, weight: .semibold))
                .foregroundStyle(VultiTheme.inkSoft)
                .lineLimit(1)
            Text("Human")
                .font(.system(size: 10))
                .foregroundStyle(color)
        }
        .frame(width: 80, height: 80)
        .background(Circle().fill(VultiTheme.paper.opacity(0.85)))
        .overlay(Circle().stroke(color, lineWidth: borderWidth).animation(.easeInOut(duration: 0.12), value: borderWidth))
        .shadow(color: .black.opacity(isHovered ? 0.10 : 0.06), radius: isHovered ? 16 : 12, y: 6)
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
