import re


def normalize_english_name(name: str) -> str:
    lowered = str(name or "").strip().lower()
    lowered = lowered.replace("-", " ").replace(",", " ")
    return " ".join(lowered.split())


def english_name_variants(english_name: str) -> set[str]:
    normalized = normalize_english_name(english_name)
    if normalized == "":
        return set()

    variants = {normalized}
    parts = normalized.split(" ")
    if len(parts) == 2:
        variants.add(f"{parts[1]} {parts[0]}")
    return variants


def is_exact_english_author_match(author_name: str, mentor_english_name: str) -> bool:
    normalized_author = normalize_english_name(author_name)
    if normalized_author == "":
        return False
    return normalized_author in english_name_variants(mentor_english_name)


def has_exact_english_author_match(author_names: list[str], mentor_english_name: str) -> bool:
    return any(
        is_exact_english_author_match(author_name, mentor_english_name)
        for author_name in author_names
    )
