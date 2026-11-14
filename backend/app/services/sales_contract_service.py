from datetime import datetime

from app.utils.auto_property import AutoProperty
from app.utils.logger import logger


class SalesContract:
    def __init__(self, model, **kwargs):
        logger.info(
            "SalesContract Object created."
        )  # Log the creation of a new SalesContract object
        self.model = model
        self._seller_name = kwargs.get(
            "seller_name", "Default Seller"
        )  # Set seller name, default is "Default Seller"
        self._buyer_name = kwargs.get(
            "buyer_name", "Default Buyer"
        )  # Set buyer name, default is "Default Buyer"

        effective_date_str = kwargs.get("effective_date")  # Get effective date from kwargs
        if effective_date_str:
            try:
                # Try to convert effective_date_str to datetime object
                self._effective_date = datetime.strptime(effective_date_str, "%Y-%m-%d")
            except ValueError:
                # If conversion fails, set effective date to current date
                self._effective_date = datetime.now()
        else:
            # If effective_date_str is not provided, set effective date to current date
            self._effective_date = datetime.now()

        # Initialize other attributes of SalesContract
        self._products_services = []
        self._total_amount = 0.0
        self._payment_terms = ""
        self._delivery_terms = ""
        self._warranties = []
        self._termination_conditions = ""

    # Auto-generated properties using AutoProperty descriptor
    seller_name = AutoProperty("seller_name")
    buyer_name = AutoProperty("buyer_name")
    effective_date = AutoProperty("effective_date")
    products_services = AutoProperty("products_services")
    total_amount = AutoProperty("total_amount")
    payment_terms = AutoProperty("payment_terms")
    delivery_terms = AutoProperty("delivery_terms")
    warranties = AutoProperty("warranties")
    termination_conditions = AutoProperty("termination_conditions")

    def add_product_or_service(self, name, description, quantity, unit_price):
        if quantity <= 0 or unit_price <= 0:
            return "Quantity and unit price must be positive."

        # Create a new product/service dictionary
        product = {
            "Name": name,
            "Description": description,
            "Quantity": quantity,
            "Unit Price": unit_price,
            "Total Price": quantity * unit_price,
        }
        self._products_services.append(product)  # Add the new product/service to the list
        self._total_amount += product["Total Price"]  # Update the total amount
        logger.info(
            f"Added product/service: {product}"
        )  # Log the addition of the new product/service
        return f"Product/Service '{name}' has been added."

    def set_payment_terms(self, terms):
        logger.info(f"Setting payment_terms: {terms}")  # Log setting of payment_terms
        self.payment_terms = terms

    def set_delivery_terms(self, terms):
        logger.info(f"Setting delivery_terms: {terms}")  # Log setting of delivery_terms
        self.delivery_terms = terms

    def add_warranty(self, warranty):
        logger.info(f"Adding warranty: {warranty}")  # Log the addition of a new warranty
        self._warranties.append(warranty)

    def set_termination_conditions(self, conditions):
        logger.info(
            f"Setting termination_conditions: {conditions}"
        )  # Log setting of termination_conditions
        self.termination_conditions = conditions

    def display_contract(self):
        # Log the display of the contract details
        logger.info("=== Sales Contract ===")
        logger.info(f"Seller               : {self.seller_name}")
        logger.info(f"Buyer                : {self.buyer_name}")
        logger.info(f"Effective Date       : {self.effective_date.strftime('%Y-%m-%d')}")
        logger.info("\nProducts/Services:")
        logger.info(
            "Name                | Description           | Quantity | Unit Price | Total Price"
        )
        logger.info(
            "-------------------------------------------------------------------------------"
        )
        for item in self.products_services:
            logger.info(
                f"{item['Name']:<20} | {item['Description']:<20} | {item['Quantity']:<8} | ${item['Unit Price']:<10,.2f} | ${item['Total Price']:<10,.2f}"
            )
        logger.info(
            "-------------------------------------------------------------------------------"
        )
        logger.info(f"Total Amount         : ${self.total_amount:,.2f}")
        logger.info(f"\nPayment Terms        : {self.payment_terms}")
        logger.info(f"Delivery Terms       : {self.delivery_terms}")
        logger.info("\nWarranties:")
        for warranty in self.warranties:
            logger.info(f"  - {warranty}")
        logger.info(f"\nTermination Conditions: {self.termination_conditions}")

    def get_total_amount(self):
        return self._total_amount  # Return the total amount of the contract
