from __future__ import annotations

import re
from typing import Dict, Tuple


ENTITY_SYNONYMS: Dict[str, Tuple[str, ...]] = {
    "patient": (
        "patient",
        "patients",
        "subject",
        "subjects",
        "individual",
        "individuals",
        "participant",
        "participants",
    ),
    "sample": (
        "sample",
        "samples",
        "biosample",
        "biosamples",
        "specimen",
        "specimens",
        "biospecimen",
        "biospecimens",
        "record",
        "records",
        "timepoint",
        "timepoints",
    ),
}


def entity_synonyms(entity: str) -> Tuple[str, ...]:
    return ENTITY_SYNONYMS.get(entity, ())


def inventory_prompt_matches(text: str, entity: str) -> bool:
    lowered = str(text or "").lower()
    if not lowered:
        return False
    templates = (
        "list {term}",
        "list of {term}",
        "{term} in the cohort",
        "{term} in the workspace",
        "{term} ids in the cohort",
        "{term} ids in the workspace",
        "{term} ids",
        "list all {term}",
        "show all {term}",
        "tell me the list of {term}",
        "which {term} are in the cohort",
        "which {term} are in the workspace",
        "who is in the cohort",
        "who is in the workspace",
    )
    for synonym in entity_synonyms(entity):
        for template in templates:
            if template.format(term=synonym) in lowered:
                return True
    return False


def inventory_count_prompt_matches(text: str, entity: str) -> bool:
    lowered = str(text or "").lower()
    if not lowered:
        return False
    templates = (
        "how many {term} do we have",
        "how many {term} we have",
        "how many {term} are in the workspace",
        "how many {term} are in this workspace",
        "how many {term} are in the cohort",
        "how many {term} are in this cohort",
        "how many {term} are there in the workspace",
        "how many {term} are there in this workspace",
        "how many {term} are there in the cohort",
        "how many {term} are there in this cohort",
    )
    for synonym in entity_synonyms(entity):
        for template in templates:
            if template.format(term=synonym) in lowered:
                return True
    return False


def entity_identifier_prefixes(entity: str) -> Tuple[str, ...]:
    singular = []
    for synonym in entity_synonyms(entity):
        if synonym.endswith("s"):
            continue
        singular.append(synonym)
    return tuple(singular)


def normalize_entity_synonym_mentions(text: str, entity: str, canonical_singular: str, canonical_plural: str) -> str:
    normalized = str(text or "")
    if not normalized:
        return normalized
    for synonym in sorted(entity_synonyms(entity), key=len, reverse=True):
        replacement = canonical_plural if synonym.endswith("s") else canonical_singular
        normalized = re.sub(rf"\b{re.escape(synonym)}\b", replacement, normalized, flags=re.IGNORECASE)
    return normalized
