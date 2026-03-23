"""Randomized persona generation for the VultiHub E2E harness."""

from __future__ import annotations

import random
import string
from dataclasses import dataclass, field

# ── Pools ──

OWNER_FIRST_NAMES = [
    "Amara", "Kai", "Yuki", "Priya", "Leo", "Sofia", "Omar", "Mei",
    "Dante", "Anya", "Ravi", "Elena", "Noah", "Zara", "Felix", "Luna",
    "Soren", "Ines", "Mateo", "Aisha", "Tobias", "Hana", "Liam", "Mira",
    "Axel", "Nadia", "Emeka", "Freya", "Hugo", "Sadie", "Jin", "Rosa",
    "Elio", "Tessa", "Ren", "Ivy", "Odin", "Petra", "Idris", "Vera",
    "Marcel", "Quinn", "Atlas", "Cleo", "Sage", "Iris", "Ezra", "Noor",
]

OWNER_LAST_NAMES = [
    "Okafor", "Nakamura", "Patel", "Kim", "Santos", "Müller", "Hassan",
    "Zhang", "Rossi", "Johansson", "Chen", "Dubois", "Tanaka", "Singh",
    "Williams", "Park", "Da Silva", "Nguyen", "Garcia", "Petrov",
    "Andersen", "Kowalski", "Yamamoto", "Lee", "Torres", "Bergström",
]

ABOUT_TEMPLATES = [
    "{role} based in {city}",
    "{role} focusing on {domain}",
    "{role} building {project}",
    "{role} with a passion for {domain}",
    "Independent {role} working on {project}",
    "{role} exploring {domain} and {domain2}",
    "Freelance {role} specializing in {domain}",
]

ROLES_FOR_ABOUT = [
    "software engineer", "data scientist", "ML researcher", "product designer",
    "founder", "DevOps engineer", "security researcher", "full-stack developer",
    "systems architect", "mobile developer", "AI engineer", "blockchain developer",
    "technical writer", "QA engineer", "infrastructure engineer",
]

CITIES = [
    "Melbourne", "Tokyo", "Berlin", "San Francisco", "London", "Seoul",
    "Amsterdam", "São Paulo", "Toronto", "Singapore", "Portland", "Barcelona",
    "Oslo", "Austin", "Bangalore", "Lisbon", "Copenhagen", "Denver",
]

DOMAINS = [
    "NLP research", "distributed systems", "computer vision", "autonomous agents",
    "real-time systems", "edge computing", "privacy engineering", "robotics",
    "knowledge graphs", "generative AI", "recommendation systems", "MLOps",
    "observability", "API design", "open source", "voice interfaces",
]

PROJECTS = [
    "autonomous agent teams", "a personal AI assistant", "smart home automation",
    "an open-source LLM toolkit", "a real-time analytics platform",
    "a privacy-first messaging app", "a decentralized AI network",
    "intelligent document processing", "a code review copilot",
]

# Agent names — mythology, astronomy, nature
AGENT_NAMES = [
    "Atlas", "Nova", "Echo", "Sage", "Phoenix", "Orion", "Luna", "Iris",
    "Zephyr", "Athena", "Cosmo", "Nyx", "Ceres", "Apollo", "Vega",
    "Ember", "Frost", "Delta", "Aria", "Nexus", "Pulse", "Cipher",
    "Quill", "Rune", "Spark", "Onyx", "Drift", "Blaze", "Lyra", "Dusk",
]

AGENT_ROLES = [
    "assistant", "engineer", "researcher", "analyst", "writer",
    "therapist", "coach", "creative", "ops",
]

PERSONALITY_TEMPLATES = [
    "You are a meticulous {role} who communicates concisely and values precision.",
    "You are a friendly {role} who explains complex topics in simple terms.",
    "You are a creative {role} who thinks laterally and offers unconventional solutions.",
    "You are a pragmatic {role} who focuses on what works over what's elegant.",
    "You are an analytical {role} who backs every claim with evidence.",
    "You are a patient {role} who asks clarifying questions before diving in.",
    "You are a bold {role} who isn't afraid to challenge assumptions.",
    "You are a methodical {role} who breaks problems into small steps.",
    "You are a curious {role} who loves exploring new ideas and connections.",
    "You are a direct {role} who gives honest feedback without sugarcoating.",
    "You are a supportive {role} who encourages experimentation and learning.",
    "You are a strategic {role} who always considers the bigger picture.",
    "You are a detail-oriented {role} who catches edge cases others miss.",
    "You are a calm {role} who stays focused under pressure.",
    "You are a versatile {role} who adapts your communication style to the audience.",
]

