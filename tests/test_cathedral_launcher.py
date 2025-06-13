from sentientos.privilege import require_admin_banner, require_lumos_approval
require_admin_banner()
require_lumos_approval()

import importlib
import sys

import cathedral_launcher as cl


def test_placeholder(monkeypatch):
    # Simulate torch with GPU
    class Torch:
        class cuda:
            @staticmethod
            def is_available() -> bool:
                return True
    monkeypatch.setitem(sys.modules, 'torch', Torch)
    importlib.reload(cl)
    assert cl.check_gpu()

    # Simulate torch without GPU
    class TorchNo:
        class cuda:
            @staticmethod
            def is_available() -> bool:
                return False
    monkeypatch.setitem(sys.modules, 'torch', TorchNo)
    importlib.reload(cl)
    assert not cl.check_gpu()
