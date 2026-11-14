"""Personal data never reaches the logs in full."""

import logging

from app.services.documents.bank_account import BankAccount
from app.services.documents.ein import EINService
from app.utils.redaction import mask


def test_mask_keeps_only_the_last_characters():
    assert mask("123-45-6789") == "*******6789"
    assert mask("1234") == "****"
    assert mask(None) == ""


def test_document_summaries_never_log_full_identifiers(caplog):
    caplog.set_level(logging.INFO, logger="manifest")
    EINService(None, responsible_party_ssn="123-45-6789").display_info()
    BankAccount(None, routing_number="021000021", account_number="000123456789").display_info()
    logged = caplog.text
    assert "123-45-6789" not in logged and "6789" in logged
    assert "021000021" not in logged
    assert "000123456789" not in logged
