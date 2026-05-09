"""Tests for clintrial.config."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from clintrial.config import Settings, get_settings

pytestmark = pytest.mark.unit


class TestSettings:
    def test_defaults(self) -> None:
        # Construct directly, not via env, to test defaults
        s = Settings(_env_file=None)  # type: ignore[call-arg]
        assert s.aws_region == "eu-west-2"
        assert s.app_env == "dev"
        assert s.log_level == "INFO"
        assert s.api_port == 8000

    def test_invalid_app_env_rejected(self) -> None:
        with pytest.raises(ValidationError):
            Settings(_env_file=None, app_env="production")  # type: ignore[call-arg, arg-type]

    def test_invalid_log_level_rejected(self) -> None:
        with pytest.raises(ValidationError):
            Settings(_env_file=None, log_level="VERBOSE")  # type: ignore[call-arg, arg-type]

    def test_port_out_of_range_rejected(self) -> None:
        with pytest.raises(ValidationError):
            Settings(_env_file=None, api_port=70_000)  # type: ignore[call-arg]

    def test_negative_producer_total_rejected(self) -> None:
        with pytest.raises(ValidationError):
            Settings(_env_file=None, producer_total_events=-1)  # type: ignore[call-arg]

    def test_invalid_region_rejected(self) -> None:
        with pytest.raises(ValidationError, match="aws_region"):
            Settings(_env_file=None, aws_region="invalid")  # type: ignore[call-arg]

    def test_cors_origin_list_parses(self) -> None:
        s = Settings(  # type: ignore[call-arg]
            _env_file=None,
            api_cors_origins="http://a.com, http://b.com ,http://c.com",
        )
        assert s.cors_origin_list == ["http://a.com", "http://b.com", "http://c.com"]

    def test_is_production_flag(self) -> None:
        dev = Settings(_env_file=None, app_env="dev")  # type: ignore[call-arg]
        prod = Settings(_env_file=None, app_env="prod")  # type: ignore[call-arg]
        assert dev.is_production is False
        assert prod.is_production is True

    def test_extra_fields_rejected(self) -> None:
        with pytest.raises(ValidationError):
            Settings(_env_file=None, made_up_field="oops")  # type: ignore[call-arg]


class TestSingleton:
    def test_get_settings_returns_same_instance(self) -> None:
        # Clear cache so the test starts fresh
        get_settings.cache_clear()
        a = get_settings()
        b = get_settings()
        assert a is b

    def test_cache_clear_yields_new_instance(self) -> None:
        a = get_settings()
        get_settings.cache_clear()
        b = get_settings()
        # New instance after cache clear (different object identity)
        assert a is not b
