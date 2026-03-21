"""Rules engine — re-exports from rules.rules for Phase 1."""

from rules.rules import (  # noqa: F401
    create_rule,
    disable_rule,
    enable_rule,
    get_active_rules,
    get_rule,
    list_rules,
    load_all_rules,
    load_rules,
    record_trigger,
    remove_rule,
    save_rules,
    update_rule,
)
