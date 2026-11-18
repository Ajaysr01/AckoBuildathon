from datetime import date
from typing import Any, Dict, List


def apply_publish_policy(comparison: Dict[str, Any], today: date = None) -> Dict[str, Any]:
    today = today or date.today()
    decisions = []
    blocking = []
    warnings = []
    for change in comparison["changes"]:
        if change.get("severity") == "breaking" and change.get("affected_consumers"):
            blocking.append(change)
        sunset = change.get("sunset_date")
        deprecated = change.get("deprecated", False)
        if sunset or deprecated:
            if sunset:
                try:
                    expired = date.fromisoformat(str(sunset)[:10]) < today
                except ValueError:
                    expired = False
                    warnings.append({"location": change["location"], "message": "Unrecognized x-sunset date '{}'.".format(sunset)})
            else:
                expired = False
            if expired and change.get("affected_consumers"):
                blocking.append(change)
            elif change.get("affected_consumers"):
                warnings.append({"location": change["location"], "message": "Deprecated/sunset element is used by declared consumers{}.".format(
                    " until {}".format(sunset) if sunset else ""
                )})
    for change in comparison["changes"]:
        decisions.append({"location": change["location"], "publish_blocked": change in blocking})
    unique_blockers = {change["location"]: change for change in blocking}
    return {
        "allowed": not unique_blockers,
        "blockers": list(unique_blockers.values()),
        "warnings": warnings,
        "policy_version": "provisional-v1",
    }
