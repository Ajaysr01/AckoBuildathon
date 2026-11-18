from copy import deepcopy
from typing import Any, Dict, Tuple

from sqlalchemy.orm import Session

from .models import ConsumerUsage, Service, SpecVersion
from .policy import apply_publish_policy

METHODS = {"get", "put", "post", "delete", "options", "head", "patch", "trace"}


def compare_specs(db: Session, before: SpecVersion, after: SpecVersion) -> Dict[str, Any]:
    if before.service_id != after.service_id:
        raise ValueError("Only versions belonging to the same provider can be compared.")
    if before.validation_status != "valid" or after.validation_status != "valid":
        raise ValueError("Both specs must be valid before they can be compared.")

    provider = db.get(Service, before.service_id)
    usages = db.query(ConsumerUsage).filter(ConsumerUsage.provider_service_id == before.service_id).all()
    consumers = {row.id: db.get(Service, row.consumer_service_id) for row in usages}
    findings = []
    old_paths = before.document.get("paths", {})
    new_paths = after.document.get("paths", {})
    old_ops = _operations(old_paths)
    new_ops = _operations(new_paths)

    old_keys = set(old_ops)
    new_keys = set(new_ops)
    old_by_shape = {(_normalize_path(path), method): (path, method) for path, method in old_keys}
    new_by_shape = {(_normalize_path(path), method): (path, method) for path, method in new_keys}
    renamed = []
    for shape in sorted(set(old_by_shape) & set(new_by_shape)):
        old_key, new_key = old_by_shape[shape], new_by_shape[shape]
        if old_key != new_key:
            renamed.append((old_key, new_key))
            old_keys.discard(old_key)
            new_keys.discard(new_key)
            findings.append(_finding(
                kind="path_parameter_renamed", location="{} {} -> {}".format(old_key[1].upper(), old_key[0], new_key[0]),
                before=old_key[0], after=new_key[0], direction="operation",
                summary="Path parameter name changed, but the endpoint shape is unchanged.",
                breaking=False, endpoint_key=old_key,
            ))
    for key in sorted(old_keys - new_keys):
        path, method = key
        findings.append(_finding(
            kind="operation_removed", location="{} {}".format(method.upper(), path),
            before="present", after="removed", direction="operation",
            summary="The {} {} operation was removed.".format(method.upper(), path),
            breaking=True, endpoint_key=key,
        ))
    for key in sorted(new_keys - old_keys):
        path, method = key
        findings.append(_finding(
            kind="operation_added", location="{} {}".format(method.upper(), path),
            before="absent", after="present", direction="operation",
            summary="The {} {} operation was added.".format(method.upper(), path),
            breaking=False, endpoint_key=key,
        ))
    comparisons = [(key, key) for key in sorted(old_keys & new_keys)] + renamed
    for old_key, new_key in comparisons:
        old_path, method = old_key
        new_path = new_key[0]
        old_op, new_op = old_ops[old_key], new_ops[new_key]
        if bool(old_op.get("x-internal")) != bool(new_op.get("x-internal")):
            now_internal = bool(new_op.get("x-internal"))
            findings.append(_finding(
                "internal_status_changed", "{} {} x-internal".format(method.upper(), new_path),
                bool(old_op.get("x-internal")), now_internal, "operation",
                "Operation is now marked internal." if now_internal else "Operation is no longer marked internal.",
                now_internal, old_key,
            ))
        findings.extend(_compare_parameters(before.document, after.document, old_path, new_path, method, old_op, new_op, old_key))
        findings.extend(_compare_body(before.document, after.document, old_path, method, old_op, new_op, old_key))
        findings.extend(_compare_responses(before.document, after.document, old_path, method, old_op, new_op, old_key))

    findings.extend(_lifecycle_findings(after.document, new_ops))

    for finding in findings:
        affected = []
        for usage in usages:
            if not _finding_applies_to_usage(finding, usage, before.document, after.document):
                continue
            if _usage_impacted(finding, usage):
                consumer = consumers.get(usage.id)
                if consumer:
                    affected.append({"name": consumer.name, "team": consumer.owner})
        unique = {(item["name"], item["team"]): item for item in affected}
        finding["affected_consumers"] = list(unique.values())
        finding["severity"] = "breaking" if finding["breaking"] else "non-breaking"
        finding["publish_blocked"] = bool(finding["breaking"] and finding["affected_consumers"])
        finding.pop("breaking", None)
        finding.pop("endpoint_key", None)
        finding.pop("direction", None)

    policy_result = apply_publish_policy({"changes": findings})
    blocked_locations = {item["location"] for item in policy_result["blockers"]}
    for finding in findings:
        finding["publish_blocked"] = finding["location"] in blocked_locations
        if finding["publish_blocked"]:
            finding["policy_reason"] = policy_result["block_reasons"].get(
                finding["location"], "This finding violates the current publish policy.")
    if policy_result["warnings"]:
        warning_locations = {item["location"] for item in policy_result["warnings"]}
        for finding in findings:
            if finding["location"] in warning_locations:
                finding["policy_warning"] = True

    return {
        "provider": provider.name if provider else None,
        "from": {"id": before.id, "version": before.version, "source_filename": before.source_filename},
        "to": {"id": after.id, "version": after.version, "source_filename": after.source_filename},
        "summary": {
            "change_count": len(findings),
            "breaking_count": sum(1 for finding in findings if finding["severity"] == "breaking"),
            "affected_consumer_count": len({consumer["name"] for finding in findings for consumer in finding["affected_consumers"]}),
            "publish_blocked": not policy_result["allowed"],
            "policy_blocker_count": len(policy_result["blockers"]),
            "warning_count": len(policy_result["warnings"]),
        },
        "changes": findings,
    }


