from app.utils.logger import logger


class FoundersAgreement:
    def __init__(self, model, **kwargs):
        """
        Initialize a Founders' Agreement document with required fields.

        Expected kwargs:
        - startup_name (str)
        - business_address (str)
        - founders (list)
        - roles_responsibilities (dict)
        - ownership_percentage (dict)
        - vesting_schedule (str)
        - ip_assignment (str)
        - exit_conditions (str)
        """
        self.model = model  # The model to be used for the Founders' Agreement
        # Initialize all the required fields with default values if not provided
        self._startup_name = kwargs.get("startup_name", "Smart Solutions Inc.")
        self._business_address = kwargs.get("business_address", "101 Startup Lane, New York, NY")
        self._founders = kwargs.get("founders", ["Alice Johnson", "Bob Smith"])
        self._roles_responsibilities = kwargs.get(
            "roles_responsibilities",
            {
                "Alice Johnson": "CEO, responsible for overall business strategy and fundraising.",
                "Bob Smith": "CTO, responsible for product development and technical leadership.",
            },
        )
        self._ownership_percentage = kwargs.get(
            "ownership_percentage", {"Alice Johnson": 60, "Bob Smith": 40}
        )
        self._vesting_schedule = kwargs.get(
            "vesting_schedule", "4-year vesting with a 1-year cliff."
        )
        self._ip_assignment = kwargs.get(
            "ip_assignment", "All IP developed under the company belongs to Smart Solutions Inc."
        )
        self._exit_conditions = kwargs.get(
            "exit_conditions",
            "A founder must offer shares to other founders before selling externally; terms apply if a founder exits within the first 2 years.",
        )
        # Log the initialization of the Founders' Agreement
        logger.info(f"Initialized FoundersAgreement for startup: {self._startup_name}")

    # Define getters and setters for all the fields
    @property
    def startup_name(self):
        return self._startup_name

    @startup_name.setter
    def startup_name(self, value):
        self._startup_name = value

    @property
    def business_address(self):
        return self._business_address

    @business_address.setter
    def business_address(self, value):
        self._business_address = value

    @property
    def founders(self):
        return self._founders

    @founders.setter
    def founders(self, value):
        self._founders = value

    @property
    def roles_responsibilities(self):
        return self._roles_responsibilities

    @roles_responsibilities.setter
    def roles_responsibilities(self, value):
        self._roles_responsibilities = value

    @property
    def ownership_percentage(self):
        return self._ownership_percentage

    @ownership_percentage.setter
    def ownership_percentage(self, value):
        self._ownership_percentage = value

    @property
    def vesting_schedule(self):
        return self._vesting_schedule

    @vesting_schedule.setter
    def vesting_schedule(self, value):
        self._vesting_schedule = value

    @property
    def ip_assignment(self):
        return self._ip_assignment

    @ip_assignment.setter
    def ip_assignment(self, value):
        self._ip_assignment = value

    @property
    def exit_conditions(self):
        return self._exit_conditions

    @exit_conditions.setter
    def exit_conditions(self, value):
        self._exit_conditions = value

    def display_info(self):
        """
        Display the details of the Founders' Agreement.
        """
        # Log the details of the Founders' Agreement
        logger.info("=== Founders' Agreement ===")
        logger.info(f"Startup Name                : {self.startup_name}")
        logger.info(f"Business Address            : {self.business_address}")
        logger.info(f"Founders                    : {', '.join(self.founders)}")
        logger.info("Roles and Responsibilities  :")
        for founder, role in self.roles_responsibilities.items():
            logger.info(f"  - {founder}: {role}")
        logger.info(
            f"Ownership Percentage        : {', '.join([f'{name} ({ownership}%)' for name, ownership in self.ownership_percentage.items()])}"
        )
        logger.info(f"Vesting Schedule            : {self.vesting_schedule}")
        logger.info(f"IP Assignment               : {self.ip_assignment}")
        logger.info(f"Exit Conditions             : {self.exit_conditions}")

    def validate(self):
        """
        Validate required fields to ensure all fields are completed and valid.

        Returns:
        - bool: True if all fields are valid, otherwise False.
        """
        # Log the start of validation
        logger.info("Validating FoundersAgreement fields.")
        required_fields = [
            self.startup_name,
            self.business_address,
            self.founders,
            self.roles_responsibilities,
            self.ownership_percentage,
            self.vesting_schedule,
            self.ip_assignment,
            self.exit_conditions,
        ]

        # Check if all fields are completed
        if any(not field for field in required_fields):
            logger.error("Error: All fields must be completed.")
            return False
        # Check if ownership percentages are valid
        if not isinstance(self.ownership_percentage, dict) or not all(
            isinstance(ownership, int | float) for ownership in self.ownership_percentage.values()
        ):
            logger.error(
                "Error: Ownership percentages should be a dictionary with founder names and percentages."
            )
            return False
        # Check if total ownership percentage is 100%
        if sum(self.ownership_percentage.values()) != 100:
            logger.error("Error: Total ownership percentage of all founders must be 100%.")
            return False
        # Check if roles and responsibilities are defined for each founder
        if not isinstance(self.roles_responsibilities, dict) or not all(
            founder in self.roles_responsibilities for founder in self.founders
        ):
            logger.error("Error: Roles and responsibilities must be defined for each founder.")
            return False
        # Log the successful validation
        logger.info("Validation successful.")
        return True

    def submit(self):
        """
        Simulate submitting the Founders' Agreement.

        Returns:
        - str: A message indicating the submission status.
        """
        # Log the start of submission
        logger.info(f"Submitting FoundersAgreement for startup: {self.startup_name}")
        if self.validate():
            # If validation is successful, simulate submission
            # TODO: Ask Mihir: Consider adding actual submission logic here
            logger.info(
                f"Founders' Agreement for {self.startup_name} has been successfully submitted."
            )
            return f"Founders' Agreement for {self.startup_name} has been successfully submitted."
        else:
            # If validation fails, log the error and return a failure message
            logger.error("Submission failed due to validation errors.")
            return "Submission failed due to validation errors."
