# orchestration/menu_validator.py
"""
Menu Validator

Responsible for validating ordered items against the menu items
cached in the SessionContext scratchpad.

- Supports direct string match ("cheeseburger").
- Supports fuzzy match ("cheese burger" ≈ "Cheeseburger").
"""

from __future__ import annotations

import difflib
from typing import List, Tuple, Any

from .session_context import SessionContext


class MenuValidator:
    """
    Validates ordered items against a menu list stored in ctx.state.scratchpad["menu_items"].
    """

    def __init__(self, fuzzy_threshold: float = 0.7) -> None:
        self.fuzzy_threshold = fuzzy_threshold

    def validate_items(
        self,
        ordered_items: List[str],
        ctx: SessionContext,
    ) -> Tuple[List[dict], List[str]]:
        """
        Returns:
        - valid_menu_items: list of dicts representing valid menu entries
        - unknown_items   : list of strings that we couldn't confidently match
        """
        menu_items = ctx.state.scratchpad.get("menu_items") or []
        if not menu_items:
            # No menu: treat everything as unknown
            return [], ordered_items

        # Build a mapping of lowercase name -> full menu item
        name_to_item = {}
        names_lower = []

        for m in menu_items:
            if isinstance(m, dict):
                name = (m.get("name") or "").strip()
            else:
                name = str(m).strip()
            if not name:
                continue
            lower = name.lower()
            name_to_item[lower] = m
            names_lower.append(lower)

        valid_items: List[dict] = []
        unknown_items: List[str] = []

        for raw in ordered_items:
            candidate = (raw or "").strip()
            if not candidate:
                continue
            cand_lower = candidate.lower()

            # Exact match first
            if cand_lower in name_to_item:
                valid_items.append(name_to_item[cand_lower])
                continue

            # Fuzzy match
            best_match = None
            best_ratio = 0.0
            for name_lower in names_lower:
                ratio = difflib.SequenceMatcher(None, cand_lower, name_lower).ratio()
                if ratio > best_ratio:
                    best_ratio = ratio
                    best_match = name_lower

            if best_match and best_ratio >= self.fuzzy_threshold:
                valid_items.append(name_to_item[best_match])
            else:
                unknown_items.append(candidate)

        return valid_items, unknown_items
