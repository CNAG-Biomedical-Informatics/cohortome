from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class RecordProvenance(BaseModel):
    source_file: str
    record_index: int
    raw_bff: Dict[str, Any]


class EvidenceBucket(BaseModel):
    count: int = 0
    examples: List[str] = Field(default_factory=list)


class EvidenceInventory(BaseModel):
    diseases: EvidenceBucket = Field(default_factory=EvidenceBucket)
    phenotypic_features: EvidenceBucket = Field(default_factory=EvidenceBucket)
    measures: EvidenceBucket = Field(default_factory=EvidenceBucket)
    treatments: EvidenceBucket = Field(default_factory=EvidenceBucket)
    procedures: EvidenceBucket = Field(default_factory=EvidenceBucket)
    exposures: EvidenceBucket = Field(default_factory=EvidenceBucket)


class EvidenceFragment(BaseModel):
    category: str
    label: str
    visit_id: str
    event_type: Optional[str] = None
    event_date: Optional[str] = None
    source_file: str
    record_index: int
    path: str
    snippet: Dict[str, Any] = Field(default_factory=dict)


class VisitContext(BaseModel):
    visit_id: str
    patient_id: str
    event_date: Optional[str] = None
    event_type: Optional[str] = None
    age_at_visit: Optional[str] = None
    sex: Optional[str] = None
    disease_label: Optional[str] = None
    diagnosis: Optional[str] = None
    biosample_id: Optional[str] = None
    evidence: EvidenceInventory = Field(default_factory=EvidenceInventory)
    notes: Dict[str, Any] = Field(default_factory=dict)
    provenance: RecordProvenance


class NavigatorVisit(BaseModel):
    visit_id: str
    event_type: Optional[str] = None
    event_date: Optional[str] = None
    diagnosis: Optional[str] = None
    evidence: EvidenceInventory = Field(default_factory=EvidenceInventory)
    key_fragments: List[EvidenceFragment] = Field(default_factory=list)
    provenance: RecordProvenance


class PatientSummary(BaseModel):
    patient_id: str
    sex: Optional[str] = None
    date_of_birth: Optional[str] = None
    vital_status: Optional[str] = None
    visit_count: int
    first_event_date: Optional[str] = None
    last_event_date: Optional[str] = None
    evidence: EvidenceInventory = Field(default_factory=EvidenceInventory)
    source_files: List[str] = Field(default_factory=list)


class PatientContext(BaseModel):
    patient_id: str
    sex: Optional[str] = None
    date_of_birth: Optional[str] = None
    age_at_first_visit: Optional[str] = None
    vital_status: Optional[str] = None
    patient_notes: Dict[str, Any] = Field(default_factory=dict)
    evidence: EvidenceInventory = Field(default_factory=EvidenceInventory)
    source_files: List[str] = Field(default_factory=list)
    visits: List[VisitContext] = Field(default_factory=list)


class PatientWorkspace(BaseModel):
    patient_id: str
    summary: PatientSummary
    patient_context: Dict[str, Any] = Field(default_factory=dict)
    evidence: EvidenceInventory = Field(default_factory=EvidenceInventory)
    key_fragments: List[EvidenceFragment] = Field(default_factory=list)
    visits: List[NavigatorVisit] = Field(default_factory=list)
