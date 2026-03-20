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
                    inlineMarkdown(text)
                case .codeBlock(let language, let code):
                    codeBlockView(language: language, code: code)
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

    // MARK: - Parsing

    private enum Segment {
        case text(String)
        case codeBlock(language: String?, code: String)
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
