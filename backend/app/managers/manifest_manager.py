"""ManifestManager: the facade that turns one idea into every generated document."""

from collections.abc import Callable
from typing import Any

from app.services.ai.layer import AILayer
from app.services.canvas.business_model_canvas import BusinessModelCanvas
from app.services.documents.articles_of_incorporation import ArticlesOfIncorporation
from app.services.documents.bank_account import BankAccount
from app.services.documents.capitalization_table import CapitalizationTable
from app.services.documents.consultant_agreement import ConsultantAgreement
from app.services.documents.ein import EINService
from app.services.documents.employee_contract import EmployeeContract, OfferLetter
from app.services.documents.employee_handbook import EmployeeHandbook
from app.services.documents.founders_agreement import FoundersAgreement
from app.services.documents.intellectual_property import IntellectualPropertyAgreement
from app.services.documents.investment_agreement import InvestmentAgreement
from app.services.documents.marketing_plan import MarketingPlan
from app.services.documents.non_disclosure_agreement import NonDisclosureAgreement
from app.services.documents.operating_agreement import OperatingAgreement
from app.services.documents.pitch_deck import PitchDeck
from app.services.documents.privacy_policy import PrivacyPolicy
from app.services.documents.product_requirements_document import ProductRequirementsDocument
from app.services.documents.product_roadmap import ProductRoadmap
from app.services.documents.sales_contract import SalesContract
from app.services.documents.shareholders_agreement import ShareholdersAgreement
from app.services.documents.standard_operating_procedure import StandardOperatingProcedure
from app.services.ideas.service import Idea
from app.services.ideas.similar_ideas import SimilarIdeas
from app.utils.logger import logger


class LazyService:
    """A service attribute that is built on first read and cached per manager.

    ``bmc = LazyService(lambda manager: BusinessModelCanvas(manager))`` calls ``BusinessModelCanvas(manager)``
    the first time ``manager.bmc`` is read. Assigning ``manager.bmc = x`` replaces it.
    """

    def __init__(self, factory: Callable[[Any], Any]) -> None:
        self.factory = factory

    def __set_name__(self, owner: type, name: str) -> None:
        self.name = name

    def __get__(self, manager: Any, owner: type | None = None) -> Any:
        if manager is None:
            return self
        service = manager.__dict__.get(self.name)
        if service is None:
            logger.debug("[ManifestManager] creating %s", self.name)
            service = self.factory(manager)
            manager.__dict__[self.name] = service
        return service

    def __set__(self, manager: Any, value: Any) -> None:
        manager.__dict__[self.name] = value


