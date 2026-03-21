import Foundation
import SwiftUI

/// Exact port of canvas/layout.ts — depth-based hierarchy layout.
struct CanvasLayout {

    // MARK: - Role colors (matches ROLE_COLORS in layout.ts)

    static let roleColors: [String: String] = [
        "assistant": "#6B8BEB",
        "ops": "#6B8BEB",
        "analyst": "#5AADE0",
        "engineer": "#8BC867",
        "researcher": "#4AC6B7",
        "therapist": "#F28B6D",
        "coach": "#F0A84A",
        "creative": "#D96BA8",
        "writer": "#E8607A",
    ]
    static let defaultColor = "#9D7AEA"
    static let ownerColor = "#E8607A"
    static let ownerNodeId = "__owner__"

    struct LayoutNode: Identifiable {
        let id: String
        let type: NodeType
        var x: CGFloat
        var y: CGFloat
        let label: String
        let sublabel: String
        let color: Color
        let status: String?
        let role: String?

        enum NodeType { case owner, agent }
    }

    struct LayoutEdge: Identifiable {
        let id: String
        let fromId: String
        let toId: String
        let type: String
        let isDeletable: Bool
    }

    // MARK: - Compute layout (exact port of computeLayout)

    static func compute(
        agents: [AgentEntry],
        relationships: [RelationshipEntry],
        owner: OwnerEntry?,
        width: CGFloat,
        height: CGFloat
    ) -> (nodes: [LayoutNode], edges: [LayoutEdge]) {
        var nodes: [LayoutNode] = []
        var edges: [LayoutEdge] = []

        // Owner node — top center, 15% margin capped at 120
        let topMargin = min(height * 0.15, 120)
        let ownerNode = LayoutNode(
            id: ownerNodeId,
            type: .owner,
            x: width / 2,
            y: topMargin,
            label: owner?.name ?? "Human",
            sublabel: "Human",
            color: Color(hex: ownerColor),
            status: nil,
            role: nil
        )
        nodes.append(ownerNode)

        guard !agents.isEmpty else { return (nodes, edges) }

        // Build managedBy map (only "manages" relationships)
        var managedBy: [String: String] = [:]
        for rel in relationships where rel.type == "manages" {
            let from = rel.source == "owner" ? ownerNodeId : rel.source
            let to = rel.target == "owner" ? ownerNodeId : rel.target
            if from != ownerNodeId {
                managedBy[to] = from
            }
        }

        // Calculate depth for each agent (recursive with cycle detection)
        var depthCache: [String: Int] = [:]

        func getDepth(_ id: String, visited: inout Set<String>) -> Int {
            if let cached = depthCache[id] { return cached }
            if visited.contains(id) { return 1 }
            visited.insert(id)

            let depth: Int
            if let parent = managedBy[id] {
                depth = getDepth(parent, visited: &visited) + 1
            } else {
                depth = 1
            }
            depthCache[id] = depth
            return depth
        }

        for agent in agents {
            var visited = Set<String>()
            _ = getDepth(agent.id, visited: &visited)
        }

        // Group agents by depth
        var depthGroups: [Int: [AgentEntry]] = [:]
        for agent in agents {
            let d = depthCache[agent.id] ?? 1
            depthGroups[d, default: []].append(agent)
        }

        let maxDepth = depthGroups.keys.max() ?? 1

        // Vertical spacing: min(180, availableHeight / (maxDepth + 0.5))
        let availableHeight = height - topMargin - 80
        let verticalSpacing = min(180, availableHeight / (CGFloat(maxDepth) + 0.5))

        // Horizontal spacing
        let horizontalPadding: CGFloat = 100
        let usableWidth = width - horizontalPadding * 2
        let nodeSpacing: CGFloat = min(220, usableWidth / CGFloat(max(agents.count, 1)))

        // Position nodes depth by depth.
        // Depth 1: centered across the canvas (children of owner).
        // Depth 2+: centered under their parent's X position.
        var positionMap: [String: CGPoint] = [:]

        // Owner position
        positionMap[ownerNodeId] = CGPoint(x: width / 2, y: topMargin)

        for depth in 1...maxDepth {
            guard let group = depthGroups[depth] else { continue }
            let y = topMargin + CGFloat(depth) * verticalSpacing

            if depth == 1 {
                // Root agents — center across full width
                let count = group.count
                let rowWidth = nodeSpacing * CGFloat(count - 1)
                let startX = width / 2 - rowWidth / 2
                for (i, agent) in group.enumerated() {
                    let x = count == 1 ? width / 2 : startX + CGFloat(i) * nodeSpacing
                    positionMap[agent.id] = CGPoint(x: x, y: y)
                }
            } else {
                // Sub-agents — group by parent, center each group under parent's X
                var byParent: [String: [AgentEntry]] = [:]
                for agent in group {
                    let parent = managedBy[agent.id] ?? ownerNodeId
                    byParent[parent, default: []].append(agent)
                }

                for (parentId, children) in byParent {
                    let parentX = positionMap[parentId]?.x ?? width / 2
                    let count = children.count
                    let rowWidth = nodeSpacing * CGFloat(count - 1)
                    let startX = parentX - rowWidth / 2

                    for (i, agent) in children.enumerated() {
                        let x = count == 1 ? parentX : startX + CGFloat(i) * nodeSpacing
                        positionMap[agent.id] = CGPoint(x: x, y: y)
                    }
                }
            }
        }

        // Build layout nodes from positions
        for agent in agents {
            let pos = positionMap[agent.id] ?? CGPoint(x: width / 2, y: topMargin + verticalSpacing)
            let roleStr = agent.role ?? ""
            let colorHex = roleColors[roleStr.lowercased()] ?? defaultColor

            nodes.append(LayoutNode(
                id: agent.id,
                type: .agent,
                x: pos.x,
                y: pos.y,
                label: agent.name,
                sublabel: roleStr,
                color: Color(hex: colorHex),
                status: agent.status,
                role: roleStr
            ))
        }

        // Implicit edges: owner → all depth-1 agents
        let depth1Ids = Set((depthGroups[1] ?? []).map(\.id))
        for id in depth1Ids {
            edges.append(LayoutEdge(
                id: "owner-\(id)",
                fromId: ownerNodeId,
                toId: id,
                type: "manages",
                isDeletable: false
            ))
        }

        // Explicit edges from relationships
        let nodeIds = Set(nodes.map(\.id))
        for rel in relationships {
            let fromId = rel.source == "owner" ? ownerNodeId : rel.source
            let toId = rel.target == "owner" ? ownerNodeId : rel.target

            guard nodeIds.contains(fromId), nodeIds.contains(toId) else { continue }

            // Skip if owner → depth-1 (already implicit)
            if fromId == ownerNodeId && depth1Ids.contains(toId) { continue }

            edges.append(LayoutEdge(
                id: rel.id,
                fromId: fromId,
                toId: toId,
                type: rel.type ?? "manages",
                isDeletable: true
            ))
        }

        return (nodes, edges)
    }
}

// MARK: - Color from hex

extension Color {
    init(hex: String) {
        let hex = hex.trimmingCharacters(in: CharacterSet(charactersIn: "#"))
        var int: UInt64 = 0
        Scanner(string: hex).scanHexInt64(&int)
        let r = Double((int >> 16) & 0xFF) / 255.0
        let g = Double((int >> 8) & 0xFF) / 255.0
        let b = Double(int & 0xFF) / 255.0
        self.init(red: r, green: g, blue: b)
    }
}
