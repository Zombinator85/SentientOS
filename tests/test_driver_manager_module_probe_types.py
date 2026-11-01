from __future__ import annotations

import pytest

from sentientos.daemons.driver_manager import DriverManager

pytestmark = pytest.mark.no_legacy_skip


def test_default_probe_combines_current_driver_and_kernel_modules() -> None:
    def command_runner(args: tuple[str, ...] | list[str]) -> str:
        if args[0] == "lspci":
            return (
                "01:00.0 VGA compatible controller [0300]: NVIDIA Corporation Test GPU\n"
                "\tKernel driver in use: nouveau\n"
                "\tKernel modules: nouveau, nvidia\n"
            )
        if args[0] == "lsmod":
            return "nvidia 1 0\n"
        return ""

    manager = DriverManager(
        command_runner=command_runner,
        subscribe_to_pulse=False,
        autoprobe=False,
    )
    report = manager._default_hardware_probe()[0]

    assert report.current_driver == "nouveau"
    assert report.modules == ("nouveau", "nvidia")
