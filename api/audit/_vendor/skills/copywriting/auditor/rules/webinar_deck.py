"""webinar_deck.py — webinar deck structural checks.

Decks aren't parsed by the email-bundle parser · this module is a placeholder for
v1 phase 2 expansion. For now it's a no-op so the registry imports cleanly.
"""

from skills.copywriting.auditor.lib.registry import Rule, HARD, YELLOW

LAYER = "WebinarDeck"
APPLIES_TO = {"webinar_deck"}

RULES = []  # Phase 2c will populate
