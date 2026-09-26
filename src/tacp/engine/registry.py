"""Central Capability Registry for TACP Device Control Plane."""

from __future__ import annotations

import logging
from typing import Any, Callable, Dict, List, Optional

from tacp.backends.base import BackendStatus, BackendType
from tacp.backends.manager import BackendManager
from tacp.engine.capability import CapabilityDefinition
from tacp.engine.resolver import CapabilityResolver
from tacp.handlers.automation_handlers import (
    handle_automation_create,
    handle_automation_list,
    handle_automation_start,
    handle_diagnostics_bundle,
    handle_tasks_cancel,
    handle_tasks_get,
    handle_tasks_list,
)
from tacp.handlers.device_handlers import (
    handle_device_battery,
    handle_device_info,
    handle_device_properties,
    handle_device_snapshot,
    handle_device_uptime,
)
from tacp.handlers.filesystem_handlers import (
    handle_fs_append,
    handle_fs_copy,
    handle_fs_delete,
    handle_fs_find,
    handle_fs_hash,
    handle_fs_list,
    handle_fs_mkdir,
    handle_fs_move,
    handle_fs_read,
    handle_fs_stat,
    handle_fs_unzip,
    handle_fs_write,
    handle_fs_zip,
)
from tacp.handlers.hardware_handlers import (
    handle_camera_capture,
    handle_camera_list,
    handle_clipboard_get,
    handle_clipboard_set,
    handle_input_capabilities,
    handle_input_key,
    handle_input_tap,
    handle_location_get,
    handle_logs_system,
    handle_microphone_record,
    handle_notifications_post,
    handle_screen_capture,
    handle_screen_info,
    handle_sensors_list,
    handle_settings_get,
    handle_tts_speak,
)
from tacp.handlers.network_handlers import (
    handle_network_diagnostics,
    handle_network_download,
    handle_network_http_request,
    handle_network_interfaces,
    handle_network_ping,
    handle_network_resolve,
    handle_wifi_status,
)
from tacp.handlers.package_handlers import (
    handle_app_launch,
    handle_app_open_url,
    handle_package_info,
    handle_package_install,
    handle_package_list,
    handle_package_path,
    handle_package_uninstall,
)
from tacp.handlers.process_handlers import (
    handle_process_inspect,
    handle_process_kill,
    handle_process_list,
    handle_process_signal,
)
from tacp.handlers.shell_handlers import (
    handle_shell_env,
    handle_shell_exec,
    handle_shell_pwd,
    handle_shell_which,
)
from tacp.handlers.storage_handlers import (
    handle_storage_cleanup_candidates,
    handle_storage_duplicates,
    handle_storage_large_files,
    handle_storage_mounts,
    handle_storage_overview,
)

logger = logging.getLogger(__name__)


