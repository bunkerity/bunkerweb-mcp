"""Optional redaction of BunkerWeb secrets in tool inputs and outputs."""

from __future__ import annotations

import base64
import binascii
import logging
import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel

from .exceptions import ToolValidationError

if TYPE_CHECKING:
    from .config import Settings

LOGGER = logging.getLogger(__name__)

REDACTED = "***REDACTED***"

# Setting names whose values are secrets: every setting typed "password" in the
# BunkerWeb plugin.json files, the private key "*_KEY_DATA" file settings,
# API_TOKEN and DATABASE_URI (may embed credentials). Matched with ``re.search``
# so multiple-setting suffixes (``_1``) and multisite server prefixes
# (``www.example.com_``) are covered. See docs/adr/0005-secret-redaction.md.
DEFAULT_REDACT_PATTERN = (
    r"PASSWORD|PASSWD|SECRET|TOKEN|API_?KEY|LICENSE_KEY|PRIVATE_KEY|_KEY_DATA"
    r"|CREDENTIAL_ITEM|HEADER_VALUE|DATABASE_URI"
)

# Plugins whose whole job cache holds secrets: certbot keys and DNS credentials,
# custom and self-signed certificate keys, CrowdSec bouncer configuration.
DEFAULT_SENSITIVE_CACHE_PLUGINS = frozenset({"letsencrypt", "customcert", "selfsigned", "crowdsec"})

# Cache files holding private keys or registration ids in any other plugin
# (default-server-cert.key, api-server-cert.key, client-key.pem, instance.id).
SENSITIVE_CACHE_FILE_PATTERN = re.compile(r"(?:\.key|key\.pem|^instance\.id)$", re.IGNORECASE)

# Tools that write BunkerWeb settings, mapped to the parameter holding them.
SETTINGS_WRITE_FIELDS: dict[str, str] = {
    "create_service": "variables",
    "update_service": "variables",
    "global_config_update": "config",
}

# Fields that carry the value of a setting in the ``methods=true`` shape and in
# plugin setting definitions; the remaining fields are metadata.
_SETTING_VALUE_FIELDS = frozenset({"value", "default"})

_PLACEHOLDER_BYTES = REDACTED.encode()

_WRITE_REFUSED = (
    "Writing sensitive settings is disabled (BUNKERWEB_REDACT_SECRETS=true). "
    "Manage secrets through the BunkerWeb UI or API directly. Offending keys: {keys}"
)

_CACHE_REFUSED = (
    "Reading cache files that hold private keys or credentials is disabled "
    "(BUNKERWEB_REDACT_SECRETS=true). Refused: {plugin}/{file_name}"
)


