import SwiftUI

/// Native canvas — warm paper background, dot grid, handle-based drag-to-connect,
/// smooth node dragging, anchored bezier edges with arrows, fitView, pan/zoom.
struct SquadCanvas: View {
    @Environment(AppState.self) private var app
    @State private var nodeOverrides: [String: CGPoint] = [:]

    // Viewport
    @State private var scale: CGFloat = 1.0
    @State private var offset: CGPoint = .zero
    @State private var dragStart: CGPoint? = nil

    // Handle-based connection
    @State private var connectFrom: String?
    @State private var connectFromHandle: HandlePosition?
    @State private var connectDragPosition: CGPoint?

    // Node drag tracking (smooth drag without jump-to-cursor)
    @State private var dragNodeStart: [String: CGPoint] = [:]

    // Edge hover — tracked here so delete button renders above nodes

    // FitView
    @State private var didFitView = false

    // Scroll-wheel zoom monitor
    @State private var scrollMonitor: Any?

    // Measured node sizes — reported by AgentNode via onNodeSize callback
    @State private var nodeSizes: [String: CGSize] = [:]

    // Matrix server name fetched from gateway integrations
    @State private var matrixServerName: String?

    // Outward padding from edge for handle position
    private let handlePad: CGFloat = 4

    // Owner node fixed size
    private let ownerSize = CGSize(width: 80, height: 80)

    private typealias LayoutResult = (nodes: [CanvasLayout.LayoutNode], edges: [CanvasLayout.LayoutEdge])

    // MARK: - Data adapters

    private var layoutRelationships: [RelationshipEntry] {
        app.relationships.map { rel in
            RelationshipEntry(
                source: rel.fromAgentId ?? "",
                target: rel.toAgentId ?? "",
                type: rel.type
            )
        }
    }

    private var layoutAgents: [AgentEntry] {
        app.agentList.map { a in
            AgentEntry(
                id: a.id, name: a.name, role: a.role, status: a.status,
                createdAt: a.createdAt, createdFrom: a.createdFrom,
                avatar: a.avatar, description: a.description
            )
        }
    }

    private var layoutOwner: OwnerEntry? {
        guard let o = app.ownerInfo else { return nil }
        return OwnerEntry(name: o.name, about: o.about)
    }

    // MARK: - Helpers

    private func nodePos(_ id: String, layout: LayoutResult, size: CGSize) -> CGPoint {
        if let override = nodeOverrides[id] { return override }
        if let node = layout.nodes.first(where: { $0.id == id }) {
            return CGPoint(x: node.x, y: node.y)
        }
        return CGPoint(x: size.width / 2, y: size.height / 2)
    }

    /// Dynamic handle offset based on measured node size
    private func handleOffset(for handle: HandlePosition, nodeId: String, nodeType: CanvasLayout.LayoutNode.NodeType) -> CGPoint {
        let size = nodeType == .owner ? ownerSize : (nodeSizes[nodeId] ?? CGSize(width: 120, height: 90))
        let hw = size.width / 2 + handlePad
        let hh = size.height / 2 + handlePad
        switch handle {
        case .top:    return CGPoint(x: 0, y: -hh)
        case .bottom: return CGPoint(x: 0, y: hh)
        case .left:   return CGPoint(x: -hw, y: 0)
        case .right:  return CGPoint(x: hw, y: 0)
        }
    }

    /// Source (output) handles — where arrows DEPART from.
    /// Human: 6, 3, 9 o'clock. Agent: 6, 3, 9 o'clock (same as manager role).
    private func sourceHandles(for type: CanvasLayout.LayoutNode.NodeType) -> [HandlePosition] {
        [.bottom, .left, .right]  // 6, 9, 3 o'clock
    }

    /// Target (input) handles — where arrows ARRIVE at.
    /// Agent: 12, 9, 3 o'clock. Human: none (owner is never managed).
    private func targetHandles(for type: CanvasLayout.LayoutNode.NodeType) -> [HandlePosition] {
        type == .owner ? [] : [.top, .left, .right]  // 12, 9, 3 o'clock
    }

