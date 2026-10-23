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
    CacheFileKeyParams,
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
    HostnameParams,
    InstanceCreateParams,
    InstancesDeleteParams,
    InstanceUpdateParams,
    JobsRunParams,
    ListServicesParams,
    LogsReadParams,
    PluginDeleteParams,
    PluginListParams,
    PluginUploadParams,
    ReloadParams,
    ServiceConvertParams,
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
    "authenticate": "Returns a new BunkerWeb API token; changes nothing in the BunkerWeb configuration.",
    "ping": "Check that the BunkerWeb API answers (GET /ping, returns pong). Use it as the fastest liveness probe; use diagnose to also check authentication, version and instances.",
    "health": "Read the API's own liveness probe (GET /health); it does not contact instances. Use instances_ping_all for instances and diagnose for auth and version checks.",
    "diagnose": "Read-only check of the connected BunkerWeb: reachability, authentication, version, MULTISITE, instances, and optionally who owns a service's settings.",
    "list_instances": "List every registered BunkerWeb instance with its status. Results may be cached up to 60 s. Use instance_get for one host, instances_ping_all for live reachability.",
    "instances_ping_all": "Ping every registered instance live and report which answer. Use instance_ping for one host; list_instances returns registration data without pinging.",
    "instances_stop_all": f"Stop every registered instance; traffic stops until they restart. Use instance_stop for one host. {DIRECT_PHRASE}",
    "instance_get": "Fetch one registered instance by hostname. Results may be cached up to 60 s. Use list_instances to find hostnames, instance_ping to test reachability.",
    "instance_ping": "Ping one instance live by hostname. Use instances_ping_all for every instance; instance_get returns the stored record without pinging.",
    "instance_stop": f"Stop one instance by hostname; it serves no traffic until restarted. Use instances_stop_all for all. {DIRECT_PHRASE}",
    "instance_create": f"Register a new instance for the scheduler to manage. Use instance_update to change one. {SAVED_PHRASE}",
    "instance_update": f"Change a registered instance; omitted fields keep their value. Use instance_create for a new host. {SAVED_PHRASE}",
    "instances_delete_bulk": f"Unregister several UI/API-registered instances; the hosts keep running. Use instance_delete for one. {SAVED_PHRASE}",
    "instance_delete": f"Unregister one UI/API-registered instance; the host keeps running. Use instances_delete_bulk for several. {SAVED_PHRASE}",
    "reload_instances": f"Reload configuration on every instance, testing it first by default. Use reload_instance for one host. {DIRECT_PHRASE}",
    "reload_instance": f"Reload configuration on one instance, testing it first by default. Use reload_instances for all. {DIRECT_PHRASE}",
    "list_bans": "List active IP bans as reported by each instance. Results may be cached up to 30 s. It gives the exact IPs and services for unban_ip when writes are enabled.",
    "ban_ip": f"Ban one or more IPs, globally or per service, for exp seconds (0 = permanent). Use unban_ip to lift a ban. {DIRECT_PHRASE}",
    "unban_ip": f"Lift bans for one or more IPs, globally or per service. Use list_bans first to find them. {DIRECT_PHRASE}",
    "list_services": "List services with their configuration and dates. Results may be cached up to 5 min. Use get_service to read one service in detail.",
    "get_service": "Read one service's settings by ID; full=true adds defaults. Cached up to 5 min. Use list_services to find IDs, global_config_read for global settings.",
    "create_service": f"Create a service from SERVER_NAME and optional settings. Use update_service to change one. {SAVED_PHRASE}",
    "update_service": f"Change a service's settings; skips unknown or externally owned keys and reads back the result. Use global_config_update for global settings. {SAVED_PHRASE}",
    "delete_service": f"Delete a service and all its settings; not reversible. Use convert_service to take it offline. {SAVED_PHRASE}",
    "convert_service": f"Switch a service between online and draft without deleting it. Use delete_service to remove it. {SAVED_PHRASE}",
    "global_config_read": "Read global settings; full=true adds defaults. Results may be cached up to 10 min. Use get_service for one service's settings.",
    "global_config_update": f"Set global settings from key-value pairs; other settings are kept. Use update_service for one service. {SAVED_PHRASE}",
    "configs_list": "List custom config snippets (service, type, name), optionally with content. Use config_get to read one snippet in full.",
    "config_get": "Read one custom config snippet with its content by service, type and name. Use configs_list to find snippets.",
    "config_create": f"Create one custom config snippet from text. Use configs_upload for several files. {SAVED_PHRASE}",
    "config_update": f"Edit, rename or move one snippet from text; omitted fields keep their value. Use config_upload_update to send a file. {SAVED_PHRASE}",
    "config_delete": f"Delete one custom config snippet. Use configs_delete_bulk for several. {SAVED_PHRASE}",
    "configs_delete_bulk": f"Delete several custom config snippets in one call. Use config_delete for one. {SAVED_PHRASE}",
    "configs_upload": f"Create snippets from base64 files, one per file, named after the file. Use config_create for text. {SAVED_PHRASE}",
    "config_upload_update": f"Replace one snippet's content from a base64 file; without new_name the file stem renames it. Use config_update for text. {SAVED_PHRASE}",
    "plugins_list": "List installed plugins, filtered by type (all, external, ui, pro). type=ui lists the IDs accepted by plugin_delete when writes are enabled; use jobs_list for jobs.",
    "plugins_upload": f"Install UI plugins from base64 archives; an existing plugin ID is refused. Use plugin_delete first to replace a UI plugin. {SAVED_PHRASE}",
    "plugin_delete": f"Uninstall one UI-installed plugin by ID; other plugins are refused. Use plugins_list with type=ui to find IDs. {SAVED_PHRASE}",
    "cache_list": "List files that scheduler jobs cached, filtered by service, plugin or job. Use cache_fetch_file to read one file.",
    "cache_delete_bulk": f"Delete several job cache files. Use cache_delete_file for one; jobs_run regenerates them. {QUEUED_PHRASE}",
    "cache_fetch_file": "Read one job cache file, keyed as listed by cache_list. Returns printable text, or base64 bytes with download=true. Use cache_list to find files.",
    "cache_delete_file": f"Delete one job cache file. Use cache_delete_bulk for several; jobs_run regenerates it. {QUEUED_PHRASE}",
    "jobs_list": "List scheduler jobs with their run history and cache metadata. Use cache_list for the files they wrote, and jobs_run when writes are enabled to trigger them.",
    "jobs_run": f"Trigger the jobs of one or more plugins, e.g. after cache_delete_file. Use jobs_list to check results. {QUEUED_PHRASE}",
    "logs_list": "List readable BunkerWeb runtime log sources.",
    "logs_read": "Read bounded recent lines from a BunkerWeb runtime log.",
}