@dataclass(frozen=True)
class RedactionPolicy:
    """Rules applied to every tool call when secret redaction is enabled.

    Attributes:
        pattern: Compiled expression matched against setting names.
        sensitive_cache_plugins: Plugin ids whose job cache must not be read.
    """

    pattern: re.Pattern[str] = field(default_factory=lambda: re.compile(DEFAULT_REDACT_PATTERN))
    sensitive_cache_plugins: frozenset[str] = DEFAULT_SENSITIVE_CACHE_PLUGINS

    def is_sensitive_key(self, key: str) -> bool:
        """Return whether a setting name holds a secret.

        Args:
            key: Setting name, possibly suffixed or prefixed by a server name.

        Returns:
            True when the name matches the redaction pattern.
        """
        return self.pattern.search(key) is not None

    def is_sensitive_cache_file(self, plugin: str | None, file_name: str | None) -> bool:
        """Return whether a job cache file may hold secrets.

        Args:
            plugin: Plugin identifier, or None.
            file_name: Cache file name, or None.

        Returns:
            True when the plugin belongs to the sensitive set or the file name
            looks like a private key.
        """
        if plugin is not None and plugin.lower() in self.sensitive_cache_plugins:
            return True
        return file_name is not None and SENSITIVE_CACHE_FILE_PATTERN.search(file_name) is not None

    def redact(self, obj: Any) -> Any:
        """Return a copy of ``obj`` with the values of sensitive keys masked.

        Dicts and lists are walked recursively and the input is never mutated.
        Empty values (None, empty strings, empty containers) are kept so callers
        can still tell whether a secret is configured.

        Args:
            obj: JSON-like value returned by a tool.

        Returns:
            The redacted copy.
        """
        if isinstance(obj, dict):
            return {
                key: (
                    self._mask(value)
                    if isinstance(key, str) and self.is_sensitive_key(key)
                    else self.redact(value)
                )
                for key, value in obj.items()
            }
        if isinstance(obj, list):
            return [self.redact(item) for item in obj]
        return obj

    def _mask(self, value: Any) -> Any:
        """Mask the value of a sensitive key, keeping setting metadata visible."""
        if value is None or value == "":
            return value
        if isinstance(value, dict):
            if _SETTING_VALUE_FIELDS & value.keys():
                return {
                    key: self._mask(item) if key in _SETTING_VALUE_FIELDS else self.redact(item)
                    for key, item in value.items()
                }
            return {key: self._mask(item) for key, item in value.items()}
        if isinstance(value, list):
            return [self._mask(item) for item in value]
        return REDACTED

    def redact_cache_entries(self, obj: Any) -> Any:
        """Mask the content of cache entries that may hold secrets.

        Args:
            obj: Result of the ``cache_list`` tool.

        Returns:
            A copy where the ``data`` of each sensitive entry is masked.
        """
        if isinstance(obj, list):
            return [self.redact_cache_entries(item) for item in obj]
        if not isinstance(obj, dict):
            return obj
        plugin = obj.get("plugin", obj.get("plugin_id"))
        file_name = obj.get("file_name")
        if self.is_sensitive_cache_file(
            plugin if isinstance(plugin, str) else None,
            file_name if isinstance(file_name, str) else None,
        ):
            return {
                key: REDACTED if key == "data" and value not in (None, "") else value
                for key, value in obj.items()
            }
        return {key: self.redact_cache_entries(value) for key, value in obj.items()}

    def find_sensitive_write(self, tool_name: str, params: BaseModel) -> list[str]:
        """List the reasons a tool call would write a secret or echo one back.

        Args:
            tool_name: Registered tool name.
            params: Validated tool parameters.

        Returns:
            Offending setting names, and the paths of fields that contain the
            redaction placeholder. Empty when the call is allowed.
        """
        offending: list[str] = []
        settings_field = SETTINGS_WRITE_FIELDS.get(tool_name)
        if settings_field is not None:
            settings = getattr(params, settings_field, None) or {}
            offending.extend(key for key in settings if self.is_sensitive_key(key))
        offending.extend(
            f"{path} (contains {REDACTED})" for path in _placeholder_paths(params.model_dump(), "")
        )
        return offending

    def check_call(self, tool_name: str, params: BaseModel) -> None:
        """Refuse a tool call that would write or read a secret.

        Args:
            tool_name: Registered tool name.
            params: Validated tool parameters.

        Raises:
            ToolValidationError: If the call sets a sensitive setting, sends the
                redaction placeholder back, or fetches a sensitive cache file.
        """
        offending = self.find_sensitive_write(tool_name, params)
        if offending:
            raise ToolValidationError(_WRITE_REFUSED.format(keys=", ".join(offending)))
        if tool_name == "cache_fetch_file":
            plugin = getattr(params, "plugin", None)
            file_name = getattr(params, "file_name", None)
            if self.is_sensitive_cache_file(plugin, file_name):
                raise ToolValidationError(_CACHE_REFUSED.format(plugin=plugin, file_name=file_name))

    def redact_result(self, tool_name: str, result: dict[str, Any]) -> dict[str, Any]:
        """Redact a tool result before it leaves the server.

        Args:
            tool_name: Registered tool name.
            result: Handler output.

        Returns:
            The redacted copy.
        """
        if tool_name == "cache_list":
            result = self.redact_cache_entries(result)
        elif tool_name == "authenticate" and result.get("token"):
            # The Biscuit token is an API credential; the client never reuses it.
            result = {**result, "token": REDACTED}
        redacted: dict[str, Any] = self.redact(result)
        return redacted


def _placeholder_paths(obj: Any, path: str) -> list[str]:
    """Return the paths of strings, keys or base64 uploads holding the placeholder."""
    if isinstance(obj, str):
        return [path or "<root>"] if REDACTED in obj else []
    if isinstance(obj, dict):
        found: list[str] = []
        for key, value in obj.items():
            child = f"{path}.{key}" if path else str(key)
            if isinstance(key, str) and REDACTED in key:
                found.append(child)
            elif key == "content_base64" and isinstance(value, str):
                if REDACTED in value or _PLACEHOLDER_BYTES in _b64decode(value):
                    found.append(child)
            else:
                found.extend(_placeholder_paths(value, child))
        return found
    if isinstance(obj, list):
        return [p for i, item in enumerate(obj) for p in _placeholder_paths(item, f"{path}[{i}]")]
    return []


def _b64decode(value: str) -> bytes:
    """Decode base64 content, returning empty bytes when it is malformed."""
    try:
        return base64.b64decode(value)
    except (binascii.Error, ValueError):
        return b""


def policy_from_settings(settings: Settings) -> RedactionPolicy | None:
    """Build the redaction policy configured by the environment.

    Args:
        settings: Application settings.

    Returns:
        The policy when ``BUNKERWEB_REDACT_SECRETS`` is enabled, otherwise None.
    """
    if not settings.redact_secrets:
        return None
    LOGGER.info("Secret redaction enabled (custom pattern: %s)", bool(settings.redact_pattern))
    return RedactionPolicy(pattern=re.compile(settings.redact_pattern or DEFAULT_REDACT_PATTERN))
