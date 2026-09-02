import os
import sys

from src.gui.main_window import MainWindow
from src.utils.helpers import get_resource_path


def _self_test():
    """Validate that the frozen app can import and locate its React UI."""
    ui_path = get_resource_path(os.path.join('src', 'gui', 'ui', 'react', 'index.html'))
    if not os.path.isfile(ui_path):
        raise SystemExit(f'Missing packaged interface: {ui_path}')
    return 0


if __name__ == '__main__':
    if '--self-test' in sys.argv:
        raise SystemExit(_self_test())
    MainWindow().run()
