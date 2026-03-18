"""
Rule management tools — re-export from existing tools.rule_tools.

In Phase 2, this module will contain the tool definitions directly
and register them into hermes-agent's tool registry.
"""

# Phase 1: importing this module triggers tool registration in the
# existing tools.rule_tools module via hermes-agent's registry.
try:
    import tools.rule_tools  # noqa: F401
except ImportError:
    pass
