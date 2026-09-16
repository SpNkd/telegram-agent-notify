#!/usr/bin/env python3
"""Small, dependency-free Telegram notifier for coding agents."""

from __future__ import annotations

import argparse
import getpass
import html
import json
import mimetypes
import os
import re
import socket
import ssl
import stat
import subprocess
import sys
import tempfile
import urllib.error
import urllib.parse
import urllib.request
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

VERSION = "0.1.0"
DEFAULT_MAX_LENGTH = 3900
MAX_TELEGRAM_TEXT_LENGTH = 4096
MAX_FILE_BYTES = 10 * 1024 * 1024

DEFAULT_CONFIG: Dict[str, Any] = {
    "enabled": True,
    "bot_token": "",
    "chat_id": "",
    "message_thread_id": None,
    "sender": "AI Agent",
    "format": "HTML",
    "max_length": DEFAULT_MAX_LENGTH,
    "oversize": "split",
    "send_files": True,
    "proxy": None,
    "ca_file": None,
    "timeout": 15,
    "bot_username": "",
    "chat_name": "",
    "topic_name": "",
    "projects": {},
}

ENV_FIELDS = {
    "TELEGRAM_BOT_TOKEN": "bot_token",
    "TELEGRAM_CHAT_ID": "chat_id",
    "TELEGRAM_MESSAGE_THREAD_ID": "message_thread_id",
    "TELEGRAM_NOTIFY_SENDER": "sender",
    "TELEGRAM_NOTIFY_ENABLED": "enabled",
    "TELEGRAM_NOTIFY_MAX_LENGTH": "max_length",
    "TELEGRAM_NOTIFY_FORMAT": "format",
    "TELEGRAM_NOTIFY_OVERSIZE": "oversize",
    "TELEGRAM_NOTIFY_SEND_FILES": "send_files",
    "TELEGRAM_NOTIFY_PROXY": "proxy",
    "TELEGRAM_NOTIFY_CA_FILE": "ca_file",
    "TELEGRAM_NOTIFY_TIMEOUT": "timeout",
}

SECRET_FILE_PATTERNS = (
    re.compile(r"^\.env(?:\..*)?$", re.IGNORECASE),
    re.compile(r".*\.(?:pem|key|p12|pfx|jks|kdbx)$", re.IGNORECASE),
    re.compile(r"^id_(?:rsa|dsa|ecdsa|ed25519)$", re.IGNORECASE),
    re.compile(r"^(?:credentials?|secrets?)\b.*$", re.IGNORECASE),
)


class ConfigError(Exception):
    """The local configuration is missing or invalid."""


class TelegramError(Exception):
    """Base class for sanitized Telegram errors."""


class TelegramNetworkError(TelegramError):
    """Telegram could not be reached."""


class TelegramAPIError(TelegramError):
    """Telegram returned an unsuccessful API response."""

    def __init__(self, message: str, status_code: Optional[int] = None):
        super().__init__(message)
        self.status_code = status_code


@dataclass
class Settings:
    enabled: bool
    bot_token: str
    chat_id: str
    message_thread_id: Optional[str]
    sender: str
    format: str
    max_length: int
    oversize: str
    send_files: bool
    proxy: Optional[str]
    ca_file: Optional[str]
    timeout: float
    bot_username: str
    chat_name: str
    topic_name: str
    projects: Dict[str, Dict[str, Any]]
    path: Path

    @classmethod
    def from_mapping(cls, values: Mapping[str, Any], path: Path) -> "Settings":
        fmt = str(values.get("format", "HTML") or "HTML").strip().upper()
        if fmt in {"TEXT", "PLAINTEXT"}:
            fmt = "PLAIN"
        if fmt not in {"HTML", "PLAIN"}:
            raise ConfigError("format must be HTML or plain")

        try:
            max_length = int(values.get("max_length", DEFAULT_MAX_LENGTH))
        except (TypeError, ValueError) as exc:
            raise ConfigError("max_length must be an integer") from exc
        if not 100 <= max_length <= MAX_TELEGRAM_TEXT_LENGTH:
            raise ConfigError("max_length must be between 100 and 4096")

        try:
            timeout = float(values.get("timeout", 15))
        except (TypeError, ValueError) as exc:
            raise ConfigError("timeout must be a number") from exc
        if not 1 <= timeout <= 120:
            raise ConfigError("timeout must be between 1 and 120 seconds")

        oversize = str(values.get("oversize", "split") or "split").lower()
        if oversize not in {"split", "truncate"}:
            raise ConfigError("oversize must be split or truncate")

        thread = values.get("message_thread_id")
        raw_projects = values.get("projects", {}) or {}
        if not isinstance(raw_projects, dict):
            raise ConfigError("projects must be an object")
        projects: Dict[str, Dict[str, Any]] = {}
        for project, override in raw_projects.items():
            if not isinstance(override, dict):
                raise ConfigError(f"project target for {project} must be an object")
            projects[str(project)] = dict(override)
        return cls(
            enabled=as_bool(values.get("enabled", True), "enabled"),
            bot_token=str(values.get("bot_token", "") or "").strip(),
            chat_id=str(values.get("chat_id", "") or "").strip(),
            message_thread_id=None if thread in (None, "") else str(thread).strip(),
            sender=str(values.get("sender", "AI Agent") or "AI Agent").strip() or "AI Agent",
            format=fmt,
            max_length=max_length,
            oversize=oversize,
            send_files=as_bool(values.get("send_files", True), "send_files"),
            proxy=(str(values["proxy"]).strip() if values.get("proxy") else None),
            ca_file=(str(values["ca_file"]).strip() if values.get("ca_file") else None),
            timeout=timeout,
            bot_username=str(values.get("bot_username", "") or "").strip(),
            chat_name=str(values.get("chat_name", "") or "").strip(),
            topic_name=str(values.get("topic_name", "") or "").strip(),
            projects=projects,
            path=path,
        )

    def to_mapping(self) -> Dict[str, Any]:
        return {
            "enabled": self.enabled,
            "bot_token": self.bot_token,
            "chat_id": self.chat_id,
            "message_thread_id": self.message_thread_id,
            "sender": self.sender,
            "format": self.format,
            "max_length": self.max_length,
            "oversize": self.oversize,
            "send_files": self.send_files,
            "proxy": self.proxy,
            "ca_file": self.ca_file,
            "timeout": self.timeout,
            "bot_username": self.bot_username,
            "chat_name": self.chat_name,
            "topic_name": self.topic_name,
            "projects": self.projects,
        }


