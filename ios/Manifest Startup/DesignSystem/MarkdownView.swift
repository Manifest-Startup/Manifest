import SwiftUI

/// Block-level Markdown for generated documents (headings, lists, quotes, code,
/// tables, rules). Parsing happens off the main thread once per document, and
/// blocks render lazily, so a 20-page patent draft scrolls smoothly.
nonisolated enum MarkdownBlock: Hashable, Sendable {
    case heading(level: Int, text: AttributedString)
    case paragraph(AttributedString)
    case bullet(depth: Int, marker: String, text: AttributedString)
    case quote(AttributedString)
    case code(String)
    case table(header: [AttributedString], rows: [[AttributedString]])
    case rule

    static func parse(_ markdown: String) -> [MarkdownBlock] {
        var blocks: [MarkdownBlock] = []
        var paragraph: [String] = []
        var code: [String]?
        var table: [[String]] = []

        func inline(_ text: String) -> AttributedString {
            let options = AttributedString.MarkdownParsingOptions(
                interpretedSyntax: .inlineOnlyPreservingWhitespace, failurePolicy: .returnPartiallyParsedIfPossible)
            return (try? AttributedString(markdown: text, options: options)) ?? AttributedString(text)
        }
        func flushParagraph() {
            guard !paragraph.isEmpty else { return }
            blocks.append(.paragraph(inline(paragraph.joined(separator: " "))))
            paragraph.removeAll()
        }
        func cells(_ line: String) -> [String] {
            var trimmed = line.trimmingCharacters(in: .whitespaces)
            if trimmed.hasPrefix("|") { trimmed.removeFirst() }
            if trimmed.hasSuffix("|") { trimmed.removeLast() }
            return trimmed.components(separatedBy: "|").map { $0.trimmingCharacters(in: .whitespaces) }
        }
        func flushTable() {
            guard !table.isEmpty else { return }
            let rows = table.filter { row in !row.allSatisfy { $0.allSatisfy { "-: ".contains($0) } } }
            if let header = rows.first {
                blocks.append(.table(header: header.map(inline), rows: rows.dropFirst().map { $0.map(inline) }))
            }
            table.removeAll()
        }

        for rawLine in markdown.components(separatedBy: .newlines) {
            let line = rawLine.trimmingCharacters(in: .whitespaces)
            if line.hasPrefix("```") {
                if let lines = code {
                    blocks.append(.code(lines.joined(separator: "\n")))
                    code = nil
                } else {
                    flushParagraph(); flushTable()
                    code = []
                }
                continue
            }
            if code != nil { code?.append(rawLine); continue }

            if line.hasPrefix("|") {
                flushParagraph()
                table.append(cells(line))
                continue
            } else {
                flushTable()
            }

            if line.isEmpty { flushParagraph(); continue }

            if let hashes = line.firstIndex(where: { $0 != "#" }), line.hasPrefix("#"),
                line[hashes] == " "
            {
                flushParagraph()
                let level = line.distance(from: line.startIndex, to: hashes)
                blocks.append(.heading(level: min(level, 4), text: inline(String(line[hashes...]).trimmingCharacters(in: .whitespaces))))
                continue
            }
            if line == "---" || line == "***" || line == "___" {
                flushParagraph(); blocks.append(.rule); continue
            }
            if line.hasPrefix(">") {
                flushParagraph()
                blocks.append(.quote(inline(String(line.dropFirst()).trimmingCharacters(in: .whitespaces))))
                continue
            }
            let indent = rawLine.prefix { $0 == " " || $0 == "\t" }.count / 2
            if let first = line.first, "-*+•".contains(first), line.dropFirst().first == " " {
                flushParagraph()
                blocks.append(.bullet(depth: min(indent, 3), marker: "•", text: inline(String(line.dropFirst(2)))))
                continue
            }
            if let dot = line.firstIndex(of: "."), line[..<dot].allSatisfy(\.isNumber), !line[..<dot].isEmpty,
                line[line.index(after: dot)...].hasPrefix(" ")
            {
                flushParagraph()
                let number = String(line[..<dot])
                let text = String(line[line.index(dot, offsetBy: 2)...])
                blocks.append(.bullet(depth: min(indent, 3), marker: "\(number).", text: inline(text)))
                continue
            }
            paragraph.append(line)
        }
        if let lines = code { blocks.append(.code(lines.joined(separator: "\n"))) }
        flushParagraph()
        flushTable()
        return blocks
    }
}

struct MarkdownView: View {
    let markdown: String
    @State private var blocks: [MarkdownBlock] = []

    var body: some View {
        LazyVStack(alignment: .leading, spacing: 12) {
            ForEach(Array(blocks.enumerated()), id: \.offset) { _, block in
                MarkdownBlockView(block: block)
            }
        }
        .textSelection(.enabled)
        .task(id: markdown) {
            let source = markdown
            blocks = await Task.detached(priority: .userInitiated) { MarkdownBlock.parse(source) }.value
        }
    }
}

private struct MarkdownBlockView: View {
    let block: MarkdownBlock

    var body: some View {
        switch block {
        case .heading(let level, let text):
            Text(text)
                .font(level == 1 ? .title.bold() : level == 2 ? .title2.bold() : level == 3 ? .title3.weight(.semibold) : .headline)
                .padding(.top, level <= 2 ? 14 : 6)
                .accessibilityAddTraits(.isHeader)
        case .paragraph(let text):
            Text(text)
                .font(.body)
                .lineSpacing(4)
                .foregroundStyle(.primary.opacity(0.92))
                .fixedSize(horizontal: false, vertical: true)
        case .bullet(let depth, let marker, let text):
            HStack(alignment: .firstTextBaseline, spacing: 10) {
                Text(marker)
                    .font(marker == "•" ? .body.weight(.bold) : .body.monospacedDigit())
                    .foregroundStyle(Theme.accent)
                    .frame(minWidth: 14, alignment: .trailing)
                Text(text).lineSpacing(3).fixedSize(horizontal: false, vertical: true)
            }
            .padding(.leading, CGFloat(depth) * 18)
        case .quote(let text):
            Text(text)
                .italic()
                .foregroundStyle(Theme.secondaryText)
                .padding(.leading, 14)
                .overlay(alignment: .leading) {
                    Capsule().fill(Theme.accent).frame(width: 3)
                }
        case .code(let code):
            ScrollView(.horizontal, showsIndicators: false) {
                Text(code)
                    .font(.system(.footnote, design: .monospaced))
                    .padding(14)
            }
            .background(Theme.background, in: .rect(cornerRadius: 12))
        case .table(let header, let rows):
            ScrollView(.horizontal, showsIndicators: false) {
                Grid(alignment: .leading, horizontalSpacing: 16, verticalSpacing: 10) {
                    GridRow {
                        ForEach(header.indices, id: \.self) { i in
                            Text(header[i]).font(.subheadline.weight(.semibold))
                        }
                    }
                    Divider()
                    ForEach(rows.indices, id: \.self) { r in
                        GridRow {
                            ForEach(rows[r].indices, id: \.self) { c in
                                Text(rows[r][c]).font(.subheadline).frame(maxWidth: 260, alignment: .leading)
                            }
                        }
                    }
                }
                .padding(14)
            }
            .background(Theme.background, in: .rect(cornerRadius: 12))
        case .rule:
            Divider().padding(.vertical, 8)
        }
    }
}
