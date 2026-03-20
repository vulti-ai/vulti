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
    @State private var hoveredEdgeId: String?

    // FitView
    @State private var didFitView = false

    // Scroll-wheel zoom monitor
    @State private var scrollMonitor: Any?

    // Measured node sizes — reported by AgentNode via onNodeSize callback
    @State private var nodeSizes: [String: CGSize] = [:]

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

    /// All source handles for a node type
    private func sourceHandles(for type: CanvasLayout.LayoutNode.NodeType) -> [HandlePosition] {
        type == .owner ? [.bottom, .left, .right] : [.bottom, .right]
    }

    /// All target handles for a node type
    private func targetHandles(for type: CanvasLayout.LayoutNode.NodeType) -> [HandlePosition] {
        type == .owner ? [] : [.top, .left] // owner has no target handles
    }

    /// Edge anchors — picks the nearest source/target handle pair so arrows
    /// always snap to the closest port handle on each node.
    private func edgeAnchors(
        fromId: String, toId: String,
        from sourcePos: CGPoint, to targetPos: CGPoint,
        fromType: CanvasLayout.LayoutNode.NodeType,
        toType: CanvasLayout.LayoutNode.NodeType
    ) -> (start: CGPoint, end: CGPoint, fromHandle: HandlePosition, toHandle: HandlePosition) {
        let srcHandles = sourceHandles(for: fromType)
        let tgtHandles = targetHandles(for: toType)

        let defaultFrom = HandlePosition.bottom
        let defaultTo = HandlePosition.top

        var bestDist: CGFloat = .greatestFiniteMagnitude
        var bestFrom = defaultFrom
        var bestTo = defaultTo

        for sh in srcHandles {
            let sOff = handleOffset(for: sh, nodeId: fromId, nodeType: fromType)
            let sPoint = CGPoint(x: sourcePos.x + sOff.x, y: sourcePos.y + sOff.y)

            for th in tgtHandles {
                let tOff = handleOffset(for: th, nodeId: toId, nodeType: toType)
                let tPoint = CGPoint(x: targetPos.x + tOff.x, y: targetPos.y + tOff.y)

                let dist = hypot(sPoint.x - tPoint.x, sPoint.y - tPoint.y)
                if dist < bestDist {
                    bestDist = dist
                    bestFrom = sh
                    bestTo = th
                }
            }
        }

        if tgtHandles.isEmpty {
            let sOff = handleOffset(for: bestFrom, nodeId: fromId, nodeType: fromType)
            return (
                CGPoint(x: sourcePos.x + sOff.x, y: sourcePos.y + sOff.y),
                targetPos,
                bestFrom, defaultTo
            )
        }

        let fromOff = handleOffset(for: bestFrom, nodeId: fromId, nodeType: fromType)
        let toOff = handleOffset(for: bestTo, nodeId: toId, nodeType: toType)
        return (
            CGPoint(x: sourcePos.x + fromOff.x, y: sourcePos.y + fromOff.y),
            CGPoint(x: targetPos.x + toOff.x, y: targetPos.y + toOff.y),
            bestFrom, bestTo
        )
    }

    /// Hit-test: find nearest node within 50px
    private func hitTestNode(at point: CGPoint, layout: LayoutResult, size: CGSize, excluding: String) -> String? {
        var closest: (id: String, dist: CGFloat)?
        for node in layout.nodes where node.id != excluding {
            let pos = nodePos(node.id, layout: layout, size: size)
            let dist = hypot(point.x - pos.x, point.y - pos.y)
            if dist < 50, closest == nil || dist < closest!.dist {
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
                VultiTheme.paper.opacity(0.85).ignoresSafeArea()
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
            }
            .onChange(of: app.agentList.count) {
                fitView(layout: layout, size: geo.size)
            }
            .onChange(of: app.panelMode) { oldVal, newVal in
                if oldVal != nil && newVal == nil {
                    withAnimation(.easeInOut(duration: 0.3)) {
                        fitView(layout: layout, size: geo.size)
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
            edgesLayer(layout: layout, size: size)
            connectPreview(layout: layout, size: size)
            nodesLayer(layout: layout, size: size)
            arrowsLayer(layout: layout, size: size)
            handleDragLayer(layout: layout, size: size)
            edgeHoverLayer(layout: layout, size: size)  // above handles so hover always works
            edgeDeleteLayer(layout: layout, size: size)  // topmost so clicks always work
        }
        .coordinateSpace(name: "canvas")
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

    // MARK: Edge hover layer — rendered ABOVE handles so hover always works

    @ViewBuilder
    private func edgeHoverLayer(layout: LayoutResult, size: CGSize) -> some View {
        ForEach(layout.edges) { edge in
            if edge.isDeletable {
                let fromPos = nodePos(edge.fromId, layout: layout, size: size)
                let toPos = nodePos(edge.toId, layout: layout, size: size)
                let fromType = layout.nodes.first(where: { $0.id == edge.fromId })?.type ?? .agent
                let toType = layout.nodes.first(where: { $0.id == edge.toId })?.type ?? .agent
                let anchors = edgeAnchors(fromId: edge.fromId, toId: edge.toId, from: fromPos, to: toPos, fromType: fromType, toType: toType)

                BezierEdge.hitZonePath(from: anchors.start, to: anchors.end,
                                       fromHandle: anchors.fromHandle, toHandle: anchors.toHandle)
                    .stroke(.clear, lineWidth: 24)
                    .contentShape(
                        BezierEdge.hitZonePath(from: anchors.start, to: anchors.end,
                                               fromHandle: anchors.fromHandle, toHandle: anchors.toHandle)
                            .strokedPath(StrokeStyle(lineWidth: 24))
                    )
                    .onHover { hovering in
                        hoveredEdgeId = hovering ? edge.id : nil
                    }
                    .allowsHitTesting(true)
            }
        }
    }

    // MARK: Edge delete layer — rendered ABOVE nodes so clicks always work

    @ViewBuilder
    private func edgeDeleteLayer(layout: LayoutResult, size: CGSize) -> some View {
        if let edgeId = hoveredEdgeId,
           let edge = layout.edges.first(where: { $0.id == edgeId }) {
            let fromPos = nodePos(edge.fromId, layout: layout, size: size)
            let toPos = nodePos(edge.toId, layout: layout, size: size)
            let fromType = layout.nodes.first(where: { $0.id == edge.fromId })?.type ?? .agent
            let toType = layout.nodes.first(where: { $0.id == edge.toId })?.type ?? .agent
            let anchors = edgeAnchors(fromId: edge.fromId, toId: edge.toId, from: fromPos, to: toPos, fromType: fromType, toType: toType)
            let mid = CGPoint(x: (anchors.start.x + anchors.end.x) / 2,
                              y: (anchors.start.y + anchors.end.y) / 2)

            Button {
                let source = edge.fromId == CanvasLayout.ownerNodeId ? "owner" : edge.fromId
                let target = edge.toId == CanvasLayout.ownerNodeId ? "owner" : edge.toId
                if let rel = app.relationships.first(where: {
                    ($0.fromAgentId == source || (source == "owner" && $0.fromAgentId == nil))
                    && ($0.toAgentId == target || (target == "owner" && $0.toAgentId == nil))
                }), let relId = rel.rawId {
                    hoveredEdgeId = nil
                    Task {
                        try? await app.client.deleteRelationship(relId)
                        await app.refreshRelationships()
                    }
                }
            } label: {
                Image(systemName: "xmark")
                    .font(.system(size: 8))
                    .foregroundStyle(VultiTheme.inkDim)
                    .frame(width: 24, height: 24)
                    .background(VultiTheme.paperWarm, in: Circle())
                    .overlay(Circle().stroke(VultiTheme.border))
            }
            .buttonStyle(.plain)
            .onHover { hovering in
                // Keep delete button alive while cursor is over it
                if hovering { hoveredEdgeId = edgeId }
            }
            .position(mid)
            .transition(.scale.combined(with: .opacity))
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
                    .frame(width: 56, height: 56)
                    .contentShape(Circle())
                    .gesture(
                        DragGesture(coordinateSpace: .named("canvas"))
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
                                Task {
                                    _ = try? await app.client.createRelationship(
                                        fromId: sourceId, toId: targetId
                                    )
                                    try? await app.client.createRelationshipRoom(
                                        fromId: sourceId, toId: targetId
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

    var bezierPath: Path {
        Path { p in
            p.move(to: from)
            p.addCurve(to: to, control1: controlPoint1, control2: controlPoint2)
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
