"""Ontology-driven checks, independent of publication metadata and OWL reasoning.

Class ancestry is used to check declared types, never to manufacture a missing
domain/range type from the very statement being validated.
"""
from __future__ import annotations

import json
import os
import re
from itertools import combinations

from rdflib import BNode, Graph, Literal, Namespace, URIRef
from rdflib.namespace import OWL, RDF, RDFS, XSD

DEFAULT_BASE = "http://localhost:3030/vietheritage"


def base_uri(value: str | None = None) -> str:
    return value if value is not None else os.environ.get("VH_BASE_URI", DEFAULT_BASE)


def term(value) -> str:
    if isinstance(value, BNode):
        return "_:blank"
    return value.n3() if isinstance(value, Literal) else str(value)


def issue(code: str, node=None, path=None, message: str = "", **extra) -> dict:
    result = {"code": code, "message": message}
    if node is not None:
        result["node"] = term(node)
    if path is not None:
        result["property"] = str(path)
    return result | extra


def report(errors: list[dict], **extra) -> dict:
    # Stable ordering and deduplication, including overlapping SHACL constraints.
    errors = [json.loads(value) for value in sorted({
        json.dumps(error, sort_keys=True, ensure_ascii=False) for error in errors
    })]
    return {"status": "FAIL" if errors else "PASS", "errors": errors, **extra}


class Contract:
    def __init__(self, data: Graph, ontology: Graph, base: str | None = None):
        self.data = data
        self.ontology = ontology
        self.base = base_uri(base)
        self.vh = Namespace(self.base + "/ontology/")
        self.classes = {node for node in ontology.subjects(RDF.type, OWL.Class)
                        if isinstance(node, URIRef) and str(node).startswith(str(self.vh))}
        self.object_properties = self.properties(OWL.ObjectProperty)
        self.datatype_properties = self.properties(OWL.DatatypeProperty)
        self._types: dict = {}

    def properties(self, kind) -> set:
        return {node for node in self.ontology.subjects(RDF.type, kind)
                if isinstance(node, URIRef) and str(node).startswith(str(self.vh))}

    def types(self, node) -> frozenset:
        if node in self._types:
            return self._types[node]
        found = set(self.data.objects(node, RDF.type)) | set(self.ontology.objects(node, RDF.type))
        pending = list(found)
        while pending:
            for parent in self.ontology.objects(pending.pop(), RDFS.subClassOf):
                if parent not in found:
                    found.add(parent)
                    pending.append(parent)
        self._types[node] = frozenset(found)
        return self._types[node]

    def matches(self, node, required) -> bool:
        if isinstance(node, Literal):
            return False
        if required == OWL.Thing:
            return isinstance(node, (URIRef, BNode))
        union = self.ontology.value(required, OWL.unionOf)
        if union is not None:
            return any(self.matches(node, member) for member in self.ontology.items(union))
        return required in self.types(node)

    def disjoint_pairs(self):
        for left, right in self.ontology.subject_objects(OWL.disjointWith):
            yield left, right, "AX-004"
        for group in self.ontology.subjects(RDF.type, OWL.AllDisjointClasses):
            members = self.ontology.value(group, OWL.members)
            for left, right in combinations(self.ontology.items(members), 2):
                yield left, right, "AX-004"
        for members in self.ontology.objects(None, OWL.disjointUnionOf):
            for left, right in combinations(self.ontology.items(members), 2):
                yield left, right, "AX-008"


def literal_matches(value, datatype) -> bool:
    if not isinstance(value, Literal) or value.language:
        return False
    if (value.datatype or XSD.string) != datatype or value.ill_typed:
        return False
    text = str(value)
    if datatype == XSD.integer:
        return re.fullmatch(r"[+-]?[0-9]+", text) is not None
    if datatype == XSD.gYear:
        match = re.fullmatch(
            r"(-?(?:[0-9]{4}|[1-9][0-9]{4,}))"
            r"(?:Z|[+-](?:(?:0[0-9]|1[0-3]):[0-5][0-9]|14:00))?", text,
        )
        return match is not None and int(match[1]) != 0
    return True