class ManifestManager:
    """One idea's workspace: holds the idea and builds each document service on first use.

    Every service below is created lazily the first time it is read and cached
    for this manager, so constructing a manager is cheap. Assigning a service
    (``manager.pitch_deck = fake``) replaces it, which tests rely on.
    """

    ai_layer = LazyService(lambda manager: AILayer())
    idea = LazyService(lambda manager: Idea(manager))
    similar_ideas = LazyService(lambda manager: SimilarIdeas(manager))
    bmc = LazyService(lambda manager: BusinessModelCanvas(manager))
    pitch_deck = LazyService(lambda manager: PitchDeck(manager))
    product_requirements_document = LazyService(
        lambda manager: ProductRequirementsDocument(manager)
    )
    product_roadmap = LazyService(lambda manager: ProductRoadmap(manager))
    marketing_plan = LazyService(lambda manager: MarketingPlan(manager))
    articles_of_incorporation = LazyService(lambda manager: ArticlesOfIncorporation(manager))
    operating_agreement = LazyService(lambda manager: OperatingAgreement(manager))
    shareholders_agreement = LazyService(lambda manager: ShareholdersAgreement(manager))
    founders_agreement = LazyService(lambda manager: FoundersAgreement(manager))
    ein_application = LazyService(lambda manager: EINService(manager))
    intellectual_property_agreement = LazyService(
        lambda manager: IntellectualPropertyAgreement(manager)
    )
    bank_account = LazyService(lambda manager: BankAccount(manager))
    capitalization_table = LazyService(lambda manager: CapitalizationTable(manager))
    investment_agreement = LazyService(lambda manager: InvestmentAgreement(manager))
    non_disclosure_agreement = LazyService(lambda manager: NonDisclosureAgreement(manager))
    sales_contract = LazyService(lambda manager: SalesContract(manager))
    employee_contract = LazyService(lambda manager: EmployeeContract(manager))
    offer_letter = LazyService(lambda manager: OfferLetter(manager))
    employee_handbook = LazyService(lambda manager: EmployeeHandbook(manager))
    consultant_agreement = LazyService(lambda manager: ConsultantAgreement(manager))
    standard_operating_procedure = LazyService(lambda manager: StandardOperatingProcedure(manager))
    privacy_policy = LazyService(lambda manager: PrivacyPolicy(manager))

    def update(self):
        """
        Update all model components using the stored idea description.
        """
        logger.info("[ManifestManager] Updating ManifestManager.")
        logger.info("[ManifestManager] Using stored idea description for update.")
        self.bmc.update()
        self.similar_ideas.update()
        self.pitch_deck.update()
        self.product_requirements_document.update()
        logger.info("[ManifestManager] All components updated successfully.")

    def generate_cost_analysis(self):
        logger.info("Delegating cost structure generation to BusinessModelCanvas.")
        return self.bmc.update_cost_breakdown()

    def generate_patent_application(self):
        logger.info("Delegating patent application generation to IntellectualPropertyAgreement.")
        return self.intellectual_property_agreement.generate_patent_application(
            self.ai_layer, self.idea.description
        )

        # ------------------------- Idea Methods -------------------------

    def set_idea(self, idea_description: str):
        """
        Set the idea description explicitly without triggering downstream updates.
        This is useful when you want to set the idea and call individual methods selectively.
        """
        logger.info(
            "[ManifestManager] Setting idea description directly via set_idea(): %s",
            idea_description,
        )
        self.idea.description = idea_description

    def get_idea_summary(self):
        """
        Get a summary of the current idea.
        """
        logger.info("Retrieving idea summary.")
        return self.idea.get_summary()

    def find_similar_ideas(self):
        """
        Use the SimilarIdeas module to find and return ideas related to the current or provided idea.
        """
        logger.info(
            "[ManifestManager] Finding similar startup ideas for: %s", self.idea.description
        )
        return self.similar_ideas.find(self.idea.description)

    def get_similar_ideas(self):
        """
        Get the similar ideas.
        """
        logger.info("[ManifestManager] Getting similar ideas.")
        return self.similar_ideas.results

    # ----------------- Business Model Canvas Methods -----------------

    def get_business_model_canvas(self):
        """
        Retrieve the current Business Model Canvas.
        """
        logger.info("Retrieving Business Model Canvas.")
        return self.bmc.get_canvas()

    # --------------------- Legal Document Methods ---------------------

    def create_articles_of_incorporation(self):
        """
        Generate the Articles of Incorporation document.
        """
        logger.info("Generating Articles of Incorporation.")
        return self.articles_of_incorporation.generate()

    def create_operating_agreement(self):
        """
        Generate the Operating Agreement document.
        """
        logger.info("Generating Operating Agreement.")
        return self.operating_agreement.generate()

    # --------------------- Financial Document Methods ---------------------

    def open_bank_account(self):
        """
        Simulate the process of opening a business bank account.
        """
        logger.info("Opening business bank account.")
        return self.bank_account.open()

    def generate_cap_table(self):
        """
        Generate the capitalization table.
        """
        logger.info("Generating capitalization table.")
        return self.capitalization_table.generate()

    # --------------------- Product Development Methods ---------------------

    def create_product_roadmap(self):
        """
        Generate a product development roadmap.
        """
        logger.info("Generating product roadmap.")
        return self.product_roadmap.generate()

    def create_non_disclosure_agreement(self):
        """
        Generate a Non-Disclosure Agreement (NDA).
        """
        logger.info("Generating Non-Disclosure Agreement.")
        return self.non_disclosure_agreement.generate()

    # --------------------- Marketing and Sales Methods ---------------------

    def create_marketing_plan(self):
        """
        Generate a marketing plan.
        """
        logger.info("Generating marketing plan.")
        return self.marketing_plan.generate()

    def create_sales_contract(self):
        """
        Generate a sales contract.
        """
        logger.info("Generating sales contract.")
        return self.sales_contract.generate()

    # --------------------- Human Resources Methods ---------------------

    def create_employee_contract(self):
        """
        Generate an employee contract.
        """
        logger.info("Generating employee contract.")
        return self.employee_contract.generate()

    def create_offer_letter(self):
        """
        Generate an offer letter.
        """
        logger.info("Generating offer letter.")
        return self.offer_letter.generate()

    def create_employee_handbook(self):
        """
        Generate an employee handbook.
        """
        logger.info("Generating employee handbook.")
        return self.employee_handbook.generate()

    # --------------------- Compliance and Legal Methods ---------------------

    def apply_for_ein(self):
        """
        Submit an EIN application.
        """
        logger.info("Submitting EIN application.")
        return self.ein_application.submit()

    def create_ip_agreement(self):
        """
        Generate an intellectual property agreement.
        """
        logger.info("Generating IP agreement.")
        return self.intellectual_property_agreement.generate()

    # --------------------- Operational and Policy Methods ---------------------

    def create_standard_operating_procedure(self):
        """
        Generate a standard operating procedure.
        """
        logger.info("Generating SOP.")
        return self.standard_operating_procedure.generate()

    def create_privacy_policy(self):
        """
        Generate a privacy policy.
        """
        logger.info("Generating privacy policy.")
        return self.privacy_policy.generate()

    def create_terms_of_service(self):
        """
        Generate terms of service.
        """
        logger.info("Generating terms of service.")
        return self.privacy_policy.generate_terms_of_service()

    def create_patent_application(self):
        """
        Generate a patent application draft.
        """
        logger.info("Generating patent application.")
        return self.generate_patent_application()

    def generate_development_roadmap(self):
        """
        Generate a development roadmap using the product roadmap model.
        """
        logger.info("Generating development roadmap.")
        return self.product_roadmap.generate()

    def generate_pitch_deck(self):
        """
        Generate a pitch deck using the model's pitch component.
        """
        logger.info("Generating pitch deck.")
        return self.pitch_deck.generate()

    def get_development_roadmap(self):
        """
        Retrieve the current product development roadmap.
        """
        logger.info("Retrieving development roadmap.")
        return self.product_roadmap.value

    def get_pitch_deck(self):
        """
        Retrieve the current Pitch Deck (returns the summary property).
        """
        logger.info("Retrieving Pitch Deck summary.")
        return self.pitch_deck.summary

    def generate_product_requirements_document(self):
        """
        Generate a product requirements document.
        """
        logger.info("Generating product requirements document.")
        return self.product_requirements_document.generate()

    def get_product_requirements_document(self):
        """
        Retrieve the current Product Requirements Document.
        """
        logger.info("Retrieving Product Requirements Document.")
        return self.product_requirements_document.summary


# The process-wide manager. Creating it is cheap: services are built lazily
# from the factories above on first use, after settings have loaded.
manifest_manager = ManifestManager()