    /// Edge anchors with directional preference:
    /// - Normal (target below source): source bottom (6) → target top (12)
    /// - Same level or target above: use left/right (3/9) handles
    private func edgeAnchors(
        fromId: String, toId: String,
        from sourcePos: CGPoint, to targetPos: CGPoint,
        fromType: CanvasLayout.LayoutNode.NodeType,
        toType: CanvasLayout.LayoutNode.NodeType
    ) -> (start: CGPoint, end: CGPoint, fromHandle: HandlePosition, toHandle: HandlePosition) {

        // No target handles (owner) — just use source bottom → target center
        if toType == .owner {
            let sOff = handleOffset(for: .bottom, nodeId: fromId, nodeType: fromType)
            return (
                CGPoint(x: sourcePos.x + sOff.x, y: sourcePos.y + sOff.y),
                targetPos,
                .bottom, .top
            )
        }

        let dy = targetPos.y - sourcePos.y  // positive = target is below source

        let fromHandle: HandlePosition
        let toHandle: HandlePosition

        if dy > 30 {
            // Normal hierarchy: target is below source
            // Depart bottom (6 o'clock), arrive top (12 o'clock)
            fromHandle = .bottom
            toHandle = .top
        } else if dy < -30 {
            // Target is ABOVE source (unusual — upward connection)
            // Depart top via left/right, arrive bottom via left/right
            // Pick side based on horizontal position
            if targetPos.x > sourcePos.x {
                fromHandle = .right
                toHandle = .left
            } else {
                fromHandle = .left
                toHandle = .right
            }
        } else {
            // Same level — horizontal connection
            if targetPos.x > sourcePos.x {
                fromHandle = .right
                toHandle = .left
            } else {
                fromHandle = .left
                toHandle = .right
            }
        }

        let fromOff = handleOffset(for: fromHandle, nodeId: fromId, nodeType: fromType)
        let toOff = handleOffset(for: toHandle, nodeId: toId, nodeType: toType)
        return (
            CGPoint(x: sourcePos.x + fromOff.x, y: sourcePos.y + fromOff.y),
            CGPoint(x: targetPos.x + toOff.x, y: targetPos.y + toOff.y),
            fromHandle, toHandle
        )
    }

    /// Hit-test: find nearest node within 50px
    private func hitTestNode(at point: CGPoint, layout: LayoutResult, size: CGSize, excluding: String) -> String? {
        // Use a generous hit zone — nodes are ~100-120px wide
        let hitRadius: CGFloat = 80
        var closest: (id: String, dist: CGFloat)?
        for node in layout.nodes where node.id != excluding {
            let pos = nodePos(node.id, layout: layout, size: size)
            let dist = hypot(point.x - pos.x, point.y - pos.y)
            if dist < hitRadius, closest == nil || dist < closest!.dist {
                closest = (node.id, dist)
            }
        }
        return closest?.id
    }

    /// FitView: auto-zoom to fit all nodes with 20% padding
    private func fitView(layout: LayoutResult, size: CGSize) {
        guard !layout.nodes.isEmpty else { return }
        let xs = layout.nodes.map(\.x)
        let ys = layout.nodes.map(\.y)
        let minX = xs.min()!, maxX = xs.max()!
        let minY = ys.min()!, maxY = ys.max()!
        let contentWidth = maxX - minX + 200
        let contentHeight = maxY - minY + 200
        guard contentWidth > 0, contentHeight > 0 else { return }
        let scaleX = size.width / contentWidth
        let scaleY = size.height / contentHeight
        let fitScale = min(scaleX, scaleY) * 0.8
        scale = max(0.4, min(1.5, fitScale))
        let centerX = (minX + maxX) / 2
        let centerY = (minY + maxY) / 2
        offset = CGPoint(
            x: (size.width / 2 - centerX) * scale,
            y: (size.height / 2 - centerY) * scale
        )
    }

    /// Tidy: clear all manual overrides so nodes snap back to computed hierarchy layout, then fit.
    private func tidyCanvas(layout: LayoutResult, size: CGSize) {
        nodeOverrides.removeAll()
        dragNodeStart.removeAll()
        fitView(layout: layout, size: size)
    }

    // MARK: - Body