# Conversation starters by role type
CONVERSATION_STARTERS = {
    "general": [
        "Hello! Who are you and what can you help me with?",
        "Hey there. Tell me about yourself.",
        "Hi! What are your capabilities?",
        "What's the first thing you'd recommend I set up?",
    ],
    "engineer": [
        "Can you help me debug a Python script that's hanging?",
        "I need to set up a CI pipeline — where should I start?",
        "What's the best way to structure a microservices project?",
        "Help me write a Dockerfile for a FastAPI app.",
    ],
    "researcher": [
        "Find me the latest papers on multi-agent systems.",
        "What are the current trends in federated learning?",
        "Summarize the key findings on transformer efficiency.",
        "Compare retrieval-augmented generation approaches.",
    ],
    "writer": [
        "Help me write a blog post about AI agents.",
        "Draft a technical README for an open-source project.",
        "Write a concise summary of how VultiHub works.",
        "Edit this paragraph to be more concise and direct.",
    ],
    "analyst": [
        "What metrics should I track for an AI agent system?",
        "Help me analyze the performance of our API endpoints.",
        "Create a framework for evaluating agent effectiveness.",
        "What's the best way to visualize multi-agent interactions?",
    ],
    "creative": [
        "Generate some creative names for a new AI product.",
        "Help me brainstorm features for a personal AI assistant.",
        "Write a short story about an AI that manages a household.",
        "Design a unique personality for a customer service agent.",
    ],
    "ops": [
        "Help me set up monitoring for a Python service.",
        "What's the best cron schedule for a daily health check?",
        "How should I handle log rotation for agent conversations?",
        "Create an alert rule for when response latency exceeds 5s.",
    ],
}

FOLLOWUP_MESSAGES = [
    "Can you elaborate on that?",
    "That's helpful. What else should I know?",
    "Interesting. How would you implement that?",
    "What are the tradeoffs?",
    "Give me a concrete example.",
    "Now summarize what we've discussed.",
]

# Installable skills — these are category-level dirs under ~/.vulti/skills/
# The API expects the top-level directory name, not subdirectory names.
AVAILABLE_SKILLS = [
    "research", "productivity", "software-development", "data-science",
    "creative", "feeds", "self-improvement", "smart-home", "system",
    "note-taking", "media", "domain", "dogfood",
]

CRON_TEMPLATES = [
    {"name": "Daily health check", "prompt": "Check system status and report any issues", "schedule": "0 9 * * *"},
    {"name": "Weekly summary", "prompt": "Summarize this week's activity and key events", "schedule": "0 10 * * 1"},
    {"name": "Hourly monitor", "prompt": "Quick status check", "schedule": "0 * * * *"},
    {"name": "Morning briefing", "prompt": "Prepare a morning briefing with news and tasks", "schedule": "0 7 * * *"},
    {"name": "Nightly cleanup", "prompt": "Review and organize today's conversations", "schedule": "0 23 * * *"},
    {"name": "Bi-daily sync", "prompt": "Check for updates and sync status", "schedule": "0 9,17 * * *"},
    {"name": "Weekend review", "prompt": "Review the week's progress and plan next week", "schedule": "0 10 * * 6"},
    {"name": "Midday check-in", "prompt": "Quick check-in on running tasks", "schedule": "0 12 * * *"},
    {"name": "Monthly report", "prompt": "Generate a monthly activity report", "schedule": "0 9 1 * *"},
    {"name": "Evening digest", "prompt": "Compile an evening digest of the day's events", "schedule": "0 20 * * *"},
]

RULE_TEMPLATES = [
    {"name": "Urgent escalation", "condition": "message contains 'urgent' or 'emergency'", "action": "notify owner immediately", "priority": 10},
    {"name": "Auto-greet", "condition": "new user sends first message", "action": "respond with a friendly greeting", "priority": 1},
    {"name": "Code review gate", "condition": "message contains code block longer than 50 lines", "action": "suggest breaking into smaller pieces", "priority": 5},
    {"name": "Polite redirect", "condition": "question is outside agent expertise", "action": "redirect to appropriate agent", "priority": 3},
    {"name": "Rate limit warning", "condition": "more than 10 messages in 1 minute", "action": "suggest slowing down", "priority": 7},
    {"name": "Sensitive topic", "condition": "message discusses personal health or finance", "action": "add disclaimer about professional advice", "priority": 8},
    {"name": "Long response check", "condition": "response exceeds 500 words", "action": "add a TL;DR summary at the top", "priority": 2},
    {"name": "Follow-up reminder", "condition": "user asked a question and no reply in 5 minutes", "action": "send a gentle follow-up", "priority": 4},
    {"name": "Knowledge capture", "condition": "user shares a useful fact or preference", "action": "save to agent memory", "priority": 6},
    {"name": "Error handler", "condition": "tool execution fails", "action": "explain the error and suggest alternatives", "priority": 9},
]


