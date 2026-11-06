"""Tests for data file encryption (AES-256-GCM)."""

import base64
import json
import os

import pytest

from app import create_app
from main import Application
from managers import DataManager, IOManager, LogicManager
from managers.logic_manager import AesGcmCipher
from models import (
    EncryptionKeyError,
    FileCipher,
    FileDecryptionError,
    PlainFileCipher,
)

KEY_VAR = AesGcmCipher.KEY_ENV_VAR

RECORD = {
    "Company Name": "Secret Coy Pte Ltd",
    "Proposal Narrative": "Replace diesel vans with electric vans.",
    "Company Total Revenue": 1_000_000.0,
}


def new_cipher() -> AesGcmCipher:
    return AesGcmCipher.from_base64(AesGcmCipher.generate_key())


def raw(path) -> bytes:
    with open(path, "rb") as file:
        return file.read()


def write_raw(path, content: bytes) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as file:
        file.write(content)


def user_record(username="alice"):
    return LogicManager().build_new_user_record(username, "Password123")


# --- AesGcmCipher ---
class TestAesGcmCipher:
    def test_round_trip(self):
        cipher = new_cipher()
        assert cipher.decrypt(cipher.encrypt(b'{"a": 1}')) == b'{"a": 1}'

    def test_layout_is_marker_nonce_ciphertext_tag(self):
        stored = new_cipher().encrypt(b"hello")
        assert stored.startswith(FileCipher.MAGIC)
        expected = (
            len(FileCipher.MAGIC) + AesGcmCipher.NONCE_BYTES + len(b"hello")
            + AesGcmCipher.TAG_BYTES
        )
        assert len(stored) == expected

    def test_plaintext_is_not_visible(self):
        assert b"Secret Coy" not in new_cipher().encrypt(b'{"name": "Secret Coy"}')

    def test_fresh_nonce_every_time(self):
        cipher = new_cipher()
        first, second = cipher.encrypt(b"same"), cipher.encrypt(b"same")
        assert first != second
        start = len(FileCipher.MAGIC)
        end = start + AesGcmCipher.NONCE_BYTES
        assert first[start:end] != second[start:end]

    def test_wrong_key_is_detected(self):
        stored = new_cipher().encrypt(b"data")
        with pytest.raises(FileDecryptionError) as err:
            new_cipher().decrypt(stored)
        assert err.value.reason == "wrong_key"

    @pytest.mark.parametrize("position", ["nonce", "ciphertext", "tag"])
    def test_any_changed_byte_is_detected(self, position):
        cipher = new_cipher()
        stored = bytearray(cipher.encrypt(b"important data"))
        index = {
            "nonce": len(FileCipher.MAGIC),
            "ciphertext": len(FileCipher.MAGIC) + AesGcmCipher.NONCE_BYTES,
            "tag": len(stored) - 1,
        }[position]
        stored[index] ^= 0x01
        with pytest.raises(FileDecryptionError) as err:
            cipher.decrypt(bytes(stored))
        assert err.value.reason == "wrong_key"

    def test_truncated_file_is_detected(self):
        cipher = new_cipher()
        stored = cipher.encrypt(b"data")
        with pytest.raises(FileDecryptionError) as err:
            cipher.decrypt(stored[: len(FileCipher.MAGIC) + 5])
        assert err.value.reason == "damaged"

    def test_plain_json_is_refused(self):
        with pytest.raises(FileDecryptionError) as err:
            new_cipher().decrypt(b'{"admin": {"role": "admin"}}')
        assert err.value.reason == "not_encrypted"

    def test_generated_keys_are_32_random_bytes(self):
        first, second = AesGcmCipher.generate_key(), AesGcmCipher.generate_key()
        assert len(base64.b64decode(first)) == 32
        assert first != second

    @pytest.mark.parametrize(
        ("text", "reason"),
        [
            (None, "missing"),
            ("   ", "missing"),
            ("not base64 at all!", "not_base64"),
            (base64.b64encode(b"too short").decode(), "wrong_length"),
            (base64.b64encode(os.urandom(16)).decode(), "wrong_length"),  # AES-128
        ],
    )
    def test_bad_keys_are_rejected(self, text, reason):
        with pytest.raises(EncryptionKeyError) as err:
            AesGcmCipher.from_base64(text)
        assert err.value.reason == reason

    def test_key_comes_from_the_environment(self, monkeypatch):
        cipher = new_cipher()
        stored = cipher.encrypt(b"x")
        key = AesGcmCipher.generate_key()
        monkeypatch.setenv(KEY_VAR, key)
        from_env = AesGcmCipher.from_environment()
        assert AesGcmCipher.from_base64(key).decrypt(from_env.encrypt(b"y")) == b"y"
        with pytest.raises(FileDecryptionError):
            from_env.decrypt(stored)

    def test_the_key_is_not_a_public_attribute(self):
        key_text = AesGcmCipher.generate_key()
        cipher = AesGcmCipher.from_base64(key_text)
        public = {name: getattr(cipher, name) for name in dir(cipher)
                  if not name.startswith("_")}
        assert key_text not in map(str, public.values())
        assert base64.b64decode(key_text) not in public.values()


