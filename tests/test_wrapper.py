import os
import shutil
import tempfile
import types
import unittest
from unittest import mock

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def load_wrapper():
    """Load bin/hostwatch as a module without running its main code or writing bytecode."""
    path = os.path.join(REPO, "bin", "hostwatch")
    module = types.ModuleType("hostwatch_wrapper")
    module.__file__ = path
    with open(path, encoding="utf-8") as fh:
        exec(compile(fh.read(), path, "exec"), module.__dict__)  # nosec B102 - repo file
    return module


class ChooseLibTest(unittest.TestCase):
    def setUp(self):
        self.wrapper = load_wrapper()
        self.root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.root, True)

    def make_package(self, *parts):
        pkg = os.path.join(self.root, *parts, "src", "hostwatch")
        os.makedirs(pkg)
        open(os.path.join(pkg, "cli.py"), "w").close()

    def test_installed_copy_ignores_usr_local_src(self):
        # A clone at /usr/local/src/hostwatch sits exactly where the installed
        # command's "checkout" would be.
        self.make_package("usr", "local")
        installed = os.path.join(self.root, "usr", "local", "bin", "hostwatch")
        with mock.patch.object(self.wrapper, "INSTALLED_BIN", installed):
            self.assertEqual(self.wrapper.choose_lib(installed), self.wrapper.INSTALLED_LIB)

    def test_checkout_uses_its_src(self):
        self.make_package("checkout")
        real = os.path.join(self.root, "checkout", "bin", "hostwatch")
        self.assertEqual(self.wrapper.choose_lib(real),
                         os.path.join(self.root, "checkout", "src"))

    def test_copy_without_package_uses_installed_lib(self):
        os.makedirs(os.path.join(self.root, "elsewhere", "src", "hostwatch"))  # no cli.py
        real = os.path.join(self.root, "elsewhere", "bin", "hostwatch")
        self.assertEqual(self.wrapper.choose_lib(real), self.wrapper.INSTALLED_LIB)

    def test_constants(self):
        self.assertEqual(self.wrapper.INSTALLED_BIN, "/usr/local/bin/hostwatch")
        self.assertEqual(self.wrapper.INSTALLED_LIB, "/usr/local/lib/hostwatch")


if __name__ == "__main__":
    unittest.main()
