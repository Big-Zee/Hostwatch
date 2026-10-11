import unittest

from hostwatch import messages
from hostwatch.sessions import Session

IPS = [("enp3s0", "192.168.1.20")]
USERS = [Session("alice", "desktop", None, 1), Session("alice", "ssh", "203.0.113.7", 1)]
T = "2026-10-11 12:01:33 CEST"


def fields(payload):
    section = next(b for b in payload["blocks"] if "fields" in b)
    return {f["text"].split("\n", 1)[0].strip("*"): f["text"].split("\n", 1)[1]
            for f in section["fields"]}


def header(payload):
    return payload["blocks"][0]["text"]["text"]


class MachineLabelTest(unittest.TestCase):
    def test_label(self):
        self.assertEqual(messages.machine_label("office-pc"), "office-pc")
        self.assertEqual(messages.machine_label("office-pc", ""), "office-pc")
        self.assertEqual(messages.machine_label("office-pc", "  "), "office-pc")
        self.assertEqual(messages.machine_label("office-pc", "Office PC"), "Office PC (office-pc)")
        self.assertEqual(messages.machine_label("office-pc", "office-pc"), "office-pc")


class SharedFormatTest(unittest.TestCase):
    def all_types(self, machine="office-pc", users=USERS):
        return {
            "boot": messages.boot_message(machine, T, T, IPS, users),
            "shutdown": messages.shutdown_message(machine, "Rebooting", T, IPS, users, "up 5 h 12 min"),
            "login": messages.login_message(machine, "alice", "SSH", T, IPS, users,
                                            rhost="203.0.113.7"),
            "test": messages.test_message(machine, T, IPS, users),
        }

    def test_headers(self):
        p = self.all_types()
        self.assertEqual(header(p["boot"]), ":desktop_computer: office-pc · Boot")
        self.assertEqual(header(p["shutdown"]), ":desktop_computer: office-pc · Rebooting")
        self.assertEqual(header(p["login"]), ":desktop_computer: office-pc · Login: alice")
        self.assertEqual(header(p["test"]), ":desktop_computer: office-pc · Test")

    def test_header_with_machine_name(self):
        p = self.all_types(machine=messages.machine_label("office-pc", "Office PC"))
        self.assertEqual(header(p["shutdown"]),
                         ":desktop_computer: Office PC (office-pc) · Rebooting")

    def test_fallbacks_start_with_machine(self):
        p = self.all_types(machine="office-pc")
        self.assertEqual(p["boot"]["text"], f"office-pc · Booted at {T}")
        self.assertEqual(p["shutdown"]["text"], f"office-pc · Rebooting at {T} (up 5 h 12 min)")
        self.assertEqual(p["login"]["text"],
                         f"office-pc · alice logged in via SSH from 203.0.113.7 at {T}")
        self.assertEqual(p["test"]["text"], f"office-pc · Test message at {T}")
        for payload in self.all_types(machine="Office PC (home-pc)").values():
            self.assertTrue(payload["text"].startswith("Office PC (home-pc) · "))

    def test_every_type_ends_with_local_ip_and_users(self):
        for name, payload in self.all_types().items():
            labels = list(fields(payload))
            self.assertEqual(labels[-2:], ["Local IP", "Users"], name)
            self.assertNotIn("Host", labels, name)
            self.assertNotIn("Event", labels, name)
            self.assertEqual(fields(payload)["Local IP"], "enp3s0: 192.168.1.20", name)
            self.assertEqual(payload["blocks"][-1]["elements"][0]["text"], "HostWatch", name)

    def test_users_rendering(self):
        users = USERS + [Session("bob", "ssh", "203.0.113.9", 2), Session("carol", "tty", None, 1)]
        f = fields(messages.test_message("office-pc", T, IPS, users))
        self.assertEqual(f["Users"], "alice · desktop\nalice · ssh from 203.0.113.7\n"
                                     "bob · ssh from 203.0.113.9 (2 sessions)\ncarol · tty")

    def test_no_users_and_no_ips(self):
        f = fields(messages.boot_message("office-pc", T, None, [], []))
        self.assertEqual(f["Users"], "_No users logged in_")
        self.assertEqual(f["Local IP"], "_no local IP_")
        self.assertEqual(f["Kernel boot"], "_unknown_")

    def test_fallback_escaped_header_literal(self):
        machine = messages.machine_label("host", "Lab <A&B>")
        p = messages.boot_message(machine, T, T, IPS, USERS)
        self.assertEqual(p["text"], f"Lab &lt;A&amp;B&gt; (host) · Booted at {T}")
        self.assertEqual(header(p), ":desktop_computer: Lab <A&B> (host) · Boot")
        login = messages.login_message("host", "<!here>", "SSH", T, IPS, [], rhost="203.0.113.7")
        self.assertNotIn("<", login["text"])

    def test_escaping_and_header_limit(self):
        users = [Session("<b>&", "tty", None, 1)]
        payload = messages.login_message("h" * 200, "<b>&", "TTY", "t", IPS, users, tty="tty3")
        self.assertEqual(fields(payload)["User"], "&lt;b&gt;&amp;")
        self.assertTrue(fields(payload)["Users"].startswith("&lt;b&gt;&amp;"))
        self.assertLessEqual(len(header(payload)), 150)