def as_bool(value: Any, field: str) -> bool:
    if isinstance(value, bool):
        return value
    normalized = str(value).strip().lower()
    if normalized in {"1", "true", "yes", "on", "y"}:
        return True
    if normalized in {"0", "false", "no", "off", "n"}:
        return False
    raise ConfigError(f"{field} must be true or false")


def config_path(environ: Optional[Mapping[str, str]] = None, home: Optional[Path] = None) -> Path:
    env = dict(environ or os.environ)
    explicit = env.get("TELEGRAM_NOTIFY_CONFIG")
    if explicit:
        return Path(explicit).expanduser()

    home_path = home or Path.home()
    if os.name == "nt" or sys.platform.startswith("win"):
        base = Path(env.get("APPDATA") or home_path / "AppData" / "Roaming")
    else:
        base = Path(env.get("XDG_CONFIG_HOME") or home_path / ".config")
    return base / "telegram-notify" / "config.json"


def read_config_file(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ConfigError(f"cannot read config file: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise ConfigError(f"invalid JSON in config file at line {exc.lineno}") from exc
    if not isinstance(value, dict):
        raise ConfigError("config file must contain a JSON object")
    return value


def _env_value(name: str, value: str) -> Any:
    if name in {"TELEGRAM_NOTIFY_ENABLED", "TELEGRAM_NOTIFY_SEND_FILES"}:
        return as_bool(value, name)
    if name in {"TELEGRAM_NOTIFY_MAX_LENGTH"}:
        try:
            return int(value)
        except ValueError as exc:
            raise ConfigError(f"{name} must be an integer") from exc
    if name == "TELEGRAM_NOTIFY_TIMEOUT":
        try:
            return float(value)
        except ValueError as exc:
            raise ConfigError(f"{name} must be a number") from exc
    return value


def load_settings(
    cli_overrides: Optional[Mapping[str, Any]] = None,
    environ: Optional[Mapping[str, str]] = None,
    path: Optional[Path] = None,
) -> Settings:
    env = dict(environ or os.environ)
    resolved_path = Path(path or config_path(env)).expanduser()
    values: Dict[str, Any] = dict(DEFAULT_CONFIG)
    values.update(read_config_file(resolved_path))

    for env_name, field in ENV_FIELDS.items():
        if env_name in env and env[env_name] != "":
            values[field] = _env_value(env_name, env[env_name])
    for key, value in (cli_overrides or {}).items():
        if value is not None:
            values[key] = value
    return Settings.from_mapping(values, resolved_path)


PROJECT_OVERRIDE_FIELDS = {"chat_id", "message_thread_id", "chat_name", "topic_name"}


def detect_project_root(start: Optional[Path] = None) -> Path:
    candidate = Path(start or Path.cwd()).expanduser()
    if candidate.exists() and candidate.is_file():
        candidate = candidate.parent
    try:
        candidate = candidate.resolve()
    except OSError:
        candidate = Path.cwd().resolve()
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=str(candidate),
            check=True,
            capture_output=True,
            text=True,
            timeout=2,
        )
    except (OSError, subprocess.SubprocessError):
        return candidate
    root = result.stdout.strip()
    return Path(root).expanduser().resolve() if root else candidate


def project_key(path: Optional[Path] = None) -> str:
    return str(detect_project_root(path))


def apply_project_override(settings: Settings, project_dir: Path) -> Settings:
    override = settings.projects.get(project_key(project_dir))
    if not override:
        return settings
    values = settings.to_mapping()
    values.update({key: value for key, value in override.items() if key in PROJECT_OVERRIDE_FIELDS})
    return Settings.from_mapping(values, settings.path)


def save_settings(settings: Settings, path: Optional[Path] = None) -> Path:
    destination = Path(path or settings.path).expanduser()
    destination.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(settings.to_mapping(), ensure_ascii=False, indent=2) + "\n"
    fd, temporary_name = tempfile.mkstemp(prefix=".config.", suffix=".tmp", dir=str(destination.parent))
    temporary = Path(temporary_name)
    try:
        os.fchmod(fd, stat.S_IRUSR | stat.S_IWUSR) if hasattr(os, "fchmod") else None
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, destination)
        if os.name != "nt":
            destination.chmod(stat.S_IRUSR | stat.S_IWUSR)
    finally:
        if temporary.exists():
            temporary.unlink()
    return destination


def validate_bot_token(token: str) -> bool:
    return bool(re.fullmatch(r"[0-9]+:[A-Za-z0-9_-]{20,}", token or ""))


def validate_chat_id(chat_id: str) -> bool:
    value = str(chat_id or "").strip()
    return bool(value and (re.fullmatch(r"-?[0-9]+", value) or re.fullmatch(r"@[A-Za-z0-9_]{5,}", value)))


def redact(value: Any, token: str = "") -> str:
    text = str(value)
    if token:
        text = text.replace(token, "***")
    return text.replace("bot" + token, "bot***") if token else text


