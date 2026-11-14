import pytest
from unittest.mock import MagicMock, patch
from app.managers.manifest_manager import ManifestManager

ALL_PATCHES = {
    'AILayer': MagicMock(),
    'Idea': MagicMock(),
    'BusinessModelCanvas': MagicMock(),
    'SimilarIdeas': MagicMock(),
    'ArticlesOfIncorporation': MagicMock(),
    'OperatingAgreement': MagicMock(),
    'ShareholdersAgreement': MagicMock(),
    'FoundersAgreement': MagicMock(),
    'EINService': MagicMock(),
    'IntellectualPropertyAgreement': MagicMock(),
    'BankAccount': MagicMock(),
    'CapitalizationTable': MagicMock(),
    'InvestmentAgreement': MagicMock(),
    'ProductRoadmap': MagicMock(),
    'NonDisclosureAgreement': MagicMock(),
    'MarketingPlan': MagicMock(),
    'SalesContract': MagicMock(),
    'PitchDeck': MagicMock(),
    'EmployeeContract': MagicMock(),
    'OfferLetter': MagicMock(),
    'EmployeeHandbook': MagicMock(),
    'ConsultantAgreement': MagicMock(),
    'StandardOperatingProcedure': MagicMock(),
    'PrivacyPolicy': MagicMock(),
    'ProductRequirementsDocument': MagicMock(),
}

@pytest.fixture
def manager():
    for patched_class in ALL_PATCHES.values():
        patched_class.reset_mock()
    with patch.multiple('app.managers.manifest_manager', **ALL_PATCHES):
        yield ManifestManager()

def test_services_are_lazy_loaded(manager):
    for patched_class in ALL_PATCHES.values():
        patched_class.assert_not_called()

    first_idea = manager.idea
    second_idea = manager.idea

    ALL_PATCHES["Idea"].assert_called_once_with(manager)
    assert first_idea is second_idea
    ALL_PATCHES["BusinessModelCanvas"].assert_not_called()

def test_properties(manager):
    # Test all property getters and setters
    manager.similar_ideas = 'test'
    assert manager.similar_ideas == 'test'
    manager.idea = 'test'
    assert manager.idea == 'test'
    manager.bmc = 'test'
    assert manager.bmc == 'test'
    manager.articles_of_incorporation = 'test'
    assert manager.articles_of_incorporation == 'test'
    manager.operating_agreement = 'test'
    assert manager.operating_agreement == 'test'
    manager.shareholders_agreement = 'test'
    assert manager.shareholders_agreement == 'test'
    manager.founders_agreement = 'test'
    assert manager.founders_agreement == 'test'
    manager.ein_application = 'test'
    assert manager.ein_application == 'test'
    manager.intellectual_property_agreement = 'test'
    assert manager.intellectual_property_agreement == 'test'
    manager.bank_account = 'test'
    assert manager.bank_account == 'test'
    manager.capitalization_table = 'test'
    assert manager.capitalization_table == 'test'
    manager.investment_agreement = 'test'
    assert manager.investment_agreement == 'test'
    manager.product_roadmap = 'test'
    assert manager.product_roadmap == 'test'
    manager.non_disclosure_agreement = 'test'
    assert manager.non_disclosure_agreement == 'test'
    manager.marketing_plan = 'test'
    assert manager.marketing_plan == 'test'
    manager.sales_contract = 'test'
    assert manager.sales_contract == 'test'
    manager.pitch_deck = 'test'
    assert manager.pitch_deck == 'test'
    manager.employee_contract = 'test'
    assert manager.employee_contract == 'test'
    manager.offer_letter = 'test'
    assert manager.offer_letter == 'test'
    manager.employee_handbook = 'test'
    assert manager.employee_handbook == 'test'
    manager.consultant_agreement = 'test'
    assert manager.consultant_agreement == 'test'
    manager.standard_operating_procedure = 'test'
    assert manager.standard_operating_procedure == 'test'
    manager.privacy_policy = 'test'
    assert manager.privacy_policy == 'test'
    manager.ai_layer = 'test'
    assert manager.ai_layer == 'test'