    var body: some View {
        GeometryReader { geo in
            let layout = CanvasLayout.compute(
                agents: layoutAgents,
                relationships: layoutRelationships,
                owner: layoutOwner,
                width: geo.size.width,
                height: geo.size.height
            )
            ZStack {
                VultiTheme.paper.opacity(0.7).ignoresSafeArea()
                VultiTheme.noiseOverlay().ignoresSafeArea()
                canvasContent(layout: layout, size: geo.size)
                    .scaleEffect(scale)
                    .offset(x: offset.x, y: offset.y)


            }
            .gesture(
                DragGesture()
                    .onChanged { value in
                        if dragStart == nil { dragStart = offset }
                        offset = CGPoint(
                            x: (dragStart?.x ?? 0) + value.translation.width,
                            y: (dragStart?.y ?? 0) + value.translation.height
                        )
                    }
                    .onEnded { _ in dragStart = nil }
            )
            .gesture(
                MagnifyGesture()
                    .onChanged { value in
                        scale = max(0.25, min(3.0, value.magnification))
                    }
            )
            .onAppear {
                scrollMonitor = NSEvent.addLocalMonitorForEvents(matching: .scrollWheel) { event in
                    let delta = event.scrollingDeltaY
                    if abs(delta) > 0.1 {
                        let factor = 1.0 + delta * 0.01
                        scale = max(0.25, min(3.0, scale * factor))
                    }
                    return event // pass through — don't swallow
                }
                if !didFitView {
                    fitView(layout: layout, size: geo.size)
                    didFitView = true
                }
                // Fetch Matrix server name
                Task {
                    if let integrations = try? await app.client.listIntegrations(),
                       let matrix = integrations.first(where: { $0.id == "matrix" }),
                       let details = matrix.details,
                       let serverName = details["server_name"]?.value as? String,
                       !serverName.isEmpty, serverName != "localhost" {
                        matrixServerName = serverName
                    }
                }
            }
            .onChange(of: app.agentList.count) {
                fitView(layout: layout, size: geo.size)
            }
            .onChange(of: app.panelMode) { oldVal, newVal in
                if oldVal != nil && newVal == nil {
                    withAnimation(.easeInOut(duration: 0.3)) {
                        tidyCanvas(layout: layout, size: geo.size)
                    }
                }
            }
            .onDisappear {
                if let monitor = scrollMonitor {
                    NSEvent.removeMonitor(monitor)
                    scrollMonitor = nil
                }
            }
        }
    }

    // MARK: - Canvas layers

    @ViewBuilder
    private func canvasContent(layout: LayoutResult, size: CGSize) -> some View {
        ZStack {
            CanvasGrid()
            groupBoundary(layout: layout, size: size)
            edgesLayer(layout: layout, size: size)
            connectPreview(layout: layout, size: size)
            nodesLayer(layout: layout, size: size)
            arrowsLayer(layout: layout, size: size)
            handleDragLayer(layout: layout, size: size)
            edgeDeleteLayer(layout: layout, size: size)  // topmost so hover/clicks always work
        }
        .coordinateSpace(name: "canvas")
    }

    // MARK: Group boundary — dotted rounded rect enclosing all nodes

    private var boundaryGradient: AngularGradient {
        AngularGradient(
            colors: [
                Color(hex: "#E8607A"),
                Color(hex: "#F28B6D"),
                Color(hex: "#F0A84A"),
                Color(hex: "#4AC6B7"),
                Color(hex: "#6B8BEB"),
                Color(hex: "#9D7AEA"),
                Color(hex: "#E8607A"),
            ],
            center: .center
        )
    }

