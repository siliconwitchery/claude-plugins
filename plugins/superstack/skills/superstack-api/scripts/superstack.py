#!/usr/bin/env python3
"""Zero-dependency CLI for the Superstack REST API.

Authentication:
    export SUPERSTACK_API_KEY="<your api key>"       # required (see --no-key)
    export SUPERSTACK_DEPLOYMENT="<deployment id>"   # or pass --deployment

Usage examples:
    superstack.py devices
    superstack.py devices --json
    superstack.py data --since 7d --devices Tomatoes --devices Kale
    superstack.py data --since 24h --until 1h --follow-pagination --json
    superstack.py logs --groups greenhouse --since 90m
    superstack.py telemetry --device 1 --days 7
    superstack.py code-get --device 1 --out main.lua
    superstack.py code-push --file main.lua --device 1
    superstack.py code-push --file main.lua --groups greenhouse --yes
    superstack.py code-start --device 1
    superstack.py code-stop --device 1
    superstack.py agent-chat --agent 1 --message "Average greenhouse temperature?"

Notes:
    - API keys are read ONLY from the SUPERSTACK_API_KEY environment
      variable, never from arguments.
    - Demo deployments allow read-only access without a key: pass --no-key.
    - --since / --until accept relative times (e.g. 7d, 24h, 90m) or
      ISO-8601 timestamps.
    - code-push confirmation is asymmetric by design: a single-device push
      (--device) proceeds immediately after printing a stderr warning, with
      no confirmation flag required; a multi-target push (--devices and/or
      --groups) additionally requires --yes, since it can affect every
      matching device.
    - Global flags (--json, --deployment, --no-key) are accepted both
      before and after the subcommand, e.g. both `superstack.py --json
      devices` and `superstack.py devices --json` work.
"""

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

BASE_URL = "https://super.siliconwitchery.com/api"
MAX_PAGE = 1000        # Documented per-request cap for data/logs
MAX_CODE_CHARS = 100000  # Documented max Lua code size


def fail(message, code=1):
    print("error: {}".format(message), file=sys.stderr)
    sys.exit(code)


def parse_time(value, name):
    """Convert '7d' / '24h' / '90m' to an ISO-8601 UTC timestamp,
    or pass through an ISO-8601 string unchanged."""
    match = re.fullmatch(r"(\d+)([dhm])", value.strip())
    if match:
        amount, unit = int(match.group(1)), match.group(2)
        delta = {"d": timedelta(days=amount),
                 "h": timedelta(hours=amount),
                 "m": timedelta(minutes=amount)}[unit]
        moment = datetime.now(timezone.utc) - delta
        return moment.strftime("%Y-%m-%dT%H:%M:%SZ")
    # Assume ISO-8601, validate loosely
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        fail("invalid {} value '{}': use e.g. 7d, 24h, 90m or an "
             "ISO-8601 timestamp".format(name, value), 2)
    return value


def to_datetime(value):
    """Parse an ISO-8601 timestamp (as produced by parse_time() or
    returned by the API) into a timezone-aware datetime for comparison."""
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def get_deployment(args):
    deployment = args.deployment or os.environ.get("SUPERSTACK_DEPLOYMENT")
    if not deployment:
        fail("no deployment id given. Pass --deployment <id> or set the "
             "SUPERSTACK_DEPLOYMENT environment variable. The Deployment ID "
             "is shown on the Settings Tab of the Superstack web app.", 2)
    return deployment


def get_api_key(args):
    if args.no_key:
        return None
    key = os.environ.get("SUPERSTACK_API_KEY")
    if not key:
        fail("SUPERSTACK_API_KEY is not set. Create an API key in the "
             "Settings Tab of the Superstack web app and export it:\n"
             "  export SUPERSTACK_API_KEY='<your key>'\n"
             "For read-only access to demo deployments, pass --no-key.", 2)
    return key