def require_credentials(settings: Settings, require_chat: bool = True) -> None:
    if not settings.bot_token:
        raise ConfigError(f"Telegram bot token is not configured. Run: {program_name()} configure")
    if not validate_bot_token(settings.bot_token):
        raise ConfigError("Telegram bot token has an invalid shape")
    if require_chat and not validate_chat_id(settings.chat_id):
        raise ConfigError(f"Telegram chat_id is not configured. Run: {program_name()} configure")


class TelegramClient:
    def __init__(self, settings: Settings, opener: Optional[Any] = None):
        self.settings = settings
        if opener is not None:
            self.opener = opener
        else:
            handlers: List[Any] = []
            if settings.proxy:
                handlers.append(urllib.request.ProxyHandler({"http": settings.proxy, "https": settings.proxy}))
            handlers.append(urllib.request.HTTPSHandler(context=self._ssl_context()))
            self.opener = urllib.request.build_opener(*handlers)

    def _ssl_context(self) -> ssl.SSLContext:
        if not self.settings.ca_file:
            return ssl.create_default_context()
        ca_path = Path(self.settings.ca_file).expanduser()
        if not ca_path.is_file():
            raise ConfigError(f"CA file does not exist: {ca_path}")
        try:
            return ssl.create_default_context(cafile=str(ca_path))
        except (OSError, ssl.SSLError):
            raise ConfigError(f"cannot load CA file as PEM certificate bundle: {ca_path}") from None

    def _call(self, method: str, params: Optional[Mapping[str, Any]] = None) -> Any:
        require_credentials(self.settings, require_chat=False)
        query = urllib.parse.urlencode({k: v for k, v in (params or {}).items() if v is not None})
        url = f"https://api.telegram.org/bot{self.settings.bot_token}/{method}"
        if query:
            url += "?" + query
        request = urllib.request.Request(url, headers={"User-Agent": "telegram-agent-notify/" + VERSION})
        try:
            with self.opener.open(request, timeout=self.settings.timeout) as response:
                raw = response.read()
        except urllib.error.HTTPError as exc:
            body = b""
            try:
                body = exc.read()
            except OSError:
                pass
            raise self._api_error(body, exc.code, self.settings.bot_token) from None
        except (urllib.error.URLError, TimeoutError, socket.timeout, OSError) as exc:
            raise self._network_error(exc) from None
        return self._decode(raw, None)

    def _post_multipart(self, method: str, fields: Mapping[str, Any], file_path: Path) -> Any:
        require_credentials(self.settings)
        boundary = "----telegram-agent-notify-" + uuid.uuid4().hex
        chunks: List[bytes] = []
        for name, value in fields.items():
            if value is None:
                continue
            chunks.extend(
                [
                    f"--{boundary}\r\n".encode(),
                    f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode(),
                    str(value).encode("utf-8"),
                    b"\r\n",
                ]
            )
        mime = mimetypes.guess_type(file_path.name)[0] or "application/octet-stream"
        try:
            file_bytes = file_path.read_bytes()
        except OSError as exc:
            raise ConfigError(f"cannot read file for sending: {exc}") from None
        chunks.extend(
            [
                f"--{boundary}\r\n".encode(),
                f'Content-Disposition: form-data; name="document"; filename="{file_path.name}"\r\n'.encode(),
                f"Content-Type: {mime}\r\n\r\n".encode(),
                file_bytes,
                b"\r\n",
                f"--{boundary}--\r\n".encode(),
            ]
        )
        body = b"".join(chunks)
        url = f"https://api.telegram.org/bot{self.settings.bot_token}/{method}"
        request = urllib.request.Request(
            url,
            data=body,
            headers={
                "Content-Type": f"multipart/form-data; boundary={boundary}",
                "User-Agent": "telegram-agent-notify/" + VERSION,
            },
            method="POST",
        )
        try:
            with self.opener.open(request, timeout=self.settings.timeout) as response:
                raw = response.read()
        except urllib.error.HTTPError as exc:
            body = b""
            try:
                body = exc.read()
            except OSError:
                pass
            raise self._api_error(body, exc.code, self.settings.bot_token) from None
        except (urllib.error.URLError, TimeoutError, socket.timeout, OSError) as exc:
            raise self._network_error(exc) from None
        return self._decode(raw, None)

    @staticmethod
    def _decode(raw: bytes, status_code: Optional[int]) -> Any:
        try:
            payload = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            raise TelegramAPIError("Telegram returned an invalid response", status_code) from None
        if not isinstance(payload, dict) or not payload.get("ok"):
            description = payload.get("description", "unknown Telegram API error") if isinstance(payload, dict) else "invalid Telegram response"
            raise TelegramAPIError(str(description), status_code)
        return payload.get("result")

    @classmethod
    def _api_error(cls, raw: bytes, status_code: Optional[int], token: str) -> TelegramAPIError:
        try:
            payload = json.loads(raw.decode("utf-8"))
            description = payload.get("description", "Telegram API request failed")
            parameters = payload.get("parameters") or {}
            retry_after = parameters.get("retry_after")
            if retry_after:
                description = f"{description} (retry after {retry_after}s)"
        except (UnicodeDecodeError, json.JSONDecodeError):
            description = f"Telegram API request failed with HTTP {status_code}"
        return TelegramAPIError(redact(description, token), status_code)

    def get_me(self) -> Mapping[str, Any]:
        result = self._call("getMe")
        return result if isinstance(result, dict) else {}

    def get_updates(self) -> List[Mapping[str, Any]]:
        result = self._call("getUpdates", {"limit": 100, "timeout": 0})
        return [item for item in result if isinstance(item, dict)] if isinstance(result, list) else []

    def send_message(self, raw_text: str) -> int:
        require_credentials(self.settings)
        chunks = prepare_chunks(raw_text, self.settings.max_length, self.settings.oversize, self.settings.format)
        last_id = 0
        for text, parse_mode in chunks:
            params: Dict[str, Any] = {
                "chat_id": self.settings.chat_id,
                "text": text,
                "parse_mode": parse_mode,
                "disable_web_page_preview": "true",
            }
            if self.settings.message_thread_id:
                params["message_thread_id"] = self.settings.message_thread_id
            result = self._call_post_form("sendMessage", params)
            if isinstance(result, dict):
                last_id = int(result.get("message_id", 0) or 0)
        return last_id

    def _call_post_form(self, method: str, params: Mapping[str, Any]) -> Any:
        require_credentials(self.settings, require_chat=False)
        body = urllib.parse.urlencode({k: v for k, v in params.items() if v is not None}).encode("utf-8")
        url = f"https://api.telegram.org/bot{self.settings.bot_token}/{method}"
        request = urllib.request.Request(
            url,
            data=body,
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "User-Agent": "telegram-agent-notify/" + VERSION,
            },
            method="POST",
        )
        try:
            with self.opener.open(request, timeout=self.settings.timeout) as response:
                raw = response.read()
        except urllib.error.HTTPError as exc:
            body = b""
            try:
                body = exc.read()
            except OSError:
                pass
            raise self._api_error(body, exc.code, self.settings.bot_token) from None
        except (urllib.error.URLError, TimeoutError, socket.timeout, OSError) as exc:
            raise self._network_error(exc) from None
        return self._decode(raw, None)

    def _network_error(self, exc: BaseException) -> TelegramNetworkError:
        reason = getattr(exc, "reason", exc)
        if isinstance(reason, ssl.SSLCertVerificationError) or "CERTIFICATE_VERIFY_FAILED" in str(reason):
            hint = (
                "TLS certificate verification failed. If a corporate proxy is in use, export its root CA "
                "as PEM and set TELEGRAM_NOTIFY_CA_FILE or rerun configure with --ca-file. "
                "TLS verification was not disabled."
            )
            return TelegramNetworkError(hint)
        return TelegramNetworkError(redact(f"network request failed: {reason}", self.settings.bot_token))

    def send_document(self, file_path: Path, caption: Optional[str] = None) -> Any:
        fields: Dict[str, Any] = {"chat_id": self.settings.chat_id}
        if self.settings.message_thread_id:
            fields["message_thread_id"] = self.settings.message_thread_id
        if caption:
            fields["caption"] = prepare_chunks(caption, 1024, "truncate", self.settings.format)[0][0]
            if self.settings.format == "HTML":
                fields["parse_mode"] = "HTML"
        return self._post_multipart("sendDocument", fields, file_path)