    @ViewBuilder
    private func groupBoundary(layout: LayoutResult, size: CGSize) -> some View {
        if layout.nodes.count > 1 {
            let labelText = matrixServerName ?? ""
            let hasLabel = !labelText.isEmpty
            let padding: CGFloat = 60
            let topExtra: CGFloat = hasLabel ? 30 : 0
            let positions = layout.nodes.map { nodePos($0.id, layout: layout, size: size) }
            let nodeSizesList = layout.nodes.map { node -> CGSize in
                if node.type == .owner { return ownerSize }
                return nodeSizes[node.id] ?? CGSize(width: 120, height: 90)
            }

            let minX = zip(positions, nodeSizesList).map { $0.0.x - $0.1.width / 2 }.min()! - padding
            let maxX = zip(positions, nodeSizesList).map { $0.0.x + $0.1.width / 2 }.max()! + padding
            let minY = zip(positions, nodeSizesList).map { $0.0.y - $0.1.height / 2 }.min()! - padding - topExtra
            let maxY = zip(positions, nodeSizesList).map { $0.0.y + $0.1.height / 2 }.max()! + padding

            let rect = CGRect(x: minX, y: minY, width: maxX - minX, height: maxY - minY)

            // Dotted boundary
            RoundedRectangle(cornerRadius: 24)
                .stroke(
                    boundaryGradient.opacity(0.5),
                    style: StrokeStyle(lineWidth: 1.5, dash: [8, 6])
                )
                .frame(width: rect.width, height: rect.height)
                .position(x: rect.midX, y: rect.midY)
                .allowsHitTesting(false)

            // Label centered on top edge
            if hasLabel {
                Text(labelText)
                    .font(.system(size: 11, weight: .medium, design: .monospaced))
                    .foregroundStyle(VultiTheme.inkMuted)
                    .padding(.horizontal, 12)
                    .padding(.vertical, 4)
                    .background(
                        RoundedRectangle(cornerRadius: 8)
                            .fill(VultiTheme.paper.opacity(0.9))
                    )
                    .overlay(
                        RoundedRectangle(cornerRadius: 8)
                            .stroke(
                                boundaryGradient.opacity(0.5),
                                style: StrokeStyle(lineWidth: 1.5, dash: [8, 6])
                            )
                    )
                    .help("Connect here: https://matrix.org/ecosystem/clients/")
                    .onTapGesture {
                        NSWorkspace.shared.open(URL(string: "https://matrix.org/ecosystem/clients/")!)
                    }
                    .position(x: rect.midX, y: rect.minY)
            }
        }
    }

    // MARK: Edges layer — bezier curves only (no hit testing)

    @ViewBuilder
    private func edgesLayer(layout: LayoutResult, size: CGSize) -> some View {
        ForEach(layout.edges) { edge in
            let fromPos = nodePos(edge.fromId, layout: layout, size: size)
            let toPos = nodePos(edge.toId, layout: layout, size: size)
            let fromType = layout.nodes.first(where: { $0.id == edge.fromId })?.type ?? .agent
            let toType = layout.nodes.first(where: { $0.id == edge.toId })?.type ?? .agent
            let anchors = edgeAnchors(fromId: edge.fromId, toId: edge.toId, from: fromPos, to: toPos, fromType: fromType, toType: toType)

            BezierEdge(from: anchors.start, to: anchors.end,
                       fromHandle: anchors.fromHandle, toHandle: anchors.toHandle)
        }
    }

    // MARK: Edge delete layer — one hover circle per deletable edge at its midpoint.
    // Each edge gets its own independent hover target that can't overlap with others.

    @ViewBuilder
    private func edgeDeleteLayer(layout: LayoutResult, size: CGSize) -> some View {
        ForEach(layout.edges) { edge in
            if edge.isDeletable {
                let fromPos = nodePos(edge.fromId, layout: layout, size: size)
                let toPos = nodePos(edge.toId, layout: layout, size: size)
                let fromType = layout.nodes.first(where: { $0.id == edge.fromId })?.type ?? .agent
                let toType = layout.nodes.first(where: { $0.id == edge.toId })?.type ?? .agent
                let anchors = edgeAnchors(fromId: edge.fromId, toId: edge.toId, from: fromPos, to: toPos, fromType: fromType, toType: toType)
                let mid = CGPoint(x: (anchors.start.x + anchors.end.x) / 2,
                                  y: (anchors.start.y + anchors.end.y) / 2)

                EdgeDeleteButton(
                    edgeId: edge.id,
                    fromId: edge.fromId == CanvasLayout.ownerNodeId ? "owner" : edge.fromId,
                    toId: edge.toId == CanvasLayout.ownerNodeId ? "owner" : edge.toId
                )
                .position(mid)
            }
        }
    }

    // MARK: Connect preview — dashed bezier from handle to cursor

