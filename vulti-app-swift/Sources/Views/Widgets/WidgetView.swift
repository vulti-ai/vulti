import SwiftUI

/// Renders a PaneWidget based on its type.
/// Matches DynamicPane.svelte — 13 widget types.
struct WidgetView: View {
    let widget: PaneWidget
    var onSendMessage: ((String) -> Void)?

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            if let title = widget.title {
                Text(title)
                    .font(.system(size: 13, weight: .semibold))
            }

            widgetContent
        }
        .padding(16)
        .background(VultiTheme.paperDeep.opacity(0.5), in: RoundedRectangle(cornerRadius: 12))
        .overlay(RoundedRectangle(cornerRadius: 12).stroke(VultiTheme.paperDeep))
    }

    @ViewBuilder
    private var widgetContent: some View {
        switch widget.type {
        case .markdown:
            MarkdownWidgetContent(data: widget.data)
        case .kv:
            KvWidgetContent(data: widget.data)
        case .table:
            TableWidgetContent(data: widget.data)
        case .image:
            ImageWidgetContent(data: widget.data)
        case .status:
            StatusWidgetContent(data: widget.data)
        case .statGrid:
            StatGridWidgetContent(data: widget.data)
        case .barChart:
            BarChartWidgetContent(data: widget.data)
        case .progress:
            ProgressWidgetContent(data: widget.data)
        case .button:
            ButtonWidgetContent(data: widget.data, onSend: onSendMessage)
        case .form:
            FormWidgetContent(data: widget.data, onSend: onSendMessage)
        case .toggleList:
            ToggleListWidgetContent(data: widget.data, onSend: onSendMessage)
        case .actionList:
            ActionListWidgetContent(data: widget.data, onSend: onSendMessage)
        case .empty:
            EmptyView()
        case .profile:
            // Profile card — rendered as kv entries fallback in WidgetView
            KvWidgetContent(data: widget.data)
        }
    }
}

// MARK: - Widget implementations

struct MarkdownWidgetContent: View {
    let data: WidgetData
    var body: some View {
        MarkdownMessageView(content: data.content ?? "", isUser: false)
    }
}

struct KvWidgetContent: View {
    let data: WidgetData
    var body: some View {
        VStack(spacing: 6) {
            ForEach(data.entries ?? []) { entry in
                HStack {
                    Text(entry.key)
                        .font(.system(size: 12))
                        .foregroundStyle(VultiTheme.inkDim)
                    Spacer()
                    Text(maskIfNeeded(entry))
                        .font(.system(size: 12, design: entry.mono == true ? .monospaced : .default))
                        .lineLimit(1)
                }
            }
        }
    }

    private func maskIfNeeded(_ entry: KvEntry) -> String {
        guard entry.masked == true, entry.value.count > 8 else { return entry.value }
        return "\(entry.value.prefix(4))...\(entry.value.suffix(4))"
    }
}

struct TableWidgetContent: View {
    let data: WidgetData
    var body: some View {
        let cols = data.columns ?? []
        let rows = data.rows ?? []

        ScrollView(.horizontal) {
            VStack(spacing: 0) {
                // Header
                HStack {
                    ForEach(cols, id: \.self) { col in
                        Text(col)
                            .font(.system(size: 11, weight: .semibold))
                            .frame(minWidth: 80, alignment: .leading)
                    }
                }
                .padding(.vertical, 6)

                Divider()

                // Rows
                ForEach(Array(rows.enumerated()), id: \.offset) { _, row in
                    HStack {
                        ForEach(Array(row.enumerated()), id: \.offset) { _, cell in
                            Text(cell)
                                .font(.system(size: 11))
                                .frame(minWidth: 80, alignment: .leading)
                        }
                    }
                    .padding(.vertical, 4)
                    Divider()
                }
            }
        }
    }
}

struct ImageWidgetContent: View {
    let data: WidgetData
    var body: some View {
        if let src = data.src, let url = URL(string: src) {
            AsyncImage(url: url) { image in
                image.resizable().scaledToFit()
            } placeholder: {
                ProgressView()
            }
            .clipShape(RoundedRectangle(cornerRadius: 8))
        }
    }
}