def prepare_chunks(text: str, max_length: int, oversize: str, fmt: str) -> List[Tuple[str, Optional[str]]]:
    safe_text = str(text or "")
    if oversize == "truncate" and len(safe_text) > max_length:
        safe_text = safe_text[: max_length - 1].rstrip() + "…"
    raw_chunks = split_text(safe_text, max_length)
    output: List[Tuple[str, Optional[str]]] = []
    for index, chunk in enumerate(raw_chunks):
        if fmt == "HTML":
            escaped = html.escape(chunk, quote=False)
            if index == 0 and "\n" not in chunk:
                escaped = "<b>" + escaped + "</b>"
            elif index == 0:
                first, rest = escaped.split("\n", 1)
                escaped = "<b>" + first + "</b>\n" + rest
            output.append((escaped, "HTML"))
        else:
            output.append((chunk, None))
    return output


def split_text(text: str, max_length: int) -> List[str]:
    if len(text) <= max_length:
        return [text]
    chunks: List[str] = []
    current = ""
    for line in text.splitlines(keepends=True):
        if len(current) + len(line) <= max_length:
            current += line
            continue
        if current:
            chunks.append(current.rstrip("\n"))
            current = ""
        while len(line) > max_length:
            cut = line.rfind(" ", 0, max_length + 1)
            if cut < max_length // 2:
                cut = max_length
            chunks.append(line[:cut].rstrip())
            line = line[cut:].lstrip()
        current = line
    if current:
        chunks.append(current.rstrip("\n"))
    return chunks or [""]


def format_completion(
    *,
    sender: str,
    status: str,
    task: str,
    summary: str,
    project: str = "",
    branch: str = "",
    commit: str = "",
    changed_files: Optional[Iterable[str]] = None,
    tests: str = "",
    error: str = "",
    last_step: str = "",
    duration: str = "",
) -> str:
    normalized = status.lower().strip()
    failed = normalized in {"failure", "failed", "error", "cancelled", "canceled"}
    icon = "❌" if failed else "✅"
    verb = "task failed" if failed else "finished"
    lines = [f"{icon} {sender} {verb}"]
    if project:
        lines += ["", f"Project: {project}"]
    if task:
        lines.append(f"Task: {task}")
    if summary:
        lines += ["", "Result:", summary]
    if error:
        lines += ["", "Error:", error]
    if last_step:
        lines += ["", "Last step:", last_step]
    if tests:
        lines += ["", "Tests:", tests]
    files = [str(item) for item in (changed_files or []) if str(item).strip()]
    if files:
        lines += ["", "Changed files:"]
        lines.extend(f"• {item}" for item in files)
    if branch:
        lines += ["", f"Branch: {branch}"]
    if commit:
        lines.append(f"Commit: {commit}")
    if duration:
        lines += ["", f"Duration: {duration}"]
    return "\n".join(lines)


def is_secret_file(path: Path) -> bool:
    name = path.name
    return any(pattern.fullmatch(name) for pattern in SECRET_FILE_PATTERNS)


def validate_file_for_sending(path: Path, force: bool = False) -> Path:
    resolved = path.expanduser().resolve()
    if not resolved.exists() or not resolved.is_file():
        raise ConfigError(f"file does not exist or is not a regular file: {path}")
    if is_secret_file(resolved) and not force:
        raise ConfigError(f"refusing to send a potentially secret file: {resolved.name}; use --force only if intentional")
    try:
        size = resolved.stat().st_size
    except OSError as exc:
        raise ConfigError(f"cannot inspect file: {exc}") from exc
    if size > MAX_FILE_BYTES:
        raise ConfigError("file is larger than the 10 MiB safety limit")
    return resolved


