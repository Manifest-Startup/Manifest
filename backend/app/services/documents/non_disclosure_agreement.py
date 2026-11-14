from datetime import datetime

from app.utils.logger import logger


class NonDisclosureAgreement:
    def __init__(self, model, **kwargs):
        logger.info(
            "NonDisclosureAgreement Object created."
        )  # Logging the creation of NonDisclosureAgreement object
        self.model = model
        effective_date_str = kwargs.get("effective_date")
        if effective_date_str:
            try:
                # Try to convert the effective_date string to a datetime object
                self._effective_date = datetime.strptime(effective_date_str, "%Y-%m-%d")
            except ValueError:
                # If conversion fails, set the effective_date to the current date and time
                self._effective_date = datetime.now()
        else:
            # If no effective_date provided, set it to the current date and time
            self._effective_date = datetime.now()

        # Get the disclosing_party, receiving_party, and confidentiality_period from kwargs, or set default values
        self._disclosing_party = kwargs.get("disclosing_party", "")
        self._receiving_party = kwargs.get("receiving_party", "")
        self._confidentiality_period = kwargs.get("confidentiality_period", 1)
        self._confidential_information = ""
        self._exclusions = []
        self._terms = []

    @property
    def effective_date(self):
        logger.debug("Accessing effective_date")  # Log when effective_date is accessed
        return self._effective_date

    @effective_date.setter
    def effective_date(self, value):
        logger.info(f"Setting effective_date: {value}")  # Log when effective_date is set
        self._effective_date = value

    @property
    def disclosing_party(self):
        logger.debug("Accessing disclosing_party")  # Log when disclosing_party is accessed
        return self._disclosing_party

    @disclosing_party.setter
    def disclosing_party(self, value):
        logger.info(f"Setting disclosing_party: {value}")  # Log when disclosing_party is set
        self._disclosing_party = value

    @property
    def receiving_party(self):
        logger.debug("Accessing receiving_party")  # Log when receiving_party is accessed
        return self._receiving_party

    @receiving_party.setter
    def receiving_party(self, value):
        logger.info(f"Setting receiving_party: {value}")  # Log when receiving_party is set
        self._receiving_party = value

    @property
    def confidentiality_period(self):
        logger.debug(
            "Accessing confidentiality_period"
        )  # Log when confidentiality_period is accessed
        return self._confidentiality_period

    @confidentiality_period.setter
    def confidentiality_period(self, value):
        logger.info(
            f"Setting confidentiality_period: {value}"
        )  # Log when confidentiality_period is set
        self._confidentiality_period = value

    @property
    def confidential_information(self):
        logger.debug(
            "Accessing confidential_information"
        )  # Log when confidential_information is accessed
        return self._confidential_information

    @confidential_information.setter
    def confidential_information(self, value):
        logger.info(
            f"Setting confidential_information: {value}"
        )  # Log when confidential_information is set
        self._confidential_information = value

    @property
    def exclusions(self):
        logger.debug("Accessing exclusions")  # Log when exclusions is accessed
        return self._exclusions

    @property
    def terms(self):
        logger.debug("Accessing terms")  # Log when terms is accessed
        return self._terms

    def add_confidential_information(self, information):
        logger.info(
            f"Adding confidential information: {information}"
        )  # Log when confidential information is added
        self._confidential_information = information

    def add_exclusion(self, exclusion):
        logger.info(f"Adding exclusion: {exclusion}")  # Log when an exclusion is added
        self._exclusions.append(exclusion)

    def add_term(self, term):
        logger.info(f"Adding term: {term}")  # Log when a term is added
        self._terms.append(term)

    def display_agreement(self):
        # Calculate the expiry date of the agreement
        expiry_date = self._effective_date.replace(
            year=self._effective_date.year + self._confidentiality_period
        ).strftime("%Y-%m-%d")

        # Log the details of the agreement
        logger.info("=== Non-Disclosure Agreement (NDA) ===")
        logger.info(f"Disclosing Party         : {self.disclosing_party}")
        logger.info(f"Receiving Party          : {self.receiving_party}")
        logger.info(f"Effective Date           : {self.effective_date.strftime('%Y-%m-%d')}")
        logger.info(f"Confidentiality Expires  : {expiry_date}")
        logger.info(f"Confidential Information : {self.confidential_information}")

        logger.info("\nExclusions:")
        for exclusion in self.exclusions:
            logger.info(f"  - {exclusion}")

        logger.info("\nTerms and Conditions:")
        for term in self.terms:
            logger.info(f"  - {term}")

    def is_expired(self):
        # Calculate the expiry date of the agreement
        expiry_date = self._effective_date.replace(
            year=self._effective_date.year + self._confidentiality_period
        )
        # Return True if the current date and time is after the expiry date, False otherwise
        return datetime.now() > expiry_date
