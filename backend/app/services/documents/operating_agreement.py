from app.utils.logger import logger


class OperatingAgreement:
    def __init__(self, model, **kwargs):
        """
        Initialize an Operating Agreement document with required fields.

        Expected kwargs:
        - llc_name (str)
        - business_address (str)
        - members (dict)
        - management_structure (str)
        - profit_distribution (str)
        - dissolution_terms (str)
        """
        self.model = model
        # Default values are provided for all the fields
        self._llc_name = kwargs.get("llc_name", "Green Energy Solutions LLC")
        self._business_address = kwargs.get(
            "business_address", "456 Sustainability Avenue, Austin, TX"
        )
        self._members = kwargs.get("members", {"Alice Johnson": 50, "Bob Smith": 50})
        self._management_structure = kwargs.get("management_structure", "Member-managed")
        self._profit_distribution = kwargs.get(
            "profit_distribution",
            "Profits and losses will be distributed according to ownership percentage.",
        )
        self._dissolution_terms = kwargs.get(
            "dissolution_terms",
            "The LLC will be dissolved upon mutual agreement of all members or if no active members remain.",
        )
        # Log the initialization of the Operating Agreement
        logger.info(f"OperatingAgreement initialized for LLC: {self._llc_name}")

    @property
    def llc_name(self):
        return self._llc_name

    @llc_name.setter
    def llc_name(self, value):
        self._llc_name = value

    @property
    def business_address(self):
        return self._business_address

    @business_address.setter
    def business_address(self, value):
        self._business_address = value

    @property
    def members(self):
        return self._members

    @members.setter
    def members(self, value):
        self._members = value

    @property
    def management_structure(self):
        return self._management_structure

    @management_structure.setter
    def management_structure(self, value):
        self._management_structure = value

    @property
    def profit_distribution(self):
        return self._profit_distribution

    @profit_distribution.setter
    def profit_distribution(self, value):
        self._profit_distribution = value

    @property
    def dissolution_terms(self):
        return self._dissolution_terms

    @dissolution_terms.setter
    def dissolution_terms(self, value):
        self._dissolution_terms = value

    def display_info(self):
        """
        Display the details of the Operating Agreement.
        """
        # Log the details of the Operating Agreement
        logger.info("=== Operating Agreement ===")
        logger.info(f"LLC Name             : {self.llc_name}")
        logger.info(f"Business Address     : {self.business_address}")
        logger.info(
            f"Members              : {', '.join([f'{name} ({ownership}%)' for name, ownership in self.members.items()])}"
        )
        logger.info(f"Management Structure : {self.management_structure}")
        logger.info(f"Profit Distribution  : {self.profit_distribution}")
        logger.info(f"Dissolution Terms    : {self.dissolution_terms}")

    def validate(self):
        """
        Validate required fields to ensure all fields are completed and valid.

        Returns:
        - bool: True if all fields are valid, otherwise False.
        """
        # List of required fields
        required_fields = [
            self.llc_name,
            self.business_address,
            self.members,
            self.management_structure,
            self.profit_distribution,
            self.dissolution_terms,
        ]

        # Check if all fields are completed
        if any(not field for field in required_fields):
            logger.error("Error: All fields must be completed.")
            return False
        # Check if members field is a dictionary and ownership is a number
        if not isinstance(self.members, dict) or not all(
            isinstance(ownership, int | float) for ownership in self.members.values()
        ):
            logger.error(
                "Error: Members should be a dictionary with names and ownership percentages."
            )
            return False
        # Check if total ownership percentage is 100%
        if sum(self.members.values()) != 100:
            logger.error("Error: Total ownership percentage of all members must be 100%.")
            return False
        # If all checks pass, validation is successful
        logger.info("Validation successful.")
        return True

    def submit(self):
        """
        Simulate submitting the Operating Agreement.

        Returns:
        - str: A message indicating the submission status.
        """
        # Log the attempt to submit the Operating Agreement
        logger.info(f"Attempting submission for Operating Agreement of {self.llc_name}.")
        if self.validate():
            # If validation is successful, simulate submission
            # TODO: Ask Mihir: Should we add a database or API call here for actual submission?
            logger.info(f"Operating Agreement for {self.llc_name} has been successfully submitted.")
            return f"Operating Agreement for {self.llc_name} has been successfully submitted."
        else:
            # If validation fails, log the error and return failure message
            logger.error("Submission failed due to validation errors.")
            return "Submission failed due to validation errors."
