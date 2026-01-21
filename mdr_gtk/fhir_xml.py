from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Optional

import xml.etree.ElementTree as ET

FHIR_NS = "http://hl7.org/fhir"
ET.register_namespace("", FHIR_NS)


SUPPORTED_STRICT_TYPES = {"Bundle", "Patient", "Observation", "Encounter", "Condition", "StructureDefinition", "ValueSet", "CodeSystem", "MedicationRequest", "Procedure", "Medication", "MedicationDispense"}

# Allowed field order for strict XML (FHIR R4 core order; subset)
STRICT_FIELD_ORDER: dict[str, list[str]] = {
    "Bundle": [
        "id","meta","implicitRules","language",
        "identifier","type","timestamp","total","link","entry","signature",
    ],
    "Patient": [
        "id","meta","implicitRules","language","text","contained","extension","modifierExtension",
        "identifier","active","name","telecom","gender","birthDate","deceasedBoolean","deceasedDateTime",
        "address","maritalStatus","multipleBirthBoolean","multipleBirthInteger","photo","contact",
        "communication","generalPractitioner","managingOrganization","link",
    ],
    "Observation": [
        "id","meta","implicitRules","language","text","contained","extension","modifierExtension",
        "identifier","basedOn","partOf","status","category","code","subject","focus","encounter",
        "effectiveDateTime","effectivePeriod","effectiveTiming","effectiveInstant",
        "issued","performer",
        "valueQuantity","valueCodeableConcept","valueString","valueBoolean","valueInteger","valueRange",
        "valueRatio","valueSampledData","valueTime","valueDateTime","valuePeriod",
        "dataAbsentReason","interpretation","note","bodySite","method","specimen","device",
        "referenceRange","hasMember","derivedFrom","component",
    ],
    "Encounter": [
        "id","meta","implicitRules","language","text","contained","extension","modifierExtension",
        "identifier","status","statusHistory","class","classHistory","type","serviceType","priority",
        "subject","episodeOfCare","basedOn","participant","appointment","period","length",
        "reasonCode","reasonReference","diagnosis","account",
        "hospitalization","location","serviceProvider","partOf",
    ],
    "Condition": [
        "id","meta","implicitRules","language","text","contained","extension","modifierExtension",
        "identifier","clinicalStatus","verificationStatus","category","severity","code","bodySite",
        "subject","encounter",
        "onsetDateTime","onsetAge","onsetPeriod","onsetRange","onsetString",
        "abatementDateTime","abatementAge","abatementPeriod","abatementRange","abatementString",
        "recordedDate","recorder","asserter",
        "stage","evidence","note",
    ],
    "StructureDefinition": [
        "id","meta","implicitRules","language","text","contained","extension","modifierExtension",
        "url","identifier","version","name","title","status","experimental","date","publisher",
        "contact","description","useContext","jurisdiction","purpose","copyright","keyword",
        "fhirVersion","mapping",
        "kind","abstract","context","contextInvariant",
        "type","baseDefinition","derivation",
        "snapshot","differential",
    ],
    "ValueSet": [
        "id","meta","implicitRules","language","text","contained","extension","modifierExtension",
        "url","identifier","version","name","title","status","experimental","date","publisher",
        "contact","description","useContext","jurisdiction","immutable","purpose","copyright",
        "compose","expansion",
    ],
    "CodeSystem": [
        "id","meta","implicitRules","language","text","contained","extension","modifierExtension",
        "url","identifier","version","name","title","status","experimental","date","publisher",
        "contact","description","useContext","jurisdiction","purpose","copyright",
        "caseSensitive","valueSet","hierarchyMeaning","compositional","versionNeeded","content",
        "supplements","count","filter","property","concept",
    ],
"Medication": [
    "id","meta","implicitRules","language","text","contained","extension","modifierExtension",
    "identifier","code","status","manufacturer","form","amount","ingredient","batch",
],
"MedicationDispense": [
    "id","meta","implicitRules","language","text","contained","extension","modifierExtension",
    "identifier","partOf","status","statusReasonCodeableConcept","statusReasonReference",
    "category","medicationCodeableConcept","medicationReference",
    "subject","context","supportingInformation","performedDateTime","performedPeriod",
    "performer","location","authorizingPrescription","type","quantity","daysSupply","whenPrepared","whenHandedOver",
    "destination","receiver","note","dosageInstruction","substitution","detectedIssue","eventHistory",
],
}



