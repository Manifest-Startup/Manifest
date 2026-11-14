from app.utils.auto_property import AutoProperty
from app.utils.logger import logger


class BankAccount:
    def __init__(self, model, **kwargs):
        logger.info(
            "BankAccount Object created."
        )  # Logging the creation of a new BankAccount object
        self.model = model  # Assigning the model to the object

        # Assigning the account holder name from the kwargs or setting it to "Default Account Holder" if not provided
        self._account_holder_name = kwargs.get(
            "account_holder_name", kwargs.get("account_holder", "Default Account Holder")
        )

        # Assigning the bank name from the kwargs or setting it to "Default Bank" if not provided
        self._bank_name = kwargs.get("bank_name", "Default Bank")

        # Assigning the account type from the kwargs or setting it to "Checking" if not provided
        self._account_type = kwargs.get("account_type", "Checking")

        # Assigning the routing number from the kwargs or setting it to "123456789" if not provided
        self._routing_number = kwargs.get("routing_number", "123456789")

        # Assigning the balance from the kwargs or setting it to 0.0 if not provided
        self._balance = kwargs.get("balance", 0.0)

    # Auto-generated properties using AutoProperty descriptor
    account_holder_name = AutoProperty("account_holder_name")
    bank_name = AutoProperty("bank_name")
    account_type = AutoProperty("account_type")
    routing_number = AutoProperty("routing_number")

    # Add balance property for deposit/withdraw tests
    @property
    def balance(self):
        return getattr(self, "_balance", 0.0)

    @balance.setter
    def balance(self, value):
        self._balance = value

    def deposit(self, amount):
        if amount <= 0:
            logger.warning("Attempted deposit with non-positive amount.")
            return "Deposit amount must be greater than zero."
        self.balance += amount
        logger.info(f"Deposited ${amount:.2f}. New balance: ${self.balance:.2f}")
        return f"${amount:.2f} has been deposited. New balance: ${self.balance:.2f}"

    def withdraw(self, amount):
        if amount <= 0:
            logger.warning("Attempted withdrawal with non-positive amount.")
            return "Withdrawal amount must be greater than zero."
        if amount > self.balance:
            logger.warning("Attempted withdrawal with insufficient funds.")
            return "Insufficient funds."
        self.balance -= amount
        logger.info(f"Withdrew ${amount:.2f}. New balance: ${self.balance:.2f}")
        return f"${amount:.2f} has been withdrawn. New balance: ${self.balance:.2f}"

    def display_info(self):
        # Logging the details of the bank account
        logger.info("=== Bank Account Information ===")
        logger.info(f"Account Holder Name : {self.account_holder_name}")
        logger.info(f"Bank Name           : {self.bank_name}")
        logger.info(f"Account Type        : {self.account_type}")
        logger.info(f"Routing Number      : {self.routing_number}")

    def validate(self):
        # Validate required fields to ensure all fields are completed and valid
        required_fields = [
            self.account_holder_name,
            self.bank_name,
            self.account_type,
            self.routing_number,
        ]

        if any(not field for field in required_fields):
            # Logging error if any required field is not completed
            logger.error("Error: All fields must be completed.")
            return False

        # Validate routing number format (basic validation)
        if not self._is_valid_routing_number(self.routing_number):
            # Logging error if routing number format is invalid
            logger.error("Error: Invalid routing number format. Expected 9 digits.")
            return False

        # Logging successful validation
        logger.info("Validation successful.")
        return True

    def _is_valid_routing_number(self, routing_number):
        # Basic routing number validation (9 digits)
        import re

        pattern = r"^\d{9}$"
        return bool(re.match(pattern, routing_number))

    def submit(self):
        # Simulate submitting the bank account application
        logger.info(
            f"Attempting to submit bank account application for {self.account_holder_name}."
        )
        if self.validate():
            # Here we might saveIdea to a database or send to an API, etc.
            # Logging successful submission
            logger.info(
                f"Bank account application for {self.account_holder_name} has been successfully submitted."
            )
            return f"Bank account application for {self.account_holder_name} has been successfully submitted."
        else:
            # Logging failed submission due to validation errors
            logger.error("Submission failed due to validation errors.")
            return "Submission failed due to validation errors."

    def get_balance(self):
        return self.balance
