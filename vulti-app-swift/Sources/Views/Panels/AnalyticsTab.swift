import SwiftUI

/// Analytics tab with overview cards, model/platform/tool breakdown, activity chart.
/// Loads from gateway via GatewayClient.
struct AgentAnalyticsTab: View {
    let agentId: String
    @Environment(AppState.self) private var app
    @State private var days = 7
    @State private var analytics: AnalyticsData?
    @State private var isLoading = false

    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            HStack {
                Picker("Period", selection: $days) {
                    Text("7 days").tag(7)
                    Text("14 days").tag(14)
                    Text("30 days").tag(30)
                    Text("90 days").tag(90)
                }
                .pickerStyle(.menu)
                .onChange(of: days) { loadAnalytics() }
                Spacer()
            }

            if isLoading {
                ProgressView()
                    .frame(maxWidth: .infinity, minHeight: 100)
            } else if let data = analytics, !data.isEmpty {
                analyticsContent(data)
            } else {
                Text(analytics?.error ?? "No analytics data available")
                    .font(.system(size: 11)).foregroundStyle(VultiTheme.inkDim)
                    .frame(maxWidth: .infinity, minHeight: 100)
            }
        }
        .onAppear { loadAnalytics() }
    }

    @ViewBuilder
    private func analyticsContent(_ data: AnalyticsData) -> some View {
        // Overview cards (4-column grid)
        LazyVGrid(columns: Array(repeating: GridItem(.flexible()), count: 4), spacing: 12) {
            StatCard(label: "Sessions", value: "\(data.overview?.totalSessions ?? 0)")
            StatCard(label: "Messages", value: "\(data.overview?.totalMessages ?? 0)")
            StatCard(label: "Tokens", value: formatNumber(data.overview?.totalTokens ?? 0))
            StatCard(label: "Est. Cost", value: "$\(String(format: "%.2f", data.overview?.estimatedCost ?? 0))")
        }

        // Secondary stats (3-column)
        LazyVGrid(columns: Array(repeating: GridItem(.flexible()), count: 3), spacing: 12) {
            StatCard(label: "Tool Calls", value: "\(data.overview?.totalToolCalls ?? 0)")
            StatCard(label: "Avg Msgs/Session", value: String(format: "%.1f", data.overview?.avgMessagesPerSession ?? 0))
            StatCard(label: "Total Hours", value: String(format: "%.1fh", data.overview?.totalHours ?? 0))
        }

        // Models table
        if let models = data.models, !models.isEmpty {
            VStack(alignment: .leading, spacing: 8) {
                Text("MODELS").font(.system(size: 12, weight: .medium)).foregroundStyle(VultiTheme.inkMuted)
                ForEach(models, id: \.model) { m in
                    HStack {
                        Text(m.model).font(.system(size: 12, design: .monospaced))
                        Spacer()
                        Text("\(m.sessions) sessions").font(.system(size: 11)).foregroundStyle(VultiTheme.inkDim)
                        Text(formatNumber(m.totalTokens) + " tokens").font(.system(size: 11)).foregroundStyle(VultiTheme.inkDim)
                        Text("$\(String(format: "%.2f", m.cost))").font(.system(size: 11))
                    }
                    Divider()
                }
            }
        }

        // Platforms
        if let platforms = data.platforms, !platforms.isEmpty {
            VStack(alignment: .leading, spacing: 8) {
                Text("PLATFORMS").font(.system(size: 12, weight: .medium)).foregroundStyle(VultiTheme.inkMuted)
                LazyVGrid(columns: [GridItem(.flexible()), GridItem(.flexible()), GridItem(.flexible())], spacing: 8) {
                    ForEach(platforms, id: \.platform) { p in
                        VStack(alignment: .leading, spacing: 4) {
                            Text(p.platform.capitalized).font(.system(size: 12, weight: .medium))
                            Text("\(p.sessions) sessions / \(p.messages) msgs")
                                .font(.system(size: 10)).foregroundStyle(VultiTheme.inkDim)
                        }
                        .padding(10)
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .background(VultiTheme.paperDeep, in: RoundedRectangle(cornerRadius: 8))
                    }
                }
            }
        }

        // Top tools (bar chart)
        if let tools = data.tools, !tools.isEmpty {
            VStack(alignment: .leading, spacing: 8) {
                Text("TOP TOOLS").font(.system(size: 12, weight: .medium)).foregroundStyle(VultiTheme.inkMuted)
                let maxCalls = tools.map(\.callCount).max() ?? 1
                ForEach(tools, id: \.toolName) { t in
                    HStack(spacing: 8) {
                        Text(t.toolName).font(.system(size: 11, design: .monospaced)).frame(width: 120, alignment: .trailing)
                        GeometryReader { geo in
                            RoundedRectangle(cornerRadius: 3)
                                .fill(.tint)
                                .frame(width: max(4, geo.size.width * CGFloat(t.callCount) / CGFloat(maxCalls)))
                        }
                        .frame(height: 16)
                        Text("\(t.callCount)").font(.system(size: 10)).foregroundStyle(VultiTheme.inkDim)
                    }
                }
            }
        }

        // Weekly activity (day-of-week bar chart)
        if let activity = data.activity {
            let dayLabels = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"]
            let maxDaily = activity.daily.max() ?? 1

            VStack(alignment: .leading, spacing: 8) {
                Text("WEEKLY ACTIVITY").font(.system(size: 12, weight: .medium)).foregroundStyle(VultiTheme.inkMuted)

                HStack(alignment: .bottom, spacing: 6) {
                    ForEach(0..<7, id: \.self) { i in
                        let count = i < activity.daily.count ? activity.daily[i] : 0
                        VStack(spacing: 4) {
                            RoundedRectangle(cornerRadius: 3)
                                .fill(.tint)
                                .frame(height: max(4, CGFloat(count) / CGFloat(max(maxDaily, 1)) * 100))
                            Text(dayLabels[i])
                                .font(.system(size: 9))
                                .foregroundStyle(VultiTheme.inkDim)
                        }
                        .frame(maxWidth: .infinity)
                    }
                }
                .frame(height: 120)
                .padding(12)
                .background(VultiTheme.paperDeep, in: RoundedRectangle(cornerRadius: 12))
            }

            // Hourly activity
            let maxHourly = activity.hourly.max() ?? 1

            VStack(alignment: .leading, spacing: 8) {
                Text("HOURLY ACTIVITY").font(.system(size: 12, weight: .medium)).foregroundStyle(VultiTheme.inkMuted)

                HStack(alignment: .bottom, spacing: 1) {
                    ForEach(0..<24, id: \.self) { h in
                        let count = h < activity.hourly.count ? activity.hourly[h] : 0
                        VStack(spacing: 2) {
                            RoundedRectangle(cornerRadius: 2)
                                .fill(.tint.opacity(0.8))
                                .frame(height: max(2, CGFloat(count) / CGFloat(max(maxHourly, 1)) * 80))
                            if h % 6 == 0 {
                                Text("\(h)").font(.system(size: 8)).foregroundStyle(VultiTheme.inkMuted)
                            } else {
                                Text("").font(.system(size: 8))
                            }
                        }
                        .frame(maxWidth: .infinity)
                    }
                }
                .frame(height: 100)
                .padding(12)
                .background(VultiTheme.paperDeep, in: RoundedRectangle(cornerRadius: 12))
            }
        }
    }

    private func loadAnalytics() {
        isLoading = true
        Task {
            let result: AnalyticsData
            do {
                result = try await app.client.getAnalyticsData(days: days, agentId: agentId)
            } catch {
                result = AnalyticsData(empty: true, error: error.localizedDescription)
            }
            analytics = result
            isLoading = false
        }
    }

    private func formatNumber(_ n: Int) -> String {
        if n >= 1_000_000 { return String(format: "%.1fM", Double(n) / 1_000_000) }
        if n >= 1_000 { return String(format: "%.1fK", Double(n) / 1_000) }
        return "\(n)"
    }
}

