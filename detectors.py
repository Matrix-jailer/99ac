import re
from typing import Dict, List
from patterns import TECH_PATTERNS


def detect_technologies_from_text(html: str, js_globals: dict, network_snippets: List[str]) -> Dict[str, List[str]]:
    results = {}
    combined_text = html + " ".join(network_snippets)

    for tech, patterns in TECH_PATTERNS.items():
        matches = []
        for pat in patterns:
            if pat.search(combined_text):
                matches.append(pat.pattern)
        if js_globals.get(tech):
            matches.append("JS global detected")
        if matches:
            results[tech] = list(set(matches))
    return results
