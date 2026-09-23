from pathlib import Path

import yaml


def test_frozen_openapi_is_parseable() -> None:
    schema = yaml.safe_load(Path(__file__).parents[2].joinpath("docs/openapi.yaml").read_text(encoding="utf-8"))
    assert schema["openapi"].startswith("3.")
    assert schema["info"]["title"] == "NianNian API"
