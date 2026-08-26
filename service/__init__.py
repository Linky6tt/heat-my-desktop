"""
Service package for system integration and startup daemon.
"""

from .systemd import (
    SERVICE_UNIT_NAME,
    disable_user_service,
    enable_user_service,
    generate_service_content,
    get_default_service_dir,
    get_service_status,
    install_user_service,
    is_service_installed,
    uninstall_user_service,
)

__all__ = [
    "SERVICE_UNIT_NAME",
    "generate_service_content",
    "install_user_service",
    "uninstall_user_service",
    "is_service_installed",
    "enable_user_service",
    "disable_user_service",
    "get_service_status",
    "get_default_service_dir",
]