def _operations(paths: Dict[str, Any]) -> Dict[Tuple[str, str], Dict[str, Any]]:
    result = {}
    for path, path_item in paths.items():
        if not isinstance(path_item, dict):
            continue
        for method, operation in path_item.items():
            if method.lower() in METHODS and isinstance(operation, dict):
                result[(path, method.lower())] = operation
    return result


def _compare_parameters(old_root, new_root, old_path, new_path, method, old_op, new_op, endpoint_key):
    old_params = _parameters(old_root, old_op, old_path)
    new_params = _parameters(new_root, new_op, new_path)
    findings = []
    for key in sorted(set(old_params) | set(new_params)):
        old, new = old_params.get(key), new_params.get(key)
        old_name = old.get("name") if old else None
        new_name = new.get("name") if new else None
        name = new_name or old_name or key
        location = "{} {} parameter {}".format(method.upper(), new_path, name)
        if old is None:
            finding = _finding("parameter_added", location, "absent", _schema_summary(new), "request",
                                     "Parameter '{}' was added to {} {}.".format(name, method.upper(), new_path),
                                     bool(new.get("required")), endpoint_key, field_path=name, metadata_schema=new.get("schema"))
            _copy_lifecycle(new, finding)
            findings.append(finding)
        elif new is None:
            finding = _finding("parameter_removed", location, _schema_summary(old), "removed", "request",
                                     "Parameter '{}' was removed from {} {}.".format(name, method.upper(), old_path),
                                     True, endpoint_key, field_path=name, metadata_schema=old.get("schema"))
            _copy_lifecycle(old, finding)
            findings.append(finding)
        else:
            if old_name != new_name and old.get("in") == "path":
                findings.append(_finding("path_parameter_renamed", "{} {} parameter {} -> {}".format(
                    method.upper(), new_path, old_name, new_name), old_name, new_name, "operation",
                    "Path parameter was renamed; the endpoint shape is unchanged.", False, endpoint_key))
            old_schema, new_schema = old.get("schema", {}), new.get("schema", {})
            findings.extend(_compare_schema(old_root, new_root, old_schema, new_schema, "parameters.{}".format(name),
                                            endpoint_key, "request", name))
            if old.get("required", False) != new.get("required", False):
                required = bool(new.get("required"))
                findings.append(_finding("parameter_required", location, old.get("required", False), required,
                                         "request", "Parameter '{}' is now {}.".format(name, "required" if required else "optional"),
                                         required, endpoint_key, field_path=name))
    return findings


