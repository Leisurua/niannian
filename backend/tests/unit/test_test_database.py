import pytest

from backend.tests.support import require_test_database


@pytest.mark.parametrize('url', [
    'sqlite:///niannian_test', 'postgresql+psycopg://localhost/production',
    'postgresql+psycopg://localhost/niannian_test?dbname=production',
    'postgresql+psycopg://localhost/niannian_test?options=-csearch_path=shared',
    'not-a-database-url',
])
def test_database_reset_refuses_unsafe_targets(url):
    with pytest.raises(ValueError):
        require_test_database(url)


def test_database_reset_accepts_explicit_test_database():
    assert require_test_database('postgresql+psycopg://localhost/niannian_test').database == 'niannian_test'
