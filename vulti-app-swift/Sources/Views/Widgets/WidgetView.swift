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
        }
    }
}

// MARK: - Widget implementations

struct MarkdownWidgetContent: View {
    let data: WidgetData
    var body: some View {
        Text(data.content ?? "")
            .font(.system(size: 13))
            .textSelection(.enabled)
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
