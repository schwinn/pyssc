import unittest
import importlib
from unittest.mock import Mock, patch

from pyssc import scan as scan_devices

scan_module = importlib.import_module("pyssc.scan")


class DiscoveryTests(unittest.TestCase):
    @patch.object(scan_module, "time")
    @patch.object(scan_module, "ServiceBrowser")
    @patch.object(scan_module, "Zeroconf")
    def test_subscribes_directly_to_ssc_service(self, zeroconf_cls, browser_cls, time_module):
        zeroconf = zeroconf_cls.return_value
        result = scan_devices(scan_time_seconds=0)

        zeroconf_cls.assert_called_once()
        browser_cls.assert_called_once()
        self.assertEqual(browser_cls.call_args.args[1], "_ssc._tcp.local.")
        self.assertEqual(result.ssc_devices, [])
        zeroconf.close.assert_called_once_with()
        time_module.sleep.assert_called_once_with(0)

    @patch.object(scan_module, "time")
    @patch.object(scan_module, "ServiceBrowser")
    @patch.object(scan_module, "Zeroconf")
    def test_each_scan_starts_with_empty_inventory(self, zeroconf_cls, browser_cls, time_module):
        first = scan_devices(scan_time_seconds=0)
        first.ssc_devices.append(Mock())
        second = scan_devices(scan_time_seconds=0)

        self.assertEqual(len(second.ssc_devices), 0)
        self.assertEqual(browser_cls.call_count, 2)


if __name__ == "__main__":
    unittest.main()