class TestPlainFileCipher:
    def test_passes_data_through(self):
        assert PlainFileCipher().encrypt(b"abc") == b"abc"
        assert PlainFileCipher().decrypt(b"abc") == b"abc"
        assert PlainFileCipher().encrypts is False

    def test_never_treats_an_encrypted_file_as_json(self):
        with pytest.raises(FileDecryptionError) as err:
            PlainFileCipher().decrypt(new_cipher().encrypt(b"{}"))
        assert err.value.reason == "no_key"


@pytest.mark.parametrize("cipher", [PlainFileCipher(), new_cipher()],
                         ids=["plain", "aes-gcm"])
def test_any_file_cipher_works_in_the_data_manager(tmp_path, cipher):
    # LSP: either cipher works in the DataManager
    data = DataManager(data_dir=str(tmp_path), cipher=cipher)
    assert data.save_new_user(user_record()) is True
    assert data.user_exists("alice")
    assert data.cipher is cipher


# --- Files are encrypted on disk ---
@pytest.fixture
def cipher():
    return new_cipher()


@pytest.fixture
def data(tmp_path, cipher):
    manager = DataManager(data_dir=str(tmp_path), cipher=cipher)
    return manager


class TestFilesAreEncryptedOnDisk:
    def test_users_file(self, data, tmp_path, cipher):
        assert data.save_new_user(user_record("alice"))
        stored = raw(tmp_path / "users.json")
        assert cipher.is_encrypted(stored)
        assert b"alice" not in stored and b"password_hash" not in stored
        assert data.get_user("alice")["username"] == "alice"

    def test_audit_history_file(self, data, tmp_path, cipher):
        data.save_new_user(user_record("alice"))
        assert data.append_user_audit("alice", {}, {}, {}, {}) is not None
        assert cipher.is_encrypted(raw(tmp_path / "audit_history.json"))
        assert len(data.get_user_audits("alice")) == 1

    def test_rules_config_file(self, data, tmp_path, cipher):
        values = {"fast_track_min_pct": 25.0}
        assert data.save_rule_config(values, "admin")
        assert cipher.is_encrypted(raw(tmp_path / "rules_config.json"))
        assert data.load_rule_config() == (values, "loaded")

    def test_record_files(self, data, tmp_path, cipher):
        data.active_user = "alice"
        assert data.save_data_to_json([RECORD], "mine") == ("mine.json", "saved")
        stored = raw(tmp_path / "records" / "alice" / "mine.json")
        assert cipher.is_encrypted(stored)
        assert b"Secret Coy" not in stored
        assert data.load_data_from_json("mine") == ([RECORD], "mine.json", "loaded")

    def test_archive_files(self, data, tmp_path, cipher):
        data.save_new_user(user_record("bob"))
        data.append_user_audit("bob", {}, {}, {}, {})
        folder, status = data.archive_user("bob", "admin")
        assert status == "archived"
        for name in ("account.json", "audit_history.json"):
            assert cipher.is_encrypted(raw(os.path.join(folder, name)))

    def test_no_temporary_plain_copy_is_left(self, data, tmp_path):
        data.save_new_user(user_record())
        assert sorted(os.listdir(tmp_path)) == ["users.json"]