struct StatCard: View {
    let label: String
    let value: String
    var body: some View {
        VStack(spacing: 4) {
            Text(value).font(.system(size: 24, weight: .bold))
            Text(label).font(.system(size: 12)).foregroundStyle(VultiTheme.inkDim)
        }
        .padding(16)
        .frame(maxWidth: .infinity)
        .background(VultiTheme.paperDeep, in: RoundedRectangle(cornerRadius: 12))
    }
}

// MARK: - Analytics data models (matches Rust AnalyticsResponse)

struct AnalyticsData: Codable {
    var empty: Bool?
    var error: String?
    var overview: AnalyticsOverview?
    var models: [ModelStats]?
    var platforms: [PlatformStats]?
    var tools: [ToolStats]?
    var activity: ActivityStats?
    var isEmpty: Bool { empty == true || (overview == nil && error == nil) }

    enum CodingKeys: String, CodingKey {
        case empty, error, overview, models, platforms, tools, activity
    }
}

struct AnalyticsOverview: Codable {
    var totalSessions: Int?
    var totalMessages: Int?
    var totalToolCalls: Int?
    var totalInputTokens: Int?
    var totalOutputTokens: Int?
    var totalTokens: Int?
    var estimatedCost: Double?
    var totalHours: Double?
    var avgMessagesPerSession: Double?
    var avgDuration: Double?