def _parameters(root, operation, path):
    result = {}
    path_item = root.get("paths", {}).get(path, {})
    parameters = list(path_item.get("parameters", [])) + list(operation.get("parameters", []))
    path_index = 0
    for parameter in parameters:
        if isinstance(parameter, dict):
            parameter = _resolve(root, parameter)
            location = parameter.get("in")
            if location == "path":
                key = "path:#{}".format(path_index)
                path_index += 1
            else:
                key = "{}:{}".format(location, parameter.get("name"))
            result[key] = parameter
    return result


def _compare_body(old_root, new_root, path, method, old_op, new_op, endpoint_key):
    old_schema = _request_schema(old_op)
    new_schema = _request_schema(new_op)
    if old_schema is None and new_schema is None:
        return []
    if old_schema is None:
        return _compare_schema({}, new_root, {}, new_schema, "requestBody", endpoint_key, "request", "")
    if new_schema is None:
        return [_finding("request_body_removed", "{} {} request body".format(method.upper(), path), "present", "removed",
                         "request", "The request body was removed.", True, endpoint_key, field_path="")]
    return _compare_schema(old_root, new_root, old_schema, new_schema, "requestBody", endpoint_key, "request", "")


def _compare_responses(old_root, new_root, path, method, old_op, new_op, endpoint_key):
    findings = []
    old_responses, new_responses = old_op.get("responses", {}), new_op.get("responses", {})
    for status in sorted(set(old_responses) | set(new_responses)):
        old, new = old_responses.get(status), new_responses.get(status)
        if old is None:
            findings.append(_finding("response_status_added", "{} {} response {}".format(method.upper(), path, status),
                                     "absent", "present", "response", "Response status {} was added.".format(status),
                                     False, endpoint_key, field_path=""))
            continue
        if new is None:
            findings.append(_finding("response_status_removed", "{} {} response {}".format(method.upper(), path, status),
                                     "present", "removed", "response", "Response status {} was removed.".format(status),
                                     True, endpoint_key, field_path=""))
            continue
        old_schema, new_schema = _response_schema(old), _response_schema(new)
        if old_schema is None and new_schema is None:
            continue
        if old_schema is None or new_schema is None:
            findings.append(_finding("response_body_changed", "{} {} response {}".format(method.upper(), path, status),
                                     "absent" if old_schema is None else "present",
                                     "absent" if new_schema is None else "present", "response",
                                     "Response body for status {} changed.".format(status), True,
                                     endpoint_key, field_path=""))
        else:
            findings.extend(_compare_schema(old_root, new_root, old_schema, new_schema,
                                            "responses.{}.body".format(status), endpoint_key, "response", ""))
    return findings