    @ViewBuilder
    private func connectPreview(layout: LayoutResult, size: CGSize) -> some View {
        if let fromId = connectFrom, let handle = connectFromHandle, let dragPos = connectDragPosition {
            let fromPos = nodePos(fromId, layout: layout, size: size)
            let fromType = layout.nodes.first(where: { $0.id == fromId })?.type ?? .agent
            let off = handleOffset(for: handle, nodeId: fromId, nodeType: fromType)
            let handlePoint = CGPoint(x: fromPos.x + off.x, y: fromPos.y + off.y)

            BezierEdge(from: handlePoint, to: dragPos, isPreview: true)
        }
    }

    // MARK: Nodes layer — tap to open, smooth drag to move

    @ViewBuilder
    private func nodesLayer(layout: LayoutResult, size: CGSize) -> some View {
        let isConnecting = connectFrom != nil

        ForEach(layout.nodes) { node in
            let pos = nodePos(node.id, layout: layout, size: size)

            Group {
                switch node.type {
                case .owner:
                    OwnerNode(name: node.label, color: node.color, showHandles: isConnecting)
                        .highPriorityGesture(
                            TapGesture().onEnded { app.openOwner() }
                        )
                        .gesture(
                            DragGesture(minimumDistance: 6, coordinateSpace: .named("canvas"))
                                .onChanged { value in
                                    if dragNodeStart[node.id] == nil {
                                        dragNodeStart[node.id] = pos
                                    }
                                    let start = dragNodeStart[node.id]!
                                    nodeOverrides[node.id] = CGPoint(
                                        x: start.x + value.translation.width,
                                        y: start.y + value.translation.height
                                    )
                                }
                                .onEnded { _ in
                                    dragNodeStart.removeValue(forKey: node.id)
                                }
                        )

                case .agent:
                    if let agent = app.agent(byId: node.id) {
                        AgentNode(
                            agent: agent,
                            isDefault: node.id == app.defaultAgentId,
                            roleColor: node.color,
                            showHandles: isConnecting,
                            onNodeSize: { size in nodeSizes[node.id] = size }
                        )
                        .highPriorityGesture(
                            TapGesture().onEnded { app.openAgent(node.id) }
                        )
                        .gesture(
                            DragGesture(minimumDistance: 6, coordinateSpace: .named("canvas"))
                                .onChanged { value in
                                    if dragNodeStart[node.id] == nil {
                                        dragNodeStart[node.id] = pos
                                    }
                                    let start = dragNodeStart[node.id]!
                                    nodeOverrides[node.id] = CGPoint(
                                        x: start.x + value.translation.width,
                                        y: start.y + value.translation.height
                                    )
                                }
                                .onEnded { _ in
                                    dragNodeStart.removeValue(forKey: node.id)
                                }
                        )
                    }
                }
            }
            .position(pos)
        }
    }

    // MARK: Arrows layer — rendered ABOVE nodes so arrow tips are visible at handles

    @ViewBuilder
    private func arrowsLayer(layout: LayoutResult, size: CGSize) -> some View {
        ForEach(layout.edges) { edge in
            let fromPos = nodePos(edge.fromId, layout: layout, size: size)
            let toPos = nodePos(edge.toId, layout: layout, size: size)
            let fromType = layout.nodes.first(where: { $0.id == edge.fromId })?.type ?? .agent
            let toType = layout.nodes.first(where: { $0.id == edge.toId })?.type ?? .agent
            let anchors = edgeAnchors(fromId: edge.fromId, toId: edge.toId, from: fromPos, to: toPos, fromType: fromType, toType: toType)

            BezierEdge.arrowHead(from: anchors.start, to: anchors.end,
                                 fromHandle: anchors.fromHandle, toHandle: anchors.toHandle)
                .fill(VultiTheme.inkMuted.opacity(0.4))
                .allowsHitTesting(false)
        }
    }

    // MARK: Handle drag layer — circles at each source handle position.
    // These sit outside the node body so they don't steal taps from the node.
    // Size is generous (56pt) so they're easy to grab.

