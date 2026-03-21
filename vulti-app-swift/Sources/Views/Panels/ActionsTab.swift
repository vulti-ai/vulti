import SwiftUI

/// Actions tab: Cron Jobs + Rules (matches original with full CRUD).
struct AgentActionsTab: View {
    let agentId: String
    var initialSubtab: String = "Jobs"
    @State private var subtab = "Jobs"

    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            VultiPicker(options: ["Jobs", "Rules"], selection: $subtab)

            if subtab == "Jobs" {
                CronJobsView(agentId: agentId)
            } else {
                RulesListView(agentId: agentId)
            }
        }
        .onAppear { subtab = initialSubtab }
    }
}

// MARK: - Cron Jobs (full CRUD — matches CronView.svelte)

struct CronJobsView: View {
    let agentId: String
    @Environment(AppState.self) private var app
    @State private var jobs: [GatewayClient.CronResponse] = []
    @State private var showForm = false
    @State private var formName = ""
    @State private var formPrompt = ""
    @State private var formSchedule = ""

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            if showForm {
                VStack(alignment: .leading, spacing: 8) {
                    TextField("Name (optional)", text: $formName)
                        .textFieldStyle(.vulti)
                    TextEditor(text: $formPrompt)
                        .font(.system(size: 12))
                        .foregroundStyle(VultiTheme.inkSoft)
                        .frame(minHeight: 60)
                        .scrollContentBackground(.hidden)
                        .padding(4)
                        .background(VultiTheme.paperDeep, in: RoundedRectangle(cornerRadius: 6))
                        .overlay(
                            formPrompt.isEmpty
                                ? Text("Prompt (required)").font(.system(size: 12)).foregroundStyle(VultiTheme.inkMuted).padding(8)
                                : nil,
                            alignment: .topLeading
                        )
                    TextField("Schedule (e.g. 30m, 0 9 * * *)", text: $formSchedule)
                        .textFieldStyle(.vulti)
                    HStack {
                        Button("Cancel") { showForm = false; clearForm() }
                        Button("Create") {
                            Task {
                                if let job = try? await app.client.createCron(
                                    agentId: agentId, name: formName, prompt: formPrompt, schedule: formSchedule
                                ) {
                                    jobs.insert(job, at: 0)
                                    showForm = false; clearForm()
                                }
                            }
                        }
                        .buttonStyle(.vultiPrimary)
                        .disabled(formPrompt.isEmpty || formSchedule.isEmpty)
                    }
                }
                .padding(12)
                .background(VultiTheme.paperDeep.opacity(0.5), in: RoundedRectangle(cornerRadius: 8))
            } else {
                Button("New Job") { showForm = true }
                    .buttonStyle(.vultiSecondary)
            }

            ForEach(jobs) { job in
                CronJobRow(job: job, agentId: agentId) {
                    Task { await loadJobs() }
                }
            }

            if jobs.isEmpty && !showForm {
                Text("No cron jobs")
                    .font(.system(size: 11)).foregroundStyle(VultiTheme.inkDim)
                    .frame(maxWidth: .infinity)
            }
        }
        .task { await loadJobs() }
    }

    private func loadJobs() async {
        jobs = (try? await app.client.listCron(agentId: agentId)) ?? []
    }

    private func clearForm() { formName = ""; formPrompt = ""; formSchedule = "" }
}

struct CronJobRow: View {
    let job: GatewayClient.CronResponse
    let agentId: String
    let onUpdate: () -> Void
    @Environment(AppState.self) private var app

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack {
                Circle()
                    .fill(job.enabled ? .green : .yellow)
                    .frame(width: 8, height: 8)
                Text(job.name ?? "Untitled")
                    .font(.system(size: 13, weight: .medium))
                Spacer()
                Button(job.enabled ? "Pause" : "Resume") {
                    Task {
                        try? await app.client.updateCron(
                            jobId: job.id,
                            updates: ["status": job.enabled ? "paused" : "active"]
                        )
                        onUpdate()
                    }
                }
                .font(.system(size: 11))
                Button(role: .destructive) {
                    Task {
                        try? await app.client.deleteCron(jobId: job.id)
                        onUpdate()
                    }
                } label: {
                    Image(systemName: "trash").font(.system(size: 11))
                }
                .buttonStyle(.plain)
            }

            Text(job.prompt ?? "")
                .font(.system(size: 11))
                .foregroundStyle(VultiTheme.inkDim)
                .lineLimit(2)

            HStack(spacing: 12) {
                Label(job.schedule ?? "", systemImage: "clock")
                    .font(.system(size: 10))
                    .foregroundStyle(VultiTheme.inkMuted)
                if let lastRun = job.lastRun, !lastRun.isEmpty {
                    Label(formatTimestamp(lastRun), systemImage: "arrow.clockwise")
                        .font(.system(size: 10))
                        .foregroundStyle(VultiTheme.inkMuted)
                }
            }