def _same_value(left, right) -> bool:
    if isinstance(left, Literal) and isinstance(right, Literal):
        try:
            return bool(left.eq(right))
        except (TypeError, ValueError):
            pass
    return left == right


def validate_axioms(data: Graph, ontology: Graph, *, base: str | None = None) -> dict:
    """Check AX-004/008 consistency and AX-009 values without assuming completeness.

    A missing disjoint-union member is not an OWL inconsistency under OWA;
    simultaneous membership of exclusive branches is.
    """
    contract = Contract(data, ontology, base)
    errors = []
    for node in set(data.subjects(RDF.type, None)):
        for left, right, axiom in contract.disjoint_pairs():
            if contract.matches(node, left) and contract.matches(node, right):
                errors.append(issue(
                    "ONTOLOGY_INCONSISTENT", node, RDF.type,
                    f"Member of disjoint classes {left} and {right}.", axiom=axiom,
                ))
    functional = contract.datatype_properties & set(ontology.subjects(RDF.type, OWL.FunctionalProperty))
    for prop in functional:
        for node in set(data.subjects(prop, None)):
            values = []
            for value in sorted(data.objects(node, prop), key=term):
                if not any(_same_value(value, other) for other in values):
                    values.append(value)
            if len(values) > 1:
                errors.append(issue(
                    "CARDINALITY_VIOLATION", node, prop, "Multiple distinct functional values.",
                    axiom="AX-009", values=[term(value) for value in values],
                ))
    axioms = {axiom: "FAIL" if any(e.get("axiom") == axiom for e in errors) else "PASS"
              for axiom in ("AX-004", "AX-008", "AX-009")}
    return report(errors, axioms=axioms)


def validate_semantics(data: Graph, ontology: Graph, *, base: str | None = None) -> dict:
    """Validate semantic fixtures or an A-Box; publication checks are separate."""
    contract = Contract(data, ontology, base)
    result = validate_axioms(data, ontology, base=base)
    errors = result["errors"]
    properties = contract.object_properties | contract.datatype_properties
    for subject, predicate, obj in data:
        if not isinstance(subject, (URIRef, BNode)) or not isinstance(predicate, URIRef):
            errors.append(issue("INVALID_RDF_TERM", subject, predicate, "Invalid RDF subject or predicate."))
        if str(predicate).startswith(str(contract.vh)) and predicate not in properties:
            errors.append(issue("NAMESPACE_VIOLATION", subject, predicate, "Unknown project property."))
        if predicate == RDF.type and str(obj).startswith(str(contract.vh)) and obj not in contract.classes:
            errors.append(issue("NAMESPACE_VIOLATION", subject, predicate, f"Unknown project class: {obj}"))
        if predicate not in properties:
            continue
        for domain in ontology.objects(predicate, RDFS.domain):
            if not contract.matches(subject, domain):
                errors.append(issue("DOMAIN_VIOLATION", subject, predicate, "Subject does not meet the ontology domain."))
        for required in ontology.objects(predicate, RDFS.range):
            if predicate in contract.datatype_properties:
                if not literal_matches(obj, required):
                    errors.append(issue("DATATYPE_VIOLATION", subject, predicate, f"Expected {required}; got {term(obj)}."))
            elif not contract.matches(obj, required):
                errors.append(issue("RANGE_VIOLATION", subject, predicate, f"Target {term(obj)} must be a {required}."))
        if (predicate in (contract.vh.builtBy, contract.vh.associatedWithPerson)
                and contract.matches(obj, contract.vh.Organization)):
            errors.append(issue("RANGE_VIOLATION", subject, predicate, "An Organization cannot be a person target."))
    for node in set(data.subjects(RDF.type, None)):
        if {contract.vh.HistoricalPerson, contract.vh.Organization} <= contract.types(node):
            errors.append(issue("INCOMPATIBLE_TYPES", node, RDF.type, "Organization and HistoricalPerson cannot describe the same project entity."))
    return report(errors, axioms=result["axioms"])