    @ViewBuilder
    private func handleDragLayer(layout: LayoutResult, size: CGSize) -> some View {
        ForEach(layout.nodes) { node in
            let pos = nodePos(node.id, layout: layout, size: size)
            let handles = sourceHandles(for: node.type)

            ForEach(handles, id: \.self) { handle in
                let off = handleOffset(for: handle, nodeId: node.id, nodeType: node.type)
                let handlePos = CGPoint(x: pos.x + off.x, y: pos.y + off.y)

                Circle()
                    .fill(Color.clear)
                    .frame(width: 20, height: 20)
                    .contentShape(Circle())
                    .gesture(
                        DragGesture(minimumDistance: 5, coordinateSpace: .named("canvas"))
                            .onChanged { value in
                                if connectFrom == nil {
                                    connectFrom = node.id
                                    connectFromHandle = handle
                                }
                                connectDragPosition = value.location
                            }
                            .onEnded { value in
                                defer {
                                    connectFrom = nil
                                    connectFromHandle = nil
                                    connectDragPosition = nil
                                }
                                guard let sourceId = connectFrom else { return }
                                guard let targetId = hitTestNode(
                                    at: value.location, layout: layout,
                                    size: size, excluding: sourceId
                                ) else { return }
                                guard targetId != CanvasLayout.ownerNodeId else { return }
                                // Drop target = manager, dragged node = managed
                                // "I dragged Test onto Flowwy" → Flowwy manages Test
                                Task {
                                    _ = try? await app.client.createRelationship(
                                        fromId: targetId, toId: sourceId
                                    )
                                    try? await app.client.createRelationshipRoom(
                                        fromId: targetId, toId: sourceId
                                    )
                                    await app.refreshRelationships()
                                }
                            }
                    )
                    .position(handlePos)
            }
        }
    }
}

// MARK: - Dot grid

/// Self-contained edge delete button — each edge gets its own hover state.
/// A 40px hover zone at the edge midpoint. Shows a soft red × on hover.
struct EdgeDeleteButton: View {
    let edgeId: String
    let fromId: String
    let toId: String
    @Environment(AppState.self) private var app
    @State private var isHovered = false

    var body: some View {
        Button {
            if let rel = app.relationships.first(where: {
                ($0.fromAgentId == fromId || (fromId == "owner" && $0.fromAgentId == nil))
                && ($0.toAgentId == toId || (toId == "owner" && $0.toAgentId == nil))
            }), let relId = rel.rawId {
                Task {
                    try? await app.client.deleteRelationship(relId)
                    await app.refreshRelationships()
                }
            }
        } label: {
            Image(systemName: "xmark")
                .font(.system(size: 7, weight: .medium))
                .foregroundStyle(isHovered ? .red : .clear)
                .frame(width: 20, height: 20)
                .background(
                    Circle()
                        .fill(isHovered ? VultiTheme.paperWarm : .clear)
                        .overlay(
                            Circle().stroke(isHovered ? Color.red.opacity(0.4) : .clear, lineWidth: 1)
                        )
                )
                .frame(width: 40, height: 40) // keep hover zone generous
                .contentShape(Circle())
        }
        .buttonStyle(.plain)
        .onHover { isHovered = $0 }
        .animation(.easeOut(duration: 0.15), value: isHovered)
    }
}

struct CanvasGrid: View {
    var body: some View {
        Canvas { context, size in
            let spacing: CGFloat = 24
            for x in stride(from: 0, to: size.width, by: spacing) {
                for y in stride(from: 0, to: size.height, by: spacing) {
                    let rect = CGRect(x: x - 0.5, y: y - 0.5, width: 1, height: 1)
                    context.fill(Path(ellipseIn: rect), with: .color(VultiTheme.inkMuted.opacity(0.3)))
                }
            }
        }
        .allowsHitTesting(false)
    }
}

// MARK: - Bezier edge

/// Bezier curve edge with direction-aware control points.
/// Departs in the direction of the source handle, arrives from the target handle direction.
/// Arrows always point into the target handle.
struct BezierEdge: View {
    let from: CGPoint
    let to: CGPoint
    var fromHandle: HandlePosition = .bottom
    var toHandle: HandlePosition = .top
    var isPreview: Bool = false

    private static let minCurvature: CGFloat = 50

    var midpoint: CGPoint {
        CGPoint(x: (from.x + to.x) / 2, y: (from.y + to.y) / 2)
    }

