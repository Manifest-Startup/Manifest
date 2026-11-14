import pytest
from app.services.articles_of_incorporation_service import ArticlesOfIncorporation

@pytest.fixture
def valid_kwargs():
    return {
        'business_name': 'TestCo',
        'business_purpose': 'Testing',
        'business_address': '123 Test St',
        'registered_agent': 'Agent Smith',
        'shares_authorized': 1000,
        'incorporator_name': 'Alice'
    }

def test_constructor_and_properties(valid_kwargs):
    aoi = ArticlesOfIncorporation(None, **valid_kwargs)
    assert aoi.business_name == 'TestCo'
    assert aoi.business_purpose == 'Testing'
    assert aoi.business_address == '123 Test St'
    assert aoi.registered_agent == 'Agent Smith'
    assert aoi.shares_authorized == 1000
    assert aoi.incorporator_name == 'Alice'

def test_validate_success(valid_kwargs):
    aoi = ArticlesOfIncorporation(None, **valid_kwargs)
    assert aoi.validate() is True

def test_validate_missing_fields(valid_kwargs):
    for key in valid_kwargs:
        bad_kwargs = valid_kwargs.copy()
        bad_kwargs[key] = ''
        aoi = ArticlesOfIncorporation(None, **bad_kwargs)
        assert not aoi.validate()

def test_validate_invalid_shares(valid_kwargs):
    bad_kwargs = valid_kwargs.copy()
    bad_kwargs['shares_authorized'] = -1
    aoi = ArticlesOfIncorporation(None, **bad_kwargs)
    assert not aoi.validate()
    bad_kwargs['shares_authorized'] = 0
    aoi = ArticlesOfIncorporation(None, **bad_kwargs)
    assert not aoi.validate()
    bad_kwargs['shares_authorized'] = 'notanint'
    aoi = ArticlesOfIncorporation(None, **bad_kwargs)
    assert not aoi.validate()

def test_submit_success(valid_kwargs):
    aoi = ArticlesOfIncorporation(None, **valid_kwargs)
    result = aoi.submit()
    assert 'successfully submitted' in result

def test_submit_failure(valid_kwargs):
    bad_kwargs = valid_kwargs.copy()
    bad_kwargs['business_name'] = ''
    aoi = ArticlesOfIncorporation(None, **bad_kwargs)
    result = aoi.submit()
    assert 'Submission failed' in result