from datetime import datetime

from app.utils.auto_property import AutoProperty
from app.utils.logger import logger


class ConsultantAgreement:
    def __init__(self, model, **kwargs):
        logger.info("ConsultantAgreement Object created.")
        self.model = model
        self._consultant_name = kwargs.get("consultant_name", "Default Consultant")
        self._company_name = kwargs.get("company_name", "Default Company")
        start_date_str = kwargs.get("start_date")
        if start_date_str:
            try:
                # Trying to convert the start date string to a datetime object
                self._start_date = datetime.strptime(start_date_str, "%Y-%m-%d")
            except ValueError:
                # If the conversion fails, setting the start date to the current date and time
                self._start_date = datetime.now()
        else:
            # If no start date is provided, setting the start date to the current date and time
            self._start_date = datetime.now()
        end_date_str = kwargs.get("end_date")
        if end_date_str:
            try:
                # Trying to convert the end date string to a datetime object
                self._end_date = datetime.strptime(end_date_str, "%Y-%m-%d")
            except ValueError:
                # If the conversion fails, setting the end date to the current date and time
                self._end_date = datetime.now()
        else:
            # If no end date is provided, setting the end date to the current date and time
            self._end_date = datetime.now()

        # Initializing the agreement terms with empty strings
        self._scope_of_work = ""
        self._payment_terms = ""
        self._confidentiality_clause = ""
        self._intellectual_property_clause = ""
        self._termination_conditions = ""

    consultant_name = AutoProperty("consultant_name")
    company_name = AutoProperty("company_name")
    start_date = AutoProperty("start_date")
    end_date = AutoProperty("end_date")
    scope_of_work = AutoProperty("scope_of_work")
    payment_terms = AutoProperty("payment_terms")
    confidentiality_clause = AutoProperty("confidentiality_clause")
    intellectual_property_clause = AutoProperty("intellectual_property_clause")
    termination_conditions = AutoProperty("termination_conditions")

    def display_agreement(self):
        logger.info(
            f"=== Consultant Agreement between {self.company_name} and {self.consultant_name} ==="
        )
        logger.info(f"Start Date               : {self.start_date.strftime('%Y-%m-%d')}")
        logger.info(f"End Date                 : {self.end_date.strftime('%Y-%m-%d')}")

        logger.info("\nScope of Work:")
        logger.info(f"  {self.scope_of_work}")

        logger.info("\nPayment Terms:")
        logger.info(f"  {self.payment_terms}")

        logger.info("\nConfidentiality Clause:")
        logger.info(f"  {self.confidentiality_clause}")

        logger.info("\nIntellectual Property Clause:")
        logger.info(f"  {self.intellectual_property_clause}")

        logger.info("\nTermination Conditions:")
        logger.info(f"  {self.termination_conditions}")