def request(args, method, path, body=None, query=None):
    """Perform an HTTP request against the Superstack API.

    Returns the decoded JSON response (or {} for empty bodies)."""
    deployment = get_deployment(args)
    url = "{}/{}{}".format(BASE_URL, deployment, path)
    if query:
        url += "?" + urllib.parse.urlencode(query)

    headers = {"Accept": "application/json"}
    key = get_api_key(args)
    if key:
        headers["X-Api-Key"] = key

    data = None
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"

    req = urllib.request.Request(url, data=data, headers=headers,
                                 method=method)
    try:
        with urllib.request.urlopen(req, timeout=90) as resp:
            raw = resp.read().decode("utf-8")
    except urllib.error.HTTPError as err:
        handle_http_error(err)
    except urllib.error.URLError as err:
        fail("could not reach {}: {}".format(BASE_URL, err.reason))

    if not raw:
        return {}
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {"raw": raw}


def handle_http_error(err):
    detail = ""
    try:
        payload = json.loads(err.read().decode("utf-8"))
        if isinstance(payload, dict) and "error" in payload:
            detail = payload["error"]
    except Exception:
        pass

    hints = {
        401: "unauthorized: check SUPERSTACK_API_KEY and its permissions",
        402: "payment required: the deployment's AI token allowance for "
             "this billing period is used up",
        403: "forbidden: the API key lacks the required permission for "
             "this operation",
        404: "not found: check the deployment id and device/agent id",
    }
    message = hints.get(err.code, "HTTP {} {}".format(err.code, err.reason))
    if detail:
        message += " ({})".format(detail)
    fail(message)


def print_table(rows, headers):
    """Print a simple aligned text table."""
    rows = [[("" if cell is None else str(cell)) for cell in row]
            for row in rows]
    widths = [len(h) for h in headers]
    for row in rows:
        for i, cell in enumerate(row):
            widths[i] = max(widths[i], len(cell))
    fmt = "  ".join("{{:<{}}}".format(w) for w in widths)
    print(fmt.format(*headers))
    print(fmt.format(*["-" * w for w in widths]))
    for row in rows:
        print(fmt.format(*row))


def build_filters(args):
    filters = {}
    if args.devices:
        filters["devices"] = args.devices
    if args.groups:
        filters["groups"] = args.groups
    if args.since:
        filters["startTime"] = parse_time(args.since, "--since")
    if args.until:
        filters["endTime"] = parse_time(args.until, "--until")
    return filters


