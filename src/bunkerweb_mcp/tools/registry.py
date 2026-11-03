"""Tool registry and orchestration."""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from mcp.types import ToolAnnotations

from ..exceptions import BunkerWebError, ToolExecutionError, ToolValidationError
from ..redaction import withheld_error
from . import (
    ban_handlers,
    cache_handlers,
    config_handlers,
    core_handlers,
    diagnose_handlers,
    instance_handlers,
    job_handlers,
    log_handlers,
    plugin_handlers,
    service_handlers,
)
from .params import (
    AuthParams,
    BanParams,
    BunkerWebClientProtocol,
    CacheDeleteBulkParams,
    CacheFetchParams,
    CacheListParams,
    ConfigCreateParams,
    ConfigKeyParams,
    ConfigListParams,
    ConfigsDeleteParams,
    ConfigUpdateParams,
    ConfigUploadParams,
    ConfigUploadUpdateParams,
    DeleteServiceParams,
    DiagnoseParams,
    EmptyParams,
    GetServiceParams,
    GlobalConfigReadParams,
    GlobalConfigUpdateParams,
    InstanceCreateParams,
    InstancesDeleteParams,
    InstanceTargetParams,
    InstanceUpdateParams,
    JobsRunParams,
    ListServicesParams,
    LogsReadParams,
    OptionalHostnameParams,
    PluginDeleteParams,
    PluginListParams,
    PluginUploadParams,
    ReloadInstancesParams,
    ServiceCreateParams,
    ServiceUpdateParams,
    SimpleHostnameParams,
    UnbanParams,
    _BaseToolParams,
)

if TYPE_CHECKING:
    from ..prompt_catalog import PromptCatalog
    from ..redaction import RedactionPolicy


SAVED_PHRASE = (
    "Saved to the database; the scheduler applies it later; this tool cannot confirm it is live."
)
DIRECT_PHRASE = "Acts on the instances immediately."
QUEUED_PHRASE = "Queued for the scheduler; this tool cannot confirm it ran."