    /// Direction vector for a handle
    private static func handleDir(_ h: HandlePosition) -> (x: CGFloat, y: CGFloat) {
        switch h {
        case .top:    return (0, -1)
        case .bottom: return (0, 1)
        case .left:   return (-1, 0)
        case .right:  return (1, 0)
        }
    }

    var controlPoint1: CGPoint {
        let dir = Self.handleDir(fromHandle)
        let dist = hypot(to.x - from.x, to.y - from.y)
        let spread = max(dist * 0.4, Self.minCurvature)
        return CGPoint(x: from.x + dir.x * spread, y: from.y + dir.y * spread)
    }

    var controlPoint2: CGPoint {
        let dir = Self.handleDir(toHandle)
        let dist = hypot(to.x - from.x, to.y - from.y)
        let spread = max(dist * 0.4, Self.minCurvature)
        // cp2 is OUTSIDE the node in the handle direction, so curve arrives going INTO the handle
        return CGPoint(x: to.x + dir.x * spread, y: to.y + dir.y * spread)
    }

    /// Curve endpoint shortened by arrowLen so the line stops at the arrow base, not the tip
    private var shortenedEnd: CGPoint {
        let arrowLen: CGFloat = 12
        let angle = atan2(to.y - controlPoint2.y, to.x - controlPoint2.x)
        return CGPoint(
            x: to.x - arrowLen * Foundation.cos(angle),
            y: to.y - arrowLen * Foundation.sin(angle)
        )
    }

    var bezierPath: Path {
        Path { p in
            p.move(to: from)
            p.addCurve(to: shortenedEnd, control1: controlPoint1, control2: controlPoint2)
        }
    }

    /// Static helper for hit zone — must match instance control point logic
    static func hitZonePath(from: CGPoint, to: CGPoint,
                            fromHandle: HandlePosition = .bottom,
                            toHandle: HandlePosition = .top) -> Path {
        let dir1 = handleDir(fromHandle)
        let dir2 = handleDir(toHandle)
        let dist = hypot(to.x - from.x, to.y - from.y)
        let spread = max(dist * 0.4, minCurvature)
        let cp1 = CGPoint(x: from.x + dir1.x * spread, y: from.y + dir1.y * spread)
        let cp2 = CGPoint(x: to.x + dir2.x * spread, y: to.y + dir2.y * spread)
        return Path { p in
            p.move(to: from)
            p.addCurve(to: to, control1: cp1, control2: cp2)
        }
    }

    /// Static arrow head path — used by arrowsLayer (rendered above nodes)
    static func arrowHead(from: CGPoint, to: CGPoint,
                          fromHandle: HandlePosition = .bottom,
                          toHandle: HandlePosition = .top) -> Path {
        let dir2 = handleDir(toHandle)
        let dist = hypot(to.x - from.x, to.y - from.y)
        let spread = max(dist * 0.4, minCurvature)
        let cp2 = CGPoint(x: to.x + dir2.x * spread, y: to.y + dir2.y * spread)

        let angle = atan2(to.y - cp2.y, to.x - cp2.x)
        let arrowLen: CGFloat = 12
        let arrowWidth: CGFloat = 8
        let tip = to
        let left = CGPoint(
            x: tip.x - arrowLen * Foundation.cos(angle) + arrowWidth * Foundation.sin(angle) / 2,
            y: tip.y - arrowLen * Foundation.sin(angle) - arrowWidth * Foundation.cos(angle) / 2
        )
        let right = CGPoint(
            x: tip.x - arrowLen * Foundation.cos(angle) - arrowWidth * Foundation.sin(angle) / 2,
            y: tip.y - arrowLen * Foundation.sin(angle) + arrowWidth * Foundation.cos(angle) / 2
        )
        return Path { p in
            p.move(to: tip)
            p.addLine(to: left)
            p.addLine(to: right)
            p.closeSubpath()
        }
    }

    var body: some View {
        ZStack {
            if isPreview {
                bezierPath
                    .stroke(VultiTheme.inkMuted.opacity(0.3), style: StrokeStyle(lineWidth: 2, dash: [6, 4]))
                    .allowsHitTesting(false)
            } else {
                bezierPath
                    .stroke(VultiTheme.inkMuted.opacity(0.25), lineWidth: 1.5)
                    .allowsHitTesting(false)
            }
        }
    }
}
