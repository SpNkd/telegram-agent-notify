import json
import ssl
import stat
import tempfile
import unittest
from argparse import Namespace
from pathlib import Path
from urllib.error import URLError

import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.telegram_notify import (  # noqa: E402
    ConfigError,
    Settings,
    TelegramClient,
    TelegramNetworkError,
    apply_project_override,
    find_targets,
    format_completion,
    load_from_args,
    load_settings,
    prepare_chunks,
    save_settings,
    validate_bot_token,
    validate_chat_id,
    validate_file_for_sending,
)


TOKEN = "1:abcdefghijklmnopqrstuvwxyz"


class FakeResponse:
    def __init__(self, payload):
        self.payload = json.dumps(payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self):
        return self.payload


class FakeOpener:
    def __init__(self, payload=None, error=None):
        self.payload = payload or {"ok": True, "result": {"message_id": 1}}
        self.error = error
        self.requests = []

    def open(self, request, timeout):
        self.requests.append((request, timeout))
        if self.error:
            raise self.error
        return FakeResponse(self.payload)


class CoreTests(unittest.TestCase):
    def test_config_loading_and_env_override(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            path.write_text(json.dumps({"bot_token": "from-file", "chat_id": "1", "sender": "file"}), encoding="utf-8")
            settings = load_settings(
                environ={"TELEGRAM_BOT_TOKEN": TOKEN, "TELEGRAM_NOTIFY_SENDER": "env"},
                path=path,
            )
            self.assertEqual(settings.bot_token, TOKEN)
            self.assertEqual(settings.sender, "env")
            self.assertEqual(settings.chat_id, "1")

    def test_insecure_tls_can_be_enabled_from_environment(self):
        settings = load_settings(environ={"TELEGRAM_NOTIFY_INSECURE_TLS": "true"}, path=Path("config.json"))
        self.assertTrue(settings.insecure_tls)

    def test_insecure_tls_context_is_explicitly_unverified(self):
        settings = Settings.from_mapping(
            {"bot_token": TOKEN, "chat_id": "1", "insecure_tls": True}, Path("config.json")
        )
        context = TelegramClient(settings)._ssl_context()
        self.assertEqual(context.verify_mode, ssl.CERT_NONE)
        self.assertFalse(context.check_hostname)

    def test_topic_target_is_discovered_without_manual_ids(self):
        targets = find_targets(
            [
                {
                    "update_id": 1,
                    "message": {
                        "message_id": 10,
                        "message_thread_id": 77,
                        "text": "ping",
                        "chat": {"id": -100123, "title": "Engineering"},
                        "forum_topic_created": {"name": "Releases"},
                    },
                }
            ]
        )
        self.assertEqual(targets, [("-100123", "77", "Engineering", "Releases")])

    def test_project_target_overrides_default_destination(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory).resolve()
            settings = Settings.from_mapping(
                {
                    "bot_token": TOKEN,
                    "chat_id": "-1001",
                    "chat_name": "Default",
                    "projects": {str(project): {"chat_id": "-1002", "chat_name": "Project"}},
                },
                Path("config.json"),
            )
            overridden = apply_project_override(settings, project)
            self.assertEqual(overridden.chat_id, "-1002")
            self.assertEqual(overridden.chat_name, "Project")
            self.assertEqual(overridden.bot_token, TOKEN)

    def test_cli_destination_override_wins_over_project_target(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory).resolve()
            config = project / "config.json"
            config.write_text(
                json.dumps(
                    {
                        "bot_token": TOKEN,
                        "chat_id": "-1001",
                        "projects": {str(project): {"chat_id": "-1002", "message_thread_id": "77"}},
                    }
                ),
                encoding="utf-8",
            )
            args = Namespace(
                config=config,
                project_dir=project,
                bot_token=None,
                chat_id="-1003",
                message_thread_id=None,
                sender=None,
                format=None,
                max_length=None,
                oversize=None,
                ca_file=None,
                timeout=None,
                proxy=None,
            )
            settings = load_from_args(args)
            self.assertEqual(settings.chat_id, "-1003")
            self.assertEqual(settings.message_thread_id, "77")

    def test_config_is_written_with_restricted_permissions(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "nested" / "config.json"
            settings = Settings.from_mapping({"bot_token": TOKEN, "chat_id": "1"}, path)
            save_settings(settings)
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
            self.assertEqual(json.loads(path.read_text(encoding="utf-8"))["bot_token"], TOKEN)

    def test_html_escaping_is_safe(self):
        chunks = prepare_chunks("<tag> & _ * [x] `code`", 100, "split", "HTML")
        rendered = chunks[0][0]
        self.assertIn("&lt;tag&gt;", rendered)
        self.assertIn("&amp;", rendered)
        self.assertNotIn("<tag>", rendered)
        self.assertEqual(chunks[0][1], "HTML")

    def test_oversized_message_is_split(self):
        chunks = prepare_chunks("line one\n" + ("word " * 40), 30, "split", "PLAIN")
        self.assertGreater(len(chunks), 1)
        self.assertTrue(all(len(text) <= 30 for text, _ in chunks))

    def test_oversized_message_can_be_truncated(self):
        chunks = prepare_chunks("x" * 100, 30, "truncate", "PLAIN")
        self.assertEqual(len(chunks), 1)
        self.assertLessEqual(len(chunks[0][0]), 30)
        self.assertTrue(chunks[0][0].endswith("…"))

    def test_completion_format_contains_only_requested_metadata(self):
        message = format_completion(
            sender="Codex",
            status="failure",
            task="Build",
            summary="Started",
            project="demo",
            error="Linker failed",
            last_step="cargo build",
            changed_files=["src/main.rs"],
        )
        self.assertIn("❌ Codex task failed", message)
        self.assertIn("Error:\nLinker failed", message)
        self.assertIn("• src/main.rs", message)
        self.assertNotIn("stdout", message)

    def test_secret_file_protection(self):
        with tempfile.TemporaryDirectory() as directory:
            secret = Path(directory) / ".env"
            secret.write_text("TOKEN=not-for-telegram", encoding="utf-8")
            with self.assertRaises(ConfigError):
                validate_file_for_sending(secret)
            self.assertEqual(validate_file_for_sending(secret, force=True), secret.resolve())

    def test_network_error_is_sanitized_and_typed(self):
        settings = Settings.from_mapping({"bot_token": TOKEN, "chat_id": "1"}, Path("config.json"))
        client = TelegramClient(settings, opener=FakeOpener(error=URLError("offline")))
        with self.assertRaises(TelegramNetworkError) as raised:
            client.send_message("hello")
        self.assertNotIn(TOKEN, str(raised.exception))

    def test_tls_error_explains_corporate_ca_configuration(self):
        settings = Settings.from_mapping({"bot_token": TOKEN, "chat_id": "1"}, Path("config.json"))
        client = TelegramClient(settings, opener=FakeOpener(error=URLError("CERTIFICATE_VERIFY_FAILED")))
        with self.assertRaises(TelegramNetworkError) as raised:
            client.send_message("hello")
        self.assertIn("TELEGRAM_NOTIFY_CA_FILE", str(raised.exception))
        self.assertIn("--insecure-tls", str(raised.exception))

    def test_invalid_token_and_missing_chat_are_rejected(self):
        self.assertFalse(validate_bot_token("not-a-token"))
        self.assertTrue(validate_bot_token(TOKEN))
        self.assertFalse(validate_chat_id(""))
        self.assertTrue(validate_chat_id("-100123456789"))
        self.assertTrue(validate_chat_id("@examplechannel"))
        settings = Settings.from_mapping({"bot_token": TOKEN, "chat_id": ""}, Path("config.json"))
        with self.assertRaises(ConfigError):
            from src.telegram_notify import require_credentials

            require_credentials(settings)

    def test_fake_api_request_makes_no_real_network_call(self):
        settings = Settings.from_mapping({"bot_token": TOKEN, "chat_id": "1"}, Path("config.json"))
        opener = FakeOpener()
        client = TelegramClient(settings, opener=opener)
        self.assertEqual(client.send_message("hello"), 1)
        self.assertEqual(len(opener.requests), 1)
        request, timeout = opener.requests[0]
        self.assertEqual(timeout, 15)
        self.assertNotIn(TOKEN.encode(), request.data)
        self.assertIn(b"chat_id=1", request.data)


if __name__ == "__main__":
    unittest.main()