TOOL_DESCRIPTIONS: dict[str, str] = {
    "create_api_token": "Create a BunkerWeb API token (Biscuit) for use outside this server; returns only the token, a live credential to keep secret. Give username and password, or omit both to use the server's credentials. Needs an API user; lifetime is BunkerWeb's API_BISCUIT_TTL_SECONDS. Redaction may mask it.",
    "ping_api": "Check that the BunkerWeb API answers (GET /ping, returns pong); needs no credentials. The fastest liveness probe. Use diagnose_bunkerweb to also check authentication, version and instances, ping_instances to reach the instances themselves.",
    "diagnose_bunkerweb": "Read-only report on the connected BunkerWeb: API reachability, authentication, version, MULTISITE and instance counts; service (a service ID) adds its existence, draft state and setting owners. A failed check shows as FAIL or null, not an error. Use ping_api for a bare probe.",
    "list_instances": "List every registered BunkerWeb instance (hostname, name, port, method, status, last_seen). Cached up to 60 s. This is registration data, not a live check: use ping_instances for reachability, get_instance for one host.",
    "ping_instances": "Ping one instance (hostname) or every registered instance (hostname omitted) and return each answer; BunkerWeb replies 502 if any ping fails. Read-only. Use list_instances for registration data without pinging.",
    "stop_instances": f"Stop one instance (hostname) or every registered instance (all=true), never both; stopped instances serve no traffic until restarted outside this API. 502 if a stop is not acknowledged. Use reload_instances to apply config instead. {DIRECT_PHRASE}",
    "get_instance": "Fetch one registered instance by hostname (name, ports, server_name, method, status, last_seen); 404 if unknown. Cached up to 60 s. Use list_instances to find hostnames, ping_instances to test reachability.",
    "create_instance": f"Register an instance (hostname may carry a scheme and port, https://host:5443). Name defaults to 'manual instance', method to api; fails if it exists. Use update_instance to change one. {SAVED_PHRASE}",
    "update_instance": f"Change a registered instance's name, ports, HTTPS flag, server_name or method; omitted fields keep their value. Unknown or read-only instances are rejected. Use create_instance for a new host. {SAVED_PHRASE}",
    "delete_instances": f"Unregister instances by hostname; use list_instances to find them. Hosts keep running (stop_instances halts them). Only UI/API-registered ones go; others come back as skipped, 404 if none can. {SAVED_PHRASE}",
    "reload_instances": f"Reload configuration on one instance (hostname) or every registered instance (all=true), never both. test=true (default) checks the config first, then reloads; test=false reloads without the check. Returns only success or a 502 error. Use stop_instances to halt. {DIRECT_PHRASE}",
    "list_bans": "List active bans as each instance reports them (ip, scope, service, kind, incl. CrowdSec entries), grouped per instance. Cached up to 30 s. Use it to check whether an IP is banned, or for the exact ip and service that unban_ips when writes are enabled needs.",
    "ban_ips": f"Ban IPs on every instance: bans is a list of {{ip, exp, reason, service}}, exp in seconds (0 = permanent), service omitted for global. All IPs are validated before any is banned. Use unban_ips to lift a ban. {DIRECT_PHRASE}",
    "unban_ips": f"Lift bans for IPs on every instance, globally or per service; match the scope list_bans shows. An IP also blocked by CrowdSec may be refused (409). Use list_bans first to find them. {DIRECT_PHRASE}",
    "list_services": "List services (id, method, is_draft, template, security mode, dates); with_drafts=false hides drafts. Cached up to 5 min. Use get_service for one service's settings, get_global_config for global ones.",
    "get_service": "Read one service's settings by ID (its first SERVER_NAME), with the method that set each; full=true adds defaults, with_drafts=false hides drafts. 404 if unknown. Cached up to 5 min. Use list_services to find IDs, get_global_config for global ones.",
    "create_service": f"Create a service named by SERVER_NAME (first word becomes its ID) with optional unprefixed settings and a draft flag. Fails if the name or a server name is taken. Use update_service to change one. {SAVED_PHRASE}",
    "update_service": f"Change a service's settings, rename it or set is_draft; needs MULTISITE=yes. Unknown or externally owned keys are skipped, and a receipt reads back the stored values. Use update_global_config for global. {SAVED_PHRASE}",
    "delete_service": f"Delete a service and all its settings, not reversible; wizard-managed services are refused. Use update_service with is_draft=true to take one offline instead. {SAVED_PHRASE}",
    "get_global_config": "Read global settings; full=true adds defaults, methods=true adds the method that set each. Cached up to 10 min. Use get_service for one service's settings.",
    "update_global_config": f"Set global settings from key-value pairs; settings you omit are kept, values are stored as strings. Use update_service for one service's settings. {SAVED_PHRASE}",
    "list_configs": "List custom config snippets (service, type, name, draft flag), optionally with content, across every scope unless filtered. Use get_config to read one snippet in full.",
    "get_config": "Read one custom config snippet with its content, by service, type and name; 404 if unknown. Use list_configs to find snippets.",
    "create_config": f"Create one custom config snippet from text (method api); fails if the name exists or the service is unknown. Use create_configs_from_files to upload files. {SAVED_PHRASE}",
    "update_config": f"Edit, rename or move a snippet from text; omitted fields keep their value. UI/API-managed or template-derived only; templates cannot be renamed. A no-op is rejected. Use update_config_from_file for files. {SAVED_PHRASE}",
    "delete_configs": f"Delete config snippets: configs is a list of {{service, type, name}}, service 'global' for global ones. Only UI/API-managed ones go; others come back as skipped, 404 if none. Use list_configs to find them. {SAVED_PHRASE}",
    "create_configs_from_files": f"Create snippets from base64 files ({{filename, content_base64}}) sharing one type and service; each is named after its sanitized file stem and bad files are reported, not fatal. Use create_config for text. {SAVED_PHRASE}",
    "update_config_from_file": f"Replace a snippet from a base64 file ({{filename, content_base64}}); without new_name the stem renames it. UI/API-managed or template-derived only; templates cannot be renamed. Use update_config for text. {SAVED_PHRASE}",
    "list_plugins": "List installed plugins, filtered by type (all, external, ui, pro). type=ui lists the IDs accepted by uninstall_plugin when writes are enabled. Use list_jobs for jobs.",
    "install_plugins": f"Install UI plugins from base64 archives ({{filename, content_base64}}; .zip, .tar.gz, .tar.xz with plugin.json). An existing plugin ID is refused; bad archives are reported. Uninstall first to replace. {SAVED_PHRASE}",
    "uninstall_plugin": f"Uninstall one UI-installed plugin by plugin_id; external and pro plugins are refused, 404 if absent. Use list_plugins type=ui to find IDs, install_plugins to add one (uninstall first to replace). {SAVED_PHRASE}",
    "list_cache_files": "List files that scheduler jobs cached (service, plugin, job, file name, checksum, last_update). with_data inlines text only; binary files show a placeholder, so read them with get_cache_file download=true. Use get_cache_file to read one.",
    "delete_cache_files": f"Delete job cache files: files is a list of {{service, plugin, job_name, file_name}} service omitted for global. Use list_cache_files to find the keys. Missing files are reported per file; run_jobs regenerates them. {QUEUED_PHRASE}",
    "get_cache_file": "Read one job cache file by service, plugin, job_name and file_name as list_cache_files shows. Returns printable text; download=true returns base64 bytes instead. 404 if missing; sensitive files are refused when secret redaction is on. Use list_cache_files to find files.",
    "list_jobs": "List scheduler jobs with their run history and cache metadata. Use list_cache_files for the files they wrote, and run_jobs when writes are enabled to trigger them.",
    "run_jobs": f"Trigger every job of the listed plugins (jobs: {{plugin, name}}; name is informational, all of a plugin's jobs run), e.g. after delete_cache_files. Returns only 'Jobs scheduled'; use list_jobs to check results. {QUEUED_PHRASE}",
    "list_logs": "List readable BunkerWeb log files under the configured log directory (name, size, modified time, rotated flag), newest first. Gzip files are excluded. Pass a source to read_log.",
    "read_log": "Read recent lines from one log source named by list_logs, newest window first, optionally filtered by a literal text query. Output is capped; next_cursor and has_more page backwards through older content.",
}


