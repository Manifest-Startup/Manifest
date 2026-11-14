from datetime import datetime

from app.utils.auto_property import AutoProperty
from app.utils.logger import logger


class StandardOperatingProcedure:
    def __init__(self, model, **kwargs):
        logger.info(
            "StandardOperatingProcedure Object created."
        )  # Logging the creation of SOP object
        self.model = model  # Assigning model
        # Assigning procedure_name, default is "Default Procedure"
        self._procedure_name = kwargs.get("procedure_name", "Default Procedure")
        # Assigning department, default is "Default Department"
        self._department = kwargs.get("department", "Default Department")

        # Getting effective_date from kwargs
        effective_date_str = kwargs.get("effective_date")
        if effective_date_str:
            try:
                # Trying to convert effective_date to datetime object
                self._effective_date = datetime.strptime(effective_date_str, "%Y-%m-%d")
            except ValueError:
                # If conversion fails, assign current date and time
                self._effective_date = datetime.now()
        else:
            # If effective_date is not provided, assign current date and time
            self._effective_date = datetime.now()

        # Assigning version, default is "1.0"
        self._version = kwargs.get("version", "1.0")
        # Initializing steps, responsibilities and reviewers as empty lists
        self._steps = []
        self._responsibilities = []
        self._reviewers = []
        # Initializing approval_requirements as empty string
        self._approval_requirements = ""

    # Auto-generated properties using AutoProperty descriptor
    procedure_name = AutoProperty("procedure_name")
    department = AutoProperty("department")
    effective_date = AutoProperty("effective_date")
    version = AutoProperty("version")
    steps = AutoProperty("steps")
    responsibilities = AutoProperty("responsibilities")
    reviewers = AutoProperty("reviewers")

    @property
    def approval_requirements(self):
        logger.debug("Accessing approval_requirements")  # Logging access to approval_requirements
        return self._approval_requirements

    @approval_requirements.setter
    def approval_requirements(self, value):
        logger.info(
            f"Setting approval_requirements: {value}"
        )  # Logging setting of approval_requirements
        self._approval_requirements = value

    def add_step(self, step_description):
        logger.info(f"Adding step: {step_description}")  # Logging addition of a step
        self._steps.append(step_description)

    def assign_responsibility(self, role, task):
        logger.info(
            f"Assigning responsibility - Role: {role}, Task: {task}"
        )  # Logging assignment of a responsibility
        self._responsibilities.append({"Role": role, "Task": task})

    def add_reviewer(self, reviewer_name, role):
        logger.info(
            f"Adding reviewer - Name: {reviewer_name}, Role: {role}"
        )  # Logging addition of a reviewer
        self._reviewers.append({"Reviewer": reviewer_name, "Role": role})

    def display_sop(self):
        logger.info(
            f"=== Standard Operating Procedure: {self.procedure_name} ==="
        )  # Logging display of SOP
        logger.info(f"Department           : {self.department}")
        logger.info(f"Effective Date       : {self.effective_date.strftime('%Y-%m-%d')}")
        logger.info(f"Version              : {self.version}")

        logger.info("\nProcedure Steps:")  # Logging procedure steps
        for i, step in enumerate(self.steps, start=1):
            logger.info(f"  Step {i}: {step}")

        logger.info("\nResponsibilities:")  # Logging responsibilities
        for responsibility in self.responsibilities:
            logger.info(
                f"  - {responsibility['Role']} is responsible for: {responsibility['Task']}"
            )

        logger.info("\nReviewers:")  # Logging reviewers
        for reviewer in self.reviewers:
            logger.info(f"  - {reviewer['Reviewer']} ({reviewer['Role']})")

        logger.info(
            f"\nApproval Requirements: {self.approval_requirements}"
        )  # Logging approval requirements

    def validate(self):
        # Validate required fields to ensure all fields are completed and valid
        required_fields = [self.procedure_name, self.department, self.effective_date, self.version]

        if any(not field for field in required_fields):
            # Logging error if any required field is not completed
            logger.error("Error: All required fields must be completed.")
            return False

        if not self.steps:
            # Logging error if no steps are defined
            logger.error("Error: At least one step must be defined.")
            return False

        # Logging successful validation
        logger.info("Validation successful.")
        return True

    def submit(self):
        # Simulate submitting the Standard Operating Procedure
        logger.info(f"Attempting to submit SOP: {self.procedure_name}")
        if self.validate():
            # Here we might saveIdea to a database or send to an API, etc.
            # Logging successful submission
            logger.info(f"SOP '{self.procedure_name}' has been successfully submitted.")
            return f"SOP '{self.procedure_name}' has been successfully submitted."
        else:
            # Logging failed submission due to validation errors
            logger.error("Submission failed due to validation errors.")
            return "Submission failed due to validation errors."