# --- Error cases ---
class TestFailureCases:
    def save_record_file(self, tmp_path, cipher):
        writer = DataManager(data_dir=str(tmp_path), cipher=cipher)
        writer.active_user = "alice"
        writer.save_data_to_json([RECORD], "mine")
        return tmp_path / "records" / "alice" / "mine.json"

    def test_wrong_key_record_file_left_unchanged(self, tmp_path, cipher):
        path = self.save_record_file(tmp_path, cipher)
        before = raw(path)
        reader = DataManager(data_dir=str(tmp_path), cipher=new_cipher())
        reader.active_user = "alice"
        assert reader.load_data_from_json("mine") == ([], "mine.json", "decrypt_failed")
        assert raw(path) == before
        assert not os.path.exists(str(path) + ".corrupt")

    def test_tampered_record_file(self, tmp_path, cipher):
        path = self.save_record_file(tmp_path, cipher)
        tampered = bytearray(raw(path))
        tampered[-5] ^= 0xFF
        write_raw(path, bytes(tampered))
        data = DataManager(data_dir=str(tmp_path), cipher=cipher)
        data.active_user = "alice"
        assert data.load_data_from_json("mine")[2] == "decrypt_failed"
        assert raw(path) == bytes(tampered)

    def test_truncated_record_file(self, tmp_path, cipher):
        path = self.save_record_file(tmp_path, cipher)
        write_raw(path, raw(path)[:20])
        data = DataManager(data_dir=str(tmp_path), cipher=cipher)
        data.active_user = "alice"
        assert data.load_data_from_json("mine")[2] == "decrypt_failed"

    def test_plain_record_file_is_not_trusted(self, tmp_path, cipher):
        path = tmp_path / "records" / "alice" / "old.json"
        write_raw(path, json.dumps([RECORD]).encode())
        data = DataManager(data_dir=str(tmp_path), cipher=cipher)
        data.active_user = "alice"
        assert data.load_data_from_json("old")[2] == "not_encrypted"
        assert raw(path) == json.dumps([RECORD]).encode()

    def test_encrypted_file_without_a_key(self, tmp_path, cipher):
        self.save_record_file(tmp_path, cipher)
        data = DataManager(data_dir=str(tmp_path))
        data.active_user = "alice"
        assert data.load_data_from_json("mine")[2] == "encrypted_no_key"

    def test_broken_json_inside_a_valid_file_is_set_aside(self, tmp_path, cipher):
        path = tmp_path / "records" / "alice" / "bad.json"
        write_raw(path, cipher.encrypt(b"{not json"))
        data = DataManager(data_dir=str(tmp_path), cipher=cipher)
        data.active_user = "alice"
        assert data.load_data_from_json("bad")[2] == "invalid_json"
        assert os.path.exists(str(path) + ".corrupt")

    def test_wrong_key_never_wipes_the_accounts(self, tmp_path, cipher):
        # wrong key must not overwrite users.json
        DataManager(data_dir=str(tmp_path), cipher=cipher).save_new_user(user_record("alice"))
        before = raw(tmp_path / "users.json")
        wrong = DataManager(data_dir=str(tmp_path), cipher=new_cipher())
        assert wrong.load_users() is None
        assert wrong.save_new_user(user_record("mallory")) is False
        assert raw(tmp_path / "users.json") == before
        assert DataManager(data_dir=str(tmp_path), cipher=cipher).user_exists("alice")

    def test_wrong_key_never_wipes_the_history(self, tmp_path, cipher):
        right = DataManager(data_dir=str(tmp_path), cipher=cipher)
        right.save_new_user(user_record("alice"))
        right.append_user_audit("alice", {}, {}, {}, {})
        before = raw(tmp_path / "audit_history.json")
        wrong = DataManager(data_dir=str(tmp_path), cipher=new_cipher())
        assert wrong.append_user_audit("alice", {}, {}, {}, {}) is None
        assert raw(tmp_path / "audit_history.json") == before

    def test_swapped_in_plain_users_file_is_not_trusted(self, tmp_path, cipher):
        fake = {"mallory": {**user_record("mallory"), "role": "admin"}}
        write_raw(tmp_path / "users.json", json.dumps(fake).encode())
        data = DataManager(data_dir=str(tmp_path), cipher=cipher)
        assert data.get_user("mallory") is None
        assert data.check_shared_files() == [("users.json", "not_encrypted")]