def test_methods(manager):
    # Patch all called methods to avoid side effects and test method calls
    manager.bmc.update = MagicMock()
    manager.similar_ideas.update = MagicMock()
    manager.pitch_deck.update = MagicMock()
    manager.product_requirements_document.update = MagicMock()
    manager.update()
    manager.bmc.update.assert_called_once()
    manager.similar_ideas.update.assert_called_once()
    manager.pitch_deck.update.assert_called_once()
    manager.product_requirements_document.update.assert_called_once()

    manager.bmc.update_cost_breakdown = MagicMock(return_value='cost')
    assert manager.generate_cost_analysis() == 'cost'

    manager.intellectual_property_agreement.generate_patent_application = MagicMock(return_value='patent')
    manager.ai_layer = MagicMock()
    manager.idea = MagicMock()
    manager.idea.description = 'desc'
    assert manager.generate_patent_application() == 'patent'

    manager.idea.get_summary = MagicMock(return_value='summary')
    assert manager.get_idea_summary() == 'summary'

    manager.similar_ideas.find = MagicMock(return_value='found')
    assert manager.find_similar_ideas() == 'found'
    manager.similar_ideas.results = 'results'
    assert manager.get_similar_ideas() == 'results'

    manager.bmc.get_canvas = MagicMock(return_value='canvas')
    assert manager.get_business_model_canvas() == 'canvas'

    # Test all create/generate methods
    manager.articles_of_incorporation.generate = MagicMock(return_value='aoi')
    assert manager.create_articles_of_incorporation() == 'aoi'
    manager.operating_agreement.generate = MagicMock(return_value='oa')
    assert manager.create_operating_agreement() == 'oa'
    manager.bank_account.open = MagicMock(return_value='bank')
    assert manager.open_bank_account() == 'bank'
    manager.capitalization_table.generate = MagicMock(return_value='cap')
    assert manager.generate_cap_table() == 'cap'
    manager.product_roadmap.generate = MagicMock(return_value='roadmap')
    assert manager.create_product_roadmap() == 'roadmap'
    manager.non_disclosure_agreement.generate = MagicMock(return_value='nda')
    assert manager.create_non_disclosure_agreement() == 'nda'
    manager.marketing_plan.generate = MagicMock(return_value='marketing')
    assert manager.create_marketing_plan() == 'marketing'
    manager.sales_contract.generate = MagicMock(return_value='sales')
    assert manager.create_sales_contract() == 'sales'
    manager.employee_contract.generate = MagicMock(return_value='emp')
    assert manager.create_employee_contract() == 'emp'
    manager.offer_letter.generate = MagicMock(return_value='offer')
    assert manager.create_offer_letter() == 'offer'
    manager.employee_handbook.generate = MagicMock(return_value='handbook')
    assert manager.create_employee_handbook() == 'handbook'
    manager.ein_application.submit = MagicMock(return_value='ein')
    assert manager.apply_for_ein() == 'ein'
    manager.intellectual_property_agreement.generate = MagicMock(return_value='ip')
    assert manager.create_ip_agreement() == 'ip'
    manager.standard_operating_procedure.generate = MagicMock(return_value='sop')
    assert manager.create_standard_operating_procedure() == 'sop'
    manager.privacy_policy.generate = MagicMock(return_value='privacy')
    assert manager.create_privacy_policy() == 'privacy'
    manager.privacy_policy.generate_terms_of_service = MagicMock(return_value='tos')
    assert manager.create_terms_of_service() == 'tos'
    manager.generate_patent_application = MagicMock(return_value='patent')
    assert manager.create_patent_application() == 'patent'
    manager.product_roadmap.generate = MagicMock(return_value='devroadmap')
    assert manager.generate_development_roadmap() == 'devroadmap'
    manager.pitch_deck.generate = MagicMock(return_value='pitch')
    assert manager.generate_pitch_deck() == 'pitch'
    manager.product_roadmap.value = 'devroadmapval'
    assert manager.get_development_roadmap() == 'devroadmapval'