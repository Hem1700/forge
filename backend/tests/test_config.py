from app.config import settings

def test_settings_has_required_fields():
    assert settings.database_url.startswith("postgresql")
    assert settings.redis_url.startswith("redis")
    assert settings.confidence_threshold == 0.75
    assert settings.thread_death_threshold == 5