struct StatusWidgetContent: View {
    let data: WidgetData

    var color: Color {
        switch data.variant {
        case "success": .green
        case "warning": .yellow
        case "error": .red
        case "info": .blue
        default: .secondary
        }
    }

    var body: some View {
        HStack(spacing: 8) {
            Circle().fill(color).frame(width: 8, height: 8)
            Text(data.label ?? "")
                .font(.system(size: 13))
            if let detail = data.detail {
                Spacer()
                Text(detail)
                    .font(.system(size: 11))
                    .foregroundStyle(VultiTheme.inkDim)
            }
        }
    }
}

/// Live analytics widget — fetches real data from the analytics API instead of using static widget data.
/// Live connections widget — shows allowed vs available counts with lists.
struct LiveConnectionsWidget: View {
    let agentId: String
    var tick: Int = 0
    @Environment(AppState.self) private var app
    @State private var allConnections: [GatewayClient.ConnectionResponse] = []
    @State private var allowedNames: Set<String> = []

    private var allowed: [GatewayClient.ConnectionResponse] {
        allConnections.filter { allowedNames.contains($0.name) }
    }
    private var available: [GatewayClient.ConnectionResponse] {
        allConnections.filter { !allowedNames.contains($0.name) }
    }

    var body: some View {
        HStack(alignment: .top, spacing: 0) {
            // Left: Allowed
            VStack(alignment: .leading, spacing: 4) {
                Text("Allowed (\(allowed.count))")
                    .font(.system(size: 11, weight: .semibold))
                    .foregroundStyle(VultiTheme.inkMuted)
                ForEach(allowed.prefix(5), id: \.name) { conn in
                    HStack {
                        Text(conn.name)
                            .font(.system(size: 11))
                        Spacer()
                        Image(systemName: "checkmark")
                            .font(.system(size: 9))
                            .foregroundStyle(.green)
                    }
                    .padding(.vertical, 1)
                }
                if allowed.count > 5 {
                    Text("+\(allowed.count - 5) more")
                        .font(.system(size: 10))
                        .foregroundStyle(VultiTheme.inkMuted)
                }
                if allowed.isEmpty {
                    Text("None")
                        .font(.system(size: 11))
                        .foregroundStyle(VultiTheme.inkDim)
                }
            }
            .frame(maxWidth: .infinity, alignment: .topLeading)

            Rectangle()
                .fill(VultiTheme.border)
                .frame(width: 1)
                .padding(.horizontal, 8)

            // Right: Available
            VStack(alignment: .leading, spacing: 4) {
                Text("Available (\(available.count))")
                    .font(.system(size: 11, weight: .semibold))
                    .foregroundStyle(VultiTheme.inkMuted)
                ForEach(available.prefix(5), id: \.name) { conn in
                    Text(conn.name)
                        .font(.system(size: 11))
                        .foregroundStyle(VultiTheme.inkDim)
                        .padding(.vertical, 1)
                }
                if available.count > 5 {
                    Text("+\(available.count - 5) more")
                        .font(.system(size: 10))
                        .foregroundStyle(VultiTheme.inkMuted)
                }
            }
            .frame(maxWidth: .infinity, alignment: .topLeading)
        }
        .task(id: tick) {
            allConnections = (try? await app.client.listConnections()) ?? []
            if let agent = try? await app.client.getAgent(agentId),
               let allowed = agent.allowedConnections {
                allowedNames = Set(allowed)
            }
        }
    }
}

struct LiveAnalyticsWidget: View {
    let agentId: String
    var tick: Int = 0
    @Environment(AppState.self) private var app
    @State private var overview: AnalyticsOverview?

    private func formatNumber(_ n: Int) -> String {
        if n >= 1_000_000 { return String(format: "%.1fM", Double(n) / 1_000_000) }
        if n >= 1_000 { return String(format: "%.1fK", Double(n) / 1_000) }
        return "\(n)"
    }

