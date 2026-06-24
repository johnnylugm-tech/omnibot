from app.core.paladin import InputSanitizer
from app.core.pii import PIIMasking


def test_id_paladin_01_single_quote_not_deleted():
    sanitizer = InputSanitizer()
    text = "Please don't delete this quote"
    result = sanitizer.sanitize(text)
    assert "don't" in result, f"Single quote was deleted, result: {result}"

def test_id_pii_01_credit_card_dash_format_ok():
    pii = PIIMasking()
    # 16-digit valid Luhn card with dashes
    text = "My card is 4111-1111-1111-1111."
    result = pii.mask(text)
    masked = result.masked_text
    assert "[credit_card_masked]" in masked
    assert "4111-1111-1111-1111" not in masked

def test_id_pii_02_phone_number_dash_format_ok():
    pii = PIIMasking()
    text = "Call me at 0-9-1-2-3-4-5-6-7-8."
    result = pii.mask(text)
    masked = result.masked_text
    assert "[phone_masked]" in masked
    assert "0-9-1-2-3-4-5-6-7-8" not in masked
