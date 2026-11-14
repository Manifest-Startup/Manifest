from datetime import datetime

from app.utils.logger import logger


class PrivacyPolicy:
    def __init__(self, model, **kwargs):
        logger.info("PrivacyPolicy Object created.")  # Logging the creation of PrivacyPolicy object
        self.model = model
        self.company_name = kwargs.get(
            "company_name", "Default Company"
        )  # Setting company name, default is "Default Company"
        effective_date_str = kwargs.get("effective_date")  # Getting effective date from kwargs
        if effective_date_str:
            try:
                # Try to convert the date string into a datetime object
                self.effective_date = datetime.strptime(effective_date_str, "%Y-%m-%d")
            except ValueError:
                # If conversion fails, set the effective date as the current date
                self.effective_date = datetime.now()
        else:
            # If no date string is provided, set the effective date as the current date
            self.effective_date = datetime.now()
        # Initialize data collection, usage, sharing, user rights and security measures as empty strings
        self._data_collection = ""
        self._data_usage = ""
        self._data_sharing = ""
        self._user_rights = ""
        self._security_measures = ""

    @property
    def data_collection(self):
        logger.debug("Accessing data_collection")  # Logging access to data_collection
        return self._data_collection

    @data_collection.setter
    def data_collection(self, value):
        logger.info(f"Setting data_collection: {value}")  # Logging the setting of data_collection
        self._data_collection = value

    @property
    def data_usage(self):
        logger.debug("Accessing data_usage")  # Logging access to data_usage
        return self._data_usage

    @data_usage.setter
    def data_usage(self, value):
        logger.info(f"Setting data_usage: {value}")  # Logging the setting of data_usage
        self._data_usage = value

    @property
    def data_sharing(self):
        logger.debug("Accessing data_sharing")  # Logging access to data_sharing
        return self._data_sharing

    @data_sharing.setter
    def data_sharing(self, value):
        logger.info(f"Setting data_sharing: {value}")  # Logging the setting of data_sharing
        self._data_sharing = value

    @property
    def user_rights(self):
        logger.debug("Accessing user_rights")  # Logging access to user_rights
        return self._user_rights

    @user_rights.setter
    def user_rights(self, value):
        logger.info(f"Setting user_rights: {value}")  # Logging the setting of user_rights
        self._user_rights = value

    @property
    def security_measures(self):
        logger.debug("Accessing security_measures")  # Logging access to security_measures
        return self._security_measures

    @security_measures.setter
    def security_measures(self, value):
        logger.info(
            f"Setting security_measures: {value}"
        )  # Logging the setting of security_measures
        self._security_measures = value

    def display_privacy_policy(self):
        # Logging the display of privacy policy details
        logger.info(f"=== Privacy Policy of {self.company_name} ===")
        logger.info(f"Effective Date       : {self.effective_date.strftime('%Y-%m-%d')}")
        logger.info(f"Data Collection: {self.data_collection}")
        logger.info(f"Data Usage: {self.data_usage}")
        logger.info(f"Data Sharing: {self.data_sharing}")
        logger.info(f"User Rights: {self.user_rights}")
        logger.info(f"Security Measures: {self.security_measures}")


class TermsOfService:
    def __init__(self, model, **kwargs):
        logger.info(
            "TermsOfService Object created."
        )  # Logging the creation of TermsOfService object
        self.model = model
        self.company_name = kwargs.get(
            "company_name", "Default Company"
        )  # Setting company name, default is "Default Company"
        effective_date_str = kwargs.get("effective_date")  # Getting effective date from kwargs
        if effective_date_str:
            try:
                # Try to convert the date string into a datetime object
                self.effective_date = datetime.strptime(effective_date_str, "%Y-%m-%d")
            except ValueError:
                # If conversion fails, set the effective date as the current date
                self.effective_date = datetime.now()
        else:
            # If no date string is provided, set the effective date as the current date
            self.effective_date = datetime.now()
        # Initialize user obligations, acceptable use, liability, account termination and other terms as empty strings
        self._user_obligations = ""
        self._acceptable_use = ""
        self._liability = ""
        self._account_termination = ""
        self._other_terms = ""

    @property
    def user_obligations(self):
        logger.debug("Accessing user_obligations")  # Logging access to user_obligations
        return self._user_obligations

    @user_obligations.setter
    def user_obligations(self, value):
        logger.info(f"Setting user_obligations: {value}")  # Logging the setting of user_obligations
        self._user_obligations = value

    @property
    def acceptable_use(self):
        logger.debug("Accessing acceptable_use")  # Logging access to acceptable_use
        return self._acceptable_use

    @acceptable_use.setter
    def acceptable_use(self, value):
        logger.info(f"Setting acceptable_use: {value}")  # Logging the setting of acceptable_use
        self._acceptable_use = value

    @property
    def liability(self):
        logger.debug("Accessing liability")  # Logging access to liability
        return self._liability

    @liability.setter
    def liability(self, value):
        logger.info(f"Setting liability: {value}")  # Logging the setting of liability
        self._liability = value

    @property
    def account_termination(self):
        logger.debug("Accessing account_termination")  # Logging access to account_termination
        return self._account_termination

    @account_termination.setter
    def account_termination(self, value):
        logger.info(
            f"Setting account_termination: {value}"
        )  # Logging the setting of account_termination
        self._account_termination = value

    @property
    def other_terms(self):
        logger.debug("Accessing other_terms")  # Logging access to other_terms
        return self._other_terms

    @other_terms.setter
    def other_terms(self, value):
        logger.info(f"Setting other_terms: {value}")  # Logging the setting of other_terms
        self._other_terms = value

    def display_terms_of_service(self):
        # Logging the display of terms of service details
        logger.info(f"=== Terms of Service of {self.company_name} ===")
        logger.info(f"Effective Date       : {self.effective_date.strftime('%Y-%m-%d')}")
        logger.info(f"User Obligations: {self.user_obligations}")
        logger.info(f"Acceptable Use: {self.acceptable_use}")
        logger.info(f"Liability: {self.liability}")
        logger.info(f"Account Termination: {self.account_termination}")
        logger.info(f"Other Terms: {self.other_terms}")
