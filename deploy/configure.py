"""Create deployment-only secrets without copying local data or credentials."""
import argparse
import os
from pathlib import Path
import re
import secrets


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("domain", help="Public DNS hostname, e.g. my-finsight.duckdns.org")
    args = parser.parse_args()
    domain = args.domain.lower()
    labels = domain.split(".")
    if (len(domain) > 253 or len(labels) < 2 or domain.replace(".", "").isdigit()
            or not all(re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", label) for label in labels)):
        parser.error("Use a DNS hostname without a scheme, port, path, or wildcard.")
    target = Path(__file__).resolve().parent / ".env"
    content = (
        f"APP_DOMAIN={domain}\n"
        f"POSTGRES_PASSWORD={secrets.token_hex(32)}\n"
        f"SECRET_KEY={secrets.token_hex(48)}\n"
        "SMTP_HOST=\nSMTP_PORT=587\nSMTP_USERNAME=\nSMTP_PASSWORD=\nSMTP_FROM_EMAIL=\n"
    )
    try:
        fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        parser.error("deploy/.env already exists. Edit it directly; do not replace a live database password.")
    with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as output:
        output.write(content)
    print("Created deploy/.env with new secrets. Keep it private; values were not printed.")


if __name__ == "__main__":
    main()