def program_name() -> str:
    return "telegram-notify"


def cli_overrides(args: argparse.Namespace) -> Dict[str, Any]:
    return {
        "bot_token": getattr(args, "bot_token", None),
        "chat_id": getattr(args, "chat_id", None),
        "message_thread_id": getattr(args, "message_thread_id", None),
        "sender": getattr(args, "sender", None),
        "format": getattr(args, "format", None),
        "max_length": getattr(args, "max_length", None),
        "oversize": getattr(args, "oversize", None),
        "ca_file": getattr(args, "ca_file", None),
        "timeout": getattr(args, "timeout", None),
        "proxy": getattr(args, "proxy", None),
    }


def add_transport_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--config", type=Path, help="override the config file path")
    parser.add_argument("--bot-token", help=argparse.SUPPRESS)
    parser.add_argument("--chat-id", help="override the destination chat id")
    parser.add_argument("--message-thread-id", help="override the Telegram topic thread id")
    parser.add_argument("--project-dir", type=Path, help="use the destination configured for this project")
    parser.add_argument("--sender", help="sender/agent name")
    parser.add_argument("--format", choices=["HTML", "plain", "PLAIN"], help="message format (default: HTML)")
    parser.add_argument("--max-length", type=int, help="visible message length before splitting")
    parser.add_argument("--oversize", choices=["split", "truncate"], help="oversize behavior")
    parser.add_argument("--ca-file", type=Path, help="PEM CA bundle for a corporate HTTPS proxy")
    parser.add_argument("--timeout", type=float, help="network timeout in seconds")
    parser.add_argument("--proxy", help=argparse.SUPPRESS)


def send_parser(prog: str, completion: bool = False) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog=prog, description="Send a concise Telegram notification.")
    if completion:
        parser.add_argument("--status", choices=["success", "failure"], default="success")
        parser.add_argument("--task", default="")
        parser.add_argument("--summary", default="")
        parser.add_argument("--project", default="")
        parser.add_argument("--branch", default="")
        parser.add_argument("--commit", default="")
        parser.add_argument("--changed-file", action="append", default=[])
        parser.add_argument("--tests", default="")
        parser.add_argument("--error", default="")
        parser.add_argument("--last-step", default="")
        parser.add_argument("--duration", default="")
    else:
        parser.add_argument("title_pos", nargs="?")
        parser.add_argument("message_pos", nargs="?")
        parser.add_argument("--title")
        parser.add_argument("--message")
        parser.add_argument("--strict", action="store_true", help="return non-zero when delivery fails")
    add_transport_options(parser)
    return parser


def load_from_args(args: argparse.Namespace) -> Settings:
    settings = load_settings(path=getattr(args, "config", None))
    if settings.projects:
        project_dir = getattr(args, "project_dir", None) or detect_project_root()
        settings = apply_project_override(settings, project_dir)
    values = settings.to_mapping()
    env = os.environ
    for env_name, field in ENV_FIELDS.items():
        if env_name in env and env[env_name] != "":
            values[field] = _env_value(env_name, env[env_name])
    for key, value in cli_overrides(args).items():
        if value is not None:
            values[key] = value
    return Settings.from_mapping(values, settings.path)


def notify(settings: Settings, raw_text: str, strict: bool = False) -> bool:
    if not settings.enabled:
        print("Telegram notifications are disabled.")
        return True
    try:
        require_credentials(settings)
        text = redact(raw_text, settings.bot_token)
        TelegramClient(settings).send_message(text)
    except (ConfigError, TelegramError) as exc:
        print(f"WARNING: Telegram notification failed: {redact(exc, settings.bot_token)}", file=sys.stderr)
        if strict:
            return False
        return True
    print("✓ Telegram message delivered.")
    return True


def handle_simple_send(argv: Sequence[str], prog: str) -> int:
    args = send_parser(prog).parse_args(list(argv))
    title = args.title if args.title is not None else args.title_pos
    message = args.message if args.message is not None else args.message_pos
    if title is None:
        send_parser(prog).error("provide a title and message")
    if message is None:
        if not sys.stdin.isatty():
            message = sys.stdin.read().strip()
        else:
            send_parser(prog).error("provide a message")
    settings = load_from_args(args)
    return 0 if notify(settings, f"{title}\n\n{message}", args.strict) else 1


def handle_completion(argv: Sequence[str], prog: str) -> int:
    args = send_parser(prog, completion=True).parse_args(list(argv))
    settings = load_from_args(args)
    raw = format_completion(
        sender=settings.sender,
        status=args.status,
        task=args.task,
        summary=args.summary,
        project=args.project,
        branch=args.branch,
        commit=args.commit,
        changed_files=args.changed_file,
        tests=args.tests,
        error=args.error,
        last_step=args.last_step,
        duration=args.duration,
    )
    return 0 if notify(settings, raw, strict=False) else 1


def prompt(label: str, default: str = "") -> str:
    suffix = f" [{default}]" if default else ""
    value = input(f"{label}{suffix}: ").strip()
    return value or default


Target = Tuple[str, Optional[str], str, str]


def _chat_name(chat: Mapping[str, Any]) -> str:
    name = chat.get("title") or " ".join(str(chat.get(key, "")) for key in ("first_name", "last_name")).strip()
    username = chat.get("username")
    if username:
        name += f" (@{username})"
    return name or "Telegram chat"