def fetch_entries(args, path, list_key):
    """Fetch data/logs, optionally following id/count pagination cursors.

    id/count pagination is a raw cursor over the *entire* dataset with no
    knowledge of the --since/--until range used for the initial request
    (per the API contract, a time range cannot be combined with id/count).
    So when following pages we must manually keep results inside
    [startTime, endTime] ourselves: entries outside that window are
    dropped, and each direction stops as soon as a page crosses the
    boundary, rather than trusting newerAvailable/olderAvailable to know
    anything about the requested range. The newer-entries loop only pages
    all the way to "now" when --until was not given; when --until was
    given, it is bounded by endTime instead.
    """
    filters = build_filters(args)
    query = {"filters": json.dumps(filters)} if filters else None
    response = request(args, "GET", path, query=query)
    entries = list(response.get(list_key, []))
    initial_older_available = response.get("olderAvailable")
    initial_newer_available = response.get("newerAvailable")

    start_time = (to_datetime(filters["startTime"])
                 if "startTime" in filters else None)
    end_time = (to_datetime(filters["endTime"])
               if "endTime" in filters else None)

    if args.follow_pagination and entries:
        base = {k: v for k, v in filters.items()
                if k not in ("startTime", "endTime")}
        seen_ids = {entry["id"] for entry in entries}

        # Page older entries from the oldest id we have. Stop once a page
        # crosses --since, once the id cursor fails to advance (guards
        # against a misbehaving API looping forever), once a page yields
        # no unseen ids, or once the API reports nothing older.
        older_available = initial_older_available
        oldest_id = min(entry["id"] for entry in entries)
        while older_available:
            page = dict(base, id=oldest_id, count=-MAX_PAGE)
            response = request(args, "GET", path,
                               query={"filters": json.dumps(page)})
            batch = response.get(list_key, [])
            new_ids = {e["id"] for e in batch if e["id"] not in seen_ids}
            if not batch or not new_ids:
                break
            in_range = batch
            crossed_boundary = False
            if start_time is not None:
                in_range = [e for e in batch
                           if to_datetime(e["timestamp"]) >= start_time]
                crossed_boundary = len(in_range) < len(batch)
            new_in_range = [e for e in in_range if e["id"] in new_ids]
            entries.extend(new_in_range)
            seen_ids.update(e["id"] for e in new_in_range)
            new_oldest = min(e["id"] for e in batch)
            if crossed_boundary or new_oldest >= oldest_id:
                break
            oldest_id = new_oldest
            older_available = response.get("olderAvailable")

        # Page newer entries from the newest id we have. Stop once a page
        # crosses --until (when given), once the id cursor fails to
        # advance, once a page yields no unseen ids, or once the API
        # reports nothing newer.
        newer_available = initial_newer_available
        newest_id = max(entry["id"] for entry in entries)
        while newer_available:
            page = dict(base, id=newest_id, count=MAX_PAGE)
            response = request(args, "GET", path,
                               query={"filters": json.dumps(page)})
            batch = response.get(list_key, [])
            new_ids = {e["id"] for e in batch if e["id"] not in seen_ids}
            if not batch or not new_ids:
                break
            in_range = batch
            crossed_boundary = False
            if end_time is not None:
                in_range = [e for e in batch
                           if to_datetime(e["timestamp"]) <= end_time]
                crossed_boundary = len(in_range) < len(batch)
            new_in_range = [e for e in in_range if e["id"] in new_ids]
            entries.extend(new_in_range)
            seen_ids.update(e["id"] for e in new_in_range)
            new_newest = max(e["id"] for e in batch)
            if crossed_boundary or new_newest <= newest_id:
                break
            newest_id = new_newest
            newer_available = response.get("newerAvailable")

    seen = set()
    unique = []
    for entry in sorted(entries, key=lambda e: e["id"]):
        if entry["id"] not in seen:
            seen.add(entry["id"])
            unique.append(entry)
    return unique


def cmd_devices(args):
    response = request(args, "GET", "/devices")
    if args.json:
        print(json.dumps(response, indent=2))
        return
    rows = [[d.get("id"), d.get("name"), d.get("group"),
             "yes" if d.get("online") else "no", d.get("codeState"),
             d.get("batteryLevel"), d.get("signalStrength")]
            for d in response.get("devices", [])]
    print_table(rows, ["ID", "NAME", "GROUP", "ONLINE", "CODE",
                       "BATTERY%", "SIGNAL%"])


def cmd_data(args):
    entries = fetch_entries(args, "/data", "data")
    if args.json:
        print(json.dumps({"data": entries}, indent=2))
        return
    rows = [[e.get("id"), e.get("timestamp"), e.get("device"),
             e.get("group"), json.dumps(e.get("data"))] for e in entries]
    print_table(rows, ["ID", "TIMESTAMP", "DEVICE", "GROUP", "DATA"])


def cmd_logs(args):
    entries = fetch_entries(args, "/logs", "logs")
    if args.json:
        print(json.dumps({"logs": entries}, indent=2))
        return
    rows = [[e.get("id"), e.get("timestamp"), e.get("device"),
             e.get("level"), e.get("message")] for e in entries]
    print_table(rows, ["ID", "TIMESTAMP", "DEVICE", "LEVEL", "MESSAGE"])


def cmd_telemetry(args):
    query = {"days": args.days} if args.days else None
    response = request(args, "GET",
                       "/device/{}/telemetry".format(args.device),
                       query=query)
    if args.json:
        print(json.dumps(response, indent=2))
        return
    rows = []
    for timestamp in sorted(response.get("telemetry", {})):
        t = response["telemetry"][timestamp]
        rows.append([timestamp, t.get("bytesSent"), t.get("bytesReceived"),
                     t.get("powerState"), t.get("batteryLevel"),
                     t.get("signalStrength"), t.get("gpsCoordinates")])
    print_table(rows, ["TIMESTAMP", "SENT", "RECEIVED", "POWER",
                       "BATTERY%", "SIGNAL%", "GPS"])


