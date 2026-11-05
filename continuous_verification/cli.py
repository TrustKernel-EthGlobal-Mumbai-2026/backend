"""JSON CLI: python -m continuous_verification.cli OPERATION [--request PATH]."""
import argparse
import json
import sys
from typing import TextIO

from .sdk import Client, InterfaceError, MAX_BYTES, OPERATIONS, decode_request, failure


class _Parser(argparse.ArgumentParser):
    def error(self, message):
        raise InterfaceError("INVALID_ARGUMENTS", "Invalid command arguments; see --help.")


def main(argv=None, *, client: Client | None = None, stdin: TextIO | None = None,
         stdout: TextIO | None = None, stderr: TextIO | None = None) -> int:
    """Host-injectable for integration; standalone default has no backend.

    --request is an operator-selected local input file, never a shell command.
    MCP does not expose this option. All diagnostics go to stderr.
    """
    stdin, stdout, stderr = stdin or sys.stdin, stdout or sys.stdout, stderr or sys.stderr
    parser = _Parser(description=__doc__)
    parser.add_argument("operation", choices=sorted(OPERATIONS))
    parser.add_argument("--request", help="UTF-8 JSON file; default reads stdin")
    try:
        args = parser.parse_args(argv)
        if args.request is None:
            raw = stdin.read(MAX_BYTES + 1)
        else:
            try:
                with open(args.request, encoding="utf-8") as source:
                    raw = source.read(MAX_BYTES + 1)
            except (OSError, UnicodeError):
                raise InterfaceError("INPUT_ERROR", "Could not read the request as UTF-8 JSON.") from None
        result = (client or Client()).call(args.operation, decode_request(raw))
    except InterfaceError as error:
        result = failure(error)
    except (OSError, UnicodeError):
        result = failure(InterfaceError("INPUT_ERROR", "Could not read request input."))
    print(json.dumps(result, ensure_ascii=True, allow_nan=False), file=stdout)
    if not result["ok"]:
        print(result["error"]["code"], file=stderr)
        return 2 if result["error"]["code"] in {"INVALID_ARGUMENTS", "INVALID_JSON", "INVALID_REQUEST", "INPUT_ERROR", "UNKNOWN_OPERATION"} else 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
