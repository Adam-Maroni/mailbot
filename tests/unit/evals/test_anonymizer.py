"""Story 9-5 AC-6: anonymizer 7-pattern positive + negative cases.

Per AC-6: each pattern has at least one positive case and one negative
(false-positive risk) case. The negative cases document the accepted
false-positive risk: the regex passes them through unchanged, relying
on Adam's review pass to catch what regex misses.
"""

from __future__ import annotations

import pytest

from evals.anonymizer import _REGEXES, anonymize


class TestEmailPattern:
    def test_positive_email_replaced(self) -> None:
        # Walk-discovered finding 2026-06-27: anonymized email template changed
        # from `<email-NNN@example.com>` to `<email-NNN-redacted>` because the
        # old template was itself email-shaped and caused validate --strict to
        # flag the corpus as having "PII matches" on every anonymized address.
        out = anonymize("contact me at adam@example.com please")
        assert "<email-" in out
        assert "-redacted>" in out
        assert "adam@example.com" not in out

    def test_negative_at_in_handle_not_an_email(self) -> None:
        # ``@adam`` (no domain) — does NOT match the email regex
        out = anonymize("check the @adam handle on social media")
        assert "@adam" in out


class TestPhonePattern:
    def test_positive_phone_replaced(self) -> None:
        out = anonymize("call 555-123-4567 today")
        assert "<phone-" in out
        assert "555-123-4567" not in out

    def test_positive_parens_phone_replaced(self) -> None:
        out = anonymize("call (555) 123-4567 today")
        assert "<phone-" in out

    def test_positive_intl_phone_replaced(self) -> None:
        out = anonymize("call +1 555-123-4567 today")
        assert "<phone-" in out

    def test_negative_long_digit_run_not_phone(self) -> None:
        # ``we shipped 5551234567 units`` — sentence-internal digit run; the
        # regex requires separators or parens, so this passes through. AC-6
        # documents this as accepted false-positive risk.
        out = anonymize("we shipped 5551234567 units")
        assert "5551234567" in out


class TestSSNPattern:
    def test_positive_ssn_replaced(self) -> None:
        out = anonymize("SSN: 123-45-6789 for verification")
        assert "<ssn-" in out
        assert "123-45-6789" not in out

    def test_negative_short_digit_dash_pattern(self) -> None:
        # ``12-34-56`` is not SSN-shaped
        out = anonymize("date code 12-34-56 logged")
        assert "12-34-56" in out


class TestCreditCardPattern:
    def test_positive_dashed_replaced(self) -> None:
        out = anonymize("card 1234-5678-9012-3456 on file")
        assert "<cc-" in out
        assert "1234-5678-9012-3456" not in out

    def test_positive_spaced_replaced(self) -> None:
        out = anonymize("card 1234 5678 9012 3456 on file")
        assert "<cc-" in out

    def test_negative_15_digit_run_not_cc(self) -> None:
        # 15 digits with no separators — not the 4x4 shape
        out = anonymize("order 123456789012345 confirmed")
        assert "123456789012345" in out

    def test_known_false_positive_16_digit_order_id(self) -> None:
        # CR-F3 (sonnet-4-6): AC-6 accepted false-positive — 16-digit order
        # IDs are indistinguishable from unseparated CC numbers because the
        # credit-card regex's `[-\s]?` makes the separator optional. Adam's
        # review pass catches these; this test documents the behavior so a
        # future maintainer doesn't "fix" the regex without understanding
        # the tradeoff.
        out = anonymize("order 1234567890123456 shipped")
        assert "<cc-" in out


class TestAddressPattern:
    def test_positive_us_address_replaced(self) -> None:
        out = anonymize("send to 123 Main Street, Anytown")
        assert "<address-" in out

    def test_negative_short_phrase_with_number_not_address(self) -> None:
        # ``3 mice`` is not address-shaped
        out = anonymize("we have 3 mice in the office")
        assert "3 mice" in out


class TestUrlWithTokensPattern:
    def test_positive_url_with_token_replaced(self) -> None:
        out = anonymize("link: https://api.example.com/v1?api_key=secret_xyz here")
        assert "<url-with-tokens-" in out
        assert "secret_xyz" not in out

    def test_positive_url_with_signature_replaced(self) -> None:
        out = anonymize("link: https://x.com/get?sig=abcdef&id=1 here")
        assert "<url-with-tokens-" in out

    def test_negative_plain_url_not_replaced(self) -> None:
        out = anonymize("see https://example.com/page for details")
        assert "https://example.com/page" in out


class TestDeterministicSeed:
    def test_same_seed_same_output(self) -> None:
        text = "contact adam@example.com or call 555-123-4567"
        a = anonymize(text, seed="seed-1")
        b = anonymize(text, seed="seed-1")
        assert a == b

    def test_different_seed_different_counters(self) -> None:
        text = "contact adam@example.com or call 555-123-4567"
        a = anonymize(text, seed="seed-1")
        b = anonymize(text, seed="seed-2")
        # Different seeds → different counter starting numbers
        # (the counter mod 900 + 1 should diverge with overwhelming probability)
        assert a != b


class TestRegexesExported:
    def test_regexes_dict_present(self) -> None:
        # AC-6 + Subtask 2.3: tests import _REGEXES directly; the leading
        # underscore signals "internal but test-accessible" per project convention.
        assert "email" in _REGEXES
        assert "phone" in _REGEXES
        assert "ssn" in _REGEXES
        assert "credit_card" in _REGEXES
        assert "address" in _REGEXES
        assert "url_with_tokens" in _REGEXES

    @pytest.mark.parametrize("kind", list(_REGEXES.keys()))
    def test_each_regex_is_compiled_pattern(self, kind: str) -> None:
        import re

        assert isinstance(_REGEXES[kind], re.Pattern)