class EventFieldsTest(unittest.TestCase):
    def test_boot_fields_and_warning(self):
        plain = messages.boot_message("my-pc", T, "2026-10-11 12:00:58 CEST", IPS, [])
        self.assertEqual(list(fields(plain)), ["Time", "Kernel boot", "Local IP", "Users"])
        self.assertEqual([b["type"] for b in plain["blocks"]], ["header", "section", "context"])
        warned = messages.boot_message("my-pc", T, None, IPS, [], unclean_previous=True)
        self.assertEqual(warned["blocks"][1]["text"]["text"],
                         ":warning: Previous shutdown was not clean (power loss or crash?)")
        self.assertEqual(warned["text"],
                         f"my-pc · Booted at {T} – previous shutdown was not clean")

    def test_shutdown_fields(self):
        p = messages.shutdown_message("my-pc", "Shutting down", T, IPS, USERS, "up 5 h 12 min")
        self.assertEqual(list(fields(p)), ["Time", "Uptime", "Local IP", "Users"])
        self.assertEqual(fields(p)["Uptime"], "up 5 h 12 min")
        unknown = messages.shutdown_message("my-pc", "Shutting down", T, [], [], None)
        self.assertEqual(fields(unknown)["Uptime"], "_unknown_")
        self.assertEqual(unknown["text"], f"my-pc · Shutting down at {T}")

    def test_login_fields(self):
        ssh = messages.login_message("my-pc", "alice", "SSH", T, IPS, USERS, tty="ssh",
                                     rhost="203.0.113.7")
        self.assertEqual(list(fields(ssh)), ["User", "Type", "Time", "Remote IP", "Local IP", "Users"])
        tty = messages.login_message("my-pc", "bob", "TTY", T, IPS, [], tty="/dev/tty3")
        self.assertEqual(fields(tty)["Terminal"], "/dev/tty3")
        self.assertEqual(tty["text"], f"my-pc · bob logged in via TTY at {T}")
        gui = messages.login_message("my-pc", "carol", "Graphical", T, IPS, [], tty=":0")
        self.assertEqual(list(fields(gui)), ["User", "Type", "Time", "Local IP", "Users"])



class HeartbeatMessageTest(unittest.TestCase):
    TABLE = "```\n    PID USER      CPU%  MEM%  NAME\n   2412 alice     98.0   3.1  firefox\n```"

    def build(self, **kw):
        args = dict(machine="office-pc", uptime_str="up 3 h 0 min",
                    since_str="2026-10-11 09:14 CEST", local_ips=IPS, users=USERS,
                    top_table=self.TABLE)
        args.update(kw)
        return messages.heartbeat_message(**args)

    def test_header_fallback_and_fields(self):
        p = self.build()
        self.assertEqual(header(p), ":desktop_computer: office-pc · Heartbeat")
        self.assertEqual(p["text"],
                         "office-pc · Alive, up 3 h 0 min (since 2026-10-11 09:14 CEST)")
        self.assertEqual(list(fields(p)), ["Uptime", "Since", "Local IP", "Users"])
        self.assertEqual(fields(p)["Since"], "2026-10-11 09:14 CEST")

    def test_process_section_after_fields_before_footer(self):
        p = self.build()
        types = [b["type"] for b in p["blocks"]]
        self.assertEqual(types, ["header", "section", "section", "context"])
        self.assertIn("fields", p["blocks"][1])
        section = p["blocks"][2]["text"]["text"]
        self.assertTrue(section.startswith("*Top processes"))
        self.assertTrue(section.endswith(self.TABLE))  # code block intact, not escaped

    def test_unknown_uptime(self):
        p = self.build(uptime_str=None, since_str=None)
        self.assertEqual(fields(p)["Uptime"], "_unknown_")
        self.assertEqual(p["text"], "office-pc · Alive")

    def test_other_types_have_no_extra_section(self):
        p = messages.test_message("office-pc", T, IPS, USERS)
        self.assertEqual([b["type"] for b in p["blocks"]], ["header", "section", "context"])


if __name__ == "__main__":
    unittest.main()
