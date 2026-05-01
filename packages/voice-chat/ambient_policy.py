import re


BACKCHANNEL_PATTERN = re.compile(r"^BACKCHANNEL\s*:\s*", re.IGNORECASE)


def should_apply_stt_correction(
    text: str,
    *,
    speaker_identified: bool,
    wake_detected: bool,
    in_conversation: bool,
    instruction_pattern: re.Pattern[str],
) -> bool:
    normalized = text.strip()
    if len(normalized) < 6:
        return False
    if speaker_identified or wake_detected or in_conversation:
        return True
    if instruction_pattern.search(normalized):
        return True
    if len(normalized) >= 14 and re.search(r"[？?]$|して$|かな$|よね$|ですか$|ますか$", normalized):
        return True
    return False


def normalize_ambient_reply(reply: str, *, emoji_replacer) -> tuple[str, str]:
    cleaned = emoji_replacer(reply, replace="").strip()
    cleaned = re.sub(r"[（(][^）)]*[）)]", "", cleaned).strip()
    if not cleaned:
        return "skip", ""
    if cleaned.strip().upper() == "SKIP":
        return "skip", ""
    if BACKCHANNEL_PATTERN.match(cleaned):
        body = BACKCHANNEL_PATTERN.sub("", cleaned, count=1).strip()
        return ("backchannel", body) if body else ("skip", "")
    return "reply", cleaned
