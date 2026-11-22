"""Тесты выбора системного CA-бандла при импорте пакета."""

import os
import unittest
from unittest import mock

import rb_tui


class CaBundleTest(unittest.TestCase):
    def setUp(self):
        self.env = mock.patch.dict(os.environ, {}, clear=False)
        self.env.start()
        self.addCleanup(self.env.stop)
        os.environ.pop("SSL_CERT_FILE", None)

    def _paths(self, cafile):
        return mock.Mock(cafile=cafile, capath=None, openssl_cafile_env=None,
                         openssl_cafile=None, openssl_capath_env=None,
                         openssl_capath=None)

    def test_keeps_explicit_override(self):
        os.environ["SSL_CERT_FILE"] = "/custom/ca.pem"
        with mock.patch("ssl.get_default_verify_paths") as paths:
            rb_tui._ensure_ca_bundle()
        paths.assert_not_called()
        self.assertEqual(os.environ["SSL_CERT_FILE"], "/custom/ca.pem")

    def test_keeps_working_default(self):
        with mock.patch("ssl.get_default_verify_paths",
                        return_value=self._paths("/etc/ssl/cert.pem")), \
                mock.patch.object(rb_tui.os.path, "isfile", return_value=True):
            rb_tui._ensure_ca_bundle()
        self.assertNotIn("SSL_CERT_FILE", os.environ)

    def test_falls_back_to_existing_system_bundle(self):
        with mock.patch("ssl.get_default_verify_paths",
                        return_value=self._paths("/usr/lib/ssl/cert.pem")), \
                mock.patch.object(
                    rb_tui.os.path, "isfile",
                    side_effect=lambda p: p == "/etc/pki/tls/certs/ca-bundle.crt"):
            rb_tui._ensure_ca_bundle()
        self.assertEqual(os.environ["SSL_CERT_FILE"],
                         "/etc/pki/tls/certs/ca-bundle.crt")

    def test_leaves_env_alone_when_nothing_found(self):
        with mock.patch("ssl.get_default_verify_paths",
                        return_value=self._paths("/missing")), \
                mock.patch.object(rb_tui.os.path, "isfile", return_value=False):
            rb_tui._ensure_ca_bundle()
        self.assertNotIn("SSL_CERT_FILE", os.environ)


if __name__ == "__main__":
    unittest.main()