SEARCH_TOOL_DESCRIPTION = (
    "Search the official BunkerWeb documentation by meaning, in any language. Returns up to limit "
    "sections with title, URL, category, relevance and content, one per document. Use it for how-to "
    "and setting questions; use the API tools to read live state. Lower min_score if nothing matches."
)


@dataclass(frozen=True)
class ToolEffect:
    read_only: bool
    destructive: bool

    def annotations(self) -> ToolAnnotations:
        if self.read_only:
            return ToolAnnotations(read_only_hint=True)
        return ToolAnnotations(read_only_hint=False, destructive_hint=self.destructive)


TOOL_EFFECTS: dict[str, ToolEffect] = {
    "ping_api": ToolEffect(read_only=True, destructive=False),
    "list_instances": ToolEffect(read_only=True, destructive=False),
    "ping_instances": ToolEffect(read_only=True, destructive=False),
    "get_instance": ToolEffect(read_only=True, destructive=False),
    "list_bans": ToolEffect(read_only=True, destructive=False),
    "list_services": ToolEffect(read_only=True, destructive=False),
    "get_service": ToolEffect(read_only=True, destructive=False),
    "get_global_config": ToolEffect(read_only=True, destructive=False),
    "list_configs": ToolEffect(read_only=True, destructive=False),
    "get_config": ToolEffect(read_only=True, destructive=False),
    "list_plugins": ToolEffect(read_only=True, destructive=False),
    "list_cache_files": ToolEffect(read_only=True, destructive=False),
    "get_cache_file": ToolEffect(read_only=True, destructive=False),
    "list_jobs": ToolEffect(read_only=True, destructive=False),
    "list_logs": ToolEffect(read_only=True, destructive=False),
    "read_log": ToolEffect(read_only=True, destructive=False),
    "search_bunkerweb_docs": ToolEffect(read_only=True, destructive=False),
    "diagnose_bunkerweb": ToolEffect(read_only=True, destructive=False),
    "create_api_token": ToolEffect(read_only=False, destructive=False),
    "create_instance": ToolEffect(read_only=False, destructive=False),
    "ban_ips": ToolEffect(read_only=False, destructive=False),
    "create_service": ToolEffect(read_only=False, destructive=False),
    "run_jobs": ToolEffect(read_only=False, destructive=False),
    "create_config": ToolEffect(read_only=False, destructive=True),
    "create_configs_from_files": ToolEffect(read_only=False, destructive=True),
    "stop_instances": ToolEffect(read_only=False, destructive=True),
    "update_instance": ToolEffect(read_only=False, destructive=True),
    "delete_instances": ToolEffect(read_only=False, destructive=True),
    "reload_instances": ToolEffect(read_only=False, destructive=True),
    "unban_ips": ToolEffect(read_only=False, destructive=True),
    "update_service": ToolEffect(read_only=False, destructive=True),
    "delete_service": ToolEffect(read_only=False, destructive=True),
    "update_global_config": ToolEffect(read_only=False, destructive=True),
    "update_config": ToolEffect(read_only=False, destructive=True),
    "delete_configs": ToolEffect(read_only=False, destructive=True),
    "update_config_from_file": ToolEffect(read_only=False, destructive=True),
    "install_plugins": ToolEffect(read_only=False, destructive=True),
    "uninstall_plugin": ToolEffect(read_only=False, destructive=True),
    "delete_cache_files": ToolEffect(read_only=False, destructive=True),
}