    enum CodingKeys: String, CodingKey {
        case totalSessions = "total_sessions"
        case totalMessages = "total_messages"
        case totalToolCalls = "total_tool_calls"
        case totalInputTokens = "total_input_tokens"
        case totalOutputTokens = "total_output_tokens"
        case totalTokens = "total_tokens"
        case estimatedCost = "estimated_cost"
        case totalHours = "total_hours"
        case avgMessagesPerSession = "avg_messages_per_session"
        case avgDuration = "avg_duration"
    }
}

struct ModelStats: Codable {
    var model: String
    var sessions: Int
    var totalTokens: Int
    var cost: Double
    enum CodingKeys: String, CodingKey {
        case model, sessions, cost
        case totalTokens = "total_tokens"
    }
}

struct PlatformStats: Codable {
    var platform: String
    var sessions: Int
    var messages: Int
    var totalTokens: Int
    enum CodingKeys: String, CodingKey {
        case platform, sessions, messages
        case totalTokens = "total_tokens"
    }
}

struct ToolStats: Codable {
    var toolName: String
    var callCount: Int
    var sessions: Int?
    var percentage: Double?
    enum CodingKeys: String, CodingKey {
        case toolName = "tool"
        case callCount = "count"
        case sessions, percentage
    }
}

struct ActivityStats: Codable {
    var byHour: [HourBucket]
    var byDay: [DayBucket]

    /// Flat counts indexed 0–23 (for chart rendering)
    var hourly: [Int] {
        var result = Array(repeating: 0, count: 24)
        for b in byHour { if b.hour >= 0 && b.hour < 24 { result[b.hour] = b.count } }
        return result
    }
    /// Flat counts indexed 0–6 Sun–Sat (for chart rendering)
    var daily: [Int] {
        let order = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"]
        var result = Array(repeating: 0, count: 7)
        for b in byDay {
            if let i = order.firstIndex(of: b.day) { result[i] = b.count }
        }
        return result
    }

    /// Convenience init from flat arrays (used by local AnalyticsStore).
    init(hourly: [Int], daily: [Int]) {
        let days = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"]
        self.byHour = hourly.enumerated().map { HourBucket(hour: $0.offset, count: $0.element) }
        self.byDay = daily.enumerated().map { DayBucket(day: days[$0.offset], count: $0.element) }
    }

    enum CodingKeys: String, CodingKey {
        case byHour = "by_hour"
        case byDay = "by_day"
    }
}

struct HourBucket: Codable {
    var hour: Int
    var count: Int
}

struct DayBucket: Codable {
    var day: String
    var count: Int
}
