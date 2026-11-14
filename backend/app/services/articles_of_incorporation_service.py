from app.utils.logger import logger


class ArticlesOfIncorporation:
    def __init__(self, model, **kwargs):
        """
        Initialize an Articles of Incorporation document with required fields.

        Expected kwargs:
        - business_name (str)
        - business_purpose (str)
        - business_address (str)
        - registered_agent (str)
        - shares_authorized (int)
        - incorporator_name (str)
        """
        self.model = model
        # Default values are provided for all the fields
        self._business_name = kwargs.get("business_name", "Tech Innovations Inc.")
        self._business_purpose = kwargs.get(
            "business_purpose", "Develop and sell innovative tech products."
        )
        self._business_address = kwargs.get(
            "business_address", "123 Innovation Drive, Silicon Valley, CA"
        )
        self._registered_agent = kwargs.get("registered_agent", "John Doe")
        self._shares_authorized = kwargs.get("shares_authorized", 10000)
        self._incorporator_name = kwargs.get("incorporator_name", "Jane Smith")
        # Logging the initialization of the ArticlesOfIncorporation
        logger.info(f"Initialized ArticlesOfIncorporation for business '{self._business_name}'")

    @property
    def business_name(self):
        return self._business_name

    @business_name.setter
    def business_name(self, value):
        self._business_name = value

    @property
    def business_purpose(self):
        return self._business_purpose

    @business_purpose.setter
    def business_purpose(self, value):
        self._business_purpose = value

    @property
    def business_address(self):
        return self._business_address

    @business_address.setter
    def business_address(self, value):
        self._business_address = value

    @property
    def registered_agent(self):
        return self._registered_agent

    @registered_agent.setter
    def registered_agent(self, value):
        self._registered_agent = value

    @property
    def shares_authorized(self):
        return self._shares_authorized

    @shares_authorized.setter
    def shares_authorized(self, value):
        self._shares_authorized = value

    @property
    def incorporator_name(self):
        return self._incorporator_name

    @incorporator_name.setter
    def incorporator_name(self, value):
        self._incorporator_name = value

    def show(self):
        """
        Show the details of the Articles of Incorporation.
        """
        # Logging the details of the Articles of Incorporation
        logger.info("=== Articles of Incorporation ===")
        logger.info(f"Business Name        : {self.business_name}")
        logger.info(f"Business Purpose     : {self.business_purpose}")
        logger.info(f"Business Address     : {self.business_address}")
        logger.info(f"Registered Agent     : {self.registered_agent}")
        logger.info(f"Shares Authorized    : {self.shares_authorized}")
        logger.info(f"Incorporator Name    : {self.incorporator_name}")

    def validate(self):
        """
        Validate required fields to ensure all fields are filled correctly.

        Returns:
        - bool: True if all fields are valid, otherwise False.
        """
        required_fields = [
            self.business_name,
            self.business_purpose,
            self.business_address,
            self.registered_agent,
            self.shares_authorized,
            self.incorporator_name,
        ]

        # Check if all fields are filled
        if any(not field for field in required_fields):
            logger.error("Error: All fields must be completed.")
            return False
        # Check if shares_authorized is a positive integer
        if not isinstance(self.shares_authorized, int) or self.shares_authorized <= 0:
            logger.error("Error: Shares authorized must be a positive integer.")
            return False
        # If all checks pass, validation is successful
        logger.info("Validation successful.")
        return True

    def submit(self):
        """
        Simulate submitting the Articles of Incorporation.

        Returns:
        - str: A message indicating the submission status.
        """
        # Log the attempt to submit the Articles of Incorporation
        logger.info(f"Attempting to submit Articles of Incorporation for {self.business_name}")
        if self.validate():
            # If validation is successful, log the successful submission
            logger.info(
                f"Articles of Incorporation for {self.business_name} have been successfully submitted."
            )
            return f"Articles of Incorporation for {self.business_name} have been successfully submitted."
        else:
            # If validation fails, log the failure
            logger.error("Submission failed due to validation errors.")
            return "Submission failed due to validation errors."

    def update(self):
        """
        Generate and update Articles of Incorporation content based on the provided idea description.
        """
        # Log the start of the AI generation process
        logger.info("Generating Articles of Incorporation using AI.")
        if hasattr(self.model, "ai_layer"):
            content = self.model.ai_layer.generate_articles_of_incorporation(
                self.model.idea.description
            )
            if isinstance(content, dict):
                for attr, value in content.items():
                    if hasattr(self, attr):
                        setattr(self, attr, value)
                        # Log the update of each attribute
                        logger.info(f"Updated '{attr}' to: {value}")
                    else:
                        # Log any unknown fields that are ignored
                        logger.warning(f"Ignored unknown field: {attr}")
            else:
                # Log an error if the AI does not return a valid dictionary
                logger.error("AI did not return a valid dictionary for Articles of Incorporation.")
        else:
            # Log a warning if the model does not have an AI layer
            logger.warning("Model does not have an AI layer.")
