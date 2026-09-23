"""
Service package for system integration and startup daemon.
"""

from .shutdown import SystemShutdownManager
from .systemd import (
    SERVICE_UNIT_NAME,
    SingleInstanceLock,
    cancel_systemd_config,
    configure_kde_session_exclusion,
    disable_user_service,
    enable_user_service,
    generate_service_content,
    get_default_service_dir,
    get_service_status,
    install_user_service,
    is_service_installed,
    kill_rogue_processes,
    stop_user_service,
    uninstall_user_service,
)

__all__ = [
    "SERVICE_UNIT_NAME",
    "SingleInstanceLock",
    "SystemShutdownManager",
    "cancel_systemd_config",
    "configure_kde_session_exclusion",
    "generate_service_content",
    "install_user_service",
    "uninstall_user_service",
    "is_service_installed",
    "enable_user_service",
    "disable_user_service",
    "get_service_status",
    "get_default_service_dir",
    "kill_rogue_processes",
    "stop_user_service",
]