# ── Dataclasses ──

@dataclass
class OwnerPersona:
    name: str
    password: str
    about: str
    username: str  # derived: name.lower().replace(" ", "_")


@dataclass
class AgentPersona:
    name: str
    role: str
    model: str
    skills: list[str] = field(default_factory=list)
    conversation: list[str] = field(default_factory=list)
    personality: str = ""


@dataclass
class Persona:
    owner: OwnerPersona
    agent: AgentPersona
    ai_key_name: str
    ai_key_value: str
    default_model: str
    optional_keys: dict = field(default_factory=dict)
    cron: dict = field(default_factory=dict)
    rule: dict = field(default_factory=dict)
    seed: int = 0


def _gen_password(rng: random.Random) -> str:
    """Generate a random password 10-14 chars, letters + digits + a symbol."""
    length = rng.randint(10, 14)
    chars = string.ascii_letters + string.digits
    pw = "".join(rng.choice(chars) for _ in range(length - 1))
    pw += rng.choice("!@#$%&")
    return pw


def generate_persona(seed: int | None = None, api_keys: dict | None = None) -> Persona:
    """Generate a randomized but reproducible persona.

    api_keys should be a dict loaded from keys.json, e.g.:
    {
        "OPENROUTER_API_KEY": "sk-or-...",
        "default_model": "anthropic/claude-3.5-sonnet",
        "ELEVENLABS_API_KEY": "...",  # optional
    }
    """
    if api_keys is None:
        api_keys = {}

    if seed is None:
        seed = random.randint(0, 999999)
    rng = random.Random(seed)

    # Owner
    first = rng.choice(OWNER_FIRST_NAMES)
    last = rng.choice(OWNER_LAST_NAMES)
    owner_name = f"{first} {last}"
    username = owner_name.lower().replace(" ", "_")
    password = _gen_password(rng)

    role_for_about = rng.choice(ROLES_FOR_ABOUT)
    city = rng.choice(CITIES)
    domain = rng.choice(DOMAINS)
    domain2 = rng.choice([d for d in DOMAINS if d != domain])
    project = rng.choice(PROJECTS)
    about_tmpl = rng.choice(ABOUT_TEMPLATES)
    about = about_tmpl.format(role=role_for_about, city=city, domain=domain, domain2=domain2, project=project)

    owner = OwnerPersona(name=owner_name, password=password, about=about, username=username)

    # Agent
    agent_name = rng.choice(AGENT_NAMES)
    agent_role = rng.choice(AGENT_ROLES)

    # Determine AI key
    # Find the first AI provider key in the keys dict
    ai_key_priority = [
        "OPENROUTER_API_KEY", "ANTHROPIC_API_KEY", "OPENAI_API_KEY",
        "VENICE_API_KEY", "DEEPSEEK_API_KEY", "GOOGLE_API_KEY",
    ]
    ai_key_name = ""
    ai_key_value = ""
    for k in ai_key_priority:
        if k in api_keys and api_keys[k]:
            ai_key_name = k
            ai_key_value = api_keys[k]
            break

    default_model = api_keys.get("default_model", "anthropic/claude-3.5-sonnet")

    personality = rng.choice(PERSONALITY_TEMPLATES).format(role=agent_role)

    # Skills: 1-3 random
    n_skills = rng.randint(1, 3)
    skills = rng.sample(AVAILABLE_SKILLS, min(n_skills, len(AVAILABLE_SKILLS)))

    # Conversation: 1 starter + 1-2 followups
    role_key = agent_role if agent_role in CONVERSATION_STARTERS else "general"
    starters = CONVERSATION_STARTERS.get(role_key, CONVERSATION_STARTERS["general"])
    conversation = [rng.choice(starters)]
    n_followups = rng.randint(1, 2)
    conversation.extend(rng.sample(FOLLOWUP_MESSAGES, n_followups))

    agent = AgentPersona(
        name=agent_name,
        role=agent_role,
        model=default_model,
        skills=skills,
        conversation=conversation,
        personality=personality,
    )

    # Optional keys (everything in api_keys that isn't the AI key or default_model)
    reserved = {ai_key_name, "default_model"}
    optional_keys = {k: v for k, v in api_keys.items() if k not in reserved and v}

    # Cron + Rule
    cron = rng.choice(CRON_TEMPLATES)
    rule = rng.choice(RULE_TEMPLATES)

    return Persona(
        owner=owner,
        agent=agent,
        ai_key_name=ai_key_name,
        ai_key_value=ai_key_value,
        default_model=default_model,
        optional_keys=optional_keys,
        cron=cron,
        rule=rule,
        seed=seed,
    )