class CapabilityRegistry:
    """Central store, discovery, and dispatch engine for all TACP capabilities."""

    def __init__(self, backend_manager: Optional[BackendManager] = None) -> None:
        self.backend_manager = backend_manager or BackendManager.get_default()
        self.resolver = CapabilityResolver(self.backend_manager)
        self._capabilities: Dict[str, CapabilityDefinition] = {}
        self._mcp_tools_cache: Optional[List[Dict[str, Any]]] = None
        self._register_all_capabilities()

    def register(self, cap: CapabilityDefinition) -> None:
        """Register a capability definition."""
        self._capabilities[cap.id] = cap
        self._mcp_tools_cache = None

    def get(self, cap_id: str) -> Optional[CapabilityDefinition]:
        """Fetch a capability definition by ID."""
        return self._capabilities.get(cap_id)

    def list_all(self) -> List[CapabilityDefinition]:
        """Return all registered capability definitions."""
        return list(self._capabilities.values())

    def list_capabilities(self, filter_category: Optional[str] = None) -> List[Dict[str, Any]]:
        """List all capabilities with their live availability and resolved backend."""
        results: List[Dict[str, Any]] = []
        for cap_id, cap in sorted(self._capabilities.items()):
            if filter_category and cap.category != filter_category:
                continue
            backend, status, reason = self.resolver.resolve(cap)
            b_type = backend.backend_type if backend else None
            data = cap.to_dict(active_backend=b_type, availability=status)
            data["resolution_details"] = reason
            results.append(data)
        return results

    def get_mcp_tools(self) -> List[Dict[str, Any]]:
        """Export all registered capabilities as standard MCP Tools."""
        if self._mcp_tools_cache is None:
            self._mcp_tools_cache = [cap.to_mcp_tool_schema() for cap in self._capabilities.values()]
        return self._mcp_tools_cache

    def dispatch(self, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Dispatch an MCP tool call to its capability resolver and handler."""
        cap = self._capabilities.get(tool_name)
        if not cap:
            return {"success": False, "error": f"Unknown tool or capability: '{tool_name}'"}
        return self.resolver.execute(cap, arguments)

    def _register_all_capabilities(self) -> None:
        """Register full suite of Android device control capabilities."""
        # 1. SHELL
        self.register(CapabilityDefinition(
            id="shell.exec",
            name="Execute Shell Command",
            description="Execute arbitrary Linux/Android command with arguments, working directory, and timeout",
            category="shell",
            supported_backends=[BackendType.TERMUX, BackendType.ANDROID_SHELL],
            parameters={
                "command": {"type": "string", "description": "Command or executable to run", "required": True},
                "args": {"type": "array", "description": "Optional command line arguments"},
                "cwd": {"type": "string", "description": "Working directory"},
                "timeout": {"type": "number", "description": "Timeout in seconds (default: 30.0)"},
                "stdin": {"type": "string", "description": "Optional stdin input text"},
            },
            handler=handle_shell_exec,
        ))
        self.register(CapabilityDefinition(
            id="shell.which",
            name="Locate Binary Executable",
            description="Locate binary executable across PATH, /system/bin, /vendor/bin",
            category="shell",
            supported_backends=[BackendType.TERMUX, BackendType.ANDROID_SHELL],
            parameters={
                "binary": {"type": "string", "description": "Executable name to locate", "required": True},
            },
            handler=handle_shell_which,
        ))
        self.register(CapabilityDefinition(
            id="shell.env",
            name="Get Environment Variables",
            description="Inspect environment variables with sensitive secrets scrubbed",
            category="shell",
            supported_backends=[BackendType.TERMUX],
            handler=handle_shell_env,
        ))
        self.register(CapabilityDefinition(
            id="shell.pwd",
            name="Get Current Working Directory",
            description="Return the current process working directory",
            category="shell",
            supported_backends=[BackendType.TERMUX],
            handler=handle_shell_pwd,
        ))

        # 2. PROCESS
        self.register(CapabilityDefinition(
            id="process.list",
            name="List Running Processes",
            description="List running Linux and Android processes with PID and command names",
            category="process",
            supported_backends=[BackendType.TERMUX, BackendType.ANDROID_SHELL],
            parameters={"limit": {"type": "integer", "description": "Maximum processes to return"}},
            handler=handle_process_list,
        ))
        self.register(CapabilityDefinition(
            id="process.inspect",
            name="Inspect Process Details",
            description="Inspect command line, memory, status, and PPID of a specific process PID",
            category="process",
            supported_backends=[BackendType.TERMUX, BackendType.ANDROID_SHELL],
            parameters={"pid": {"type": "integer", "description": "Process ID to inspect", "required": True}},
            handler=handle_process_inspect,
        ))
        self.register(CapabilityDefinition(
            id="process.signal",
            name="Send Signal to Process",
            description="Send an OS signal (e.g. 15 for SIGTERM, 9 for SIGKILL) to target PID",
            category="process",
            supported_backends=[BackendType.TERMUX],
            parameters={
                "pid": {"type": "integer", "description": "Target PID", "required": True},
                "signal": {"type": "integer", "description": "Signal number (default: 15 SIGTERM)"},
            },
            handler=handle_process_signal,
        ))
        self.register(CapabilityDefinition(
            id="process.kill",
            name="Force Kill Process",
            description="Terminate a running process PID with SIGKILL",
            category="process",
            supported_backends=[BackendType.TERMUX],
            parameters={"pid": {"type": "integer", "description": "Target PID", "required": True}},
            handler=handle_process_kill,
        ))

        # 3. DEVICE
        self.register(CapabilityDefinition(
            id="device.info",
            name="Device & OS Telemetry",
            description="Get device model, manufacturer, Android OS version, SDK level, CPU cores, RAM, and SELinux",
            category="device",
            supported_backends=[BackendType.TERMUX, BackendType.ANDROID_SHELL],
            handler=handle_device_info,
        ))
        self.register(CapabilityDefinition(
            id="device.properties",
            name="Query Android Properties",
            description="Query Android system properties (getprop) by key or list all",
            category="device",
            supported_backends=[BackendType.ANDROID_SHELL, BackendType.TERMUX],
            parameters={"key": {"type": "string", "description": "Specific getprop key (e.g. ro.build.version.release)"}},
            handler=handle_device_properties,
        ))
        self.register(CapabilityDefinition(
            id="device.battery",
            name="Battery & Power Status",
            description="Query battery level, health, charging state, and temperature",
            category="battery",
            supported_backends=[BackendType.TERMUX_API, BackendType.ANDROID_SHELL],
            dependencies=["Termux:API APK or Shell"],
            handler=handle_device_battery,
        ))
        self.register(CapabilityDefinition(
            id="device.uptime",
            name="Device Uptime",
            description="Return device uptime in seconds and human-readable format",
            category="device",
            supported_backends=[BackendType.TERMUX],
            handler=handle_device_uptime,
        ))
        self.register(CapabilityDefinition(
            id="device.snapshot",
            name="Complete Device State Snapshot",
            category="device",
            description="Collect complete multi-domain state snapshot (hardware, OS, memory, storage roots, backends)",
            supported_backends=[BackendType.TERMUX],
            handler=handle_device_snapshot,
        ))

        # 4. FILESYSTEM
        self.register(CapabilityDefinition(
            id="filesystem.list",
            name="List Directory Entries",
            description="List entries inside directory with size, modified time, and mode",
            category="filesystem",
            supported_backends=[BackendType.TERMUX],
            parameters={
                "path": {"type": "string", "description": "Directory path", "default": "."},
                "limit": {"type": "integer", "description": "Maximum entries to return"},
            },
            handler=handle_fs_list,
        ))
        self.register(CapabilityDefinition(
            id="filesystem.stat",
            name="File / Directory Stat",
            description="Get detailed metadata, permissions, and file statistics",
            category="filesystem",
            supported_backends=[BackendType.TERMUX],
            parameters={"path": {"type": "string", "description": "Target path", "required": True}},
            handler=handle_fs_stat,
        ))
        self.register(CapabilityDefinition(
            id="filesystem.read",
            name="Read File Content",
            description="Read text or binary data from file with offset and limit protection",
            category="filesystem",
            supported_backends=[BackendType.TERMUX],
            parameters={
                "path": {"type": "string", "description": "Path to file", "required": True},
                "offset": {"type": "integer", "description": "Byte offset to start reading from"},
                "max_bytes": {"type": "integer", "description": "Maximum bytes to read (default: 512KB)"},
                "base64": {"type": "boolean", "description": "Return content encoded in base64"},
            },
            handler=handle_fs_read,
        ))
        self.register(CapabilityDefinition(
            id="filesystem.write",
            name="Write File Content",
            description="Write text or base64 data to target file path",
            category="filesystem",
            supported_backends=[BackendType.TERMUX],
            mutating=True,
            parameters={
                "path": {"type": "string", "description": "Target file path", "required": True},
                "content": {"type": "string", "description": "File content (text or base64)", "required": True},
                "base64": {"type": "boolean", "description": "Treat content as base64-encoded binary"},
            },
            handler=handle_fs_write,
        ))
        self.register(CapabilityDefinition(
            id="filesystem.append",
            name="Append to File",
            description="Append text content to existing or new file",
            category="filesystem",
            supported_backends=[BackendType.TERMUX],
            mutating=True,
            parameters={
                "path": {"type": "string", "description": "Target file path", "required": True},
                "content": {"type": "string", "description": "Content to append", "required": True},
            },
            handler=handle_fs_append,
        ))
        self.register(CapabilityDefinition(
            id="filesystem.copy",
            name="Copy File or Directory",
            description="Copy file or directory tree to destination",
            category="filesystem",
            supported_backends=[BackendType.TERMUX],
            mutating=True,
            parameters={
                "source": {"type": "string", "description": "Source path", "required": True},
                "destination": {"type": "string", "description": "Destination path", "required": True},
            },
            handler=handle_fs_copy,
        ))
        self.register(CapabilityDefinition(
            id="filesystem.move",
            name="Move / Rename Path",
            description="Move or rename file or directory",
            category="filesystem",
            supported_backends=[BackendType.TERMUX],
            mutating=True,
            parameters={
                "source": {"type": "string", "description": "Source path", "required": True},
                "destination": {"type": "string", "description": "Destination path", "required": True},
            },
            handler=handle_fs_move,
        ))
        self.register(CapabilityDefinition(
            id="filesystem.delete",
            name="Delete File or Directory",
            description="Delete file or directory (with recursive option)",
            category="filesystem",
            supported_backends=[BackendType.TERMUX],
            mutating=True,
            parameters={
                "path": {"type": "string", "description": "Target path to delete", "required": True},
                "recursive": {"type": "boolean", "description": "Recursively remove directories"},
            },
            handler=handle_fs_delete,
        ))
        self.register(CapabilityDefinition(
            id="filesystem.mkdir",
            name="Create Directory",
            description="Create directory including parent directories",
            category="filesystem",
            supported_backends=[BackendType.TERMUX],
            mutating=True,
            parameters={"path": {"type": "string", "description": "Directory path to create", "required": True}},
            handler=handle_fs_mkdir,
        ))
        self.register(CapabilityDefinition(
            id="filesystem.find",
            name="Find Files by Glob",
            description="Find files matching glob pattern recursively",
            category="filesystem",
            supported_backends=[BackendType.TERMUX],
            parameters={
                "path": {"type": "string", "description": "Search root path", "default": "."},
                "pattern": {"type": "string", "description": "Glob pattern (e.g. *.py, *.apk)", "default": "*"},
                "limit": {"type": "integer", "description": "Maximum matches to return"},
            },
            handler=handle_fs_find,
        ))
        self.register(CapabilityDefinition(
            id="filesystem.hash",
            name="Compute File Hash",
            description="Compute SHA-256, MD5, or SHA-1 cryptographic hash of a file",
            category="filesystem",
            supported_backends=[BackendType.TERMUX],
            parameters={
                "path": {"type": "string", "description": "Path to file", "required": True},
                "algorithm": {"type": "string", "description": "Hash algorithm (sha256, md5, sha1)", "default": "sha256"},
            },
            handler=handle_fs_hash,
        ))
        self.register(CapabilityDefinition(
            id="filesystem.zip",
            name="Create Zip Archive",
            description="Compress file or directory into a zip archive",
            category="filesystem",
            supported_backends=[BackendType.TERMUX],
            mutating=True,
            parameters={
                "source": {"type": "string", "description": "Source file or directory", "required": True},
                "archive_path": {"type": "string", "description": "Output zip archive path", "required": True},
            },
            handler=handle_fs_zip,
        ))
        self.register(CapabilityDefinition(
            id="filesystem.unzip",
            name="Extract Zip Archive",
            description="Extract zip archive to target directory",
            category="filesystem",
            supported_backends=[BackendType.TERMUX],
            mutating=True,
            parameters={
                "archive_path": {"type": "string", "description": "Zip archive path to extract", "required": True},
                "destination": {"type": "string", "description": "Target destination directory", "default": "."},
            },
            handler=handle_fs_unzip,
        ))

        # 5. STORAGE
        self.register(CapabilityDefinition(
            id="storage.overview",
            name="Storage Roots Overview",
            description="Inspect available storage roots, total/used/free space, and mount types",
            category="storage",
            supported_backends=[BackendType.TERMUX],
            handler=handle_storage_overview,
        ))
        self.register(CapabilityDefinition(
            id="storage.mounts",
            name="List Mounted Filesystems",
            description="Inspect all mounted filesystems from /proc/mounts",
            category="storage",
            supported_backends=[BackendType.TERMUX],
            handler=handle_storage_mounts,
        ))
        self.register(CapabilityDefinition(
            id="storage.large_files",
            name="Find Large Files",
            description="Discover files exceeding a specified size threshold (default: 50MB)",
            category="storage",
            supported_backends=[BackendType.TERMUX],
            parameters={
                "path": {"type": "string", "description": "Path to scan", "default": "/data/data/com.termux/files/home"},
                "threshold_mb": {"type": "number", "description": "Size threshold in MB", "default": 50.0},
                "limit": {"type": "integer", "description": "Max files to return", "default": 50},
            },
            handler=handle_storage_large_files,
        ))
        self.register(CapabilityDefinition(
            id="storage.duplicates",
            name="Detect Duplicate Files",
            description="Detect duplicate files by matching size and cryptographic hashes",
            category="storage",
            supported_backends=[BackendType.TERMUX],
            parameters={
                "path": {"type": "string", "description": "Path to scan", "default": "/data/data/com.termux/files/home"},
                "limit": {"type": "integer", "description": "Max duplicate groups to report", "default": 20},
            },
            handler=handle_storage_duplicates,
        ))
        self.register(CapabilityDefinition(
            id="storage.cleanup_candidates",
            name="Find Cleanup Candidates",
            description="Scan for cache directories, temporary files, and dangling artifacts",
            category="storage",
            supported_backends=[BackendType.TERMUX],
            parameters={"path": {"type": "string", "description": "Path to scan", "default": "/data/data/com.termux/files/home"}},
            handler=handle_storage_cleanup_candidates,
        ))

        # 6. PACKAGE & APPS
        self.register(CapabilityDefinition(
            id="package.list",
            name="List Installed Packages",
            description="List installed Android packages (third-party, system, or all)",
            category="package",
            supported_backends=[BackendType.ANDROID_SHELL, BackendType.SHIZUKU, BackendType.ROOT],
            parameters={
                "type": {"type": "string", "description": "Package filter: third_party, system, all", "default": "third_party"},
                "filter": {"type": "string", "description": "Optional substring filter"},
                "limit": {"type": "integer", "description": "Max packages to return"},
            },
            handler=handle_package_list,
        ))
        self.register(CapabilityDefinition(
            id="package.path",
            name="Get Package APK Path",
            description="Get APK file location for an installed package",
            category="package",
            supported_backends=[BackendType.ANDROID_SHELL, BackendType.SHIZUKU, BackendType.ROOT],
            parameters={"package": {"type": "string", "description": "Package name", "required": True}},
            handler=handle_package_path,
        ))
        self.register(CapabilityDefinition(
            id="package.info",
            name="Inspect Package Metadata",
            description="Inspect package APK size, DEX count, and manifest presence",
            category="package",
            supported_backends=[BackendType.ANDROID_SHELL, BackendType.TERMUX],
            parameters={"package": {"type": "string", "description": "Package name", "required": True}},
            handler=handle_package_info,
        ))
        self.register(CapabilityDefinition(
            id="package.install",
            name="Install APK Package",
            description="Install APK package (requires Shizuku or root)",
            category="package",
            supported_backends=[BackendType.SHIZUKU, BackendType.ROOT, BackendType.ADB],
            mutating=True,
            privilege_level="shell",
            dependencies=["Shizuku or Root"],
            setup_instructions="Start Shizuku via Wireless Debugging to enable rootless package installation.",
            parameters={"apk_path": {"type": "string", "description": "Path to APK file", "required": True}},
            handler=handle_package_install,
        ))
        self.register(CapabilityDefinition(
            id="package.uninstall",
            name="Uninstall Package",
            description="Uninstall package from device (requires Shizuku or root)",
            category="package",
            supported_backends=[BackendType.SHIZUKU, BackendType.ROOT, BackendType.ADB],
            mutating=True,
            privilege_level="shell",
            dependencies=["Shizuku or Root"],
            parameters={"package": {"type": "string", "description": "Package name to uninstall", "required": True}},
            handler=handle_package_uninstall,
        ))
        self.register(CapabilityDefinition(
            id="app.launch",
            name="Launch Application",
            description="Launch an Android application by package name",
            category="app",
            supported_backends=[BackendType.ANDROID_SHELL, BackendType.TERMUX],
            parameters={"package": {"type": "string", "description": "Package name to launch", "required": True}},
            handler=handle_app_launch,
        ))
        self.register(CapabilityDefinition(
            id="app.open_url",
            name="Open URL in Browser",
            description="Open URL or deep link in default browser / application",
            category="app",
            supported_backends=[BackendType.TERMUX],
            parameters={"url": {"type": "string", "description": "URL to open", "required": True}},
            handler=handle_app_open_url,
        ))

        # 7. NETWORK
        self.register(CapabilityDefinition(
            id="network.interfaces",
            name="List Network Interfaces",
            description="Inspect active network interfaces and IP addresses",
            category="network",
            supported_backends=[BackendType.TERMUX],
            handler=handle_network_interfaces,
        ))
        self.register(CapabilityDefinition(
            id="network.ping",
            name="Ping Host",
            description="Ping a remote IP or domain to test round-trip latency and packet loss",
            category="network",
            supported_backends=[BackendType.TERMUX],
            parameters={
                "host": {"type": "string", "description": "Host to ping", "default": "1.1.1.1"},
                "count": {"type": "integer", "description": "Number of packets", "default": 3},
            },
            handler=handle_network_ping,
        ))
        self.register(CapabilityDefinition(
            id="network.resolve",
            name="Resolve DNS Hostname",
            description="Perform DNS hostname resolution and return IP addresses",
            category="network",
            supported_backends=[BackendType.TERMUX],
            parameters={"host": {"type": "string", "description": "Domain name to resolve", "required": True}},
            handler=handle_network_resolve,
        ))
        self.register(CapabilityDefinition(
            id="network.http_request",
            name="HTTP Client Request",
            description="Execute structured HTTP request (GET, POST, PUT, DELETE) with headers and body",
            category="network",
            supported_backends=[BackendType.TERMUX],
            parameters={
                "url": {"type": "string", "description": "Target HTTP URL", "required": True},
                "method": {"type": "string", "description": "HTTP method (GET, POST, etc.)", "default": "GET"},
                "headers": {"type": "object", "description": "HTTP request headers"},
                "body": {"type": "string", "description": "Request body content"},
                "timeout": {"type": "number", "description": "Request timeout in seconds", "default": 15.0},
            },
            handler=handle_network_http_request,
        ))
        self.register(CapabilityDefinition(
            id="network.download",
            name="Download File",
            description="Download file from remote URL to local destination path",
            category="network",
            supported_backends=[BackendType.TERMUX],
            mutating=True,
            parameters={
                "url": {"type": "string", "description": "Remote file URL", "required": True},
                "destination": {"type": "string", "description": "Local destination path", "required": True},
            },
            handler=handle_network_download,
        ))
        self.register(CapabilityDefinition(
            id="network.diagnostics",
            name="Network Diagnostics",
            description="Run comprehensive network diagnostic check (interfaces, DNS, ping)",
            category="network",
            supported_backends=[BackendType.TERMUX],
            handler=handle_network_diagnostics,
        ))
        self.register(CapabilityDefinition(
            id="wifi.status",
            name="Wi-Fi Connection Info",
            description="Query Wi-Fi connection info and status",
            category="wifi",
            supported_backends=[BackendType.TERMUX_API, BackendType.ANDROID_BRIDGE],
            dependencies=["Termux:API APK or Android Bridge"],
            handler=handle_wifi_status,
        ))

        # 8. HARDWARE, SENSORS, SCREEN, INPUT
        self.register(CapabilityDefinition(
            id="screen.info",
            name="Screen Information",
            description="Query screen resolution, pixel density, and orientation",
            category="screen",
            supported_backends=[BackendType.ANDROID_SHELL, BackendType.ANDROID_BRIDGE],
            handler=handle_screen_info,
        ))
        self.register(CapabilityDefinition(
            id="screen.capture",
            name="Capture Screen",
            description="Capture screenshot of current display (requires MediaProjection or Root)",
            category="screen",
            supported_backends=[BackendType.MEDIA_PROJECTION, BackendType.ROOT, BackendType.ANDROID_BRIDGE],
            dependencies=["TACP Android Bridge (MediaProjection) or Root"],
            setup_instructions="Install TACP Android Bridge and grant Screen Capture permission.",
            handler=handle_screen_capture,
        ))
        self.register(CapabilityDefinition(
            id="input.tap",
            name="Inject Touch Tap",
            description="Simulate touch tap at (x, y) coordinates (requires Shizuku or Accessibility)",
            category="input",
            supported_backends=[BackendType.SHIZUKU, BackendType.ACCESSIBILITY, BackendType.ROOT],
            privilege_level="shell",
            dependencies=["Shizuku or Accessibility Service"],
            setup_instructions="Enable Shizuku or turn on TACP Accessibility Service in Android Settings.",
            parameters={
                "x": {"type": "integer", "description": "X coordinate", "required": True},
                "y": {"type": "integer", "description": "Y coordinate", "required": True},
            },
            handler=handle_input_tap,
        ))
        self.register(CapabilityDefinition(
            id="input.key",
            name="Inject Key Event",
            description="Inject Android hardware keyevent (e.g. KEYCODE_BACK, KEYCODE_HOME)",
            category="input",
            supported_backends=[BackendType.SHIZUKU, BackendType.ACCESSIBILITY, BackendType.ROOT],
            privilege_level="shell",
            dependencies=["Shizuku or Accessibility Service"],
            parameters={"key": {"type": "string", "description": "Android key name or code", "required": True}},
            handler=handle_input_key,
        ))
        self.register(CapabilityDefinition(
            id="input.capabilities",
            name="Input Injection Capabilities",
            description="Report which input simulation methods are currently usable",
            category="input",
            supported_backends=[BackendType.TERMUX],
            handler=handle_input_capabilities,
        ))
        self.register(CapabilityDefinition(
            id="camera.list",
            name="List Cameras",
            description="Discover available hardware cameras (front/back)",
            category="camera",
            supported_backends=[BackendType.TERMUX_API, BackendType.ANDROID_BRIDGE],
            dependencies=["com.termux.api APK or Android Bridge"],
            handler=handle_camera_list,
        ))
        self.register(CapabilityDefinition(
            id="camera.capture",
            name="Capture Photo",
            description="Capture photo from camera and save to file",
            category="camera",
            supported_backends=[BackendType.TERMUX_API, BackendType.ANDROID_BRIDGE],
            dependencies=["com.termux.api APK or Android Bridge"],
            handler=handle_camera_capture,
        ))
        self.register(CapabilityDefinition(
            id="microphone.record",
            name="Record Audio",
            description="Record audio snippet from microphone",
            category="microphone",
            supported_backends=[BackendType.TERMUX_API, BackendType.ANDROID_BRIDGE],
            dependencies=["com.termux.api APK or Android Bridge"],
            handler=handle_microphone_record,
        ))
        self.register(CapabilityDefinition(
            id="tts.speak",
            name="Text-to-Speech Speak",
            description="Synthesize speech audio from text input",
            category="audio",
            supported_backends=[BackendType.TERMUX_API, BackendType.ANDROID_BRIDGE],
            dependencies=["com.termux.api APK or Android Bridge"],
            parameters={"text": {"type": "string", "description": "Text to speak", "required": True}},
            handler=handle_tts_speak,
        ))
        self.register(CapabilityDefinition(
            id="location.get",
            name="Get GPS Location",
            description="Get current GPS latitude, longitude, and accuracy",
            category="location",
            supported_backends=[BackendType.TERMUX_API, BackendType.ANDROID_BRIDGE],
            dependencies=["com.termux.api APK or Android Bridge"],
            handler=handle_location_get,
        ))
        self.register(CapabilityDefinition(
            id="sensors.list",
            name="List Hardware Sensors",
            description="List available hardware sensors (accelerometer, gyroscope, light, proximity)",
            category="sensors",
            supported_backends=[BackendType.TERMUX_API, BackendType.ANDROID_BRIDGE],
            dependencies=["com.termux.api APK or Android Bridge"],
            handler=handle_sensors_list,
        ))
        self.register(CapabilityDefinition(
            id="clipboard.get",
            name="Read Clipboard",
            description="Read text from Android system clipboard",
            category="clipboard",
            supported_backends=[BackendType.TERMUX_API, BackendType.ANDROID_BRIDGE],
            dependencies=["com.termux.api APK or Android Bridge"],
            handler=handle_clipboard_get,
        ))
        self.register(CapabilityDefinition(
            id="clipboard.set",
            name="Write Clipboard",
            description="Set text onto Android system clipboard",
            category="clipboard",
            supported_backends=[BackendType.TERMUX_API, BackendType.ANDROID_BRIDGE],
            dependencies=["com.termux.api APK or Android Bridge"],
            parameters={"text": {"type": "string", "description": "Text to copy", "required": True}},
            handler=handle_clipboard_set,
        ))
        self.register(CapabilityDefinition(
            id="notifications.post",
            name="Post Status Bar Notification",
            description="Post an Android status bar notification",
            category="notifications",
            supported_backends=[BackendType.TERMUX_API, BackendType.ANDROID_BRIDGE],
            dependencies=["com.termux.api APK or Android Bridge"],
            parameters={
                "title": {"type": "string", "description": "Notification title", "default": "TACP"},
                "content": {"type": "string", "description": "Notification body content", "required": True},
            },
            handler=handle_notifications_post,
        ))
        self.register(CapabilityDefinition(
            id="settings.get",
            name="Read Android Setting",
            description="Read system, secure, or global Android setting value",
            category="settings",
            supported_backends=[BackendType.SHIZUKU, BackendType.ROOT, BackendType.ANDROID_SHELL],
            dependencies=["Shizuku or Root"],
            parameters={
                "key": {"type": "string", "description": "Setting key name", "required": True},
                "namespace": {"type": "string", "description": "Namespace: system, secure, global", "default": "system"},
            },
            handler=handle_settings_get,
        ))
        self.register(CapabilityDefinition(
            id="logs.system",
            name="Read System Logcat",
            description="Retrieve recent logcat entries from Android system log buffer",
            category="logs",
            supported_backends=[BackendType.ANDROID_SHELL, BackendType.SHIZUKU, BackendType.ROOT],
            parameters={
                "lines": {"type": "integer", "description": "Number of log lines to retrieve", "default": 50},
                "filter": {"type": "string", "description": "Optional logcat tag/filter spec"},
            },
            handler=handle_logs_system,
        ))

        # 9. AUTOMATION, TASKS, DIAGNOSTICS
        self.register(CapabilityDefinition(
            id="tasks.list",
            name="List Background Tasks",
            description="List running and completed background tasks",
            category="tasks",
            supported_backends=[BackendType.TERMUX],
            handler=handle_tasks_list,
        ))
        self.register(CapabilityDefinition(
            id="tasks.get",
            name="Get Task Details",
            description="Get status, progress, and output of a specific task ID",
            category="tasks",
            supported_backends=[BackendType.TERMUX],
            parameters={"task_id": {"type": "string", "description": "Task ID", "required": True}},
            handler=handle_tasks_get,
        ))
        self.register(CapabilityDefinition(
            id="tasks.cancel",
            name="Cancel Task",
            description="Cancel a running task",
            category="tasks",
            supported_backends=[BackendType.TERMUX],
            parameters={"task_id": {"type": "string", "description": "Task ID to cancel", "required": True}},
            handler=handle_tasks_cancel,
        ))
        self.register(CapabilityDefinition(
            id="automation.create",
            name="Create Workflow Automation",
            description="Define a reusable multi-step JSON capability workflow",
            category="automation",
            supported_backends=[BackendType.TERMUX],
            parameters={
                "name": {"type": "string", "description": "Automation workflow name", "required": True},
                "steps": {"type": "array", "description": "List of capability execution steps", "required": True},
                "description": {"type": "string", "description": "Optional workflow description"},
            },
            handler=handle_automation_create,
        ))
        self.register(CapabilityDefinition(
            id="automation.list",
            name="List Automations",
            description="List all registered workflow automations",
            category="automation",
            supported_backends=[BackendType.TERMUX],
            handler=handle_automation_list,
        ))
        self.register(CapabilityDefinition(
            id="automation.start",
            name="Start Automation",
            description="Execute a registered automation workflow",
            category="automation",
            supported_backends=[BackendType.TERMUX],
            parameters={"automation_id": {"type": "string", "description": "Automation ID", "required": True}},
            handler=handle_automation_start,
        ))
        self.register(CapabilityDefinition(
            id="diagnostics.bundle",
            name="Generate Diagnostic Bundle",
            description="Compile an archive (.zip) containing system telemetry, capability matrix, and logs",
            category="diagnostics",
            supported_backends=[BackendType.TERMUX],
            handler=handle_diagnostics_bundle,
        ))


default_registry = CapabilityRegistry()
