from datetime import datetime

from app.utils.logger import logger


class EmployeeContract:
    def __init__(self, model, **kwargs):
        logger.info(
            "EmployeeContract Object created."
        )  # Logging the creation of EmployeeContract object
        self.model = model
        self._employee_name = kwargs.get(
            "employee_name", "Default Employee"
        )  # Setting default value for employee_name if not provided
        self._position = kwargs.get(
            "position", "Default Position"
        )  # Setting default value for position if not provided

        start_date_str = kwargs.get("start_date")
        if start_date_str:
            try:
                self._start_date = datetime.strptime(
                    start_date_str, "%Y-%m-%d"
                )  # Parsing the start_date string to datetime object
            except ValueError:
                self._start_date = (
                    datetime.now()
                )  # If parsing fails, set start_date to current date
        else:
            self._start_date = (
                datetime.now()
            )  # If start_date is not provided, set it to current date

        self._salary = kwargs.get("salary", 0.0)  # Setting default value for salary if not provided
        self._employment_type = kwargs.get(
            "employment_type", "Full-Time"
        )  # Setting default value for employment_type if not provided
        self._benefits = []  # Initializing benefits as an empty list
        self._confidentiality_clause = ""  # Initializing confidentiality_clause as an empty string
        self._termination_conditions = ""  # Initializing termination_conditions as an empty string

    # Below are the property and setter methods for each attribute of EmployeeContract class
    # Each property method logs the access of the attribute and returns its value
    # Each setter method logs the new value being set to the attribute and updates the attribute's value

    @property
    def employee_name(self):
        logger.debug("Accessing employee_name")
        return self._employee_name

    @employee_name.setter
    def employee_name(self, value):
        logger.info(f"Setting employee_name: {value}")
        self._employee_name = value

    @property
    def position(self):
        logger.debug("Accessing position")
        return self._position

    @position.setter
    def position(self, value):
        logger.info(f"Setting position: {value}")
        self._position = value

    @property
    def start_date(self):
        logger.debug("Accessing start_date")
        return self._start_date

    @start_date.setter
    def start_date(self, value):
        logger.info(f"Setting start_date: {value}")
        self._start_date = value

    @property
    def salary(self):
        logger.debug("Accessing salary")
        return self._salary

    @salary.setter
    def salary(self, value):
        logger.info(f"Setting salary: {value}")
        self._salary = value

    @property
    def employment_type(self):
        logger.debug("Accessing employment_type")
        return self._employment_type

    @employment_type.setter
    def employment_type(self, value):
        logger.info(f"Setting employment_type: {value}")
        self._employment_type = value

    @property
    def benefits(self):
        logger.debug("Accessing benefits")
        return self._benefits

    @benefits.setter
    def benefits(self, value):
        logger.info(f"Setting benefits: {value}")
        self._benefits = value

    @property
    def confidentiality_clause(self):
        logger.debug("Accessing confidentiality_clause")
        return self._confidentiality_clause

    @confidentiality_clause.setter
    def confidentiality_clause(self, value):
        logger.info(f"Setting confidentiality_clause: {value}")
        self._confidentiality_clause = value

    @property
    def termination_conditions(self):
        logger.debug("Accessing termination_conditions")
        return self._termination_conditions

    @termination_conditions.setter
    def termination_conditions(self, value):
        logger.info(f"Setting termination_conditions: {value}")
        self._termination_conditions = value

    def add_benefit(self, benefit):
        logger.info(f"Adding benefit: {benefit}")  # Logging the benefit being added
        self._benefits.append(benefit)  # Adding the benefit to the benefits list

    def display_contract(self):
        # This method logs the details of the employee contract
        logger.info(f"=== Employee Contract for {self.employee_name} ===")
        logger.info(f"Position            : {self.position}")
        logger.info(f"Start Date          : {self.start_date.strftime('%Y-%m-%d')}")
        logger.info(f"Salary              : ${self.salary:,.2f} per year")
        logger.info(f"Employment Type     : {self.employment_type}")

        logger.info("\nBenefits:")
        for benefit in self.benefits:
            logger.info(f"  - {benefit}")

        logger.info(f"\nConfidentiality Clause: {self.confidentiality_clause}")
        logger.info(f"\nTermination Conditions: {self.termination_conditions}")


class OfferLetter:
    def __init__(self, model, **kwargs):
        logger.info("OfferLetter Object created.")  # Logging the creation of OfferLetter object
        self.model = model
        self._employee_name = kwargs.get(
            "employee_name", "Default Candidate"
        )  # Setting default value for employee_name if not provided
        self._position = kwargs.get(
            "position", "Default Position"
        )  # Setting default value for position if not provided

        start_date_str = kwargs.get("start_date")
        if start_date_str:
            try:
                self._start_date = datetime.strptime(
                    start_date_str, "%Y-%m-%d"
                )  # Parsing the start_date string to datetime object
            except ValueError:
                self._start_date = (
                    datetime.now()
                )  # If parsing fails, set start_date to current date
        else:
            self._start_date = (
                datetime.now()
            )  # If start_date is not provided, set it to current date

        self._starting_salary = kwargs.get(
            "starting_salary", 0.0
        )  # Setting default value for starting_salary if not provided
        self._hiring_manager = kwargs.get(
            "hiring_manager", "Default Hiring Manager"
        )  # Setting default value for hiring_manager if not provided

    # Below are the property and setter methods for each attribute of OfferLetter class
    # Each property method logs the access of the attribute and returns its value
    # Each setter method logs the new value being set to the attribute and updates the attribute's value

    @property
    def employee_name(self):
        logger.debug("Accessing employee_name (OfferLetter)")
        return self._employee_name

    @employee_name.setter
    def employee_name(self, value):
        logger.info(f"Setting employee_name (OfferLetter): {value}")
        self._employee_name = value

    @property
    def position(self):
        logger.debug("Accessing position (OfferLetter)")
        return self._position

    @position.setter
    def position(self, value):
        logger.info(f"Setting position (OfferLetter): {value}")
        self._position = value

    @property
    def start_date(self):
        logger.debug("Accessing start_date (OfferLetter)")
        return self._start_date

    @start_date.setter
    def start_date(self, value):
        logger.info(f"Setting start_date (OfferLetter): {value}")
        self._start_date = value

    @property
    def starting_salary(self):
        logger.debug("Accessing starting_salary")
        return self._starting_salary

    @starting_salary.setter
    def starting_salary(self, value):
        logger.info(f"Setting starting_salary: {value}")
        self._starting_salary = value

    @property
    def hiring_manager(self):
        logger.debug("Accessing hiring_manager")
        return self._hiring_manager

    @hiring_manager.setter
    def hiring_manager(self, value):
        logger.info(f"Setting hiring_manager: {value}")
        self._hiring_manager = value

    def display_offer_letter(self):
        # This method logs the details of the offer letter
        logger.info("=== Offer Letter ===")
        logger.info(f"Dear {self.employee_name},")
        logger.info(f"We are pleased to offer you the position of {self.position} at our company.")
        logger.info(
            f"Your start date will be {self.start_date.strftime('%Y-%m-%d')}, and your starting salary will be ${self.starting_salary:,.2f} per year."
        )
        logger.info(
            "Please idea that this offer is contingent upon successful completion of background checks and other pre-employment conditions."
        )
        logger.info(
            f"We look forward to welcoming you to the team!\n\nBest regards,\n{self.hiring_manager}"
        )
