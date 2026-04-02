from __future__ import annotations

from typing import Dict, Tuple


ENTITY_SYNONYMS: Dict[str, Tuple[str, ...]] = {
    "patient": (
        "patient",
        "patients",
        "subject",
        "subjects",
        "individual",
        "individuals",
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
        "{term} ids in the cohort",
        "{term} ids",
        "list all {term}",
        "show all {term}",
        "tell me the list of {term}",
        "which {term} are in the cohort",
        "who is in the cohort",
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
