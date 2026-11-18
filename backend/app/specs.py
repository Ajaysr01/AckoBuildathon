import json
from pathlib import Path
from typing import Any, Dict, List, Tuple

import yaml
from openapi_spec_validator import validate


class SpecError(ValueError):
    pass


def parse_document(raw: str, filename: str) -> Dict[str, Any]:
    if Path(filename).suffix.lower() not in {".yaml", ".yml", ".json"}:
        raise SpecError("OpenAPI file must use YAML (.yaml/.yml) or JSON (.json).")
    try:
        parsed = json.loads(raw) if filename.lower().endswith(".json") else yaml.safe_load(raw)
    except (ValueError, yaml.YAMLError) as exc:
        raise SpecError("Could not parse specification: {}".format(exc))
    if not isinstance(parsed, dict):
        raise SpecError("Specification root must be an object.")
    return parsed


def validate_document(document: Dict[str, Any]) -> List[str]:
    errors = []
    if document.get("openapi") != "3.0.3":
        errors.append("openapi must be 3.0.3.")
    info = document.get("info")
    if not isinstance(info, dict):
        errors.append("info must be an object.")
    elif not isinstance(info.get("title"), str) or not info["title"].strip():
        errors.append("info.title is required.")
    elif not isinstance(info.get("version"), str) or not info["version"].strip():
        errors.append("info.version is required.")
    paths = document.get("paths")
    if not isinstance(paths, dict):
        errors.append("paths must be an object.")
    else:
        for path, path_item in paths.items():
            if not isinstance(path_item, dict):
                errors.append("paths.{} must be an object.".format(path))
                continue
            for method, operation in path_item.items():
                if method.lower() not in {"get", "put", "post", "delete", "options", "head", "patch", "trace", "parameters", "$ref", "summary", "description", "servers"}:
                    errors.append("paths.{} has unsupported path-item key '{}'.".format(path, method))
                    continue
                if method.lower() in {"get", "put", "post", "delete", "options", "head", "patch", "trace"} and not isinstance(operation, dict):
                    errors.append("paths.{}.{} must be an object.".format(path, method))
                elif method.lower() in {"get", "put", "post", "delete", "options", "head", "patch", "trace"} and not isinstance(operation.get("responses"), dict):
                    errors.append("paths.{}.{} must define responses.".format(path, method))
    if not errors:
        try:
            validate(document)
        except Exception as exc:
            errors.append("OpenAPI validation failed: {}".format(str(exc).splitlines()[0]))
    return errors


def _validate_refs(node: Any, errors: List[str], root: Dict[str, Any], location: str = "") -> None:
    if isinstance(node, dict):
        ref = node.get("$ref")
        if isinstance(ref, str) and ref.startswith("#/"):
            target = None
            # Local references are resolved from the document root by the caller below.
            target = root
            for segment in ref[2:].split("/"):
                segment = segment.replace("~1", "/").replace("~0", "~")
                if not isinstance(target, dict) or segment not in target:
                    target = None
                    break
                target = target[segment]
            if target is None:
                errors.append("Unresolved local $ref '{}' at {}.".format(ref, location or "/"))
        elif isinstance(ref, str) and not ref.startswith("#/"):
            errors.append("External $ref '{}' is not supported; references must stay within this file.".format(ref))
        for key, value in node.items():
            _validate_refs(value, errors, root, "{}.{}".format(location, key))
    elif isinstance(node, list):
        for index, value in enumerate(node):
            _validate_refs(value, errors, root, "{}[{}]".format(location, index))


def validate_with_refs(document: Dict[str, Any]) -> List[str]:
    errors = []
    _validate_refs(document, errors, document)
    if not errors:
        errors.extend(validate_document(document))
    return errors


def version_from_document(document: Dict[str, Any]) -> str:
    info = document.get("info") or {}
    version = info.get("version") if isinstance(info, dict) else None
    if not isinstance(version, str) or not version.strip():
        raise SpecError("info.version is required and must be a non-empty string.")
    return version.strip()


def parse_and_validate(raw: str, filename: str) -> Tuple[Dict[str, Any], List[str]]:
    document = parse_document(raw, filename)
    return document, validate_with_refs(document)
