.PHONY: test-contract test-all

# Run contract integration tests (MQTT E2E + REST API)
# Requires: uv installed, Django DB migrated
test-contract:
	uv run pytest tests/test_contract_mqtt_e2e.py tests/test_api.py -v --tb=short

# Run all project tests
test-all:
	uv run pytest -v --tb=short