    var body: some View {
        Group {
            if let o = overview {
                LazyVGrid(columns: [GridItem(.flexible()), GridItem(.flexible())], spacing: 6) {
                    CompactStat(label: "Sessions", value: "\(o.totalSessions ?? 0)")
                    CompactStat(label: "Messages", value: formatNumber(o.totalMessages ?? 0))
                    CompactStat(label: "Tokens", value: formatNumber(o.totalTokens ?? 0))
                    CompactStat(label: "Cost", value: "$\(String(format: "%.2f", o.estimatedCost ?? 0))")
                }
            } else {
                ProgressView()
                    .frame(maxWidth: .infinity, minHeight: 40)
            }
        }
        .task(id: tick) {
            let data = try? await app.client.getAnalyticsData(days: 7, agentId: agentId)
            overview = data?.overview
        }
    }
}

/// Live jobs widget — fetches real cron jobs from the API.
struct LiveJobsWidget: View {
    let agentId: String
    var tick: Int = 0
    @Environment(AppState.self) private var app
    @State private var jobs: [GatewayClient.CronResponse] = []

    var body: some View {
        Group {
            if jobs.isEmpty {
                HStack(spacing: 6) {
                    Text("\u{2014}")
                        .font(.system(size: 12))
                        .foregroundStyle(VultiTheme.inkDim)
                    Text("None scheduled")
                        .font(.system(size: 12))
                        .foregroundStyle(VultiTheme.inkDim)
                }
            } else {
                VStack(spacing: 6) {
                    ForEach(jobs.prefix(5)) { job in
                        HStack {
                            Text(job.name ?? job.id)
                                .font(.system(size: 12))
                                .foregroundStyle(VultiTheme.inkDim)
                            Spacer()
                            Text("\(job.schedule ?? "")  \(job.enabled ? "\u{2713}" : "\u{23f8}")")
                                .font(.system(size: 12, design: .monospaced))
                                .lineLimit(1)
                        }
                    }
                    if jobs.count > 5 {
                        Text("+\(jobs.count - 5) more")
                            .font(.system(size: 10))
                            .foregroundStyle(VultiTheme.inkMuted)
                    }
                }
            }
        }
        .task(id: tick) {
            jobs = (try? await app.client.listCron(agentId: agentId)) ?? []
        }
    }
}

/// Live rules widget — fetches real rules from the API.
struct LiveRulesWidget: View {
    let agentId: String
    var tick: Int = 0
    @Environment(AppState.self) private var app
    @State private var rules: [GatewayClient.RuleResponse] = []

    var body: some View {
        Group {
            if rules.isEmpty {
                HStack(spacing: 6) {
                    Text("\u{2014}")
                        .font(.system(size: 12))
                        .foregroundStyle(VultiTheme.inkDim)
                    Text("None configured")
                        .font(.system(size: 12))
                        .foregroundStyle(VultiTheme.inkDim)
                }
            } else {
                VStack(spacing: 6) {
                    ForEach(rules.prefix(5)) { rule in
                        HStack {
                            Text(rule.name ?? rule.id)
                                .font(.system(size: 12))
                                .foregroundStyle(VultiTheme.inkDim)
                            Spacer()
                            Text((rule.enabled ?? true) ? "\u{2713}" : "\u{23f8}")
                                .font(.system(size: 12))
                        }
                    }
                    if rules.count > 5 {
                        Text("+\(rules.count - 5) more")
                            .font(.system(size: 10))
                            .foregroundStyle(VultiTheme.inkMuted)
                    }
                }
            }
        }
        .task(id: tick) {
            rules = (try? await app.client.listRules(agentId: agentId)) ?? []
        }
    }
}

/// Live skills widget — two-column layout matching connections widget.
struct LiveSkillsWidget: View {
    let agentId: String
    var tick: Int = 0
    @Environment(AppState.self) private var app
    @State private var installed: [GatewayClient.SkillResponse] = []
    @State private var allAvailable: [GatewayClient.SkillResponse] = []

