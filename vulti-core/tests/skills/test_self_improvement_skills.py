"""Tests for self-improvement skills: reflect and curate-memory.

Validates that the skill files are well-formed, discoverable by the skill
index builder, and that the prompt_builder MEMORY_GUIDANCE includes the
reflection hook.
"""

import pytest
from pathlib import Path

from agent.prompt_builder import (
    _parse_skill_file,
    build_skills_system_prompt,
    MEMORY_GUIDANCE,
)


# =========================================================================
# Skill file validation — reflect
# =========================================================================


class TestReflectSkill:
    """Validate the reflect skill is well-formed and loadable."""

    @pytest.fixture()
    def skill_path(self):
        """Return the path to the reflect skill in the source tree."""
        return Path(__file__).parent.parent.parent / "skills" / "self-improvement" / "reflect" / "SKILL.md"

    def test_skill_file_exists(self, skill_path):
        assert skill_path.exists(), f"reflect SKILL.md not found at {skill_path}"

    def test_skill_parses_correctly(self, skill_path):
        is_compatible, frontmatter, description = _parse_skill_file(skill_path)
        assert is_compatible, "reflect skill should be platform-compatible"
        assert frontmatter.get("name") == "reflect"
        assert "reflect" in description.lower()

    def test_skill_has_required_tags(self, skill_path):
        _, frontmatter, _ = _parse_skill_file(skill_path)
        vulti_meta = frontmatter.get("metadata", {}).get("vulti", {})
        tags = vulti_meta.get("tags", [])
        assert "memory" in tags
        assert "reflection" in tags

    def test_skill_references_all_three_dimensions(self, skill_path):
        """The reflect skill should cover soul (USER.md), memories (MEMORY.md), and understanding."""
        content = skill_path.read_text()
        assert "USER.md" in content, "reflect skill should reference USER.md for soul"
        assert "MEMORY.md" in content, "reflect skill should reference MEMORY.md for memories"
        assert "SOUL.md" in content, "reflect skill should reference SOUL.md for understanding"

    def test_skill_references_memory_tool(self, skill_path):
        """The reflect skill should use the memory tool for persistence."""
        content = skill_path.read_text()
        assert "memory(" in content or "memory tool" in content.lower()

    def test_skill_has_selectivity_guidance(self, skill_path):
        """Should not manufacture insights — some sessions produce zero updates."""
        content = skill_path.read_text()
        assert "selective" in content.lower() or "nothing meaningful" in content.lower()


# =========================================================================
# Skill file validation — curate-memory
# =========================================================================


class TestCurateMemorySkill:
    """Validate the curate-memory skill is well-formed and loadable."""

    @pytest.fixture()
    def skill_path(self):
        return Path(__file__).parent.parent.parent / "skills" / "self-improvement" / "curate-memory" / "SKILL.md"

    def test_skill_file_exists(self, skill_path):
        assert skill_path.exists(), f"curate-memory SKILL.md not found at {skill_path}"

    def test_skill_parses_correctly(self, skill_path):
        is_compatible, frontmatter, description = _parse_skill_file(skill_path)
        assert is_compatible, "curate-memory skill should be platform-compatible"
        assert frontmatter.get("name") == "curate-memory"

    def test_skill_has_required_tags(self, skill_path):
        _, frontmatter, _ = _parse_skill_file(skill_path)
        vulti_meta = frontmatter.get("metadata", {}).get("vulti", {})
        tags = vulti_meta.get("tags", [])
        assert "memory" in tags
        assert "curation" in tags

    def test_skill_has_decay_rules(self, skill_path):
        """The curate skill must define importance/freshness decay logic."""
        content = skill_path.read_text()
        assert "importance" in content.lower()
        assert "freshness" in content.lower() or "stale" in content.lower()

    def test_skill_protects_corrections(self, skill_path):
        """Correction/feedback entries should never be deleted without supersession."""
        content = skill_path.read_text()
        assert "correction" in content.lower()
        assert "superseded" in content.lower() or "never delete" in content.lower()

    def test_skill_has_consolidation_step(self, skill_path):
        """Should merge duplicates and promote patterns."""
        content = skill_path.read_text()
        assert "merge" in content.lower() or "consolidat" in content.lower()
        assert "duplicate" in content.lower()

    def test_skill_references_memory_tool(self, skill_path):
        content = skill_path.read_text()
        assert "memory" in content.lower()
        assert "remove" in content.lower()
        assert "replace" in content.lower()


