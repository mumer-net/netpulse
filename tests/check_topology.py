"""Validate netpulse.clab.yml against containerlab's published JSON schema (run in CI)."""

import json
import sys
import urllib.request
from pathlib import Path

import jsonschema
import yaml

SCHEMA_URL = "https://raw.githubusercontent.com/srl-labs/containerlab/v0.79.0/schemas/clab.schema.json"


def main() -> int:
    raw = urllib.request.urlopen(SCHEMA_URL, timeout=30).read().decode()
    # The schema uses ECMAScript \p{L} and \p{N} classes, which Python's re module doesn't support.
    raw = raw.replace("\\\\p{L}", "a-zA-Z").replace("\\\\p{N}", "0-9")
    schema = json.loads(raw)
    topology = yaml.safe_load((Path(__file__).resolve().parents[1] / "netpulse.clab.yml").read_text())
    errors = list(jsonschema.validators.validator_for(schema)(schema).iter_errors(topology))
    for error in errors:
        print(f"{list(error.path)}: {error.message[:200]}")
    print(f"{len(errors)} schema errors")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
