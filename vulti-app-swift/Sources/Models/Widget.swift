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
    var id: String { title ?? UUID().uuidString }
    var type: WidgetType
    var title: String?
    var data: WidgetData

    enum CodingKeys: String, CodingKey {
        case type, title, data
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

    // toggle_list
    var toggleItems: [ToggleItem]?
    var onToggleMessage: String?

    // action_list
    var actionItems: [ActionItem]?

    enum CodingKeys: String, CodingKey {
        case content, entries, columns, rows, src, alt, width, height
        case label, variant, detail, stats, orientation, items
        case percent, indeterminate, message, fields
        case submitLabel = "submit_label"
        case messageTemplate = "message_template"
        case toggleItems = "toggle_items"
        case onToggleMessage = "on_toggle_message"
        case actionItems = "action_items"
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
