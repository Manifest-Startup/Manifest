from app.services.documents.bank_account import BankAccount


def test_deposit_and_withdraw():
    acct = BankAccount(None, account_holder="Alice", balance=100.0)

    message = acct.deposit(50)
    assert acct.get_balance() == 150.0
    assert "50.00" in message

    message = acct.withdraw(30)
    assert acct.get_balance() == 120.0
    assert "30.00" in message


def test_invalid_transactions():
    acct = BankAccount(None, balance=20.0)

    assert acct.deposit(-5) == "Deposit amount must be greater than zero."
    assert acct.withdraw(-1) == "Withdrawal amount must be greater than zero."
    assert acct.withdraw(50) == "Insufficient funds."
    assert acct.get_balance() == 20.0
