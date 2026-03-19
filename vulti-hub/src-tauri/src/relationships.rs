use crate::agents::{load_registry, save_registry};
use crate::types::{OkResponse, OwnerEntry, OwnerResponse, RelationshipEntry, RelationshipResponse};

fn entry_to_response(e: &RelationshipEntry) -> RelationshipResponse {
    RelationshipResponse {
        id: e.id.clone(),
        from_agent_id: e.from_agent_id.clone(),
        to_agent_id: e.to_agent_id.clone(),
        rel_type: e.rel_type.clone(),
        matrix_room_id: e.matrix_room_id.clone(),
        created_at: e.created_at.clone(),
    }
}

#[tauri::command]
pub fn list_relationships() -> Result<Vec<RelationshipResponse>, String> {
    let reg = load_registry();
    Ok(reg.relationships.iter().map(entry_to_response).collect())
}

#[tauri::command]
pub fn create_relationship(
    from_id: String,
    to_id: String,
    rel_type: String,
) -> Result<RelationshipResponse, String> {
    let mut reg = load_registry();

    // Validate agents exist ("owner" is always valid)
    if from_id != "owner" && !reg.agents.contains_key(&from_id) {
        return Err(format!("Agent '{}' not found", from_id));
    }
    if to_id != "owner" && !reg.agents.contains_key(&to_id) {
        return Err(format!("Agent '{}' not found", to_id));
    }

    // Prevent duplicate relationships
    if reg.relationships.iter().any(|r| r.from_agent_id == from_id && r.to_agent_id == to_id) {
        return Err("Relationship already exists".to_string());
    }

    let entry = RelationshipEntry {
        id: uuid::Uuid::new_v4().to_string(),
        from_agent_id: from_id,
        to_agent_id: to_id,
        rel_type,
        matrix_room_id: None,
        created_at: chrono::Utc::now().to_rfc3339(),
    };

    let response = entry_to_response(&entry);
    reg.relationships.push(entry);
    save_registry(&reg)?;

    Ok(response)
}

#[tauri::command]
pub fn delete_relationship(rel_id: String) -> Result<OkResponse, String> {
    let mut reg = load_registry();
    let before = reg.relationships.len();
    reg.relationships.retain(|r| r.id != rel_id);
    if reg.relationships.len() == before {
        return Err(format!("Relationship '{}' not found", rel_id));
    }
    save_registry(&reg)?;
    Ok(OkResponse { ok: true })
}

#[tauri::command]
pub fn update_relationship(
    rel_id: String,
    updates: serde_json::Value,
) -> Result<RelationshipResponse, String> {
    let mut reg = load_registry();
    let entry = reg
        .relationships
        .iter_mut()
        .find(|r| r.id == rel_id)
        .ok_or_else(|| format!("Relationship '{}' not found", rel_id))?;

    if let Some(v) = updates.get("matrix_room_id").and_then(|v| v.as_str()) {
        entry.matrix_room_id = Some(v.to_string());
    }
    if let Some(v) = updates.get("rel_type").and_then(|v| v.as_str()) {
        entry.rel_type = v.to_string();
    }

    let response = entry_to_response(entry);
    save_registry(&reg)?;
    Ok(response)
}

#[tauri::command]
pub fn get_owner() -> Result<OwnerResponse, String> {
    let reg = load_registry();
    let owner = reg.owner.unwrap_or_default();
    Ok(OwnerResponse {
        name: owner.name,
        avatar: owner.avatar,
        about: owner.about,
    })
}

#[tauri::command]
pub fn update_owner(name: String, avatar: Option<String>, about: Option<String>) -> Result<OwnerResponse, String> {
    let mut reg = load_registry();
    let owner = OwnerEntry {
        name: name.clone(),
        avatar: avatar.clone(),
        about: about.clone(),
    };
    reg.owner = Some(owner);
    save_registry(&reg)?;
    Ok(OwnerResponse { name, avatar, about })
}