            if let output = job.lastOutput, !output.isEmpty {
                Text(output)
                    .font(.system(size: 10, design: .monospaced))
                    .foregroundStyle(VultiTheme.inkDim)
                    .padding(8)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .background(VultiTheme.paperWarm.opacity(0.5), in: RoundedRectangle(cornerRadius: 6))
                    .lineLimit(4)
            }
        }
        .padding(10)
        .background(VultiTheme.paperDeep.opacity(0.3), in: RoundedRectangle(cornerRadius: 8))
    }

    private func formatTimestamp(_ ts: String) -> String {
        let formatter = ISO8601DateFormatter()
        formatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        let date = formatter.date(from: ts) ?? ISO8601DateFormatter().date(from: ts)
        guard let date else { return String(ts.prefix(16)) }
        let display = DateFormatter()
        if Calendar.current.isDateInToday(date) {
            display.dateFormat = "HH:mm"
        } else {
            display.dateFormat = "MMM d HH:mm"
        }
        return display.string(from: date)
    }
}

// MARK: - Rules (full CRUD — matches original)

struct RulesListView: View {
    let agentId: String
    @Environment(AppState.self) private var app
    @State private var rules: [GatewayClient.RuleResponse] = []
    @State private var showForm = false
    @State private var formName = ""
    @State private var formCondition = ""
    @State private var formAction = ""
    @State private var formPriority = 0
    @State private var formCooldown = ""

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            if showForm {
                VStack(alignment: .leading, spacing: 8) {
                    TextField("Name", text: $formName).textFieldStyle(.vulti)
                    TextField("IF (condition)", text: $formCondition).textFieldStyle(.vulti)
                    TextField("THEN (action)", text: $formAction).textFieldStyle(.vulti)
                    HStack {
                        Stepper("Priority: \(formPriority)", value: $formPriority)
                            .font(.system(size: 12))
                        TextField("Cooldown (min)", text: $formCooldown)
                            .textFieldStyle(.vulti)
                            .frame(width: 100)
                    }
                    HStack {
                        Button("Cancel") { showForm = false; clearForm() }
                        Button("Create") {
                            Task {
                                if let rule = try? await app.client.createRule(
                                    condition: formCondition, action: formAction,
                                    name: formName.isEmpty ? nil : formName,
                                    priority: formPriority,
                                    cooldownMinutes: Int(formCooldown),
                                    agentId: agentId
                                ) {
                                    rules.insert(rule, at: 0)
                                    showForm = false; clearForm()
                                }
                            }
                        }
                        .buttonStyle(.vultiPrimary)
                        .disabled(formCondition.isEmpty || formAction.isEmpty)
                    }
                }
                .padding(12)
                .background(VultiTheme.paperDeep.opacity(0.5), in: RoundedRectangle(cornerRadius: 8))
            } else {
                Button("+ New Rule") { showForm = true }
                    .buttonStyle(.vultiSecondary)
            }

            ForEach(rules) { rule in
                RuleRow(rule: rule) {
                    Task { await loadRules() }
                }
            }

            if rules.isEmpty && !showForm {
                Text("No rules")
                    .font(.system(size: 11)).foregroundStyle(VultiTheme.inkDim)
                    .frame(maxWidth: .infinity)
            }
        }
        .task { await loadRules() }
    }

    private func loadRules() async {
        rules = (try? await app.client.listRules(agentId: agentId)) ?? []
    }

    private func clearForm() {
        formName = ""; formCondition = ""; formAction = ""; formPriority = 0; formCooldown = ""
    }
}

struct RuleRow: View {
    let rule: GatewayClient.RuleResponse
    let onUpdate: () -> Void
    @Environment(AppState.self) private var app

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack {
                Circle().fill((rule.enabled ?? true) ? .green : .yellow).frame(width: 8, height: 8)
                Text(rule.name ?? "Untitled").font(.system(size: 13, weight: .medium))
                if let priority = rule.priority, priority != 0 {
                    Text("P\(priority)")
                        .font(.system(size: 9, weight: .bold))
                        .padding(.horizontal, 4).padding(.vertical, 1)
                        .background(VultiTheme.paperDeep, in: Capsule())
                }
                Spacer()
                Button((rule.enabled ?? true) ? "Disable" : "Enable") {
                    Task {
                        try? await app.client.updateRule(
                            ruleId: rule.id,
                            updates: ["enabled": (rule.enabled ?? true) ? "false" : "true"]
                        )
                        onUpdate()
                    }
                }
                .font(.system(size: 11))
                Button(role: .destructive) {
                    Task {
                        try? await app.client.deleteRule(ruleId: rule.id)
                        onUpdate()
                    }
                } label: {
                    Image(systemName: "trash").font(.system(size: 11))
                }
                .buttonStyle(.plain)
            }

            HStack(spacing: 4) {
                Text("IF").font(.system(size: 10, weight: .bold)).foregroundStyle(.tint)
                Text(rule.condition ?? "").font(.system(size: 11)).foregroundStyle(VultiTheme.inkDim)
            }
            HStack(spacing: 4) {
                Text("THEN").font(.system(size: 10, weight: .bold)).foregroundStyle(.green)
                Text(rule.action ?? "").font(.system(size: 11)).foregroundStyle(VultiTheme.inkDim)
            }

            HStack(spacing: 12) {
                Label("\(rule.triggerCount ?? 0) triggers", systemImage: "bolt")
                if let cd = rule.cooldownMinutes { Label("\(cd)m cooldown", systemImage: "timer") }
                if let last = rule.lastTriggeredAt {
                    Label(last, systemImage: "clock")
                }
            }
            .font(.system(size: 10))
            .foregroundStyle(VultiTheme.inkMuted)
        }
        .padding(10)
        .background(VultiTheme.paperDeep.opacity(0.3), in: RoundedRectangle(cornerRadius: 8))
    }
}