def _compare_schema(old_root, new_root, old_schema, new_schema, location, endpoint_key, direction, field_path):
    old_schema = _resolve(old_root, old_schema)
    new_schema = _resolve(new_root, new_schema)
    if not isinstance(old_schema, dict) or not isinstance(new_schema, dict):
        if old_schema != new_schema:
            return [_finding("schema_changed", location, _schema_summary(old_schema), _schema_summary(new_schema), direction,
                             "Schema at {} changed.".format(location), True, endpoint_key, field_path)]
        return []
    findings = []
    old_type, new_type = old_schema.get("type"), new_schema.get("type")
    if old_type != new_type and (old_type is not None or new_type is not None):
        findings.append(_finding("type_changed", location + ".type", old_type, new_type, direction,
                                 "The data type at {} changed from {} to {}.".format(location, old_type, new_type),
                                 True, endpoint_key, field_path))
    for key in ("format", "enum", "minimum", "maximum", "minLength", "maxLength", "pattern", "nullable"):
        if old_schema.get(key) != new_schema.get(key) and (key in old_schema or key in new_schema):
            old_value, new_value = old_schema.get(key), new_schema.get(key)
            breaking = _constraint_breaking(key, old_value, new_value, direction)
            findings.append(_finding("{}_changed".format(key), location + "." + key, old_value, new_value, direction,
                                     "Constraint '{}' changed at {}.".format(key, location), breaking,
                                     endpoint_key, field_path))
    old_required = set(old_schema.get("required", []) or [])
    new_required = set(new_schema.get("required", []) or [])
    old_props = old_schema.get("properties", {}) or {}
    new_props = new_schema.get("properties", {}) or {}
    for name in sorted(set(old_props) | set(new_props)):
        child_path = _join_path(field_path, name)
        child_loc = location + ".properties." + name
        old_child, new_child = old_props.get(name), new_props.get(name)
        if old_child is None:
            is_required = name in new_required
            finding = _finding("field_added", child_loc, "absent", _schema_summary(new_child), direction,
                                     "Field '{}' was added{}.".format(child_path, " and is required" if is_required else ""),
                                     direction == "request" and is_required, endpoint_key, child_path, new_child)
            _copy_lifecycle(new_child or {}, finding)
            findings.append(finding)
        elif new_child is None:
            finding = _finding("field_removed", child_loc, _schema_summary(old_child), "removed", direction,
                               "Field '{}' was removed.".format(child_path), True, endpoint_key, child_path, old_child)
            _copy_lifecycle(old_child or {}, finding)
            findings.append(finding)
        else:
            findings.extend(_compare_schema(old_root, new_root, old_child, new_child, child_loc, endpoint_key, direction, child_path))
            if (name in old_required) != (name in new_required):
                now_required = name in new_required
                finding = _finding("field_required", child_loc + ".required", name in old_required, now_required,
                                         direction, "Field '{}' is now {}.".format(child_path, "required" if now_required else "optional"),
                                         direction == "request" and now_required, endpoint_key, child_path, new_child)
                _copy_lifecycle(new_child or old_child or {}, finding)
                findings.append(finding)
    old_items, new_items = old_schema.get("items"), new_schema.get("items")
    if old_items is not None and new_items is not None:
        findings.extend(_compare_schema(old_root, new_root, old_items, new_items, location + ".items", endpoint_key,
                                        direction, _join_path(field_path, "[]")))
    elif old_items != new_items:
        findings.append(_finding("array_items_changed", location + ".items", _schema_summary(old_items),
                                 _schema_summary(new_items), direction, "Array item schema changed at {}.".format(location),
                                 True, endpoint_key, _join_path(field_path, "[]")))
    return findings


def _request_schema(operation):
    body = operation.get("requestBody", {})
    content = body.get("content", {}) if isinstance(body, dict) else {}
    media = content.get("application/json") or next(iter(content.values()), {}) if content else {}
    return media.get("schema") if isinstance(media, dict) else None


def _response_schema(response):
    content = response.get("content", {}) if isinstance(response, dict) else {}
    media = content.get("application/json") or next(iter(content.values()), {}) if content else {}
    return media.get("schema") if isinstance(media, dict) else None


def _resolve(root, schema):
    if not isinstance(schema, dict) or "$ref" not in schema:
        return schema or {}
    ref = schema["$ref"]
    if not ref.startswith("#/"):
        return schema
    target = root
    for part in ref[2:].split("/"):
        part = part.replace("~1", "/").replace("~0", "~")
        target = target.get(part) if isinstance(target, dict) else None
        if target is None:
            return schema
    resolved = deepcopy(target)
    resolved.update({key: value for key, value in schema.items() if key != "$ref"})
    return resolved


