from __future__ import annotations

import sys
from pathlib import Path

# Windows: force UTF-8 so Korean output doesn't crash on CP949 terminals
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

import click
from rich.console import Console

from .engine import recommend
from .renderer import render
from .scanner import enrich_with_source, scan_helm_values, scan_k8s_dir


# CLI entrypoint registered as the `scalead` command in pyproject.toml.
# This module only wires together scanning, recommendation, and rendering.
@click.command(context_settings={"help_option_names": ["-h", "--help"]})
@click.argument("target", metavar="TARGET")
@click.option(
    "--source", "-s",
    default=None,
    metavar="DIR",
    help="앱 소스 디렉토리 (선택). 정적 분석으로 메트릭/큐 감지 정확도 향상.",
)
@click.option(
    "--format", "-f", "fmt",
    default="rich",
    type=click.Choice(["rich", "json"], case_sensitive=False),
    help="출력 형식 (기본: rich)",
    show_default=True,
)
def main(target: str, source: str | None, fmt: str) -> None:
    """K8s 오토스케일링 정책 어드바이저

    \b
    TARGET: Helm values 파일(.yaml) 또는 k8s 매니페스트 디렉토리

    \b
    예시:
      scalead helm/traffic-lab/values.yaml
      scalead helm/traffic-lab/values-dev.yaml --source ./app
      scalead k8s/demo-app/
    """
    console = Console(stderr=True)
    p = Path(target)

    if not p.exists():
        console.print(f"[red]오류:[/red] 경로를 찾을 수 없습니다 → {target}")
        sys.exit(1)

    try:
        if p.is_dir():
            # Manifest mode: scan a directory of Kubernetes YAML resources.
            scan = scan_k8s_dir(target)
        else:
            # Helm mode: scan one values.yaml file.
            scan = scan_helm_values(target)
    except Exception as exc:
        console.print(f"[red]스캔 실패:[/red] {exc}")
        sys.exit(1)

    if source:
        src = Path(source)
        if not src.is_dir():
            console.print(f"[yellow]경고:[/yellow] 소스 경로 없음 → {source} (스킵)")
        else:
            enrich_with_source(source, scan)

    # Recommendation rules are isolated in engine.py so they can evolve
    # without changing how inputs are parsed.
    result = recommend(scan)

    if fmt == "json":
        import dataclasses, json
        print(json.dumps(dataclasses.asdict(result), indent=2, ensure_ascii=False))
    else:
        out = Console()
        render(result, out)


if __name__ == "__main__":
    main()
