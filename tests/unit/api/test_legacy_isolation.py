import importlib
import sys


def test_app_import_does_not_import_legacy_modules() -> None:
    for module_name in list(sys.modules):
        if module_name.startswith("app.legacy"):
            sys.modules.pop(module_name)

    importlib.import_module("app.main")

    assert all(not module_name.startswith("app.legacy") for module_name in sys.modules)