def _constraint_breaking(key, old, new, direction):
    if key == "enum":
        if old is None:
            return direction == "request"
        if new is None:
            return False
        return bool(set(old) - set(new)) if direction == "request" else bool(set(new) - set(old))
    if key in {"minimum", "minLength"}:
        return new is not None and (old is None or new > old)
    if key in {"maximum", "maxLength"}:
        return new is not None and (old is None or new < old)
    if key in {"format", "pattern"}:
        return new != old
    if key == "nullable":
        return old is True and new is False
    return new != old


def _finding(kind, location, before, after, direction, summary, breaking, endpoint_key, field_path="", metadata_schema=None):
    finding = {"kind": kind, "location": location, "before": before, "after": after, "direction": direction,
            "summary": summary, "breaking": breaking, "endpoint_key": endpoint_key,
            "field_path": field_path or ""}
    if isinstance(metadata_schema, dict):
        _copy_lifecycle(metadata_schema, finding)
    return finding


def _operation_usage_matches(endpoint_key, usage):
    path, method = endpoint_key
    if method != usage.method.lower():
        return False
    return _normalize_path(path) == _normalize_path(usage.path)


def _normalize_path(path):
    return "/".join("{}" if part.startswith("{") and part.endswith("}") else part for part in path.strip("/").split("/"))


def _usage_impacted(finding, usage):
    if finding["kind"] in {"operation_removed", "response_status_removed", "response_body_changed"}:
        return True
    path = finding["field_path"]
    if finding["direction"] == "request":
        declared = usage.sends or []
    elif finding["direction"] == "response":
        declared = usage.reads or []
    else:
        return True
    if finding["direction"] == "request" and finding["kind"] in {"field_added", "field_required", "parameter_added", "parameter_required"} and finding["breaking"]:
        # Consumers use this operation but have not declared sending the newly required input.
        return not any(_field_matches(finding["field_path"], used) for used in declared)
    if not path:
        return bool(declared)
    return any(_field_matches(path, used) for used in declared)


def _finding_applies_to_usage(finding, usage, before, after):
    if _operation_usage_matches(finding["endpoint_key"], usage):
        return True
    if finding["kind"] in {"operation_removed", "operation_added"}:
        return False
    if not finding["field_path"]:
        return False
    used_path = usage.path
    method = usage.method.lower()
    if _normalize_path(finding["endpoint_key"][0]) == _normalize_path(used_path):
        return False
    if not any(_field_matches(finding["field_path"], item) for item in (usage.sends or []) + (usage.reads or [])):
        # A newly-required request field is impactful precisely when it is not declared as sent.
        if not (finding["direction"] == "request" and finding["breaking"] and finding["kind"] in {"field_added", "field_required", "parameter_added", "parameter_required"}):
            return False
    for document in (before, after):
        operation = _operations(document.get("paths", {})).get((used_path, method))
        if not operation:
            operation = next((op for (path, verb), op in _operations(document.get("paths", {})).items()
                              if verb == method and _normalize_path(path) == _normalize_path(used_path)), None)
        if operation and _operation_contains_field(document, operation, finding["direction"], finding["field_path"]):
            return True
    return False


def _operation_contains_field(document, operation, direction, field_path):
    schemas = []
    if direction == "request":
        schema = _request_schema(operation)
        if schema is not None:
            schemas.append(schema)
        for parameter in operation.get("parameters", []):
            parameter = _resolve(document, parameter)
            if parameter.get("schema"):
                schemas.append(parameter["schema"])
    elif direction == "response":
        for response in operation.get("responses", {}).values():
            schema = _response_schema(response)
            if schema is not None:
                schemas.append(schema)
    return any(_schema_has_path(document, schema, field_path.split(".")) for schema in schemas)