def _topic_name(message: Mapping[str, Any], thread_id: Optional[str]) -> str:
    if not thread_id:
        return ""
    created = message.get("forum_topic_created")
    if isinstance(created, dict) and created.get("name"):
        return str(created["name"])
    reply = message.get("reply_to_message")
    if isinstance(reply, dict):
        reply_created = reply.get("forum_topic_created")
        if isinstance(reply_created, dict) and reply_created.get("name"):
            return str(reply_created["name"])
    return f"thread {thread_id}"


def find_targets(updates: Iterable[Mapping[str, Any]]) -> List[Target]:
    found: Dict[Tuple[str, str], Target] = {}
    for update in updates:
        message = update.get("message") or update.get("channel_post") or update.get("edited_message")
        if not isinstance(message, dict):
            continue
        chat = message.get("chat")
        if not isinstance(chat, dict) or "id" not in chat:
            continue
        chat_id = str(chat["id"])
        thread = message.get("message_thread_id")
        thread_id = None if thread in (None, "") else str(thread)
        target = (chat_id, thread_id, _chat_name(chat), _topic_name(message, thread_id))
        found[(chat_id, thread_id or "")] = target
    return list(found.values())


def find_chats(updates: Iterable[Mapping[str, Any]]) -> List[Tuple[str, str]]:
    """Backward-compatible chat-only view of discovered updates."""
    found: Dict[str, str] = {}
    for chat_id, _thread_id, name, _topic in find_targets(updates):
        found.setdefault(chat_id, name)
    return list(found.items())


def format_target(target: Target) -> str:
    chat_id, thread_id, chat_name, topic_name = target
    label = chat_name
    if thread_id:
        label += f" — topic: {topic_name or 'thread ' + thread_id}"
    return f"{label} (chat_id {chat_id})"


def choose_chat(client: TelegramClient) -> Target:
    print("Send a message in the target group or topic and press Enter.")
    input()
    targets = find_targets(client.get_updates())
    if not targets:
        manual = prompt("No chat found. Enter chat_id manually")
        if not validate_chat_id(manual):
            raise ConfigError("chat_id must be a numeric id or @channelusername")
        thread = prompt("Topic thread id (optional; leave empty for General)")
        return manual, thread or None, "Configured chat", f"thread {thread}" if thread else ""
    if len(targets) == 1:
        target = targets[0]
        answer = prompt(f"Use {format_target(target)}? Y/n", "Y").lower()
        if answer not in {"", "y", "yes"}:
            manual = prompt("Enter chat_id manually")
            if not validate_chat_id(manual):
                raise ConfigError("chat_id must be a numeric id or @channelusername")
            thread = prompt("Topic thread id (optional; leave empty for General)")
            return manual, thread or None, "Configured chat", f"thread {thread}" if thread else ""
        return target
    print("Found destinations:")
    for index, target in enumerate(targets, 1):
        print(f"  {index}. {format_target(target)}")
    selected = prompt("Choose a destination", "1")
    try:
        return targets[int(selected) - 1]
    except (ValueError, IndexError) as exc:
        raise ConfigError("invalid destination selection") from exc


