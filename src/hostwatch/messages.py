"""Slack Block Kit payload builders. Pure functions: data in, dict out.

Every message goes through ``build()`` so all types share one format:
header ":desktop_computer: <machine> · <event>", an optional notice line, the
event's own fields followed by Local IP and Users, and the HostWatch footer.
The plain-text fallback (push notifications) starts with the machine label.
"""

FOOTER = "HostWatch"
HEADER_LIMIT = 150  # Slack's maximum for header text
SEPARATOR = " · "  # " · "
UNCLEAN_WARNING = "Previous shutdown was not clean (power loss or crash?)"


def _escape(text):
    return str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def machine_label(hostname, machine_name=""):
    """``Office PC (office-pc)`` when a distinct friendly name is set, else the hostname."""
    name = (machine_name or "").strip()
    if not name or name == hostname:
        return hostname
    return f"{name} ({hostname})"


def _local_ips(local_ips):
    """``local_ips`` is a list of (interface, address), shown one per line."""
    if not local_ips:
        return "_no local IP_"
    return "\n".join(f"{_escape(iface)}: {_escape(addr)}" for iface, addr in local_ips)


def _users(users):
    """``users`` is a list of sessions.Session (user, kind, remote, count)."""
    if not users:
        return "_No users logged in_"
    lines = []
    for user, kind, remote, count in users:
        line = f"{_escape(user)}{SEPARATOR}{kind}"
        if remote:
            line += f" from {_escape(remote)}"
        if count > 1:
            line += f" ({count} sessions)"
        lines.append(line)
    return "\n".join(lines)


def build(machine, event, fields, summary, local_ips, users, notice=None, sections=None):
    """The one shared message format.

    ``machine`` is the label from machine_label(); ``fields`` are the event's
    own (label, mrkdwn value) pairs; ``summary`` is the plain-text event line
    that follows the machine label in the fallback; ``sections`` are optional
    (title, mrkdwn) full-width blocks placed after the fields.
    """
    all_fields = list(fields) + [("Local IP", _local_ips(local_ips)), ("Users", _users(users))]
    blocks = [{
        "type": "header",
        "text": {
            "type": "plain_text",
            "text": f":desktop_computer: {machine}{SEPARATOR}{event}"[:HEADER_LIMIT],
            "emoji": True,
        },
    }]
    if notice:
        blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": notice}})
    blocks += [
        {
            "type": "section",
            "fields": [
                {"type": "mrkdwn", "text": f"*{label}*\n{value}"} for label, value in all_fields
            ],
        },
    ]
    for title, text in sections or ():
        blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": f"*{title}*\n{text}"}})
    blocks.append({"type": "context", "elements": [{"type": "mrkdwn", "text": FOOTER}]})
    return {"text": f"{machine}{SEPARATOR}{summary}", "blocks": blocks}


def boot_message(machine, time_str, boot_time_str, local_ips, users, unclean_previous=False):
    fields = [
        ("Time", _escape(time_str)),
        ("Kernel boot", _escape(boot_time_str) if boot_time_str else "_unknown_"),
    ]
    summary = f"Booted at {time_str}"
    notice = None
    if unclean_previous:
        notice = f":warning: {UNCLEAN_WARNING}"
        summary += " – previous shutdown was not clean"
    return build(machine, "Boot", fields, summary, local_ips, users, notice)


def shutdown_message(machine, event, time_str, local_ips, users, uptime_str):
    """``event`` is "Shutting down" or "Rebooting"."""
    fields = [
        ("Time", _escape(time_str)),
        ("Uptime", _escape(uptime_str) if uptime_str else "_unknown_"),
    ]
    summary = f"{event} at {time_str}"
    if uptime_str:
        summary += f" ({uptime_str})"
    return build(machine, event, fields, summary, local_ips, users)


def login_message(machine, user, login_type, time_str, local_ips, users, tty=None, rhost=None):
    fields = [
        ("User", _escape(user)),
        ("Type", _escape(login_type)),
        ("Time", _escape(time_str)),
    ]
    summary = f"{user} logged in via {login_type}"
    if login_type == "SSH":
        fields.append(("Remote IP", _escape(rhost) if rhost else "_unknown_"))
        if rhost:
            summary += f" from {rhost}"
    elif login_type == "TTY":
        fields.append(("Terminal", _escape(tty) if tty else "_unknown_"))
    summary += f" at {time_str}"
    return build(machine, f"Login: {user}", fields, summary, local_ips, users)


def heartbeat_message(machine, uptime_str, since_str, local_ips, users, top_table):
    """``top_table`` is the code block from processes.format_table()."""
    fields = [
        ("Uptime", _escape(uptime_str) if uptime_str else "_unknown_"),
        ("Since", _escape(since_str) if since_str else "_unknown_"),
    ]
    summary = "Alive"
    if uptime_str:
        summary += f", {uptime_str}"
    if since_str:
        summary += f" (since {since_str})"
    return build(machine, "Heartbeat", fields, summary, local_ips, users,
                 sections=[("Top processes (CPU over 1 s, % of one core)", top_table)])


def test_message(machine, time_str, local_ips, users):
    return build(machine, "Test", [("Time", _escape(time_str))],
                 f"Test message at {time_str}", local_ips, users)