def effect_for(name: str) -> ToolEffect:
    return TOOL_EFFECTS.get(name, ToolEffect(read_only=False, destructive=True))


class Tools:
    """Collection of callable tools wired to the BunkerWeb client."""

    def __init__(
        self,
        client: BunkerWebClientProtocol,
        prompt_catalog: PromptCatalog | None = None,
        logs_path: Path | None = None,
        redaction: RedactionPolicy | None = None,
        read_only: bool = False,
    ) -> None:
        self._client = client
        from ..prompt_catalog import PromptCatalog

        self._prompt_catalog = prompt_catalog or PromptCatalog({})
        self._registry: dict[
            str, tuple[type[_BaseToolParams], Callable[[Any], Awaitable[dict[str, Any]]]]
        ] = {
            # Core handlers
            "create_api_token": (AuthParams, self._wrap(core_handlers.handle_create_api_token)),
            "ping_api": (EmptyParams, self._wrap(core_handlers.handle_ping_api)),
            "diagnose_bunkerweb": (DiagnoseParams, self._wrap(diagnose_handlers.handle_diagnose)),
            # Instance handlers
            "list_instances": (EmptyParams, self._wrap(instance_handlers.handle_list_instances)),
            "ping_instances": (
                OptionalHostnameParams,
                self._wrap(instance_handlers.handle_ping_instances),
            ),
            "stop_instances": (
                InstanceTargetParams,
                self._wrap(instance_handlers.handle_stop_instances),
            ),
            "get_instance": (
                SimpleHostnameParams,
                self._wrap(instance_handlers.handle_get_instance),
            ),
            "create_instance": (
                InstanceCreateParams,
                self._wrap(instance_handlers.handle_create_instance),
            ),
            "update_instance": (
                InstanceUpdateParams,
                self._wrap(instance_handlers.handle_update_instance),
            ),
            "delete_instances": (
                InstancesDeleteParams,
                self._wrap(instance_handlers.handle_delete_instances),
            ),
            "reload_instances": (
                ReloadInstancesParams,
                self._wrap(instance_handlers.handle_reload_instances),
            ),
            # Ban handlers
            "list_bans": (EmptyParams, self._wrap(ban_handlers.handle_list_bans)),
            "ban_ips": (BanParams, self._wrap(ban_handlers.handle_ban_ip)),
            "unban_ips": (UnbanParams, self._wrap(ban_handlers.handle_unban_ip)),
            # Service handlers
            "list_services": (
                ListServicesParams,
                self._wrap(service_handlers.handle_list_services),
            ),
            "get_service": (GetServiceParams, self._wrap(service_handlers.handle_get_service)),
            "create_service": (
                ServiceCreateParams,
                self._wrap(service_handlers.handle_create_service),
            ),
            "update_service": (
                ServiceUpdateParams,
                self._wrap(service_handlers.handle_update_service),
            ),
            "delete_service": (
                DeleteServiceParams,
                self._wrap(service_handlers.handle_delete_service),
            ),
            # Config handlers
            "get_global_config": (
                GlobalConfigReadParams,
                self._wrap(config_handlers.handle_get_global_config),
            ),
            "update_global_config": (
                GlobalConfigUpdateParams,
                self._wrap(config_handlers.handle_update_global_config),
            ),
            "list_configs": (ConfigListParams, self._wrap(config_handlers.handle_list_configs)),
            "get_config": (ConfigKeyParams, self._wrap(config_handlers.handle_get_config)),
            "create_config": (
                ConfigCreateParams,
                self._wrap(config_handlers.handle_create_config),
            ),
            "update_config": (
                ConfigUpdateParams,
                self._wrap(config_handlers.handle_update_config),
            ),
            "delete_configs": (
                ConfigsDeleteParams,
                self._wrap(config_handlers.handle_delete_configs),
            ),
            "create_configs_from_files": (
                ConfigUploadParams,
                self._wrap(config_handlers.handle_upload_configs),
            ),
            "update_config_from_file": (
                ConfigUploadUpdateParams,
                self._wrap(config_handlers.handle_update_config_upload),
            ),
            # Plugin handlers
            "list_plugins": (PluginListParams, self._wrap(plugin_handlers.handle_list_plugins)),
            "install_plugins": (
                PluginUploadParams,
                self._wrap(plugin_handlers.handle_upload_plugins),
            ),
            "uninstall_plugin": (
                PluginDeleteParams,
                self._wrap(plugin_handlers.handle_delete_plugin),
            ),
            # Cache handlers
            "list_cache_files": (CacheListParams, self._wrap(cache_handlers.handle_list_cache)),
            "delete_cache_files": (
                CacheDeleteBulkParams,
                self._wrap(cache_handlers.handle_delete_cache_files),
            ),
            "get_cache_file": (
                CacheFetchParams,
                self._wrap(cache_handlers.handle_fetch_cache_file),
            ),
            # Job handlers
            "list_jobs": (EmptyParams, self._wrap(job_handlers.handle_list_jobs)),
            "run_jobs": (JobsRunParams, self._wrap(job_handlers.handle_run_jobs)),
        }
        if logs_path is not None:
            log_reader = log_handlers.LogReader(logs_path)
            self._registry.update(
                {
                    "list_logs": (EmptyParams, log_reader.list_logs),
                    "read_log": (LogsReadParams, log_reader.read_logs),
                }
            )
        if redaction is not None:
            self._registry = {
                name: (model, self._redact(name, handler, redaction))
                for name, (model, handler) in self._registry.items()
            }
        if read_only:
            self._registry = {
                name: entry for name, entry in self._registry.items() if effect_for(name).read_only
            }

    def _wrap(
        self, handler: Callable[[BunkerWebClientProtocol, Any], Awaitable[dict[str, Any]]]
    ) -> Callable[[Any], Awaitable[dict[str, Any]]]:
        """Wrap a handler to inject the client."""

        async def wrapped(params: Any) -> dict[str, Any]:
            return await handler(self._client, params)

        return wrapped

    @staticmethod
    def _redact(
        name: str,
        handler: Callable[[Any], Awaitable[dict[str, Any]]],
        policy: RedactionPolicy,
    ) -> Callable[[Any], Awaitable[dict[str, Any]]]:
        """Wrap a handler so its inputs are checked and its output redacted."""

        async def redacted(params: Any) -> dict[str, Any]:
            policy.check_call(name, params)
            try:
                result = await handler(params)
            except (ToolValidationError, ToolExecutionError):
                raise
            except Exception as exc:  # noqa: BLE001 - upstream details may hold secrets
                raise withheld_error(exc) from None
            return policy.redact_result(name, result)

        return redacted

    def list_descriptors(self) -> list[dict[str, Any]]:
        """Return JSON-serializable metadata describing available tools."""
        descriptors: list[dict[str, Any]] = []
        for name, (model, _) in self._registry.items():
            effect = effect_for(name)
            entry = {
                "name": name,
                "description": TOOL_DESCRIPTIONS[name],
                "input_schema": model.model_json_schema(),
                "read_only": effect.read_only,
                "destructive": effect.destructive,
            }
            prompt = self._prompt_catalog.get(name)
            if prompt:
                entry["prompt"] = prompt
            descriptors.append(entry)
        return descriptors

    def iter_registered(
        self,
    ) -> Iterable[
        tuple[
            str, type[_BaseToolParams], Callable[[Any], Awaitable[dict[str, Any]]], str, str | None
        ]
    ]:
        """Yield metadata for each registered tool."""
        for name, (model, handler) in self._registry.items():
            yield name, model, handler, TOOL_DESCRIPTIONS[name], self._prompt_catalog.get(name)

    def get_tool(self, name: str) -> Callable[[dict[str, Any]], Awaitable[dict[str, Any]]] | None:
        """Get an executable tool by name."""
        entry = self._registry.get(name)
        if entry is None:
            return None
        params_model, handler = entry

        async def executor(payload: dict[str, Any]) -> dict[str, Any]:
            try:
                params = params_model.model_validate(payload)
            except Exception as exc:  # noqa: BLE001 - bubble up validation errors
                raise ToolValidationError(str(exc)) from exc
            try:
                return await handler(params)
            except BunkerWebError as exc:
                raise ToolExecutionError(str(exc)) from exc
            except (ToolValidationError, ToolExecutionError):
                raise
            except Exception as exc:  # noqa: BLE001 - ensure consistent tool errors
                raise ToolExecutionError("Unexpected tool execution error") from exc

        return executor

    def get_prompt(self, name: str) -> str | None:
        """Return the configured prompt for a tool, if any."""
        return self._prompt_catalog.get(name)
