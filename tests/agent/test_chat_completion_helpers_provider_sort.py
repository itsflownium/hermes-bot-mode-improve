from agent.provider_routing import validate_sort


def test_validated_openrouter_provider_sort_accepts_valid_values():
    assert validate_sort("price") == "price"
    assert validate_sort(" latency ") == "latency"
    assert validate_sort("THROUGHPUT") == "throughput"


def test_validated_openrouter_provider_sort_rejects_invalid_values():
    assert validate_sort("intelligence") is None
    assert validate_sort("") is None
    assert validate_sort(None) is None
