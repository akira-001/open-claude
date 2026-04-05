#!/usr/bin/env python3
"""ポートレジストリのバリデーションと現在の使用状況を表示する。"""

import subprocess
import sys
import tomllib
from pathlib import Path

REGISTRY = Path.home() / ".config" / "ports.toml"


def load_registry() -> dict[str, int]:
    with open(REGISTRY, "rb") as f:
        data = tomllib.load(f)
    return data.get("services", {})


def check_duplicates(services: dict[str, int]) -> list[str]:
    port_to_names: dict[int, list[str]] = {}
    for name, port in services.items():
        port_to_names.setdefault(port, []).append(name)
    errors = []
    for port, names in port_to_names.items():
        if len(names) > 1:
            errors.append(f"  port {port}: {', '.join(names)}")
    return errors


def check_listening(port: int) -> str | None:
    try:
        out = subprocess.check_output(
            ["lsof", "-ti", f":{port}"], text=True, stderr=subprocess.DEVNULL
        ).strip()
        return out.split("\n")[0] if out else None
    except subprocess.CalledProcessError:
        return None


def main() -> None:
    services = load_registry()

    # 重複チェック
    dupes = check_duplicates(services)
    if dupes:
        print("CONFLICT — ポート重複:")
        for d in dupes:
            print(d)
        print()

    # 状況表示
    print(f"{'サービス':<25} {'ポート':>6}  {'状態'}")
    print("-" * 50)
    for name, port in sorted(services.items(), key=lambda x: x[1]):
        pid = check_listening(port)
        status = f"UP (pid {pid})" if pid else "DOWN"
        print(f"{name:<25} {port:>6}  {status}")

    if dupes:
        sys.exit(1)


if __name__ == "__main__":
    main()