    private var installedNames: Set<String> {
        Set(installed.map(\.name))
    }
    private var notInstalled: [GatewayClient.SkillResponse] {
        allAvailable.filter { !installedNames.contains($0.name) }
    }

    var body: some View {
        HStack(alignment: .top, spacing: 0) {
            // Left: Installed
            VStack(alignment: .leading, spacing: 4) {
                Text("Installed (\(installed.count))")
                    .font(.system(size: 11, weight: .semibold))
                    .foregroundStyle(VultiTheme.inkMuted)
                ForEach(installed.prefix(5), id: \.name) { skill in
                    HStack {
                        Text(skill.name)
                            .font(.system(size: 11))
                        Spacer()
                        Image(systemName: "checkmark")
                            .font(.system(size: 9))
                            .foregroundStyle(.green)
                    }
                    .padding(.vertical, 1)
                }
                if installed.count > 5 {
                    Text("+\(installed.count - 5) more")
                        .font(.system(size: 10))
                        .foregroundStyle(VultiTheme.inkMuted)
                }
                if installed.isEmpty {
                    Text("None")
                        .font(.system(size: 11))
                        .foregroundStyle(VultiTheme.inkDim)
                }
            }
            .frame(maxWidth: .infinity, alignment: .topLeading)

            Rectangle()
                .fill(VultiTheme.border)
                .frame(width: 1)
                .padding(.horizontal, 8)

            // Right: Available
            VStack(alignment: .leading, spacing: 4) {
                Text("Available (\(notInstalled.count))")
                    .font(.system(size: 11, weight: .semibold))
                    .foregroundStyle(VultiTheme.inkMuted)
                ForEach(notInstalled.prefix(5), id: \.name) { skill in
                    Text(skill.name)
                        .font(.system(size: 11))
                        .foregroundStyle(VultiTheme.inkDim)
                        .padding(.vertical, 1)
                }
                if notInstalled.count > 5 {
                    Text("+\(notInstalled.count - 5) more")
                        .font(.system(size: 10))
                        .foregroundStyle(VultiTheme.inkMuted)
                }
            }
            .frame(maxWidth: .infinity, alignment: .topLeading)
        }
        .task(id: tick) {
            installed = (try? await app.client.listAgentSkills(agentId: agentId)) ?? []
            allAvailable = (try? await app.client.listAvailableSkills()) ?? []
        }
    }
}

/// Live profile widget — fetches agent metadata + soul/user/memory status from API.
struct LiveProfileWidget: View {
    let agentId: String
    var tick: Int = 0
    var onDrill: ((DrillTarget) -> Void)?
    @Environment(AppState.self) private var app
    @State private var hasSoul = false
    @State private var userCount = 0
    @State private var memoryCount = 0

    private var agent: GatewayClient.AgentResponse? {
        app.agent(byId: agentId)
    }

    var body: some View {
        VStack(spacing: 14) {
            HStack(spacing: 12) {
                if let agent {
                    AgentAvatar(agent: agent, size: 44)
                } else {
                    RoundedRectangle(cornerRadius: 8)
                        .fill(VultiTheme.paperWarm)
                        .frame(width: 44, height: 44)
                        .overlay(Text(String(agentId.prefix(1)).uppercased())
                            .font(.system(size: 18, weight: .semibold))
                            .foregroundStyle(VultiTheme.inkDim))
                }
                VStack(alignment: .leading, spacing: 2) {
                    Text(agent?.name ?? agentId)
                        .font(.system(size: 16, weight: .semibold))
                        .foregroundStyle(VultiTheme.inkSoft)
                    if let role = agent?.role, !role.isEmpty {
                        Text(role)
                            .font(.system(size: 12))
                            .foregroundStyle(VultiTheme.inkMuted)
                    }
                }
                Spacer()
            }

            HStack(spacing: 0) {
                drillLink("Soul", icon: "sparkles", hasContent: hasSoul, target: .soul)
                Divider().frame(height: 20).padding(.horizontal, 8)
                drillLink("User", icon: "person", count: userCount, target: .user)
                Divider().frame(height: 20).padding(.horizontal, 8)
                drillLink("Memories", icon: "brain", count: memoryCount, target: .memories)
                Spacer()
            }
        }
        .task(id: tick) {
            await app.refreshAgents()
            if let soul = try? await app.client.getSoul(agentId: agentId) {
                hasSoul = !soul.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
            }
            if let mem = try? await app.client.getMemories(agentId: agentId) {
                let userRaw = mem.user.trimmingCharacters(in: .whitespacesAndNewlines)
                userCount = userRaw.isEmpty ? 0 : userRaw.components(separatedBy: "\u{00A7}").filter { !$0.trimmingCharacters(in: .whitespaces).isEmpty }.count
                let memRaw = mem.memory.trimmingCharacters(in: .whitespacesAndNewlines)
                memoryCount = memRaw.isEmpty ? 0 : memRaw.components(separatedBy: "\u{00A7}").filter { !$0.trimmingCharacters(in: .whitespaces).isEmpty }.count
            }
        }
    }

