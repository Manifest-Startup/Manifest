from app.utils.auto_property import AutoProperty
from app.utils.logger import logger
from app.utils.redaction import mask


class EINService:
    def __init__(self, model, **kwargs):
        logger.info("EINService Object created.")
        self.model = model
        self._business_name = kwargs.get("business_name", "Default Business")
        self._business_address = kwargs.get("business_address", "Default Address")
        self._business_type = kwargs.get("business_type", "LLC")
        self._responsible_party_name = kwargs.get("responsible_party_name", "Default Owner")
        self._responsible_party_ssn = kwargs.get("responsible_party_ssn", "123-45-6789")
        self._responsible_party_address = kwargs.get(
            "responsible_party_address", "Default Owner Address"
        )

    business_name = AutoProperty("business_name")
    business_address = AutoProperty("business_address")
    business_type = AutoProperty("business_type")
    responsible_party_name = AutoProperty("responsible_party_name")
    responsible_party_ssn = AutoProperty("responsible_party_ssn")
    responsible_party_address = AutoProperty("responsible_party_address")

    def display_info(self):
        logger.info("=== EIN Application ===")
        logger.info(f"Business Name              : {self.business_name}")
        logger.info(f"Business Address           : {self.business_address}")
        logger.info(f"Business Type              : {self.business_type}")
        logger.info(f"Responsible Party Name     : {self.responsible_party_name}")
        logger.info(f"Responsible Party SSN      : {mask(self.responsible_party_ssn)}")
        logger.info(f"Responsible Party Address  : {self.responsible_party_address}")

    def validate(self):
        # Validate required fields to ensure all fields are completed and valid
        required_fields = [
            self.business_name,
            self.business_address,
            self.business_type,
            self.responsible_party_name,
            self.responsible_party_ssn,
            self.responsible_party_address,
        ]

        if any(not field for field in required_fields):
            # Logging error if any required field is not completed
            logger.error("Error: All fields must be completed.")
            return False

        # Validate SSN format (basic validation)
        if not self._is_valid_ssn(self.responsible_party_ssn):
            # Logging error if SSN format is invalid
            logger.error("Error: Invalid SSN format. Expected format: XXX-XX-XXXX")
            return False

        # Logging successful validation
        logger.info("Validation successful.")
        return True

    def _is_valid_ssn(self, ssn):
        # Basic SSN validation (XXX-XX-XXXX format)
        import re

        pattern = r"^\d{3}-\d{2}-\d{4}$"
        return bool(re.match(pattern, ssn))

    def submit(self):
        # Simulate submitting the EIN application
        logger.info(f"Attempting to submit EIN application for {self.business_name}.")
        if self.validate():
            # Here we might saveIdea to a database or send to an API, etc.
            # Logging successful submission
            logger.info(
                f"EIN application for {self.business_name} has been successfully submitted."
            )
            return f"EIN application for {self.business_name} has been successfully submitted."
        else:
            # Logging failed submission due to validation errors
            logger.error("Submission failed due to validation errors.")
            return "Submission failed due to validation errors."