def handle_configure(argv: Sequence[str], prog: str) -> int:
    parser = argparse.ArgumentParser(prog=prog, description="Configure and test a Telegram bot.")
    parser.add_argument("--config", type=Path)
    parser.add_argument("--bot-token", help=argparse.SUPPRESS)
    parser.add_argument("--chat-id", help="use a known destination chat id")
    parser.add_argument("--message-thread-id", help="use a Telegram topic thread id")
    scope = parser.add_mutually_exclusive_group()
    scope.add_argument("--project-dir", type=Path, help="save this destination for one project")
    scope.add_argument("--default", action="store_true", help="save this destination as the default")
    parser.add_argument("--sender")
    parser.add_argument("--format", choices=["HTML", "plain", "PLAIN"])
    parser.add_argument("--max-length", type=int)
    parser.add_argument("--oversize", choices=["split", "truncate"])
    parser.add_argument("--ca-file", type=Path, help="PEM CA bundle for a corporate HTTPS proxy")
    parser.add_argument("--timeout", type=float)
    parser.add_argument("--proxy", help=argparse.SUPPRESS)
    files = parser.add_mutually_exclusive_group()
    files.add_argument("--send-files", dest="send_files", action="store_true", help="allow explicit send-file uploads")
    files.add_argument("--no-send-files", dest="send_files", action="store_false", help="disable send-file uploads")
    parser.add_argument("--yes", action="store_true", help="accept supplied values without optional prompts")
    parser.add_argument("--no-test", action="store_true", help="save without sending a test message")
    args = parser.parse_args(list(argv))
    path = Path(args.config or config_path()).expanduser()
    existing = dict(DEFAULT_CONFIG)
    existing.update(read_config_file(path))

    token = args.bot_token or getpass.getpass("Paste Telegram bot token: ").strip()
    if not validate_bot_token(token):
        raise ConfigError("bot token has an invalid shape")
    ca_default = os.environ.get("TELEGRAM_NOTIFY_CA_FILE") or existing.get("ca_file")
    proxy_default = os.environ.get("TELEGRAM_NOTIFY_PROXY") or existing.get("proxy")
    timeout_default = os.environ.get("TELEGRAM_NOTIFY_TIMEOUT") or existing.get("timeout", 15)
    probe_values = dict(
        existing,
        bot_token=token,
        chat_id=args.chat_id or existing.get("chat_id", ""),
        ca_file=args.ca_file or ca_default,
        proxy=args.proxy or proxy_default,
        timeout=args.timeout if args.timeout is not None else timeout_default,
    )
    probe = Settings.from_mapping(probe_values, path)
    me = TelegramClient(probe).get_me()
    username = str(me.get("username", "") or "")
    display_bot = "@" + username if username else str(me.get("first_name", "Telegram bot"))
    print(f"✓ Bot: {display_bot}")

    scope_project: Optional[Path] = None
    if args.project_dir:
        scope_project = detect_project_root(args.project_dir)
    elif not args.default and not args.yes:
        current_project = detect_project_root()
        choice = prompt(
            f"Save destination for [1] all projects or [2] current project ({current_project})",
            "1",
        )
        if choice == "2":
            scope_project = current_project
        elif choice != "1":
            raise ConfigError("choose 1 for the default or 2 for the current project")

    existing_projects = existing.get("projects", {}) or {}
    if not isinstance(existing_projects, dict):
        raise ConfigError("projects must be an object")
    destination_defaults = dict(existing)
    if scope_project:
        project_target = existing_projects.get(project_key(scope_project), {})
        if project_target and not isinstance(project_target, dict):
            raise ConfigError("project target must be an object")
        destination_defaults.update(project_target)

    if args.chat_id:
        target = (
            str(args.chat_id),
            str(args.message_thread_id or destination_defaults.get("message_thread_id") or "") or None,
            str(destination_defaults.get("chat_name", "Configured chat")),
            str(destination_defaults.get("topic_name", "") or ""),
        )
    elif destination_defaults.get("chat_id") and args.yes:
        target = (
            str(destination_defaults["chat_id"]),
            str(destination_defaults.get("message_thread_id") or "") or None,
            str(destination_defaults.get("chat_name", "Configured chat")),
            str(destination_defaults.get("topic_name", "") or ""),
        )
    else:
        target = choose_chat(probe)
    chat_id, thread, chat_name, topic_name = target

    def optional(name: str, flag_value: Any, old_key: str, default: str, source: Mapping[str, Any] = existing) -> str:
        if flag_value is not None:
            return str(flag_value)
        if args.yes:
            return str(source.get(old_key, default) or default)
        return prompt(name, str(source.get(old_key, default) or default))

    sender = optional("Sender/agent name", args.sender, "sender", "Codex")
    thread = str(args.message_thread_id or thread or "")
    fmt = optional("Format (HTML/plain)", args.format, "format", "HTML").upper()
    max_len = int(args.max_length if args.max_length is not None else existing.get("max_length", DEFAULT_MAX_LENGTH))
    oversize = optional("Oversize behavior (split/truncate)", args.oversize, "oversize", "split").lower()
    timeout = float(args.timeout if args.timeout is not None else existing.get("timeout", 15))
    proxy = optional("Proxy URL (optional)", args.proxy, "proxy", "", {**existing, "proxy": proxy_default})
    ca_file = optional("CA PEM file (optional)", args.ca_file, "ca_file", "", {**existing, "ca_file": ca_default})
    if args.send_files is not None:
        send_files = args.send_files
    elif args.yes:
        send_files = bool(existing.get("send_files", True))
    else:
        send_files = prompt("Allow explicit file sending? Y/n", "Y").lower() in {"", "y", "yes"}

    saved_values = dict(existing, enabled=True, bot_token=token, sender=sender, format=fmt, max_length=max_len,
                        oversize=oversize, timeout=timeout, proxy=proxy or None, ca_file=ca_file or None,
                        send_files=send_files, bot_username=username)
    if scope_project:
        projects = dict(existing_projects)
        projects[project_key(scope_project)] = {
            "chat_id": chat_id,
            "message_thread_id": thread or None,
            "chat_name": chat_name,
            "topic_name": topic_name,
        }
        saved_values["projects"] = projects
    else:
        saved_values.update(
            chat_id=chat_id,
            message_thread_id=thread or None,
            chat_name=chat_name,
            topic_name=topic_name,
        )
    settings = Settings.from_mapping(saved_values, path)
    save_settings(settings)
    print(f"✓ Configuration saved: {settings.path}")
    if not args.no_test:
        print("Testing notification...")
        test_settings = apply_project_override(settings, scope_project) if scope_project else settings
        if not notify(test_settings, f"✅ {settings.sender} notifications configured successfully.", strict=True):
            return 1
    return 0


def handle_test(argv: Sequence[str], prog: str) -> int:
    parser = argparse.ArgumentParser(prog=prog, description="Send a test notification.")
    add_transport_options(parser)
    args = parser.parse_args(list(argv))
    settings = load_from_args(args)
    if not settings.enabled:
        print("Telegram notifications are disabled.")
        return 0
    return 0 if notify(settings, f"✅ {settings.sender} test notification.", strict=True) else 1


def handle_status(argv: Sequence[str], prog: str) -> int:
    parser = argparse.ArgumentParser(prog=prog, description="Show redacted configuration status.")
    parser.add_argument("--config", type=Path)
    parser.add_argument("--project-dir", type=Path, help="show the destination for this project")
    parser.add_argument("--no-check", action="store_true", help="do not contact Telegram")
    args = parser.parse_args(list(argv))
    settings = load_settings(path=args.config)
    if settings.projects:
        settings = apply_project_override(settings, args.project_dir or detect_project_root())
    print("Telegram Agent Notifications")
    print(f"Enabled: {'yes' if settings.enabled else 'no'}")
    print(f"Bot: @{settings.bot_username}" if settings.bot_username else f"Bot: {'configured' if settings.bot_token else 'not configured'}")
    print(f"Chat: {settings.chat_name or ('configured' if settings.chat_id else 'not configured')}")
    if settings.message_thread_id:
        print(f"Topic: {settings.topic_name or ('thread ' + settings.message_thread_id)}")
    print("Token: configured (hidden)" if settings.bot_token else "Token: not configured")
    print(f"Config: {settings.path}")
    if args.no_check or not settings.bot_token:
        print("Connection: not checked")
    else:
        try:
            TelegramClient(settings).get_me()
            print("Connection: OK")
        except TelegramError as exc:
            print(f"Connection: failed ({redact(exc, settings.bot_token)})")
    return 0


