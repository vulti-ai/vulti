import SwiftUI

/// Renders chat message content with markdown support.
/// Splits on fenced code blocks (```), renders inline markdown via AttributedString,
/// and renders code blocks with monospace font on a dark background.
struct MarkdownMessageView: View {
    let content: String
    let isUser: Bool

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            ForEach(Array(segments.enumerated()), id: \.offset) { _, segment in
                switch segment {
                case .text(let text):
                    // Split text into sub-segments: plain text and tables
                    ForEach(Array(splitTables(text).enumerated()), id: \.offset) { _, sub in
                        switch sub {
                        case .text(let t): inlineMarkdown(t)
                        case .table(let h, let r): tableView(header: h, rows: r)
                        default: EmptyView()
                        }
                    }
                case .codeBlock(let language, let code):
                    codeBlockView(language: language, code: code)
                case .table(let header, let rows):
                    tableView(header: header, rows: rows)
                }
            }
        }
    }

    // MARK: - Inline markdown

    @ViewBuilder
    private func inlineMarkdown(_ text: String) -> some View {
        let trimmed = text.trimmingCharacters(in: .whitespacesAndNewlines)
        if !trimmed.isEmpty {
            if let attributed = try? AttributedString(
                markdown: trimmed,
                options: .init(interpretedSyntax: .inlineOnlyPreservingWhitespace)
            ) {
                Text(attributed)
                    .font(.system(size: 13))
                    .foregroundStyle(isUser ? .white : VultiTheme.inkSoft)
                    .tint(isUser ? .white : .blue)
                    .textSelection(.enabled)
                    .fixedSize(horizontal: false, vertical: true)
            } else {
                // Fallback to plain text if markdown parsing fails
                Text(trimmed)
                    .font(.system(size: 13))
                    .foregroundStyle(isUser ? .white : VultiTheme.inkSoft)
                    .textSelection(.enabled)
            }
        }
    }

    // MARK: - Code block

    @ViewBuilder
    private func codeBlockView(language: String?, code: String) -> some View {
        VStack(alignment: .leading, spacing: 0) {
            if let lang = language, !lang.isEmpty {
                Text(lang)
                    .font(.system(size: 10, weight: .medium, design: .monospaced))
                    .foregroundStyle(VultiTheme.inkDim)
                    .padding(.horizontal, 10)
                    .padding(.top, 8)
                    .padding(.bottom, 4)
            }

            ScrollView(.horizontal, showsIndicators: true) {
                Text(code)
                    .font(.system(size: 12, design: .monospaced))
                    .foregroundStyle(VultiTheme.inkSoft)
                    .textSelection(.enabled)
                    .padding(.horizontal, 10)
                    .padding(.vertical, language != nil && !language!.isEmpty ? 4 : 10)
                    .padding(.bottom, 4)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(
            RoundedRectangle(cornerRadius: 8)
                .fill(VultiTheme.paperWarm.opacity(0.6))
                .overlay(
                    RoundedRectangle(cornerRadius: 8)
                        .stroke(VultiTheme.border, lineWidth: 0.5)
                )
        )
    }

    // MARK: - Table

    @ViewBuilder
    private func tableView(header: [String], rows: [[String]]) -> some View {
        VStack(alignment: .leading, spacing: 0) {
            // Header row
            HStack(spacing: 0) {
                ForEach(Array(header.enumerated()), id: \.offset) { _, col in
                    Text(col)
                        .font(.system(size: 11, weight: .semibold))
                        .foregroundStyle(isUser ? .white.opacity(0.9) : VultiTheme.inkSoft)
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .padding(.horizontal, 8)
                        .padding(.vertical, 6)
                }
            }
            .background(isUser ? Color.white.opacity(0.1) : VultiTheme.paperDeep.opacity(0.5))

            // Separator
            Rectangle()
                .fill(isUser ? Color.white.opacity(0.2) : VultiTheme.border)
                .frame(height: 1)

            // Data rows
            ForEach(Array(rows.enumerated()), id: \.offset) { rowIdx, row in
                HStack(spacing: 0) {
                    ForEach(Array(row.enumerated()), id: \.offset) { _, cell in
                        Text(cell)
                            .font(.system(size: 11))
                            .foregroundStyle(isUser ? .white.opacity(0.85) : VultiTheme.inkSoft)
                            .frame(maxWidth: .infinity, alignment: .leading)
                            .padding(.horizontal, 8)
                            .padding(.vertical, 4)
                    }
                }
                if rowIdx < rows.count - 1 {
                    Rectangle()
                        .fill(isUser ? Color.white.opacity(0.1) : VultiTheme.border.opacity(0.5))
                        .frame(height: 0.5)
                }
            }
        }
        .clipShape(RoundedRectangle(cornerRadius: 6))
        .overlay(RoundedRectangle(cornerRadius: 6).stroke(isUser ? Color.white.opacity(0.2) : VultiTheme.border))
        .textSelection(.enabled)
    }

    // MARK: - Parsing

    private enum Segment {
        case text(String)
        case codeBlock(language: String?, code: String)
        case table(header: [String], rows: [[String]])
    }

    /// Parse markdown tables from a text block, returning a mix of text and table segments.
    private func splitTables(_ text: String) -> [Segment] {
        let lines = text.components(separatedBy: "\n")
        var result: [Segment] = []
        var textBuffer: [String] = []
        var i = 0

        func flushText() {
            let joined = textBuffer.joined(separator: "\n")
            if !joined.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
                result.append(.text(joined))
            }
            textBuffer.removeAll()
        }

        while i < lines.count {
            let line = lines[i]
            // Detect table: line with pipes, followed by separator line (|---|---|)
            if line.contains("|") && i + 1 < lines.count {
                let nextLine = lines[i + 1]
                let isSeparator = nextLine.contains("|") &&
                    nextLine.replacingOccurrences(of: "|", with: "")
                           .replacingOccurrences(of: "-", with: "")
                           .replacingOccurrences(of: ":", with: "")
                           .replacingOccurrences(of: " ", with: "")
                           .isEmpty

                if isSeparator {
                    flushText()
                    // Parse header
                    let header = parseTableRow(line)
                    // Skip separator
                    i += 2
                    // Parse data rows
                    var rows: [[String]] = []
                    while i < lines.count && lines[i].contains("|") {
                        let row = parseTableRow(lines[i])
                        if !row.isEmpty { rows.append(row) }
                        i += 1
                    }
                    if !header.isEmpty {
                        result.append(.table(header: header, rows: rows))
                    }
                    continue
                }
            }
            textBuffer.append(line)
            i += 1
        }
        flushText()

        if result.isEmpty {
            result.append(.text(text))
        }
        return result
    }

    private func parseTableRow(_ line: String) -> [String] {
        line.split(separator: "|", omittingEmptySubsequences: false)
            .map { $0.trimmingCharacters(in: .whitespaces) }
            .filter { !$0.isEmpty }
    }

    /// Split content on ``` fenced code block delimiters.
    private var segments: [Segment] {
        let delimiter = "```"
        var result: [Segment] = []
        var remaining = content

        while let openRange = remaining.range(of: delimiter) {
            // Text before the opening ```
            let before = String(remaining[remaining.startIndex..<openRange.lowerBound])
            if !before.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
                result.append(.text(before))
            }

            // After the opening ```
            var afterOpen = String(remaining[openRange.upperBound...])

            // Extract optional language identifier (first line after ```)
            var language: String?
            if let newline = afterOpen.firstIndex(of: "\n") {
                let firstLine = String(afterOpen[afterOpen.startIndex..<newline])
                    .trimmingCharacters(in: .whitespaces)
                if !firstLine.isEmpty && !firstLine.contains(" ") && firstLine.count < 20 {
                    language = firstLine
                    afterOpen = String(afterOpen[afterOpen.index(after: newline)...])
                }
            }

            // Find closing ```
            if let closeRange = afterOpen.range(of: delimiter) {
                let code = String(afterOpen[afterOpen.startIndex..<closeRange.lowerBound])
                result.append(.codeBlock(
                    language: language,
                    code: code.hasSuffix("\n")
                        ? String(code.dropLast())
                        : code
                ))
                remaining = String(afterOpen[closeRange.upperBound...])
            } else {
                // No closing ``` found — treat rest as code block
                let code = afterOpen
                result.append(.codeBlock(
                    language: language,
                    code: code.hasSuffix("\n")
                        ? String(code.dropLast())
                        : code
                ))
                remaining = ""
            }
        }

        // Any remaining text after last code block
        if !remaining.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
            result.append(.text(remaining))
        }

        // If no segments were produced, return the whole content as text
        if result.isEmpty {
            result.append(.text(content))
        }

        return result
    }
}