def _schema_has_path(root, schema, parts):
    schema = _resolve(root, schema)
    if not parts:
        return True
    part = parts[0]
    if part == "[]":
        items = schema.get("items") if isinstance(schema, dict) else None
        if items:
            return _schema_has_path(root, items, parts[1:])
        # The same shared component may be returned as an object by one operation
        # and as an array item by another; the consumer path need not include [].
        return _schema_has_path(root, schema, parts[1:])
    if part == "[*]":
        items = schema.get("items") if isinstance(schema, dict) else None
        return bool(items) and _schema_has_path(root, items, parts[1:])
    if isinstance(schema, dict) and schema.get("type") == "array" and schema.get("items"):
        if _schema_has_path(root, schema["items"], parts):
            return True
    properties = schema.get("properties", {}) if isinstance(schema, dict) else {}
    child = properties.get(part)
    return child is not None and _schema_has_path(root, child, parts[1:])


def _field_matches(changed, used):
    def normalize(value):
        value = value.replace("[]", "[*]").strip(".")
        return value.removeprefix("[*].")
    changed, used = normalize(changed), normalize(used)
    if changed == used:
        return True
    return changed.startswith(used + ".") or used.startswith(changed + ".") or changed.startswith(used + "[*]") or used.startswith(changed + "[*]")


def _join_path(parent, child):
    if not parent:
        return child
    if child == "[]":
        return parent + "[]"
    return parent + "." + child


def _schema_summary(schema):
    if not isinstance(schema, dict):
        return schema
    return {key: schema[key] for key in ("type", "format", "enum", "required") if key in schema}


def _copy_lifecycle(schema, finding):
    if schema.get("deprecated"):
        finding["deprecated"] = True
    if schema.get("x-sunset"):
        finding["sunset_date"] = schema["x-sunset"]


def _lifecycle_findings(document, operations):
    findings = []
    for (path, method), operation in operations.items():
        if operation.get("deprecated") or operation.get("x-sunset"):
            finding = _finding("lifecycle", "{} {}".format(method.upper(), path), "present", "present",
                               "operation", "Operation is deprecated or has a sunset date.", False, (path, method))
            _copy_lifecycle(operation, finding)
            findings.append(finding)
        request_schema = _request_schema(operation)
        if request_schema is not None:
            _collect_schema_lifecycle(document, request_schema, "requestBody", "request", (path, method), findings)
        for parameter in operation.get("parameters", []):
            parameter = _resolve(document, parameter)
            if parameter.get("schema") is not None:
                _collect_schema_lifecycle(document, parameter["schema"], "parameters." + str(parameter.get("name", "")),
                                          "request", (path, method), findings)
        for status, response in operation.get("responses", {}).items():
            schema = _response_schema(response)
            if schema is not None:
                _collect_schema_lifecycle(document, schema, "responses.{}.body".format(status), "response", (path, method), findings)
    return findings


def _collect_schema_lifecycle(root, schema, location, direction, endpoint_key, findings, field_path="", visited=None):
    visited = visited or set()
    ref = schema.get("$ref") if isinstance(schema, dict) else None
    if ref:
        if ref in visited:
            return
        visited = set(visited)
        visited.add(ref)
    resolved = _resolve(root, schema)
    if not isinstance(resolved, dict):
        return
    if resolved.get("deprecated") or resolved.get("x-sunset"):
        finding = _finding("lifecycle", location, "present", "present", direction,
                           "Field '{}' is deprecated or has a sunset date.".format(field_path or location),
                           False, endpoint_key, field_path)
        _copy_lifecycle(resolved, finding)
        findings.append(finding)
    for name, child in (resolved.get("properties", {}) or {}).items():
        child_path = _join_path(field_path, name)
        _collect_schema_lifecycle(root, child, location + ".properties." + name, direction, endpoint_key, findings, child_path, visited)
    if resolved.get("items"):
        _collect_schema_lifecycle(root, resolved["items"], location + ".items", direction, endpoint_key, findings,
                                  _join_path(field_path, "[]"), visited)