    private func drillLink(_ title: String, icon: String, hasContent: Bool, target: DrillTarget) -> some View {
        drillLink(title, icon: icon, count: hasContent ? nil : 0, target: target)
    }

    private func drillLink(_ title: String, icon: String, count: Int?, target: DrillTarget) -> some View {
        Button {
            onDrill?(target)
        } label: {
            HStack(spacing: 4) {
                Image(systemName: icon)
                    .font(.system(size: 11))
                Text(title)
                    .font(.system(size: 12, weight: .medium))
                if let c = count, c > 0 {
                    Text("(\(c))")
                        .font(.system(size: 11))
                        .foregroundStyle(VultiTheme.inkDim)
                } else if count == 0 {
                    Circle()
                        .fill(VultiTheme.inkMuted.opacity(0.3))
                        .frame(width: 5, height: 5)
                }
                Image(systemName: "chevron.right")
                    .font(.system(size: 9))
                    .foregroundStyle(VultiTheme.inkMuted)
            }
            .foregroundStyle(VultiTheme.primary)
        }
        .buttonStyle(.plain)
    }
}

/// Live wallet widget — fetches card from creditcard.json API, vault from CLI-backed API.
struct LiveWalletWidget: View {
    let agentId: String
    var tick: Int = 0
    @Environment(AppState.self) private var app
    @State private var cardName: String?
    @State private var cardLast4: String?
    @State private var cardExpiry: String?
    @State private var vaultId: String?
    @State private var vaultName: String?
    @State private var portfolioValue: String?
    @State private var chainCount: Int = 0
    @State private var loaded = false

    private var hasCard: Bool { cardLast4 != nil && !(cardLast4?.isEmpty ?? true) }
    private var hasVault: Bool { vaultName != nil && !(vaultName?.isEmpty ?? true) }

