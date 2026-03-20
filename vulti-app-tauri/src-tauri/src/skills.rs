use serde::{Deserialize, Serialize};
use std::fs;
use std::path::PathBuf;

use crate::vulti_home::vulti_home;

#[derive(Debug, Serialize, Deserialize, Clone, Default)]
pub struct Skill {
    pub name: String,
    pub description: String,
    #[serde(default)]
    pub category: String,
    #[serde(default)]
    pub installed: bool,
}

/// Parse SKILL.md frontmatter to extract name and description
fn parse_skill_md(content: &str) -> Option<(String, String)> {
    let trimmed = content.trim();
    if !trimmed.starts_with("---") {
        return None;
    }
    let rest = &trimmed[3..];
    let end = rest.find("---")?;
    let frontmatter = &rest[..end];

    let mut name = String::new();
    let mut description = String::new();
    for line in frontmatter.lines() {
        let line = line.trim();
        if let Some(val) = line.strip_prefix("name:") {
            name = val.trim().trim_matches('"').trim_matches('\'').to_string();
        } else if let Some(val) = line.strip_prefix("description:") {
            description = val.trim().trim_matches('"').trim_matches('\'').to_string();
        }
    }
    if name.is_empty() {
        None
    } else {
        Some((name, description))
    }
}

/// Recursively find all SKILL.md files in a directory
fn find_skills(dir: &PathBuf, category_prefix: &str) -> Vec<Skill> {
    let mut skills = Vec::new();
    let entries = match fs::read_dir(dir) {
        Ok(e) => e,
        Err(_) => return skills,
    };

    for entry in entries.flatten() {
        let path = entry.path();
        if !path.is_dir() {
            continue;
        }

        let dir_name = path.file_name().unwrap_or_default().to_string_lossy().to_string();
        let skill_md = path.join("SKILL.md");

        if skill_md.exists() {
            if let Ok(content) = fs::read_to_string(&skill_md) {
                if let Some((name, description)) = parse_skill_md(&content) {
                    let category = if category_prefix.is_empty() {
                        String::new()
                    } else {
                        category_prefix.to_string()
                    };
                    skills.push(Skill {
                        name,
                        description,
                        category,
                        installed: false,
                    });
                }
            }
        } else {
            // It's a category directory — recurse
            let sub_category = if category_prefix.is_empty() {
                dir_name.clone()
            } else {
                format!("{}/{}", category_prefix, dir_name)
            };
            skills.extend(find_skills(&path, &sub_category));
        }
    }
    skills
}

#[tauri::command]
pub fn list_available_skills() -> Vec<Skill> {
    let skills_dir = vulti_home().join("skills");
    find_skills(&skills_dir, "")
}

#[tauri::command]
pub fn list_agent_skills(agent_id: String) -> Vec<Skill> {
    let agent_skills_dir = vulti_home().join("agents").join(&agent_id).join("skills");
    let mut skills = find_skills(&agent_skills_dir, "");
    for s in &mut skills {
        s.installed = true;
    }
    skills
}

#[tauri::command]
pub fn install_agent_skill(agent_id: String, skill_name: String) -> Result<Skill, String> {
    let global_skills = vulti_home().join("skills");
    let agent_skills = vulti_home().join("agents").join(&agent_id).join("skills");

    // Find the skill in global skills (search recursively)
    let source = find_skill_path(&global_skills, &skill_name)
        .ok_or_else(|| format!("Skill '{}' not found in global skills", skill_name))?;

    let dest = agent_skills.join(&skill_name);
    if dest.exists() {
        return Err(format!("Skill '{}' already installed for agent '{}'", skill_name, agent_id));
    }

    // Create symlink to global skill
    #[cfg(unix)]
    {
        std::os::unix::fs::symlink(&source, &dest)
            .map_err(|e| format!("Failed to link skill: {}", e))?;
    }
    #[cfg(not(unix))]
    {
        // Fallback: copy directory
        copy_dir_all(&source, &dest)
            .map_err(|e| format!("Failed to copy skill: {}", e))?;
    }

    // Read the skill metadata
    let skill_md = dest.join("SKILL.md");
    let (name, description) = if let Ok(content) = fs::read_to_string(&skill_md) {
        parse_skill_md(&content).unwrap_or((skill_name.clone(), String::new()))
    } else {
        (skill_name, String::new())
    };

    Ok(Skill {
        name,
        description,
        category: String::new(),
        installed: true,
    })
}

#[tauri::command]
pub fn remove_agent_skill(agent_id: String, skill_name: String) -> Result<(), String> {
    let agent_skills = vulti_home().join("agents").join(&agent_id).join("skills");
    let skill_path = agent_skills.join(&skill_name);

    if !skill_path.exists() {
        return Err(format!("Skill '{}' not installed for agent '{}'", skill_name, agent_id));
    }

    // If it's a symlink, just remove the link. If it's a real dir, remove recursively.
    if skill_path.is_symlink() {
        fs::remove_file(&skill_path).map_err(|e| format!("Failed to remove symlink: {}", e))?;
    } else {
        fs::remove_dir_all(&skill_path).map_err(|e| format!("Failed to remove skill: {}", e))?;
    }

    Ok(())
}

/// Find a skill directory by name (recursive search through categories)
fn find_skill_path(base: &PathBuf, name: &str) -> Option<PathBuf> {
    let direct = base.join(name);
    if direct.join("SKILL.md").exists() {
        return Some(direct);
    }

    // Search in category subdirectories
    let entries = fs::read_dir(base).ok()?;
    for entry in entries.flatten() {
        let path = entry.path();
        if path.is_dir() && !path.join("SKILL.md").exists() {
            // This is a category dir, search inside
            if let Some(found) = find_skill_path(&path, name) {
                return Some(found);
            }
        }
    }
    None
}

#[cfg(not(unix))]
fn copy_dir_all(src: &PathBuf, dst: &PathBuf) -> std::io::Result<()> {
    fs::create_dir_all(dst)?;
    for entry in fs::read_dir(src)? {
        let entry = entry?;
        let dest_path = dst.join(entry.file_name());
        if entry.path().is_dir() {
            copy_dir_all(&entry.path(), &dest_path)?;
        } else {
            fs::copy(entry.path(), dest_path)?;
        }
    }
    Ok(())
}
