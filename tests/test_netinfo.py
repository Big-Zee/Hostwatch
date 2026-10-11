import json
import subprocess
import unittest
from types import SimpleNamespace
from unittest import mock

from hostwatch import config, netinfo


def iface(name, state, addrs, flags=("BROADCAST", "MULTICAST", "UP", "LOWER_UP")):
    return {"ifname": name, "operstate": state, "flags": list(flags), "addr_info": addrs}


def v4(addr):
    return {"family": "inet", "local": addr, "scope": "global"}


def v6(addr, scope="global"):
    return {"family": "inet6", "local": addr, "scope": scope}


IP_JSON = [
    iface("lo", "UNKNOWN", [v4("127.0.0.1"), v6("::1", "host")], flags=("LOOPBACK", "UP")),
    iface("enp3s0", "UP", [v4("192.168.1.20"), v6("2001:db8::20"), v6("fe80::1", "link")]),
    iface("wlp2s0", "DOWN", [], flags=("BROADCAST", "MULTICAST")),
    iface("docker0", "UP", [v4("172.17.0.1")]),
    iface("veth1a2b", "UP", [v6("fe80::2", "link")]),
    iface("virbr0", "DOWN", [v4("192.168.122.1")]),
    iface("tailscale0", "UNKNOWN", [v4("100.64.0.5")], flags=("POINTOPOINT", "UP")),
    iface("wwan0", "UNKNOWN", [v4("10.20.30.40")], flags=("POINTOPOINT", "UP", "LOWER_UP")),
]


class ParseTest(unittest.TestCase):
    def test_default_filter(self):
        self.assertEqual(
            netinfo.parse_ip_json(IP_JSON, config.DEFAULT_SKIP_INTERFACES),
            [("enp3s0", "192.168.1.20"), ("wwan0", "10.20.30.40")],
        )

    def test_ipv6_global_only_when_enabled(self):
        result = netinfo.parse_ip_json(IP_JSON, config.DEFAULT_SKIP_INTERFACES, include_ipv6=True)
        self.assertIn(("enp3s0", "2001:db8::20"), result)
        self.assertNotIn(("enp3s0", "fe80::1"), result)

    def test_loopback_address_on_regular_interface(self):
        data = [iface("enp0s8", "UP", [v4("127.0.1.1"), v4("192.168.56.10"),
                                       v6("::1", "global")])]
        self.assertEqual(netinfo.parse_ip_json(data, (), include_ipv6=True),
                         [("enp0s8", "192.168.56.10")])

    def test_docker_scenario(self):
        data = [IP_JSON[0], IP_JSON[1], IP_JSON[3], IP_JSON[4]]
        self.assertEqual(netinfo.parse_ip_json(data, config.DEFAULT_SKIP_INTERFACES),
                         [("enp3s0", "192.168.1.20")])

    def test_custom_prefixes(self):
        result = netinfo.parse_ip_json(IP_JSON, ("enp",))
        self.assertIn(("docker0", "172.17.0.1"), result)
        self.assertNotIn(("enp3s0", "192.168.1.20"), result)

    def test_nothing_usable(self):
        self.assertEqual(netinfo.parse_ip_json([IP_JSON[0]], ()), [])


class LocalAddressesTest(unittest.TestCase):
    def test_runs_ip_json(self):
        run = mock.Mock(return_value=SimpleNamespace(stdout=json.dumps(IP_JSON)))
        result = netinfo.local_addresses(config.DEFAULT_SKIP_INTERFACES, run=run)
        self.assertEqual(run.call_args.args[0], ["ip", "-j", "addr", "show"])
        self.assertEqual(result[0], ("enp3s0", "192.168.1.20"))

    def test_undecodable_output_is_replaced(self):
        run = mock.Mock(return_value=SimpleNamespace(stdout="[]"))
        netinfo.local_addresses((), run=run)
        self.assertEqual(run.call_args.kwargs["errors"], "replace")

    @mock.patch.object(netinfo.log, "warning")
    def test_command_failure_gives_empty_list(self, _warning):
        run = mock.Mock(side_effect=subprocess.CalledProcessError(1, "ip"))
        self.assertEqual(netinfo.local_addresses((), run=run), [])
        run = mock.Mock(side_effect=FileNotFoundError("ip"))
        self.assertEqual(netinfo.local_addresses((), run=run), [])


def systemctl_out(stdout):
    return mock.Mock(return_value=SimpleNamespace(stdout=stdout))


class ShutdownDetectionTest(unittest.TestCase):
    def test_reboot_job(self):
        run = systemctl_out("1 reboot.target start waiting\n7 systemd-reboot.service start waiting\n")
        self.assertEqual(netinfo.shutdown_kind(run=run), "Rebooting")
        self.assertEqual(run.call_args.args[0], ["systemctl", "list-jobs", "--no-legend", "--plain"])
        self.assertEqual(run.call_args.kwargs["timeout"], 2)

    def test_kexec_and_soft_reboot_count_as_reboot(self):
        for target in ("kexec.target", "soft-reboot.target"):
            run = systemctl_out(f"3 {target} start waiting\n")
            self.assertEqual(netinfo.shutdown_kind(run=run), "Rebooting")

    def test_poweroff_and_halt(self):
        for target in ("poweroff.target", "halt.target"):
            run = systemctl_out(f"1 {target} start waiting\n")
            self.assertEqual(netinfo.shutdown_kind(run=run), "Shutting down")

    def test_unknown_falls_back(self):
        self.assertEqual(netinfo.shutdown_kind(run=systemctl_out("")), "Shutting down")
        failing = mock.Mock(side_effect=subprocess.TimeoutExpired("systemctl", 2))
        self.assertEqual(netinfo.shutdown_kind(run=failing), "Shutting down")
        missing = mock.Mock(side_effect=FileNotFoundError("systemctl"))
        self.assertEqual(netinfo.shutdown_kind(run=missing), "Shutting down")

    def test_systemctl_output_decoded_with_replacement(self):
        for call in (netinfo.system_stopping, netinfo.shutdown_kind):
            run = systemctl_out("")
            call(run=run)
            self.assertEqual(run.call_args.kwargs["errors"], "replace", call.__name__)

    def test_system_stopping(self):
        self.assertTrue(netinfo.system_stopping(run=systemctl_out("stopping\n")))
        for state in ("running\n", "degraded\n", "starting\n", ""):
            self.assertFalse(netinfo.system_stopping(run=systemctl_out(state)), state)
        failing = mock.Mock(side_effect=subprocess.TimeoutExpired("systemctl", 2))
        self.assertFalse(netinfo.system_stopping(run=failing))


if __name__ == "__main__":
    unittest.main()