def handle_doctor(argv: Sequence[str], prog: str) -> int:
    parser = argparse.ArgumentParser(prog=prog, description="Check local configuration and Telegram connectivity.")
    parser.add_argument("--config", type=Path)
    parser.add_argument("--project-dir", type=Path, help="check the destination for this project")
    args = parser.parse_args(list(argv))
    path = Path(args.config or config_path()).expanduser()
    checks: List[Tuple[str, bool, str]] = []
    checks.append(("config file", path.exists(), str(path)))
    try:
        settings = load_settings(path=path)
        if settings.projects:
            settings = apply_project_override(settings, args.project_dir or detect_project_root())
        checks.append(("bot token", validate_bot_token(settings.bot_token), "shape valid" if settings.bot_token else "missing"))
        checks.append(("chat_id", validate_chat_id(settings.chat_id), "valid" if settings.chat_id else "missing"))
        if path.exists() and os.name != "nt":
            mode = stat.S_IMODE(path.stat().st_mode)
            checks.append(("config permissions", (mode & 0o077) == 0, oct(mode)))
        if settings.ca_file:
            ca_path = Path(settings.ca_file).expanduser()
            checks.append(("CA file", ca_path.is_file(), str(ca_path)))
        if settings.bot_token and validate_bot_token(settings.bot_token):
            try:
                TelegramClient(settings).get_me()
                checks.append(("Telegram API", True, "reachable"))
            except TelegramError as exc:
                checks.append(("Telegram API", False, redact(exc, settings.bot_token)))
    except ConfigError as exc:
        checks.append(("configuration", False, str(exc)))
    for name, ok, detail in checks:
        print(f"{'✓' if ok else '✗'} {name}: {detail}")
    return 0 if all(ok for _, ok, _ in checks) else 1


def handle_toggle(argv: Sequence[str], enable: bool, prog: str) -> int:
    parser = argparse.ArgumentParser(prog=prog)
    parser.add_argument("--config", type=Path)
    args = parser.parse_args(list(argv))
    settings = load_settings(path=args.config)
    settings.enabled = enable
    save_settings(settings)
    print(f"Telegram notifications {'enabled' if enable else 'disabled'}.")
    return 0


def handle_send_file(argv: Sequence[str], prog: str) -> int:
    parser = argparse.ArgumentParser(prog=prog, description="Explicitly send one report file to Telegram.")
    parser.add_argument("path", type=Path)
    parser.add_argument("--caption", default="")
    parser.add_argument("--force", action="store_true", help="allow a filename that looks secret")
    parser.add_argument("--strict", action="store_true")
    add_transport_options(parser)
    args = parser.parse_args(list(argv))
    settings = load_from_args(args)
    if not settings.enabled:
        print("Telegram notifications are disabled.")
        return 0
    try:
        if not settings.send_files:
            print("File sending is disabled in configuration.")
            return 0
        path = validate_file_for_sending(args.path, args.force)
        require_credentials(settings)
        TelegramClient(settings).send_document(path, args.caption or None)
        print("✓ Telegram file delivered.")
        return 0
    except (ConfigError, TelegramError) as exc:
        print(f"WARNING: Telegram file delivery failed: {redact(exc, settings.bot_token)}", file=sys.stderr)
        return 1 if args.strict else 0


def handle_hook(argv: Sequence[str], prog: str) -> int:
    parser = argparse.ArgumentParser(prog=prog, description="Send a small optional lifecycle-hook notification.")
    parser.add_argument("--agent", default="AI Agent")
    parser.add_argument("--event", default="session ended")
    parser.add_argument("--config", type=Path)
    args = parser.parse_args(list(argv))
    try:
        data = json.load(sys.stdin) if not sys.stdin.isatty() else {}
    except json.JSONDecodeError:
        data = {}
    cwd = str(data.get("cwd", "") or "")
    reason = str(data.get("reason", "") or "")
    project = Path(cwd).name if cwd else ""
    raw = format_completion(
        sender=args.agent,
        status="success",
        task=f"{args.event}",
        summary="The agent lifecycle session ended. Use the completion skill for a task summary.",
        project=project,
        duration=reason,
    )
    settings = load_settings(path=args.config)
    return 0 if notify(settings, raw, strict=False) else 1


def usage(prog: str) -> None:
    print(
        f"""Usage:
  {prog} \"Title\" \"Message\"
  {prog} send --title \"Title\" --message \"Message\"
  {prog} completion --status success --task \"...\" --summary \"...\"

Commands: configure, test, status, doctor, enable, disable, send-file, hook
Run '{prog} <command> --help' for details.
"""
    )


def main(argv: Optional[Sequence[str]] = None) -> int:
    values = list(argv if argv is not None else sys.argv[1:])
    prog = program_name()
    if not values or values[0] in {"-h", "--help"}:
        usage(prog)
        return 0
    if values[0] in {"--version", "-V"}:
        print(VERSION)
        return 0
    command = values[0]
    rest = values[1:]
    try:
        if command in {"send", "notify"}:
            return handle_simple_send(rest, f"{prog} {command}")
        if command == "completion":
            return handle_completion(rest, f"{prog} completion")
        if command == "configure":
            return handle_configure(rest, f"{prog} configure")
        if command == "test":
            return handle_test(rest, f"{prog} test")
        if command == "status":
            return handle_status(rest, f"{prog} status")
        if command == "doctor":
            return handle_doctor(rest, f"{prog} doctor")
        if command == "enable":
            return handle_toggle(rest, True, f"{prog} enable")
        if command == "disable":
            return handle_toggle(rest, False, f"{prog} disable")
        if command == "send-file":
            return handle_send_file(rest, f"{prog} send-file")
        if command == "hook":
            return handle_hook(rest, f"{prog} hook")
        return handle_simple_send(values, prog)
    except (ConfigError, TelegramError) as exc:
        print(f"ERROR: {redact(exc)}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("Cancelled.", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