    var body: some View {
        Group {
            if !loaded {
                ProgressView()
                    .frame(maxWidth: .infinity, minHeight: 40)
            } else if hasCard && hasVault {
                HStack(alignment: .top, spacing: 12) {
                    CreditCardVisual(name: cardName ?? "", last4: cardLast4 ?? "", expiry: cardExpiry ?? "")
                        .frame(maxWidth: .infinity)
                    VaultVisual(name: vaultName ?? "Vault", vaultId: vaultId ?? "", portfolioValue: portfolioValue, chainCount: chainCount)
                        .frame(maxWidth: .infinity)
                }
            } else if hasCard {
                CreditCardVisual(name: cardName ?? "", last4: cardLast4 ?? "", expiry: cardExpiry ?? "")
            } else if hasVault {
                VaultVisual(name: vaultName ?? "Vault", vaultId: vaultId ?? "", portfolioValue: portfolioValue, chainCount: chainCount)
            } else {
                HStack {
                    Image(systemName: "creditcard")
                        .font(.system(size: 20))
                        .foregroundStyle(VultiTheme.inkMuted.opacity(0.4))
                    Text("No card or vault set up")
                        .font(.system(size: 12))
                        .foregroundStyle(VultiTheme.inkDim)
                    Spacer()
                }
            }
        }
        .task(id: tick) {
            // Fetch credit card
            if let wallet = try? await app.client.getWallet(agentId: agentId) {
                if let cc = wallet["credit_card"]?.value as? [String: Any] {
                    cardName = cc["name"] as? String ?? cc["cardholder_name"] as? String
                    if let num = cc["number"] as? String, num.count >= 4 {
                        cardLast4 = String(num.suffix(4))
                    }
                    cardExpiry = cc["expiry"] as? String
                }
            }
            // Fetch vault
            do {
                let vault = try await app.client.getVault(agentId: agentId)
                print("[LiveWallet] vault for \(agentId): name=\(vault.name ?? "nil") id=\(vault.vaultId ?? "nil")")
                if let name = vault.name, !name.isEmpty {
                    vaultId = vault.vaultId
                    vaultName = name
                    chainCount = vault.chains ?? 0
                    if let portfolio = try? await app.client.getVaultPortfolio(agentId: agentId) {
                        portfolioValue = portfolio.data?.portfolio?.totalValue?.amount
                    }
                } else {
                    vaultId = nil
                    vaultName = nil
                    portfolioValue = nil
                    chainCount = 0
                }
            } catch {
                print("[LiveWallet] vault fetch failed for \(agentId): \(error)")
                vaultId = nil
                vaultName = nil
                portfolioValue = nil
                chainCount = 0
            }
            loaded = true
        }
    }
}

/// Compact stat for half-width analytics widget
private struct CompactStat: View {
    let label: String
    let value: String
    var body: some View {
        VStack(spacing: 2) {
            Text(value)
                .font(.system(size: 14, weight: .bold))
                .foregroundStyle(VultiTheme.inkSoft)
            Text(label)
                .font(.system(size: 9))
                .foregroundStyle(VultiTheme.inkDim)
        }
        .frame(maxWidth: .infinity)
        .padding(.vertical, 6)
        .background(VultiTheme.paperDeep, in: RoundedRectangle(cornerRadius: 8))
    }
}

struct StatGridWidgetContent: View {
    let data: WidgetData
    var body: some View {
        let stats = data.stats ?? []
        LazyVGrid(columns: Array(repeating: GridItem(.flexible()), count: min(stats.count, 4)), spacing: 12) {
            ForEach(stats) { stat in
                VStack(spacing: 4) {
                    Text(stat.value)
                        .font(.system(size: 18, weight: .bold))
                    if let unit = stat.unit {
                        Text(unit)
                            .font(.system(size: 10))
                            .foregroundStyle(VultiTheme.inkDim)
                    }
                    Text(stat.label)
                        .font(.system(size: 10))
                        .foregroundStyle(VultiTheme.inkDim)
                }
                .padding(12)
                .frame(maxWidth: .infinity)
                .background(VultiTheme.paperDeep, in: RoundedRectangle(cornerRadius: 12))
            }
        }
    }
}

struct BarChartWidgetContent: View {
    let data: WidgetData
    var body: some View {
        let items = data.items ?? []
        let maxVal = items.map { $0.max ?? $0.value }.max() ?? 1

        VStack(spacing: 6) {
            ForEach(items) { item in
                HStack(spacing: 8) {
                    Text(item.label)
                        .font(.system(size: 11))
                        .frame(width: 60, alignment: .trailing)
                    GeometryReader { geo in
                        RoundedRectangle(cornerRadius: 3)
                            .fill(.tint)
                            .frame(width: geo.size.width * (item.value / maxVal))
                    }
                    .frame(height: 16)
                }
            }
        }
    }
}

struct ProgressWidgetContent: View {
    let data: WidgetData

