# Interface Class
from app.services.ai_layer_service import AILayer

# Legal Formation and Structure
from app.services.articles_of_incorporation_service import ArticlesOfIncorporation

# Financial Documents
from app.services.bank_account_service import BankAccount
from app.services.business_model_canvas_service import BusinessModelCanvas
from app.services.capitalization_table_service import CapitalizationTable
from app.services.consultant_agreement_service import ConsultantAgreement

# Compliance
from app.services.ein_service import EINService

# Human Resources
from app.services.employee_contract_service import EmployeeContract, OfferLetter
from app.services.employee_handbook_service import EmployeeHandbook
from app.services.founders_agreement_service import FoundersAgreement
from app.services.idea_service import Idea
from app.services.intellectual_property_service import IntellectualPropertyAgreement
from app.services.investment_agreement_service import InvestmentAgreement

# Sales and Marketing
from app.services.marketing_plan_service import MarketingPlan
from app.services.non_disclosure_agreement_service import NonDisclosureAgreement
from app.services.operating_agreement_service import OperatingAgreement

# Presentation
from app.services.pitch_deck_service import PitchDeck
from app.services.privacy_policy_service import PrivacyPolicy
from app.services.product_requirements_document_service import ProductRequirementsDocument

# Product Development and IP
from app.services.product_roadmap_service import ProductRoadmap
from app.services.sales_contract_service import SalesContract
from app.services.shareholders_agreement_service import ShareholdersAgreement
from app.services.similar_ideas_service import SimilarIdeas

# Operational Documents
from app.services.standard_operating_procedure_service import StandardOperatingProcedure
from app.utils.logger import logger


