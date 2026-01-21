from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class RegistrableItem:
    uuid: str
    item_type: str
    preferred_name: str
    definition: str
    context_uuid: Optional[str] = None
    registration_authority_uuid: Optional[str] = None
    registration_status: str = "Candidate"
    administrative_status: str = "Draft"
    steward: Optional[str] = None
    submitting_organization: Optional[str] = None
    version: int = 1
