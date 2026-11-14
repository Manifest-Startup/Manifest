from app.utils.logger import logger


class IntellectualPropertyAgreement:
    # Internal prompt template for generating a provisional patent application
    _patent_prompt = """
    Given the startup idea: "{idea}", write a draft for a provisional patent application.
    The draft should include:
    - Title of the invention
    - Abstract
    - Background
    - Summary of the invention
    - Detailed description of the invention
    - Claims (example set)
    - Potential diagrams or illustrations (described in words)

    Format the response in clearly labeled sections.
    """

    def __init__(self, model, **kwargs):
        """
        Initialize an Intellectual Property Agreement with required fields.

        Expected kwargs:
        - company_name (str)
        - company_address (str)
        - parties (list)
        - confidentiality_clause (str)
        - usage_rights (str)
        - transfer_conditions (str)
        """
        self.model = model  # AI model for generating patent drafts
        # Default values are provided for all fields, but can be overridden by kwargs
        self._company_name = kwargs.get("company_name", "Innovative AI Corp")
        self._company_address = kwargs.get("company_address", "456 AI Blvd, San Francisco, CA")
        self._parties = kwargs.get("parties", ["Alice Green", "Bob Blue", "Innovative AI Corp"])
        self._confidentiality_clause = kwargs.get(
            "confidentiality_clause",
            "All parties must keep proprietary information confidential and not disclose it without consent.",
        )
        self._usage_rights = kwargs.get(
            "usage_rights",
            "The company retains exclusive rights to use, modify, and distribute the IP.",
        )
        self._transfer_conditions = kwargs.get(
            "transfer_conditions",
            "IP ownership may be transferred only upon board approval and written agreement.",
        )
        self.patents = []  # List to store patents
        self.copyrights = []  # List to store copyrights
        self.trademarks = []  # List to store trademarks
        logger.info(f"Initialized IntellectualPropertyAgreement for company: {self._company_name}")

    # Getters and setters for all fields
    @property
    def company_name(self):
        return self._company_name

    @company_name.setter
    def company_name(self, value):
        self._company_name = value

    @property
    def company_address(self):
        return self._company_address

    @company_address.setter
    def company_address(self, value):
        self._company_address = value

    @property
    def parties(self):
        return self._parties

    @parties.setter
    def parties(self, value):
        self._parties = value

    @property
    def confidentiality_clause(self):
        return self._confidentiality_clause

    @confidentiality_clause.setter
    def confidentiality_clause(self, value):
        self._confidentiality_clause = value

    @property
    def usage_rights(self):
        return self._usage_rights

    @usage_rights.setter
    def usage_rights(self, value):
        self._usage_rights = value

    @property
    def transfer_conditions(self):
        return self._transfer_conditions

    @transfer_conditions.setter
    def transfer_conditions(self, value):
        self._transfer_conditions = value

    # Methods for adding patents, copyrights, and trademarks
    def add_patent(self, patent_name, inventor, patent_number, filing_date, expiration_date):
        patent = self.Patent(patent_name, inventor, patent_number, filing_date, expiration_date)
        self.patents.append(patent)
        logger.info(f"Added patent: {patent_name}")

    def add_copyright(self, title, author, registration_number, registration_date, work_type):
        copyright_obj = self.Copyright(
            title, author, registration_number, registration_date, work_type
        )
        self.copyrights.append(copyright_obj)
        logger.info(f"Added copyright: {title}")

    def add_trademark(
        self, trademark_name, owner, registration_number, registration_date, description
    ):
        trademark = self.Trademark(
            trademark_name, owner, registration_number, registration_date, description
        )
        self.trademarks.append(trademark)
        logger.info(f"Added trademark: {trademark_name}")

    # Method to display all information about the agreement
    def display_info(self):
        """
        Display the details of the Intellectual Property Agreement.
        """
        logger.info("=== Intellectual Property Agreement ===")
        logger.info(f"Company Name              : {self.company_name}")
        logger.info(f"Company Address           : {self.company_address}")
        logger.info(f"Parties Involved          : {', '.join(self.parties)}")
        logger.info(f"Confidentiality Clause    : {self.confidentiality_clause}")
        logger.info(f"Usage Rights              : {self.usage_rights}")
        logger.info(f"Transfer Conditions       : {self.transfer_conditions}")
        logger.info("\nPatents:")
        for patent in self.patents:
            patent.display_info()
        logger.info("\nCopyrights:")
        for copyright in self.copyrights:
            copyright.display_info()
        logger.info("\nTrademarks:")
        for trademark in self.trademarks:
            trademark.display_info()

    # Method to validate all fields of the agreement
    def validate(self):
        """
        Validate required fields to ensure all fields are completed and valid.

        Returns:
        - bool: True if all fields are valid, otherwise False.
        """
        required_fields = [
            self.company_name,
            self.company_address,
            self.parties,
            self.confidentiality_clause,
            self.usage_rights,
            self.transfer_conditions,
        ]

        if any(not field for field in required_fields):
            logger.error("Error: All fields must be completed.")
            return False
        if not isinstance(self.parties, list) or not all(
            isinstance(party, str) for party in self.parties
        ):
            logger.error("Error: Parties must be a list of names.")
            return False
        return True

    # Method to simulate submission of the agreement
    def submit(self):
        """
        Simulate submitting the Intellectual Property Agreement.

        Returns:
        - str: A message indicating the submission status.
        """
        if self.validate():
            # Here we might saveIdea to a database or send to an API, etc.
            message = f"Intellectual Property Agreement for {self.company_name} has been successfully submitted."
            logger.info(message)
            return message
        else:
            message = "Submission failed due to validation errors."
            logger.error(message)
            return message

    # Inner classes for patents, copyrights, and trademarks
    class Patent:
        def __init__(self, patent_name, inventor, patent_number, filing_date, expiration_date):
            self.patent_name = patent_name
            self.inventor = inventor
            self.patent_number = patent_number
            self.filing_date = filing_date
            self.expiration_date = expiration_date
            logger.info(f"Initialized Patent: {patent_name}")

        def display_info(self):
            logger.info(f"  - Patent Name          : {self.patent_name}")
            logger.info(f"    Inventor             : {self.inventor}")
            logger.info(f"    Patent Number        : {self.patent_number}")
            logger.info(f"    Filing Date          : {self.filing_date}")
            logger.info(f"    Expiration Date      : {self.expiration_date}")

    class Copyright:
        def __init__(self, title, author, registration_number, registration_date, work_type):
            self.title = title
            self.author = author
            self.registration_number = registration_number
            self.registration_date = registration_date
            self.work_type = work_type
            logger.info(f"Initialized Copyright: {title}")

        def display_info(self):
            logger.info(f"  - Title                : {self.title}")
            logger.info(f"    Author               : {self.author}")
            logger.info(f"    Registration Number  : {self.registration_number}")
            logger.info(f"    Registration Date    : {self.registration_date}")
            logger.info(f"    Work Type            : {self.work_type}")

    class Trademark:
        def __init__(
            self, trademark_name, owner, registration_number, registration_date, description
        ):
            self.trademark_name = trademark_name
            self.owner = owner
            self.registration_number = registration_number
            self.registration_date = registration_date
            self.description = description
            logger.info(f"Initialized Trademark: {trademark_name}")

        def display_info(self):
            logger.info(f"  - Trademark Name       : {self.trademark_name}")
            logger.info(f"    Owner                : {self.owner}")
            logger.info(f"    Registration Number  : {self.registration_number}")
            logger.info(f"    Registration Date    : {self.registration_date}")
            logger.info(f"    Description          : {self.description}")

    # Private method to generate a patent draft using the AI model
    def _generate(self):
        """
        Internal method to generate a draft patent application using a standardized prompt.
        Uses the model's AI layer and idea description to generate content.
        Stores the result in the 'patents' list and returns the content.
        """
        logger.info("Generating patent application using AI layer from model.")
        content = self.model.ai_layer.generate_text(
            [
                {
                    "role": "user",
                    "content": self._patent_prompt.format(idea=self.model.idea_description),
                }
            ]
        )
        self.patents.append({"generated_draft": content})
        logger.info("Patent application content added to patents list.")
        return content

    # Method to update the agreement with a new idea
    def update(self):
        """
        Update the patent-related content using the AI layer and the given idea description.
        This will regenerate and store a new patent draft based on the idea.
        """
        logger.info("Updating IntellectualPropertyAgreement with new idea.")
        self._generate()
