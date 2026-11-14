from app.graphql.schema import _display_name


def test_display_name_prefers_full_name():
    assert _display_name({"first_name": "Ada", "last_name": "Lovelace", "email": "ada@example.com"}) == "Ada Lovelace"


def test_display_name_falls_back_to_email_handle():
    assert _display_name({"first_name": None, "last_name": None, "email": "hello@manifeststartup.com"}) == "hello"


def test_display_name_uses_default_when_record_is_empty():
    assert _display_name({}, default="Anonymous") == "Anonymous"