def cmd_code_get(args):
    response = request(args, "GET", "/device/{}/code".format(args.device))
    code = response.get("code", "")
    if args.out:
        with open(args.out, "w", encoding="utf-8") as handle:
            handle.write(code)
        print("wrote {} characters to {}".format(len(code), args.out))
    else:
        print(code)


def cmd_code_push(args):
    if not args.device and not args.devices and not args.groups:
        fail("specify a target: --device <id>, or --devices/--groups "
             "<names> for a multi-device push", 2)
    if args.device and (args.devices or args.groups):
        fail("--device cannot be combined with --devices/--groups", 2)

    try:
        with open(args.file, "r", encoding="utf-8") as handle:
            code = handle.read()
    except OSError as err:
        fail("could not read {}: {}".format(args.file, err), 2)
    if len(code) > MAX_CODE_CHARS:
        fail("{} is {} characters; the API allows at most {} "
             "characters".format(args.file, len(code), MAX_CODE_CHARS), 2)

    print("warning: pushed code OVERWRITES the existing code on the target "
          "device(s), starts running immediately, and the transfer counts "
          "towards your data allowance.", file=sys.stderr)

    if args.device:
        request(args, "PUT", "/device/{}/code".format(args.device),
                body={"code": code})
        print("pushed {} to device {}".format(args.file, args.device))
        return

    if not args.yes:
        fail("multi-device push affects every matching device. Re-run "
             "with --yes to confirm.", 2)
    body = {"code": code}
    if args.groups:
        body["groups"] = args.groups
    if args.devices:
        body["devices"] = args.devices
    request(args, "PUT", "/code/push", body=body)
    targets = (args.devices or []) + (args.groups or [])
    print("pushed {} to: {}".format(args.file, ", ".join(targets)))


def cmd_code_start(args):
    request(args, "PUT", "/device/{}/code/start".format(args.device))
    print("code started on device {}".format(args.device))


def cmd_code_stop(args):
    request(args, "PUT", "/device/{}/code/stop".format(args.device))
    print("code stopped on device {}".format(args.device))


def cmd_agent_chat(args):
    body = {"messages": [{"role": "user", "content": args.message}]}
    response = request(args, "POST",
                       "/agent/{}/query".format(args.agent), body=body)
    if args.json:
        print(json.dumps(response, indent=2))
        return
    print(response.get("response", ""))


def add_filter_arguments(parser):
    parser.add_argument("--devices", action="append", metavar="NAME",
                        help="filter by device name (repeatable)")
    parser.add_argument("--groups", action="append", metavar="NAME",
                        help="filter by device group (repeatable)")
    parser.add_argument("--since", metavar="TIME",
                        help="start of time range, e.g. 7d, 24h, 90m, "
                             "or ISO-8601")
    parser.add_argument("--until", metavar="TIME",
                        help="end of time range, e.g. 1h or ISO-8601")
    parser.add_argument("--follow-pagination", action="store_true",
                        help="follow id/count cursors to fetch all pages "
                             "(max {} entries/page)".format(MAX_PAGE))


