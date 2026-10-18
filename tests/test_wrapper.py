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


class SanitizePamEnvironmentTest(unittest.TestCase):
    def setUp(self):
        self.wrapper = load_wrapper()

    def test_noop_without_pam_type(self):
        environ = {"PATH": "/home/alice/bin:/usr/bin", "LD_PRELOAD": "/home/alice/evil.so"}
        before = dict(environ)
        self.wrapper.sanitize_pam_environment(environ)
        self.assertEqual(environ, before)

    def test_strips_everything_but_pam_vars_when_pam_type_set(self):
        environ = {
            "PAM_TYPE": "open_session", "PAM_SERVICE": "sshd", "PAM_USER": "alice",
            "PAM_RHOST": "203.0.113.7", "PAM_TTY": "ssh",
            "PATH": "/home/alice/bin:/usr/bin",
            "LD_PRELOAD": "/home/alice/evil.so",
            "OPENSSL_CONF": "/home/alice/openssl.cnf",
            "SSL_CERT_FILE": "/home/alice/fake-ca.pem",
            "https_proxy": "http://attacker.example:8080",
        }
        self.wrapper.sanitize_pam_environment(environ)
        self.assertEqual(environ, {
            "PAM_TYPE": "open_session", "PAM_SERVICE": "sshd", "PAM_USER": "alice",
            "PAM_RHOST": "203.0.113.7", "PAM_TTY": "ssh",
            "PATH": "/usr/sbin:/usr/bin:/sbin:/bin", "LANG": "C.UTF-8",
        })

    def test_main_skips_sanitizing_on_dry_run(self):
        with mock.patch.object(self.wrapper, "sanitize_pam_environment") as sanitize, \
                mock.patch.object(self.wrapper, "choose_lib", return_value=REPO + "/src"), \
                mock.patch("hostwatch.cli.main", return_value=0):
            code = self.wrapper.main(["hostwatch", "login", "--dry-run"], {"PAM_TYPE": "open_session"})
        self.assertEqual(code, 0)
        sanitize.assert_not_called()

    def test_main_sanitizes_outside_dry_run(self):
        environ = {"PAM_TYPE": "open_session", "PATH": "/home/alice/bin",
                   "LD_PRELOAD": "/home/alice/evil.so"}
        with mock.patch.object(self.wrapper, "choose_lib", return_value=REPO + "/src"), \
                mock.patch("hostwatch.cli.main", return_value=0):
            code = self.wrapper.main(["hostwatch", "login"], environ)
        self.assertEqual(code, 0)
        self.assertEqual(environ["PATH"], "/usr/sbin:/usr/bin:/sbin:/bin")
        self.assertNotIn("LD_PRELOAD", environ)


if __name__ == "__main__":
    unittest.main()