@dataclass
class XmlBuildResult:
    ok: bool
    message: str
    element: Optional[ET.Element] = None


def _tag(name: str) -> str:
    return f"{{{FHIR_NS}}}{name}"


def _is_primitive(v: Any) -> bool:
    return isinstance(v, (str, int, float, bool))


def _primitive_el(parent: ET.Element, name: str, value: Any) -> ET.Element:
    el = ET.SubElement(parent, _tag(name))
    # FHIR XML primitive values go into the "value" attribute
    el.set("value", "true" if value is True else "false" if value is False else str(value))
    return el


def _serialize_generic(parent: ET.Element, key: str, value: Any) -> None:
    # Generic FHIR-like XML serializer:
    # - primitives -> <key value="..."/>
    # - dict -> <key> ... </key>
    # - list -> repeated <key>...</key>
    if value is None:
        return
    if isinstance(value, list):
        for item in value:
            _serialize_generic(parent, key, item)
        return
    if _is_primitive(value):
        _primitive_el(parent, key, value)
        return

    el = ET.SubElement(parent, _tag(key))
    if isinstance(value, dict):
        for k, v in value.items():
            if k == "resourceType":
                continue
            _serialize_generic(el, k, v)
    else:
        # fallback: stringify
        _primitive_el(parent, key, json.dumps(value, ensure_ascii=False))


def _unknown_fields(resource: dict[str, Any], allowed: set[str]) -> set[str]:
    return {k for k in resource.keys() if k not in allowed and k != "resourceType"}


def resource_to_xml_element(resource: dict[str, Any], *, mode: str = "best-effort") -> XmlBuildResult:
    """Convert a single FHIR JSON resource dict into an XML Element.

    mode:
      - "best-effort": serialize any resource generically (FHIR-like), no strict validation.
      - "strict": only supports Bundle/Patient/Observation and rejects unknown fields for those types.
    """
    rt = resource.get("resourceType")
    if not isinstance(rt, str) or not rt:
        return XmlBuildResult(False, "Missing resourceType")

    if mode not in ("best-effort", "strict", "strictish"):
        return XmlBuildResult(False, f"Invalid mode: {mode}")

    if mode in ("strict", "strictish"):
        if rt not in SUPPORTED_STRICT_TYPES:
            if mode == "strictish":
                # fallback to best-effort for unsupported types
                root = ET.Element(_tag(rt))
                for k, v in resource.items():
                    if k == "resourceType":
                        continue
                    _serialize_generic(root, k, v)
                return XmlBuildResult(True, f"OK (strictish fallback for {rt})", element=root)
            return XmlBuildResult(False, f"Strict XML supports only: {sorted(SUPPORTED_STRICT_TYPES)} (got {rt})")
        order = STRICT_FIELD_ORDER[rt]
        allowed = set(order)
        unknown = _unknown_fields(resource, allowed)
        if unknown:
            if mode == "strictish":
                root = ET.Element(_tag(rt))
                for k, v in resource.items():
                    if k == "resourceType":
                        continue
                    _serialize_generic(root, k, v)
                return XmlBuildResult(True, f"OK (strictish fallback unknown fields for {rt})", element=root)
            return XmlBuildResult(False, f"Strict XML: unknown fields for {rt}: {sorted(unknown)}")

        root = ET.Element(_tag(rt))
        for k in order:
            if k not in resource:
                continue
            v = resource.get(k)
            if k == "entry" and rt == "Bundle":
                # entry is a list of dicts, each -> <entry>...
                if isinstance(v, list):
                    for entry in v:
                        if not isinstance(entry, dict):
                            continue
                        entry_el = ET.SubElement(root, _tag("entry"))
                        # Bundle.entry fields ordering subset
                        if "fullUrl" in entry:
                            _primitive_el(entry_el, "fullUrl", entry["fullUrl"])
                        if "resource" in entry and isinstance(entry["resource"], dict):
                            res_wrap = ET.SubElement(entry_el, _tag("resource"))
                            child = resource_to_xml_element(entry["resource"], mode=mode)
                            if not child.ok or child.element is None:
                                return child
                            res_wrap.append(child.element)
                continue

            _serialize_generic(root, k, v)
        return XmlBuildResult(True, "OK", element=root)

    # best-effort
    root = ET.Element(_tag(rt))
    for k, v in resource.items():
        if k == "resourceType":
            continue
        _serialize_generic(root, k, v)
    return XmlBuildResult(True, "OK", element=root)
