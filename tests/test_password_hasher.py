"""Tests for PasswordHasher on its own (no LogicManager, files or network).

A low iteration count keeps these fast; the default count is checked separately.
"""

from logic_manager import PasswordHasher

FAST = 1_000  # iterations used in most tests so the suite stays quick


def make_hasher() -> PasswordHasher:
    return PasswordHasher(iterations=FAST)


# ---- Hashing -----------------------------------------------------------------


def test_default_iterations_are_200000():
    assert PasswordHasher.DEFAULT_ITERATIONS == 200_000
    assert PasswordHasher().hash_password("pw")["iterations"] == 200_000


def test_hash_contains_the_expected_fields():
    result = make_hasher().hash_password("correct horse")
    assert result["algorithm"] == "pbkdf2_sha256"
    assert result["iterations"] == FAST
    assert len(result["salt"]) == PasswordHasher.SALT_BYTES * 2  # hex
    assert len(result["password_hash"]) == 64  # SHA-256 in hex


def test_same_password_and_salt_give_the_same_hash():
    hasher = make_hasher()
    first = hasher.hash_password("correct horse")
    second = hasher.hash_password("correct horse", salt_hex=first["salt"])
    assert first["password_hash"] == second["password_hash"]


def test_same_password_gets_a_different_salt_each_time():
    hasher = make_hasher()
    first = hasher.hash_password("samepassword")
    second = hasher.hash_password("samepassword")
    assert first["salt"] != second["salt"]
    assert first["password_hash"] != second["password_hash"]


# ---- New user records ------------------------------------------------------------


def test_new_user_record_never_contains_the_plain_password():
    record = make_hasher().build_new_user_record("alice", "correct horse")
    assert record["username"] == "alice"
    assert "correct horse" not in str(record)


# ---- Verifying a login ------------------------------------------------------------


def test_correct_password_verifies():
    hasher = make_hasher()
    record = hasher.build_new_user_record("alice", "correct horse")
    assert hasher.verify_password("correct horse", record)


def test_wrong_password_case_or_spacing_fails():
    hasher = make_hasher()
    record = hasher.build_new_user_record("alice", "correct horse")
    for attempt in ("wrong horse", "Correct Horse", " correct horse", "correct horse "):
        assert not hasher.verify_password(attempt, record), attempt


def test_unicode_password_round_trips():
    hasher = make_hasher()
    record = hasher.build_new_user_record("alice", "pässwörd✓")
    assert hasher.verify_password("pässwörd✓", record)
    assert not hasher.verify_password("passwoerd", record)


def test_unknown_user_fails():
    assert not make_hasher().verify_password("whatever", None)


def test_non_string_password_fails():
    hasher = make_hasher()
    record = hasher.build_new_user_record("alice", "correct horse")
    assert not hasher.verify_password(None, record)
    assert not hasher.verify_password(12345, record)


def test_password_at_the_limit_works_and_beyond_is_refused():
    hasher = make_hasher()
    limit = PasswordHasher.MAX_PASSWORD_CHARS_CHECKED
    record = hasher.build_new_user_record("alice", "x" * limit)
    assert hasher.verify_password("x" * limit, record)
    assert not hasher.verify_password("x" * (limit + 1), record)


# ---- Damaged or hand-edited records ----------------------------------------------


def test_missing_salt_or_hash_fails_safely():
    hasher = make_hasher()
    record = hasher.build_new_user_record("alice", "correct horse")
    for field in ("salt", "password_hash"):
        damaged = dict(record)
        del damaged[field]
        assert not hasher.verify_password("correct horse", damaged), field


def test_bad_salt_or_hash_values_fail_instead_of_crashing():
    hasher = make_hasher()
    assert not hasher.verify_password(
        "x", {"salt": "zz", "password_hash": "1", "iterations": 5}
    )
    assert not hasher.verify_password("x", {"salt": 5, "password_hash": None})


def test_bad_iteration_counts_are_refused():
    hasher = make_hasher()
    record = hasher.build_new_user_record("alice", "correct horse")
    for iterations in (0, -1, True, "1000", PasswordHasher.MAX_STORED_ITERATIONS + 1):
        damaged = dict(record, iterations=iterations)
        assert not hasher.verify_password("correct horse", damaged), iterations


def test_missing_iterations_falls_back_to_the_default():
    hasher = PasswordHasher()  # default iterations
    record = hasher.build_new_user_record("alice", "correct horse")
    del record["iterations"]
    assert hasher.verify_password("correct horse", record)