def build_common_parser():
    """Global flags shared by the top-level parser and every subparser.

    Using `parents=[common]` on both means flags like --json, --deployment,
    and --no-key are accepted whether given before or after the subcommand
    name, e.g. both `superstack.py --json devices` and
    `superstack.py devices --json` work.

    Each flag's default is argparse.SUPPRESS rather than its "real" default
    (False / None). This matters because of a subtle argparse behaviour:
    when a subcommand is dispatched, the subparser parses its remaining
    arguments into a *fresh* namespace using its own copy of these actions,
    then copies every attribute from that namespace onto the shared one --
    unconditionally overwriting anything already set. If these actions had
    normal defaults, a flag given *before* the subcommand (e.g.
    `--json devices`) would be silently reset to its default by the
    subparser's copy when the flag wasn't repeated after the subcommand.
    SUPPRESS means the subparser simply omits the attribute when it wasn't
    given to it, leaving whatever the top-level parser already set intact.
    apply_common_defaults() then fills in the real defaults afterwards for
    whichever flags were never supplied at all.
    """
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--deployment", metavar="ID",
                        default=argparse.SUPPRESS,
                        help="deployment id (default: $SUPERSTACK_DEPLOYMENT)")
    common.add_argument("--no-key", action="store_true",
                        default=argparse.SUPPRESS,
                        help="skip the API key (demo deployments only)")
    common.add_argument("--json", action="store_true",
                        default=argparse.SUPPRESS,
                        help="print raw JSON instead of a table")
    return common


def apply_common_defaults(args):
    """Fill in real defaults for global flags that were omitted entirely
    (see build_common_parser() for why SUPPRESS is used as the argparse
    default)."""
    args.deployment = getattr(args, "deployment", None)
    args.no_key = getattr(args, "no_key", False)
    args.json = getattr(args, "json", False)
    return args


def build_parser():
    common = build_common_parser()
    parser = argparse.ArgumentParser(
        prog="superstack.py",
        description="CLI for the Superstack REST API "
                    "(https://super.siliconwitchery.com)",
        parents=[common])
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("devices", help="list all devices", parents=[common])
    p.set_defaults(func=cmd_devices)

    p = sub.add_parser("data", help="retrieve device data", parents=[common])
    add_filter_arguments(p)
    p.set_defaults(func=cmd_data)

    p = sub.add_parser("logs", help="retrieve device logs", parents=[common])
    add_filter_arguments(p)
    p.set_defaults(func=cmd_logs)

    p = sub.add_parser("telemetry", help="retrieve device telemetry",
                       parents=[common])
    p.add_argument("--device", required=True, metavar="ID",
                   help="device id")
    p.add_argument("--days", type=int, metavar="N",
                   help="days of history (default: current billing period)")
    p.set_defaults(func=cmd_telemetry)

    p = sub.add_parser("code-get", help="download a device's Lua code",
                       parents=[common])
    p.add_argument("--device", required=True, metavar="ID",
                   help="device id")
    p.add_argument("--out", metavar="FILE",
                   help="write code to FILE instead of stdout")
    p.set_defaults(func=cmd_code_get)

    p = sub.add_parser("code-push", help="push Lua code to device(s)",
                       parents=[common])
    p.add_argument("--file", required=True, metavar="FILE",
                   help="Lua source file (max {} chars)".format(
                       MAX_CODE_CHARS))
    p.add_argument("--device", metavar="ID",
                   help="target a single device by id")
    p.add_argument("--devices", action="append", metavar="NAME",
                   help="target devices by name (repeatable)")
    p.add_argument("--groups", action="append", metavar="NAME",
                   help="target device groups (repeatable)")
    p.add_argument("--yes", action="store_true",
                   help="confirm a multi-device push")
    p.set_defaults(func=cmd_code_push)

    p = sub.add_parser("code-start", help="start code on a device",
                       parents=[common])
    p.add_argument("--device", required=True, metavar="ID",
                   help="device id")
    p.set_defaults(func=cmd_code_start)

    p = sub.add_parser("code-stop", help="stop code on a device",
                       parents=[common])
    p.add_argument("--device", required=True, metavar="ID",
                   help="device id")
    p.set_defaults(func=cmd_code_stop)

    p = sub.add_parser("agent-chat", help="ask an AI agent a question",
                       parents=[common])
    p.add_argument("--agent", required=True, metavar="ID",
                   help="agent id")
    p.add_argument("--message", required=True, metavar="TEXT",
                   help="question for the agent")
    p.set_defaults(func=cmd_agent_chat)

    return parser


def main():
    args = apply_common_defaults(build_parser().parse_args())
    args.func(args)


if __name__ == "__main__":
    main()
