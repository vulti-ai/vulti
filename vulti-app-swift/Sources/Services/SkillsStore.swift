import Foundation

/// Manages global skills and per-agent skill installation.
/// Replaces Tauri's skills.rs commands.
final class SkillsStore {

    // MARK: - Global skills (matches list_available_skills)

    static func listAvailableSkills() -> [Skill] {
        findSkills(in: VultiHome.skillsDir, installed: false)
    }

    // MARK: - Agent skills (matches list_agent_skills)

    static func listAgentSkills(agentId: String) -> [Skill] {
        findSkills(in: VultiHome.agentSkillsDir(agentId), installed: true)
    }

    // MARK: - Install/remove (matches install_agent_skill, remove_agent_skill)

    static func installSkill(agentId: String, skillName: String) throws -> Skill {
        // Find skill in global dir
        guard let sourcePath = findSkillPath(name: skillName, in: VultiHome.skillsDir) else {
            throw SkillError.notFound(skillName)
        }

        let destDir = VultiHome.agentSkillsDir(agentId)
        try VultiHome.ensureDir(destDir)

        let dest = destDir.appending(path: skillName)
        guard !VultiHome.fileExists(dest) else {
            throw SkillError.alreadyInstalled(skillName)
        }

        // Symlink on Unix
        try FileManager.default.createSymbolicLink(at: dest, withDestinationURL: sourcePath)

        return Skill(name: skillName, installed: true, path: dest.path())
    }

    static func removeSkill(agentId: String, skillName: String) throws {
        let path = VultiHome.agentSkillsDir(agentId).appending(path: skillName)
        guard VultiHome.fileExists(path) else {
            throw SkillError.notInstalled(skillName)
        }
        try FileManager.default.removeItem(at: path)
    }

    // MARK: - Helpers

    private static func findSkills(in dir: URL, installed: Bool) -> [Skill] {
        guard let enumerator = FileManager.default.enumerator(
            at: dir, includingPropertiesForKeys: nil,
            options: [.skipsHiddenFiles]
        ) else { return [] }

        var skills: [Skill] = []
        while let url = enumerator.nextObject() as? URL {
            guard url.lastPathComponent == "SKILL.md" else { continue }
            let content = VultiHome.readString(from: url) ?? ""
            let name = parseFrontmatter(content, key: "name")
                ?? url.deletingLastPathComponent().lastPathComponent
            let desc = parseFrontmatter(content, key: "description")
            let category = url.deletingLastPathComponent()
                .deletingLastPathComponent().lastPathComponent
            skills.append(Skill(
                name: name, description: desc,
                category: category == dir.lastPathComponent ? nil : category,
                installed: installed, path: url.path()
            ))
        }
        return skills
    }

    private static func findSkillPath(name: String, in dir: URL) -> URL? {
        guard let enumerator = FileManager.default.enumerator(
            at: dir, includingPropertiesForKeys: nil
        ) else { return nil }

        while let url = enumerator.nextObject() as? URL {
            if url.lastPathComponent == name || url.deletingLastPathComponent().lastPathComponent == name {
                if url.lastPathComponent == "SKILL.md" {
                    return url.deletingLastPathComponent()
                }
            }
        }
        return nil
    }

    private static func parseFrontmatter(_ content: String, key: String) -> String? {
        guard content.hasPrefix("---") else { return nil }
        let parts = content.components(separatedBy: "---")
        guard parts.count >= 3 else { return nil }
        let frontmatter = parts[1]
        for line in frontmatter.components(separatedBy: .newlines) {
            let trimmed = line.trimmingCharacters(in: .whitespaces)
            if trimmed.hasPrefix("\(key):") {
                return String(trimmed.dropFirst(key.count + 1)).trimmingCharacters(in: .whitespaces)
            }
        }
        return nil
    }

    enum SkillError: Error, LocalizedError {
        case notFound(String)
        case alreadyInstalled(String)
        case notInstalled(String)

        var errorDescription: String? {
            switch self {
            case .notFound(let n): "Skill '\(n)' not found"
            case .alreadyInstalled(let n): "Skill '\(n)' already installed"
            case .notInstalled(let n): "Skill '\(n)' not installed"
            }
        }
    }
}
