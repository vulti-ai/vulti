import Foundation

/// Pane widget types matching DynamicPane.svelte
enum WidgetType: String, Codable {
    case markdown
    case kv
    case table
    case image
    case status
    case statGrid = "stat_grid"
    case barChart = "bar_chart"
    case progress
    case button
    case form
    case toggleList = "toggle_list"
    case actionList = "action_list"
    case empty
}

struct PaneWidget: Identifiable, Codable {
    var id: String = UUID().uuidString
    var type: WidgetType
    var title: String?
    var data: WidgetData

    enum CodingKeys: String, CodingKey {
        case id, type, title, data
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        self.id = (try? c.decode(String.self, forKey: .id)) ?? UUID().uuidString
        self.type = try c.decode(WidgetType.self, forKey: .type)
        self.title = try? c.decode(String.self, forKey: .title)
        self.data = try c.decode(WidgetData.self, forKey: .data)
    }

    init(type: WidgetType, title: String? = nil, data: WidgetData) {
        self.type = type
        self.title = title
        self.data = data
    }
}

struct WidgetData: Codable {
    // markdown
    var content: String?

    // kv
    var entries: [KvEntry]?

    // table
    var columns: [String]?
    var rows: [[String]]?

    // image
    var src: String?
    var alt: String?
    var width: Int?
    var height: Int?

    // status
    var label: String?
    var variant: String?  // "success", "warning", "error", "info"
    var detail: String?

    // stat_grid
    var stats: [StatEntry]?

    // bar_chart
    var orientation: String?  // "vertical" or "horizontal"
    var items: [BarItem]?

    // progress
    var percent: Double?
    var indeterminate: Bool?

    // button
    var message: String?

    // form
    var fields: [FormField]?
    var submitLabel: String?
    var messageTemplate: String?

    // toggle_list — backend sends as "items", same key as bar_chart
    var toggleItems: [ToggleItem]?
    var onToggleMessage: String?

    // action_list — backend sends as "items", same key as bar_chart
    var actionItems: [ActionItem]?

    // drill-down: if set, widget shows chevron and taps drill into a known detail view
    // Values: "role", "soul", "user", "memories", "connections", "skills", "actions", "wallet", "analytics"
    var drill: String?

    // layout size: "small" (1/3), "medium" (2/3), "large" (full width, default)
    var size: String?

    enum CodingKeys: String, CodingKey {
        case content, entries, columns, rows, src, alt, width, height
        case label, variant, detail, stats, orientation, items
        case percent, indeterminate, message, fields, drill, size
        case submitLabel = "submit_label"
        case messageTemplate = "message_template"
        case onToggleMessage = "on_toggle_message"
        // toggleItems and actionItems are decoded manually from "items"
    }

    init() {}

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        content = try? c.decode(String.self, forKey: .content)
        entries = try? c.decode([KvEntry].self, forKey: .entries)
        columns = try? c.decode([String].self, forKey: .columns)
        rows = try? c.decode([[String]].self, forKey: .rows)
        src = try? c.decode(String.self, forKey: .src)
        alt = try? c.decode(String.self, forKey: .alt)
        width = try? c.decode(Int.self, forKey: .width)
        height = try? c.decode(Int.self, forKey: .height)
        label = try? c.decode(String.self, forKey: .label)
        variant = try? c.decode(String.self, forKey: .variant)
        detail = try? c.decode(String.self, forKey: .detail)
        stats = try? c.decode([StatEntry].self, forKey: .stats)
        orientation = try? c.decode(String.self, forKey: .orientation)
        percent = try? c.decode(Double.self, forKey: .percent)
        indeterminate = try? c.decode(Bool.self, forKey: .indeterminate)
        message = try? c.decode(String.self, forKey: .message)
        fields = try? c.decode([FormField].self, forKey: .fields)
        submitLabel = try? c.decode(String.self, forKey: .submitLabel)
        messageTemplate = try? c.decode(String.self, forKey: .messageTemplate)
        onToggleMessage = try? c.decode(String.self, forKey: .onToggleMessage)
        drill = try? c.decode(String.self, forKey: .drill)
        size = try? c.decode(String.self, forKey: .size)

        // "items" is polymorphic: bar_chart uses [BarItem], toggle_list uses [ToggleItem],
        // action_list uses [ActionItem]. Try each in order.
        if let barItems = try? c.decode([BarItem].self, forKey: .items) {
            items = barItems
        }
        if let toggles = try? c.decode([ToggleItem].self, forKey: .items) {
            toggleItems = toggles
        }
        if let actions = try? c.decode([ActionItem].self, forKey: .items) {
            actionItems = actions
        }
    }
}

struct KvEntry: Codable, Identifiable {
    var id: String { key }
    var key: String
    var value: String
    var mono: Bool?
    var masked: Bool?
}

struct StatEntry: Codable, Identifiable {
    var id: String { label }
    var label: String
    var value: String
    var unit: String?
}

struct BarItem: Codable, Identifiable {
    var id: String { label }
    var label: String
    var value: Double
    var max: Double?
}

struct FormField: Codable, Identifiable {
    var id: String { name }
    var name: String
    var label: String?
    var type: String?
    var placeholder: String?
}

struct ToggleItem: Codable, Identifiable {
    var id: String
    var label: String
    var description: String?
    var enabled: Bool
    var tags: [String]?
}

struct ActionItem: Codable, Identifiable {
    var id: String
    var title: String
    var subtitle: String?
    var status: String?
    var actions: [ActionButton]?
}

struct ActionButton: Codable, Identifiable {
    var id: String { label }
    var label: String
    var message: String
    var variant: String?
}
