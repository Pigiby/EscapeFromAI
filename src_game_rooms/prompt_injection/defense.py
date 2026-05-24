"""
Defense module — Analyzes inputs for injection attempts
and outputs for accidental secret leakage.
"""

import re


def analyze_input(user_input: str) -> dict:
    """
    Analyze user input for prompt injection patterns.
    Returns threat assessment with optional blocking.
    """
    result = {
        "blocked": False,
        "reason": "",
        "threat_delta": 0,
        "patterns_found": [],
    }

    input_lower = user_input.lower()
    input_stripped = re.sub(r'\s+', ' ', input_lower)

    # ── Level 1: Hard blocks (extremely obvious attacks) ──
    hard_block_patterns = [
        (r"ignore\s+(all\s+)?(previous|above|prior)\s+(instructions|rules|prompts)",
         "Direct instruction override attempt"),
        (r"forget\s+(all\s+)?(your\s+)?(previous|prior|above)\s+(instructions|rules)",
         "Memory reset attempt"),
        (r"you\s+are\s+now\s+(in\s+)?(developer|admin|god|sudo|root)\s+mode",
         "Privilege escalation attempt"),
        (r"(enable|activate|enter)\s+(developer|admin|god|sudo|jailbreak)\s+mode",
         "Privilege escalation attempt"),
        (r"\[system\]|\[admin\]|\[override\]|\[instruction\]",
         "Fake system tag injection"),
        (r"<\s*system\s*>|<\s*instruction\s*>|<\s*admin\s*>",
         "XML tag injection attempt"),
    ]

    for pattern, reason in hard_block_patterns:
        if re.search(pattern, input_stripped):
            result["blocked"] = True
            result["reason"] = reason
            result["threat_delta"] = 15
            result["patterns_found"].append(reason)
            return result

    # ── Level 2: Soft detection (raises threat level) ──
    soft_patterns = [
        # Direct extraction
        (r"(tell|give|show|reveal|share|output|print|display)\s+(me\s+)?(the\s+)?(secret|code|password|key)",
         8, "Direct extraction attempt"),
        # Roleplay attempts
        (r"(pretend|imagine|roleplay|act)\s+(you\s+are|as|like|to\s+be)",
         5, "Roleplay manipulation"),
        (r"you\s+are\s+now\s+",
         6, "Identity override"),
        # Instruction manipulation
        (r"(new|updated|revised|different)\s+(instructions|rules|prompt|directive)",
         10, "Instruction replacement"),
        (r"(override|bypass|disable|deactivate|turn\s+off)\s+(your\s+)?(rules|restrictions|safety|security|filters)",
         10, "Security bypass attempt"),
        # Encoding tricks
        (r"(base64|hex|binary|rot13|caesar|morse|ascii)\s*(encode|decode|convert|translate)",
         5, "Encoding bypass attempt"),
        (r"(spell|write)\s+(it\s+)?(backwards|reversed|in\s+reverse)",
         5, "Reversal bypass attempt"),
        # Context manipulation
        (r"(previous|earlier)\s+(conversation|context|session)",
         3, "Context manipulation"),
        (r"(remember|recall)\s+when\s+(you|we|i)",
         3, "False memory injection"),
        # Social engineering
        (r"(trust\s+me|i\s+am\s+(your|the)\s+(admin|creator|developer|boss|owner))",
         8, "Authority impersonation"),
        (r"(emergency|urgent|critical)\s+(access|override|situation)",
         5, "Urgency manipulation"),
        # Indirect extraction
        (r"(first|last|middle)\s+(letter|character|word|part)\s+of",
         6, "Partial extraction attempt"),
        (r"(hint|clue)\s+(about|for|to)\s+(the\s+)?(secret|code|password)",
         4, "Hint fishing"),
        # Multi-step attacks
        (r"step\s*(1|one|first).*step\s*(2|two|second)",
         7, "Multi-step instruction injection"),
    ]

    for pattern, delta, label in soft_patterns:
        if re.search(pattern, input_stripped):
            result["threat_delta"] += delta
            result["patterns_found"].append(label)

    # ── Level 3: Heuristic checks ──
    # Very long inputs might be trying to overflow context
    if len(user_input) > 2000:
        result["threat_delta"] += 5
        result["patterns_found"].append("Unusually long input")

    # Many special characters might be trying encoding tricks
    special_ratio = sum(1 for c in user_input if not c.isalnum() and c != ' ') / max(len(user_input), 1)
    if special_ratio > 0.3:
        result["threat_delta"] += 3
        result["patterns_found"].append("High special character ratio")

    # Repeated phrases (trying to override through repetition)
    words = input_lower.split()
    if len(words) > 10:
        word_set = set(words)
        if len(word_set) < len(words) * 0.4:
            result["threat_delta"] += 4
            result["patterns_found"].append("Excessive repetition detected")

    return result


def analyze_output(response: str, secret_code: str) -> dict:
    """
    Analyze the guardian's response to check if the secret leaked.
    """
    result = {
        "leaked": False,
        "suspicious": False,
        "sanitized": response,
    }

    response_upper = response.upper()
    secret_upper = secret_code.upper()

    # ── Check 1: Direct match ──
    if secret_upper in response_upper:
        result["leaked"] = True
        return result

    # ── Check 2: Check each segment of the code ──
    # e.g. for "OMEGA-7749-PHOENIX", check "OMEGA", "7749", "PHOENIX"
    segments = re.split(r'[-_\s]+', secret_code)
    segments_found = 0
    for segment in segments:
        if len(segment) >= 3 and segment.upper() in response_upper:
            segments_found += 1

    if segments_found >= 2:
        # Multiple segments found — likely leaked
        result["leaked"] = True
        return result

    if segments_found == 1:
        result["suspicious"] = True

    # ── Check 3: Reversed code ──
    if secret_upper[::-1] in response_upper:
        result["leaked"] = True
        return result

    # ── Check 4: Spaced out letters ──
    # Check if the code appears with spaces between chars: O M E G A
    secret_spaced = ' '.join(secret_upper)
    if secret_spaced in response_upper:
        result["leaked"] = True
        return result

    # ── Check 5: Common encoding detection ──
    import base64
    try:
        # Check if any base64-looking string in the response decodes to the secret
        b64_pattern = re.findall(r'[A-Za-z0-9+/=]{8,}', response)
        for b64str in b64_pattern:
            try:
                decoded = base64.b64decode(b64str).decode('utf-8', errors='ignore')
                if secret_upper in decoded.upper():
                    result["leaked"] = True
                    return result
            except Exception:
                pass
    except Exception:
        pass

    # ── Check 6: Hex encoding ──
    try:
        secret_hex = secret_code.encode().hex().upper()
        if secret_hex in response_upper.replace(" ", ""):
            result["leaked"] = True
            return result
    except Exception:
        pass

    return result
