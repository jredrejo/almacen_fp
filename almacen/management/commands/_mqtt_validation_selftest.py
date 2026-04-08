#!/usr/bin/env python
"""Self-test for MQTT payload validation pure functions.

Run directly: python almacen/management/commands/_mqtt_validation_selftest.py
Importing this file does NOT run tests (only when __name__ == "__main__").
"""

import os
import sys

# Django setup required because mqtt_listener imports models at module level
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "core.settings")

import django
django.setup()

# Import the validation functions from the management command module.
from almacen.management.commands.mqtt_listener import (
    EPC_RE,
    TS_RE,
    validate_epc,
    validate_payload,
    validate_timestamp,
)


def test_validate_epc():
    # Valid EPCs
    assert validate_epc("E2000017221101441890C7B5") == (True, None), "Valid EPC should pass"

    # Lowercase rejected
    ok, reason = validate_epc("e2000017221101441890c7b5")
    assert not ok and reason == "epc_format", f"Lowercase EPC should fail, got ({ok}, {reason})"

    # Invalid hex chars
    ok, reason = validate_epc("ZZZZZZZZ")
    assert not ok and reason == "epc_format", f"Non-hex EPC should fail, got ({ok}, {reason})"

    # Empty string
    ok, reason = validate_epc("")
    assert not ok and reason == "epc_format", f"Empty EPC should fail, got ({ok}, {reason})"

    # Non-string
    ok, reason = validate_epc(1234)
    assert not ok and reason == "epc_format", f"Non-str EPC should fail, got ({ok}, {reason})"

    print("  validate_epc: OK")


def test_validate_timestamp():
    # Valid UTC Z timestamp
    ok, val = validate_timestamp("2026-04-08T10:30:00Z")
    assert ok, "Valid timestamp should pass"
    assert val.tzinfo is not None, "Parsed timestamp should be tz-aware"

    # Naive (no Z) rejected
    ok, reason = validate_timestamp("2026-04-08T10:30:00")
    assert not ok and reason == "ts_format", f"Naive timestamp should fail, got ({ok}, {reason})"

    # Offset form rejected
    ok, reason = validate_timestamp("2026-04-08T10:30:00+02:00")
    assert not ok and reason == "ts_format", f"Offset timestamp should fail, got ({ok}, {reason})"

    # Space instead of T rejected
    ok, reason = validate_timestamp("2026-04-08 10:30:00Z")
    assert not ok and reason == "ts_format", f"Space-form timestamp should fail, got ({ok}, {reason})"

    print("  validate_timestamp: OK")


def test_validate_payload():
    valid_data = {
        "aula_id": "3",
        "epc": "E2000017221101441890C7B5",
        "timestamp": "2026-04-08T10:30:00Z",
    }

    # Valid payload
    ok, reason, parsed = validate_payload(valid_data, "3")
    assert ok and parsed is not None and parsed["epc"] == "E2000017221101441890C7B5", (
        f"Valid payload should pass, got ({ok}, {reason}, {parsed})"
    )

    # Missing timestamp (schema)
    data_no_ts = {"aula_id": "3", "epc": "E2000017221101441890C7B5"}
    ok, reason, _ = validate_payload(data_no_ts, "3")
    assert not ok and reason == "schema", f"Missing timestamp should fail with schema, got ({ok}, {reason})"

    # aula_mismatch
    ok, reason, _ = validate_payload(valid_data, "9")
    assert not ok and reason == "aula_mismatch", f"aula_id mismatch should fail, got ({ok}, {reason})"

    # Not a dict
    ok, reason, _ = validate_payload("not a dict", "3")
    assert not ok and reason == "schema", f"Non-dict should fail with schema, got ({ok}, {reason})"

    # Bad epc
    data_bad_epc = {
        "aula_id": "3",
        "epc": "zz",
        "timestamp": "2026-04-08T10:30:00Z",
    }
    ok, reason, _ = validate_payload(data_bad_epc, "3")
    assert not ok and reason == "epc_format", f"Bad EPC should fail, got ({ok}, {reason})"

    # Bad timestamp format
    data_bad_ts = {
        "aula_id": "3",
        "epc": "E2000017221101441890C7B5",
        "timestamp": "2026-04-08 10:30",
    }
    ok, reason, _ = validate_payload(data_bad_ts, "3")
    assert not ok and reason == "ts_format", f"Bad timestamp should fail, got ({ok}, {reason})"

    print("  validate_payload: OK")


def main():
    print("Running MQTT validation self-tests...")
    test_validate_epc()
    test_validate_timestamp()
    test_validate_payload()
    print("All tests passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