# --- Start-up check ---
class TestCheckSharedFiles:
    def test_nothing_saved_yet_is_fine(self, data):
        assert data.check_shared_files() == []

    def test_readable_files_are_fine(self, data):
        data.save_new_user(user_record())
        data.save_rule_config({"fast_track_min_pct": 25.0}, "admin")
        assert data.check_shared_files() == []

    def test_wrong_key_is_reported(self, tmp_path, cipher):
        DataManager(data_dir=str(tmp_path), cipher=cipher).save_new_user(user_record())
        other = DataManager(data_dir=str(tmp_path), cipher=new_cipher())
        assert other.check_shared_files() == [("users.json", "wrong_key")]


# --- Migrating old plain files ---
class TestEncryptExistingFiles:
    def make_plain_folder(self, tmp_path):
        plain = DataManager(data_dir=str(tmp_path))
        plain.save_new_user(user_record("alice"))
        plain.append_user_audit("alice", {}, {}, {}, {})
        plain.active_user = "alice"
        plain.save_data_to_json([RECORD], "mine")
        (tmp_path / "app.log").write_text("log line", encoding="utf-8")
        (tmp_path / "records" / "alice" / "report.pdf").write_bytes(b"%PDF-1.4")

    def test_encrypts_every_plain_data_file(self, tmp_path, cipher):
        self.make_plain_folder(tmp_path)
        data = DataManager(data_dir=str(tmp_path), cipher=cipher)
        result = data.encrypt_existing_files()
        assert sorted(result["encrypted"]) == sorted([
            "users.json", "audit_history.json", os.path.join("records", "alice", "mine.json"),
        ])
        assert data.check_shared_files() == []
        assert data.user_exists("alice")
        data.active_user = "alice"
        assert data.load_data_from_json("mine")[2] == "loaded"

    def test_logs_and_pdfs_are_left_alone(self, tmp_path, cipher):
        self.make_plain_folder(tmp_path)
        DataManager(data_dir=str(tmp_path), cipher=cipher).encrypt_existing_files()
        assert (tmp_path / "app.log").read_text(encoding="utf-8") == "log line"
        assert (tmp_path / "records" / "alice" / "report.pdf").read_bytes() == b"%PDF-1.4"

    def test_running_twice_changes_nothing(self, tmp_path, cipher):
        self.make_plain_folder(tmp_path)
        data = DataManager(data_dir=str(tmp_path), cipher=cipher)
        data.encrypt_existing_files()
        before = raw(tmp_path / "users.json")
        second = data.encrypt_existing_files()
        assert second["encrypted"] == []
        assert len(second["already"]) == 3
        assert raw(tmp_path / "users.json") == before

    def test_other_key_and_invalid_files_are_left_alone(self, tmp_path, cipher):
        other_key_file = tmp_path / "records" / "alice" / "other.json"
        broken_file = tmp_path / "records" / "alice" / "broken.json"
        write_raw(other_key_file, new_cipher().encrypt(b"[]"))
        write_raw(broken_file, b"{not json")
        result = DataManager(data_dir=str(tmp_path), cipher=cipher).encrypt_existing_files()
        assert result["unreadable"] == [os.path.join("records", "alice", "other.json")]
        assert result["invalid"] == [os.path.join("records", "alice", "broken.json")]
        assert raw(broken_file) == b"{not json"

    def test_needs_a_key(self, tmp_path):
        with pytest.raises(ValueError):
            DataManager(data_dir=str(tmp_path)).encrypt_existing_files()


# --- App start-up ---
@pytest.fixture
def no_dotenv(monkeypatch):
    # don't load the real .env in tests
    monkeypatch.setattr(Application, "load_environment", staticmethod(lambda: None))