# =========================================================================
# Category description
# =========================================================================


class TestSelfImprovementCategory:
    def test_description_file_exists(self):
        desc = Path(__file__).parent.parent.parent / "skills" / "self-improvement" / "DESCRIPTION.md"
        assert desc.exists()
        content = desc.read_text()
        assert len(content.strip()) > 0


# =========================================================================
# Skills index integration — both skills appear in system prompt
# =========================================================================


class TestSkillsIndexIntegration:
    def test_reflect_appears_in_skills_index(self, monkeypatch, tmp_path):
        """When installed to ~/.vulti/skills/, reflect should appear in the system prompt index."""
        monkeypatch.setenv("VULTI_HOME", str(tmp_path))
        skills_dir = tmp_path / "skills" / "self-improvement" / "reflect"
        skills_dir.mkdir(parents=True)

        source = Path(__file__).parent.parent.parent / "skills" / "self-improvement" / "reflect" / "SKILL.md"
        if source.exists():
            (skills_dir / "SKILL.md").write_text(source.read_text())
        else:
            (skills_dir / "SKILL.md").write_text(
                "---\nname: reflect\ndescription: End-of-conversation reflection\n"
                "metadata:\n  vulti:\n    tags: [memory, reflection]\n---\n# Reflect\n"
            )

        result = build_skills_system_prompt()
        assert "reflect" in result
        assert "self-improvement" in result.lower() or "reflect" in result.lower()

    def test_curate_memory_appears_in_skills_index(self, monkeypatch, tmp_path):
        """When installed, curate-memory should appear in the system prompt index."""
        monkeypatch.setenv("VULTI_HOME", str(tmp_path))
        skills_dir = tmp_path / "skills" / "self-improvement" / "curate-memory"
        skills_dir.mkdir(parents=True)

        source = Path(__file__).parent.parent.parent / "skills" / "self-improvement" / "curate-memory" / "SKILL.md"
        if source.exists():
            (skills_dir / "SKILL.md").write_text(source.read_text())
        else:
            (skills_dir / "SKILL.md").write_text(
                "---\nname: curate-memory\ndescription: Memory curation pass\n"
                "metadata:\n  vulti:\n    tags: [memory, curation]\n---\n# Curate Memory\n"
            )

        result = build_skills_system_prompt()
        assert "curate-memory" in result


# =========================================================================
# Prompt builder — reflection hook in MEMORY_GUIDANCE
# =========================================================================


class TestMemoryGuidanceReflectionHook:
    def test_memory_guidance_mentions_reflect_skill(self):
        """MEMORY_GUIDANCE should tell the agent to load reflect at end of conversation."""
        assert "reflect" in MEMORY_GUIDANCE.lower()

    def test_memory_guidance_mentions_soul_concept(self):
        """MEMORY_GUIDANCE should reference soul (USER.md) as a reflection target."""
        assert "soul" in MEMORY_GUIDANCE.lower() or "USER.md" in MEMORY_GUIDANCE

    def test_memory_guidance_mentions_three_layers(self):
        """MEMORY_GUIDANCE should reference the three reflection layers."""
        guidance_lower = MEMORY_GUIDANCE.lower()
        assert "soul" in guidance_lower
        assert "memories" in guidance_lower or "memory.md" in guidance_lower
        assert "understanding" in guidance_lower

    def test_memory_guidance_preserves_existing_content(self):
        """The reflection addition should not break existing memory guidance."""
        assert "durable facts" in MEMORY_GUIDANCE
        assert "Do NOT save task progress" in MEMORY_GUIDANCE
        assert "session_search" in MEMORY_GUIDANCE
