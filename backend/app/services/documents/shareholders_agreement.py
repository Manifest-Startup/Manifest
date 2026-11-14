from app.utils.auto_property import AutoProperty
from app.utils.logger import logger


class ShareholdersAgreement:
    def __init__(self, model, **kwargs):
        # Logging the initialization of the ShareholdersAgreement object
        logger.info("Initializing ShareholdersAgreement object.")
        self.model = model
        # Setting default values for the required fields if not provided
        self._company_name = kwargs.get("company_name", "Tech Ventures Inc.")
        self._business_address = kwargs.get(
            "business_address", "789 Innovation Blvd, San Francisco, CA"
        )
        self._shareholders = kwargs.get(
            "shareholders", {"Alice Green": 40, "Bob Blue": 30, "Charlie Red": 30}
        )
        self._board_structure = kwargs.get(
            "board_structure",
            "The board consists of a CEO, CFO, and CTO with equal decision-making authority.",
        )
        self._share_transfer_restrictions = kwargs.get(
            "share_transfer_restrictions", "Shares cannot be transferred without board approval."
        )
        self._voting_rights = kwargs.get(
            "voting_rights",
            "Each share entitles the holder to one vote on major company decisions.",
        )
        self._dividend_policy = kwargs.get(
            "dividend_policy",
            "Dividends will be distributed based on ownership percentage, subject to board approval.",
        )
        self._termination_conditions = kwargs.get(
            "termination_conditions",
            "The company will be dissolved upon unanimous shareholder agreement or court order.",
        )

    # Auto-generated properties using AutoProperty descriptor
    company_name = AutoProperty("company_name")
    business_address = AutoProperty("business_address")
    shareholders = AutoProperty("shareholders")
    board_structure = AutoProperty("board_structure")
    share_transfer_restrictions = AutoProperty("share_transfer_restrictions")
    voting_rights = AutoProperty("voting_rights")
    dividend_policy = AutoProperty("dividend_policy")
    termination_conditions = AutoProperty("termination_conditions")

    def display_info(self):
        # Logging the details of the Shareholders Agreement
        logger.info("=== Shareholders Agreement ===")
        logger.info(f"Company Name                : {self.company_name}")
        logger.info(f"Business Address            : {self.business_address}")
        logger.info(
            f"Shareholders                : {', '.join([f'{name} ({ownership}%)' for name, ownership in self.shareholders.items()])}"
        )
        logger.info(f"Board Structure             : {self.board_structure}")
        logger.info(f"Share Transfer Restrictions : {self.share_transfer_restrictions}")
        logger.info(f"Voting Rights               : {self.voting_rights}")
        logger.info(f"Dividend Policy             : {self.dividend_policy}")
        logger.info(f"Termination Conditions      : {self.termination_conditions}")

    def validate(self):
        # Validate required fields to ensure all fields are completed and valid
        required_fields = [
            self.company_name,
            self.business_address,
            self.shareholders,
            self.board_structure,
            self.share_transfer_restrictions,
            self.voting_rights,
            self.dividend_policy,
            self.termination_conditions,
        ]

        if any(not field for field in required_fields):
            # Logging error if any required field is not completed
            logger.error("Error: All fields must be completed.")
            return False
        if not isinstance(self.shareholders, dict) or not all(
            isinstance(ownership, int | float) for ownership in self.shareholders.values()
        ):
            # Logging error if shareholders is not a dictionary or ownership percentages are not numbers
            logger.error(
                "Error: Shareholders should be a dictionary with names and ownership percentages."
            )
            return False
        if sum(self.shareholders.values()) != 100:
            # Logging error if total ownership percentage of all shareholders is not 100%
            logger.error("Error: Total ownership percentage of all shareholders must be 100%.")
            return False
        # Logging successful validation
        logger.info("Validation successful.")
        return True

    def submit(self):
        # Simulate submitting the Shareholders Agreement
        logger.info(f"Attempting to submit Shareholders Agreement for {self.company_name}.")
        if self.validate():
            # Here we might saveIdea to a database or send to an API, etc.
            # Logging successful submission
            logger.info(
                f"Shareholders Agreement for {self.company_name} has been successfully submitted."
            )
            return (
                f"Shareholders Agreement for {self.company_name} has been successfully submitted."
            )
        else:
            # Logging failed submission due to validation errors
            logger.error("Submission failed due to validation errors.")
            return "Submission failed due to validation errors."