@dataclass(frozen=True)
class ToolEffect:
    read_only: bool
    destructive: bool

    def annotations(self) -> ToolAnnotations:
        if self.read_only:
            return ToolAnnotations(read_only_hint=True)
        return ToolAnnotations(read_only_hint=False, destructive_hint=self.destructive)


TOOL_EFFECTS: dict[str, ToolEffect] = {
    "ping": ToolEffect(read_only=True, destructive=False),
    "health": ToolEffect(read_only=True, destructive=False),
    "list_instances": ToolEffect(read_only=True, destructive=False),
    "instances_ping_all": ToolEffect(read_only=True, destructive=False),
    "instance_get": ToolEffect(read_only=True, destructive=False),
    "instance_ping": ToolEffect(read_only=True, destructive=False),
    "list_bans": ToolEffect(read_only=True, destructive=False),
    "list_services": ToolEffect(read_only=True, destructive=False),
    "get_service": ToolEffect(read_only=True, destructive=False),
    "global_config_read": ToolEffect(read_only=True, destructive=False),
    "configs_list": ToolEffect(read_only=True, destructive=False),
    "config_get": ToolEffect(read_only=True, destructive=False),
    "plugins_list": ToolEffect(read_only=True, destructive=False),
    "cache_list": ToolEffect(read_only=True, destructive=False),
    "cache_fetch_file": ToolEffect(read_only=True, destructive=False),
    "jobs_list": ToolEffect(read_only=True, destructive=False),
    "logs_list": ToolEffect(read_only=True, destructive=False),
    "logs_read": ToolEffect(read_only=True, destructive=False),
    "search_bunkerweb_docs": ToolEffect(read_only=True, destructive=False),
    "diagnose": ToolEffect(read_only=True, destructive=False),
    "authenticate": ToolEffect(read_only=False, destructive=False),
    "instance_create": ToolEffect(read_only=False, destructive=False),
    "ban_ip": ToolEffect(read_only=False, destructive=False),
    "create_service": ToolEffect(read_only=False, destructive=False),
    "jobs_run": ToolEffect(read_only=False, destructive=False),
    "config_create": ToolEffect(read_only=False, destructive=True),
    "configs_upload": ToolEffect(read_only=False, destructive=True),
    "instances_stop_all": ToolEffect(read_only=False, destructive=True),
    "instance_stop": ToolEffect(read_only=False, destructive=True),
    "instance_update": ToolEffect(read_only=False, destructive=True),
    "instances_delete_bulk": ToolEffect(read_only=False, destructive=True),
    "instance_delete": ToolEffect(read_only=False, destructive=True),
    "reload_instances": ToolEffect(read_only=False, destructive=True),
    "reload_instance": ToolEffect(read_only=False, destructive=True),
    "unban_ip": ToolEffect(read_only=False, destructive=True),
    "update_service": ToolEffect(read_only=False, destructive=True),
    "delete_service": ToolEffect(read_only=False, destructive=True),
    "convert_service": ToolEffect(read_only=False, destructive=True),
    "global_config_update": ToolEffect(read_only=False, destructive=True),
    "config_update": ToolEffect(read_only=False, destructive=True),
    "config_delete": ToolEffect(read_only=False, destructive=True),
    "configs_delete_bulk": ToolEffect(read_only=False, destructive=True),
    "config_upload_update": ToolEffect(read_only=False, destructive=True),
    "plugins_upload": ToolEffect(read_only=False, destructive=True),
    "plugin_delete": ToolEffect(read_only=False, destructive=True),
    "cache_delete_bulk": ToolEffect(read_only=False, destructive=True),
    "cache_delete_file": ToolEffect(read_only=False, destructive=True),
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
            "authenticate": (AuthParams, self._wrap(core_handlers.handle_authenticate)),
            "ping": (EmptyParams, self._wrap(core_handlers.handle_ping)),
            "health": (EmptyParams, self._wrap(core_handlers.handle_health)),
            "diagnose": (DiagnoseParams, self._wrap(diagnose_handlers.handle_diagnose)),
            # Instance handlers
            "list_instances": (EmptyParams, self._wrap(instance_handlers.handle_list_instances)),
            "instances_ping_all": (
                EmptyParams,
                self._wrap(instance_handlers.handle_ping_instances),
            ),
            "instances_stop_all": (
                EmptyParams,
                self._wrap(instance_handlers.handle_stop_instances),
            ),
            "instance_get": (
                SimpleHostnameParams,
                self._wrap(instance_handlers.handle_get_instance),
            ),
            "instance_ping": (
                SimpleHostnameParams,
                self._wrap(instance_handlers.handle_ping_instance),
            ),
            "instance_stop": (
                SimpleHostnameParams,
                self._wrap(instance_handlers.handle_stop_instance),
            ),
            "instance_create": (
                InstanceCreateParams,
                self._wrap(instance_handlers.handle_create_instance),
            ),
            "instance_update": (
                InstanceUpdateParams,
                self._wrap(instance_handlers.handle_update_instance),
            ),
            "instances_delete_bulk": (
                InstancesDeleteParams,
                self._wrap(instance_handlers.handle_delete_instances),
            ),
            "instance_delete": (
                SimpleHostnameParams,
                self._wrap(instance_handlers.handle_delete_instance),
            ),
            "reload_instances": (
                ReloadParams,
                self._wrap(instance_handlers.handle_reload_instances),
            ),
            "reload_instance": (
                HostnameParams,
                self._wrap(instance_handlers.handle_reload_instance),
            ),
            # Ban handlers
            "list_bans": (EmptyParams, self._wrap(ban_handlers.handle_list_bans)),
            "ban_ip": (BanParams, self._wrap(ban_handlers.handle_ban_ip)),
            "unban_ip": (UnbanParams, self._wrap(ban_handlers.handle_unban_ip)),
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
            "convert_service": (
                ServiceConvertParams,
                self._wrap(service_handlers.handle_convert_service),
            ),
            # Config handlers
            "global_config_read": (
                GlobalConfigReadParams,
                self._wrap(config_handlers.handle_read_global_config),
            ),
            "global_config_update": (
                GlobalConfigUpdateParams,
                self._wrap(config_handlers.handle_update_global_config),
            ),
            "configs_list": (ConfigListParams, self._wrap(config_handlers.handle_list_configs)),
            "config_get": (ConfigKeyParams, self._wrap(config_handlers.handle_get_config)),
            "config_create": (
                ConfigCreateParams,
                self._wrap(config_handlers.handle_create_config),
            ),
            "config_update": (
                ConfigUpdateParams,
                self._wrap(config_handlers.handle_update_config),
            ),
            "config_delete": (
                ConfigKeyParams,
                self._wrap(config_handlers.handle_delete_config),
            ),
            "configs_delete_bulk": (
                ConfigsDeleteParams,
                self._wrap(config_handlers.handle_delete_configs_bulk),
            ),
            "configs_upload": (
                ConfigUploadParams,
                self._wrap(config_handlers.handle_upload_configs),
            ),
            "config_upload_update": (
                ConfigUploadUpdateParams,
                self._wrap(config_handlers.handle_update_config_upload),
            ),
            # Plugin handlers
            "plugins_list": (PluginListParams, self._wrap(plugin_handlers.handle_list_plugins)),
            "plugins_upload": (
                PluginUploadParams,
                self._wrap(plugin_handlers.handle_upload_plugins),
            ),
            "plugin_delete": (
                PluginDeleteParams,
                self._wrap(plugin_handlers.handle_delete_plugin),
            ),
            # Cache handlers
            "cache_list": (CacheListParams, self._wrap(cache_handlers.handle_list_cache)),
            "cache_delete_bulk": (
                CacheDeleteBulkParams,
                self._wrap(cache_handlers.handle_delete_cache_bulk),
            ),
            "cache_fetch_file": (
                CacheFetchParams,
                self._wrap(cache_handlers.handle_fetch_cache_file),
            ),
            "cache_delete_file": (
                CacheFileKeyParams,
                self._wrap(cache_handlers.handle_delete_cache_file),
            ),
            # Job handlers
            "jobs_list": (EmptyParams, self._wrap(job_handlers.handle_list_jobs)),
            "jobs_run": (JobsRunParams, self._wrap(job_handlers.handle_run_jobs)),
        }
        if logs_path is not None:
            log_reader = log_handlers.LogReader(logs_path)
            self._registry.update(
                {
                    "logs_list": (EmptyParams, log_reader.list_logs),
                    "logs_read": (LogsReadParams, log_reader.read_logs),
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