class TestLaunch:
    def test_logic_manager_builds_without_a_key(self, monkeypatch):
        monkeypatch.delenv(KEY_VAR, raising=False)
        logic = LogicManager()
        with pytest.raises(EncryptionKeyError):
            _ = logic.file_cipher

    def test_logic_manager_owns_one_cipher(self):
        logic = LogicManager()
        assert isinstance(logic.file_cipher, AesGcmCipher)
        assert logic.file_cipher is logic.file_cipher

    def test_application_without_a_key_cannot_be_built(self, monkeypatch):
        monkeypatch.delenv(KEY_VAR, raising=False)
        with pytest.raises(EncryptionKeyError):
            Application()

    @pytest.mark.parametrize("value", [None, "", "short", "!!!"])
    def test_no_or_bad_key_stops_the_app(self, monkeypatch, capsys, no_dotenv, value):
        if value is None:
            monkeypatch.delenv(KEY_VAR, raising=False)
        else:
            monkeypatch.setenv(KEY_VAR, value)
        with pytest.raises(SystemExit) as stop:
            Application.launch([])
        assert stop.value.code == 1
        out = capsys.readouterr().out
        assert "cannot start" in out
        assert "--generate-key" in out

    def test_generate_key_prints_a_usable_key(self, monkeypatch, capsys, no_dotenv):
        monkeypatch.delenv(KEY_VAR, raising=False)
        Application.launch(["--generate-key"])
        line = next(
            row.strip() for row in capsys.readouterr().out.splitlines()
            if row.strip().startswith(f"{KEY_VAR}=")
        )
        AesGcmCipher.from_base64(line.split("=", 1)[1])

    def test_encrypt_existing_data_command(self, monkeypatch, capsys, tmp_path, no_dotenv):
        DataManager(data_dir=str(tmp_path)).save_new_user(user_record())
        monkeypatch.setenv("DATA_DIR", str(tmp_path))
        Application.launch(["--encrypt-existing-data"])
        assert "Encrypted now: 1" in capsys.readouterr().out
        assert FileCipher.is_encrypted(raw(tmp_path / "users.json"))

    def test_wrong_key_stops_before_the_login_screen(self, tmp_path, cipher, capsys):
        DataManager(data_dir=str(tmp_path), cipher=cipher).save_new_user(user_record())
        io = IOManager()
        io.show_welcome_sequence = lambda: pytest.fail("must stop before the welcome")
        app = Application(
            io=io,
            logic=LogicManager(),
            data=DataManager(data_dir=str(tmp_path), cipher=new_cipher()),
        )
        with pytest.raises(SystemExit):
            app.run()
        out = capsys.readouterr().out
        assert "users.json" in out and "Nothing was changed" in out

    def test_plain_files_ask_for_the_migration(self, tmp_path, capsys):
        DataManager(data_dir=str(tmp_path)).save_new_user(user_record())
        app = Application(
            io=IOManager(),
            logic=LogicManager(),
            data=DataManager(data_dir=str(tmp_path), cipher=new_cipher()),
        )
        assert app.shared_files_are_readable() is False
        assert "--encrypt-existing-data" in capsys.readouterr().out


# --- Web app ---
class TestWeb:
    def test_server_will_not_start_without_a_key(self, monkeypatch, tmp_path):
        monkeypatch.delenv(KEY_VAR, raising=False)
        with pytest.raises(EncryptionKeyError):
            create_app({"TESTING": True, "DATA_DIR": str(tmp_path)})

    def test_server_will_not_start_with_the_wrong_key(self, tmp_path, cipher):
        DataManager(data_dir=str(tmp_path), cipher=cipher).save_new_user(user_record())
        with pytest.raises(RuntimeError, match="users.json"):
            create_app({"TESTING": True, "DATA_DIR": str(tmp_path)})

    def test_accounts_made_on_the_web_are_encrypted(self, tmp_path):
        app = create_app({"TESTING": True, "DATA_DIR": str(tmp_path)})
        client = app.test_client()
        response = client.post(
            "/api/register", json={"username": "webuser", "password": "Test1234!"}
        )
        assert response.status_code in (200, 201)
        stored = raw(tmp_path / "users.json")
        assert FileCipher.is_encrypted(stored)
        assert b"webuser" not in stored
        assert client.post(
            "/api/login", json={"username": "webuser", "password": "Test1234!"}
        ).status_code == 200