    var color: Color {
        switch data.variant {
        case "success": .green
        case "warning": .yellow
        case "error": .red
        default: .blue
        }
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            if let label = data.label {
                HStack {
                    Text(label).font(.system(size: 12))
                    Spacer()
                    if let pct = data.percent, data.indeterminate != true {
                        Text("\(Int(pct))%").font(.system(size: 11)).foregroundStyle(VultiTheme.inkDim)
                    }
                }
            }
            GeometryReader { geo in
                ZStack(alignment: .leading) {
                    RoundedRectangle(cornerRadius: 4)
                        .fill(VultiTheme.paperDeep)
                    RoundedRectangle(cornerRadius: 4)
                        .fill(color)
                        .frame(width: geo.size.width * ((data.percent ?? 0) / 100))
                }
            }
            .frame(height: 8)
        }
    }
}

struct ButtonWidgetContent: View {
    let data: WidgetData
    var onSend: ((String) -> Void)?

    var body: some View {
        Button(data.label ?? "Action") {
            if let msg = data.message { onSend?(msg) }
        }
        .buttonStyle(.vultiPrimary)
    }
}

struct FormWidgetContent: View {
    let data: WidgetData
    var onSend: ((String) -> Void)?
    @State private var values: [String: String] = [:]

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            ForEach(data.fields ?? []) { field in
                VStack(alignment: .leading, spacing: 2) {
                    if let label = field.label {
                        Text(label).font(.system(size: 11)).foregroundStyle(VultiTheme.inkDim)
                    }
                    TextField(field.placeholder ?? "", text: Binding(
                        get: { values[field.name] ?? "" },
                        set: { values[field.name] = $0 }
                    ))
                    .textFieldStyle(.vulti)
                }
            }
            Button(data.submitLabel ?? "Submit") {
                var msg = data.messageTemplate ?? ""
                for (key, val) in values {
                    msg = msg.replacingOccurrences(of: "{\(key)}", with: val)
                }
                onSend?(msg)
                values.removeAll()
            }
            .buttonStyle(.vultiPrimary)
        }
    }
}

struct ToggleListWidgetContent: View {
    let data: WidgetData
    var onSend: ((String) -> Void)?
    @State private var states: [String: Bool] = [:]

    var body: some View {
        VStack(spacing: 8) {
            ForEach(data.toggleItems ?? []) { item in
                Toggle(isOn: Binding(
                    get: { states[item.id] ?? item.enabled },
                    set: { newVal in
                        states[item.id] = newVal
                        if let template = data.onToggleMessage {
                            let msg = template
                                .replacingOccurrences(of: "{id}", with: item.id)
                                .replacingOccurrences(of: "{state}", with: newVal ? "on" : "off")
                            onSend?(msg)
                        }
                    }
                )) {
                    VStack(alignment: .leading, spacing: 2) {
                        Text(item.label).font(.system(size: 12))
                        if let desc = item.description {
                            Text(desc).font(.system(size: 10)).foregroundStyle(VultiTheme.inkDim)
                        }
                    }
                }
                .toggleStyle(.checkbox)
            }
        }
    }
}

struct ActionListWidgetContent: View {
    let data: WidgetData
    var onSend: ((String) -> Void)?

    var body: some View {
        VStack(spacing: 8) {
            ForEach(data.actionItems ?? []) { item in
                HStack {
                    Circle()
                        .fill(statusColor(item.status))
                        .frame(width: 8, height: 8)
                    VStack(alignment: .leading, spacing: 2) {
                        Text(item.title).font(.system(size: 12, weight: .medium))
                        if let sub = item.subtitle {
                            Text(sub).font(.system(size: 10)).foregroundStyle(VultiTheme.inkDim).lineLimit(1)
                        }
                    }
                    Spacer()
                    ForEach(item.actions ?? []) { action in
                        Button(action.label) {
                            let msg = action.message.replacingOccurrences(of: "{id}", with: item.id)
                            onSend?(msg)
                        }
                        .font(.system(size: 11))
                        .buttonStyle(.bordered)
                    }
                }
            }
        }
    }

    private func statusColor(_ status: String?) -> Color {
        switch status {
        case "active": .green
        case "paused": .yellow
        case "error": .red
        default: .secondary
        }
    }
}