class ManifestManager:
    def __init__(self, *args, **kwargs):
        logger.info(
            "ManifestManager Object created."
        )  # Logging the creation of ManifestManager object
        self._service_factories = {
            "_ai_layer": AILayer,
            "_idea": lambda: Idea(self),
            "_bmc": lambda: BusinessModelCanvas(self),
            "_articles_of_incorporation": lambda: ArticlesOfIncorporation(self),
            "_operating_agreement": lambda: OperatingAgreement(self),
            "_shareholders_agreement": lambda: ShareholdersAgreement(self),
            "_founders_agreement": lambda: FoundersAgreement(self),
            "_ein_application": lambda: EINService(self),
            "_intellectual_property_agreement": lambda: IntellectualPropertyAgreement(self),
            "_bank_account": lambda: BankAccount(self),
            "_capitalization_table": lambda: CapitalizationTable(self),
            "_investment_agreement": lambda: InvestmentAgreement(self),
            "_product_roadmap": lambda: ProductRoadmap(self),
            "_non_disclosure_agreement": lambda: NonDisclosureAgreement(self),
            "_marketing_plan": lambda: MarketingPlan(self),
            "_sales_contract": lambda: SalesContract(self),
            "_pitch": lambda: PitchDeck(self),
            "_employee_contract": lambda: EmployeeContract(self),
            "_offer_letter": lambda: OfferLetter(self),
            "_employee_handbook": lambda: EmployeeHandbook(self),
            "_consultant_agreement": lambda: ConsultantAgreement(self),
            "_standard_operating_procedure": lambda: StandardOperatingProcedure(self),
            "_privacy_policy": lambda: PrivacyPolicy(self),
            "_similar_ideas": lambda: SimilarIdeas(self),
            "_product_requirements_document": lambda: ProductRequirementsDocument(self),
        }
        for service_attr in self._service_factories:
            setattr(self, service_attr, None)

    def _get_service(self, service_attr: str, service_name: str):
        service = getattr(self, service_attr)
        if service is None:
            logger.debug("[ManifestManager] Lazy initializing %s", service_name)
            service = self._service_factories[service_attr]()
            setattr(self, service_attr, service)
        return service

    # Property decorators for getter and setter methods of all the services
    @property
    def similar_ideas(self):
        logger.debug(
            "[ManifestManager] Accessing similar ideas property"
        )  # Logging the access of similar ideas
        return self._get_service("_similar_ideas", "similar ideas")

    @similar_ideas.setter
    def similar_ideas(self, value):
        logger.info(
            f"[ManifestManager] Setting similar ideas: {value}"
        )  # Logging the setting of similar ideas
        self._similar_ideas = value

    @property
    def idea(self):
        logger.debug("Accessing idea")  # Logging the access of idea
        return self._get_service("_idea", "idea")

    @idea.setter
    def idea(self, value):
        logger.info(f"Setting idea: {value}")  # Logging the setting of idea
        self._idea = value

    @property
    def bmc(self):
        logger.debug(
            "Accessing business model canvas"
        )  # Logging the access of business model canvas
        return self._get_service("_bmc", "business model canvas")

    @bmc.setter
    def bmc(self, value):
        logger.info(
            f"Setting business model canvas: {value}"
        )  # Logging the setting of business model canvas
        self._bmc = value

    @property
    def articles_of_incorporation(self):
        logger.debug(
            "Accessing articles of incorporation"
        )  # Logging the access of articles of incorporation
        return self._get_service("_articles_of_incorporation", "articles of incorporation")

    @articles_of_incorporation.setter
    def articles_of_incorporation(self, value):
        logger.info(
            f"Setting articles of incorporation: {value}"
        )  # Logging the setting of articles of incorporation
        self._articles_of_incorporation = value

    @property
    def operating_agreement(self):
        logger.debug("Accessing operating agreement")  # Logging the access of operating agreement
        return self._get_service("_operating_agreement", "operating agreement")

    @operating_agreement.setter
    def operating_agreement(self, value):
        logger.info(
            f"Setting operating agreement: {value}"
        )  # Logging the setting of operating agreement
        self._operating_agreement = value

    @property
    def shareholders_agreement(self):
        logger.debug(
            "Accessing shareholders agreement"
        )  # Logging the access of shareholders agreement
        return self._get_service("_shareholders_agreement", "shareholders agreement")

    @shareholders_agreement.setter
    def shareholders_agreement(self, value):
        logger.info(
            f"Setting shareholders agreement: {value}"
        )  # Logging the setting of shareholders agreement
        self._shareholders_agreement = value

    @property
    def founders_agreement(self):
        logger.debug("Accessing founders agreement")  # Logging the access of founders agreement
        return self._get_service("_founders_agreement", "founders agreement")

    @founders_agreement.setter
    def founders_agreement(self, value):
        logger.info(
            f"Setting founders agreement: {value}"
        )  # Logging the setting of founders agreement
        self._founders_agreement = value

    @property
    def ein_application(self):
        logger.debug("Accessing EIN application")  # Logging the access of EIN application
        return self._get_service("_ein_application", "EIN application")

    @ein_application.setter
    def ein_application(self, value):
        logger.info(f"Setting EIN application: {value}")  # Logging the setting of EIN application
        self._ein_application = value

    @property
    def intellectual_property_agreement(self):
        logger.debug(
            "Accessing intellectual property agreement"
        )  # Logging the access of intellectual property agreement
        return self._get_service(
            "_intellectual_property_agreement", "intellectual property agreement"
        )

    @intellectual_property_agreement.setter
    def intellectual_property_agreement(self, value):
        logger.info(
            f"Setting intellectual property agreement: {value}"
        )  # Logging the setting of intellectual property agreement
        self._intellectual_property_agreement = value

    @property
    def bank_account(self):
        logger.debug("Accessing bank account")  # Logging the access of bank account
        return self._get_service("_bank_account", "bank account")

    @bank_account.setter
    def bank_account(self, value):
        logger.info(f"Setting bank account: {value}")  # Logging the setting of bank account
        self._bank_account = value

    @property
    def capitalization_table(self):
        logger.debug("Accessing capitalization table")  # Logging the access of capitalization table
        return self._get_service("_capitalization_table", "capitalization table")

    @capitalization_table.setter
    def capitalization_table(self, value):
        logger.info(
            f"Setting capitalization table: {value}"
        )  # Logging the setting of capitalization table
        self._capitalization_table = value

    @property
    def investment_agreement(self):
        logger.debug("Accessing investment agreement")  # Logging the access of investment agreement
        return self._get_service("_investment_agreement", "investment agreement")

    @investment_agreement.setter
    def investment_agreement(self, value):
        logger.info(
            f"Setting investment agreement: {value}"
        )  # Logging the setting of investment agreement
        self._investment_agreement = value

    @property
    def product_roadmap(self):
        logger.debug("Accessing product roadmap")  # Logging the access of product roadmap
        return self._get_service("_product_roadmap", "product roadmap")

    @product_roadmap.setter
    def product_roadmap(self, value):
        logger.info(f"Setting product roadmap: {value}")  # Logging the setting of product roadmap
        self._product_roadmap = value

    @property
    def non_disclosure_agreement(self):
        logger.debug(
            "Accessing non disclosure agreement"
        )  # Logging the access of non disclosure agreement
        return self._get_service("_non_disclosure_agreement", "non disclosure agreement")

    @non_disclosure_agreement.setter
    def non_disclosure_agreement(self, value):
        logger.info(
            f"Setting non disclosure agreement: {value}"
        )  # Logging the setting of non disclosure agreement
        self._non_disclosure_agreement = value

    @property
    def marketing_plan(self):
        logger.debug("Accessing marketing plan")  # Logging the access of marketing plan
        return self._get_service("_marketing_plan", "marketing plan")

    @marketing_plan.setter
    def marketing_plan(self, value):
        logger.info(f"Setting marketing plan: {value}")  # Logging the setting of marketing plan
        self._marketing_plan = value

    @property
    def sales_contract(self):
        logger.debug("Accessing sales contract")  # Logging the access of sales contract
        return self._get_service("_sales_contract", "sales contract")

    @sales_contract.setter
    def sales_contract(self, value):
        logger.info(f"Setting sales contract: {value}")  # Logging the setting of sales contract
        self._sales_contract = value

    @property
    def pitch_deck(self):
        logger.debug("Accessing pitch deck")
        return self._get_service("_pitch", "pitch deck")

    @pitch_deck.setter
    def pitch_deck(self, value):
        logger.info(f"Setting pitch deck: {value}")
        self._pitch = value

    @property
    def employee_contract(self):
        logger.debug("Accessing employee contract")  # Logging the access of employee contract
        return self._get_service("_employee_contract", "employee contract")

    @employee_contract.setter
    def employee_contract(self, value):
        logger.info(
            f"Setting employee contract: {value}"
        )  # Logging the setting of employee contract
        self._employee_contract = value

    @property
    def offer_letter(self):
        logger.debug("Accessing offer letter")  # Logging the access of offer letter
        return self._get_service("_offer_letter", "offer letter")

    @offer_letter.setter
    def offer_letter(self, value):
        logger.info(f"Setting offer letter: {value}")  # Logging the setting of offer letter
        self._offer_letter = value

    @property
    def employee_handbook(self):
        logger.debug("Accessing employee handbook")  # Logging the access of employee handbook
        return self._get_service("_employee_handbook", "employee handbook")

    @employee_handbook.setter
    def employee_handbook(self, value):
        logger.info(
            f"Setting employee handbook: {value}"
        )  # Logging the setting of employee handbook
        self._employee_handbook = value

    @property
    def consultant_agreement(self):
        logger.debug("Accessing consultant agreement")  # Logging the access of consultant agreement
        return self._get_service("_consultant_agreement", "consultant agreement")

    @consultant_agreement.setter
    def consultant_agreement(self, value):
        logger.info(
            f"Setting consultant agreement: {value}"
        )  # Logging the setting of consultant agreement
        self._consultant_agreement = value

    @property
    def standard_operating_procedure(self):
        logger.debug(
            "Accessing standard operating procedure"
        )  # Logging the access of standard operating procedure
        return self._get_service("_standard_operating_procedure", "standard operating procedure")

    @standard_operating_procedure.setter
    def standard_operating_procedure(self, value):
        logger.info(
            f"Setting standard operating procedure: {value}"
        )  # Logging the setting of standard operating procedure
        self._standard_operating_procedure = value

    @property
    def privacy_policy(self):
        logger.debug("Accessing privacy policy")  # Logging the access of privacy policy
        return self._get_service("_privacy_policy", "privacy policy")

    @privacy_policy.setter
    def privacy_policy(self, value):
        logger.info(f"Setting privacy policy: {value}")  # Logging the setting of privacy policy
        self._privacy_policy = value

    @property
    def ai_layer(self):
        logger.debug("Accessing AILayer")  # Logging the access of AILayer
        return self._get_service("_ai_layer", "AILayer")

    @ai_layer.setter
    def ai_layer(self, value):
        logger.info(f"Setting AILayer: {value}")  # Logging the setting of AILayer
        self._ai_layer = value

    @property
    def product_requirements_document(self):
        logger.debug("Accessing product requirements document")
        return self._get_service("_product_requirements_document", "product requirements document")

    @product_requirements_document.setter
    def product_requirements_document(self, value):
        logger.info(f"Setting product requirements document: {value}")
        self._product_requirements_document = value

    def update(self):
        """
        Update all model components using the stored idea description.
        """
        logger.info(
            "[ManifestManager] Updating ManifestManager."
        )  # Logging the update of ManifestManager
        logger.info(
            "[ManifestManager] Using stored idea description for update."
        )  # Logging the use of stored idea description for update
        self.bmc.update()
        self.similar_ideas.update()
        self.pitch_deck.update()
        self.product_requirements_document.update()
        logger.info(
            "[ManifestManager] All components updated successfully."
        )  # Logging the successful update of all components

    def generate_cost_analysis(self):
        logger.info(
            "Delegating cost structure generation to BusinessModelCanvas."
        )  # Logging the delegation of cost structure generation to BusinessModelCanvas
        return self.bmc.update_cost_breakdown()

    def generate_patent_application(self):
        logger.info(
            "Delegating patent application generation to IntellectualPropertyAgreement."
        )  # Logging the delegation of patent application generation to IntellectualPropertyAgreement
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
        )  # Logging the setting of idea description directly via set_idea()
        self.idea.description = idea_description

    def get_idea_summary(self):
        """
        Get a summary of the current idea.
        """
        logger.info("Retrieving idea summary.")  # Logging the retrieval of idea summary
        return self.idea.get_summary()

    def find_similar_ideas(self):
        """
        Use the SimilarIdeas module to find and return ideas related to the current or provided idea.
        """
        logger.info(
            "[ManifestManager] Finding similar startup ideas for: %s", self.idea.description
        )  # Logging the finding of similar startup ideas
        return self.similar_ideas.find(self.idea.description)

    def get_similar_ideas(self):
        """
        Get the similar ideas.
        """
        logger.info(
            "[ManifestManager] Getting similar ideas."
        )  # Logging the getting of similar ideas
        return self.similar_ideas.results

    # ----------------- Business Model Canvas Methods -----------------

    def get_business_model_canvas(self):
        """
        Retrieve the current Business Model Canvas.
        """
        logger.info(
            "Retrieving Business Model Canvas."
        )  # Logging the retrieval of Business Model Canvas
        return self.bmc.get_canvas()

    # --------------------- Legal Document Methods ---------------------

    def create_articles_of_incorporation(self):
        """
        Generate the Articles of Incorporation document.
        """
        logger.info(
            "Generating Articles of Incorporation."
        )  # Logging the generation of Articles of Incorporation
        return self.articles_of_incorporation.generate()

    def create_operating_agreement(self):
        """
        Generate the Operating Agreement document.
        """
        logger.info(
            "Generating Operating Agreement."
        )  # Logging the generation of Operating Agreement
        return self.operating_agreement.generate()

    # --------------------- Financial Document Methods ---------------------

    def open_bank_account(self):
        """
        Simulate the process of opening a business bank account.
        """
        logger.info(
            "Opening business bank account."
        )  # Logging the opening of business bank account
        return self.bank_account.open()

    def generate_cap_table(self):
        """
        Generate the capitalization table.
        """
        logger.info(
            "Generating capitalization table."
        )  # Logging the generation of capitalization table
        return self.capitalization_table.generate()

    # --------------------- Product Development Methods ---------------------

    def create_product_roadmap(self):
        """
        Generate a product development roadmap.
        """
        logger.info("Generating product roadmap.")  # Logging the generation of product roadmap
        return self.product_roadmap.generate()

    def create_non_disclosure_agreement(self):
        """
        Generate a Non-Disclosure Agreement (NDA).
        """
        logger.info(
            "Generating Non-Disclosure Agreement."
        )  # Logging the generation of Non-Disclosure Agreement
        return self.non_disclosure_agreement.generate()

    # --------------------- Marketing and Sales Methods ---------------------

    def create_marketing_plan(self):
        """
        Generate a marketing plan.
        """
        logger.info("Generating marketing plan.")  # Logging the generation of marketing plan
        return self.marketing_plan.generate()

    def create_sales_contract(self):
        """
        Generate a sales contract.
        """
        logger.info("Generating sales contract.")  # Logging the generation of sales contract
        return self.sales_contract.generate()

    # --------------------- Human Resources Methods ---------------------

    def create_employee_contract(self):
        """
        Generate an employee contract.
        """
        logger.info("Generating employee contract.")  # Logging the generation of employee contract
        return self.employee_contract.generate()

    def create_offer_letter(self):
        """
        Generate an offer letter.
        """
        logger.info("Generating offer letter.")  # Logging the generation of offer letter
        return self.offer_letter.generate()

    def create_employee_handbook(self):
        """
        Generate an employee handbook.
        """
        logger.info("Generating employee handbook.")  # Logging the generation of employee handbook
        return self.employee_handbook.generate()

    # --------------------- Compliance and Legal Methods ---------------------

    def apply_for_ein(self):
        """
        Submit an EIN application.
        """
        logger.info("Submitting EIN application.")  # Logging the submission of EIN application
        return self.ein_application.submit()

    def create_ip_agreement(self):
        """
        Generate an intellectual property agreement.
        """
        logger.info("Generating IP agreement.")  # Logging the generation of IP agreement
        return self.intellectual_property_agreement.generate()

    # --------------------- Operational and Policy Methods ---------------------

    def create_standard_operating_procedure(self):
        """
        Generate a standard operating procedure.
        """
        logger.info("Generating SOP.")  # Logging the generation of SOP
        return self.standard_operating_procedure.generate()

    def create_privacy_policy(self):
        """
        Generate a privacy policy.
        """
        logger.info("Generating privacy policy.")  # Logging the generation of privacy policy
        return self.privacy_policy.generate()

    def create_terms_of_service(self):
        """
        Generate terms of service.
        """
        logger.info("Generating terms of service.")  # Logging the generation of terms of service
        return self.privacy_policy.generate_terms_of_service()

    def create_patent_application(self):
        """
        Generate a patent application draft.
        """
        logger.info(
            "Generating patent application."
        )  # Logging the generation of patent application
        return self.generate_patent_application()

    def generate_development_roadmap(self):
        """
        Generate a development roadmap using the product roadmap model.
        """
        logger.info(
            "Generating development roadmap."
        )  # Logging the generation of development roadmap
        return self.product_roadmap.generate()

    def generate_pitch_deck(self):
        """
        Generate a pitch deck using the model's pitch component.
        """
        logger.info("Generating pitch deck.")  # Logging the generation of pitch deck
        return self.pitch_deck.generate()

    def get_development_roadmap(self):
        """
        Retrieve the current product development roadmap.
        """
        logger.info(
            "Retrieving development roadmap."
        )  # Logging the retrieval of development roadmap
        return self.product_roadmap.value

    def get_pitch_deck(self):
        """
        Retrieve the current Pitch Deck (returns the summary property).
        """
        logger.info("Retrieving Pitch Deck summary.")  # Logging the retrieval of Pitch Deck summary
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
