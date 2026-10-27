"""SEC Pro Beta user-scoped installer. Python 3.11+, standard library only."""
from __future__ import annotations

import argparse
import base64
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import subprocess
import sys
import tarfile
import tempfile
import tomllib

ROOT = Path(__file__).resolve().parent
BEGIN = "<!-- SEC_PRO_BETA:BEGIN -->"
END = "<!-- SEC_PRO_BETA:END -->"


def write_managed(path, data):
    """Back up only changed files; leave unrelated directory entries alone."""
    path = Path(path)
    if path.is_symlink():
        raise ValueError(f"Refusing managed symlink: {path}")
    if path.exists() and path.read_bytes() == data:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        shutil.copy2(path, path.with_name(path.name + ".secpro-backup-" + stamp))
    path.write_bytes(data)


def merge_agents(path, block):
    text = path.read_text(encoding="utf-8-sig") if path.exists() else ""
    if text.count(BEGIN) != text.count(END) or text.count(BEGIN) > 1:
        raise ValueError("AGENTS.md has ambiguous SEC Pro Beta markers; resolve them first")
    if BEGIN in text:
        start, end = text.index(BEGIN), text.index(END) + len(END)
        if end < start:
            raise ValueError("Invalid AGENTS.md marker order")
        updated = text[:start] + block + text[end:]
    else:
        updated = text + ("\n\n" if text and not text.endswith("\n\n") else "") + block + "\n"
    write_managed(path, updated.encode("utf-8"))


def node_runtime():
    home = actual_user_home()
    bundled = home / ".cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin"
    def candidates():
        yield from (str(bundled / "node.exe"), str(bundled / "node"), shutil.which("node"), shutil.which("node.exe"))
        # Only fall back to scoped discovery after direct candidates fail.
        for base in (home / "AppData/Local/OpenAI/Codex/runtimes", home / "AppData/Local/Programs/Codex", home / "AppData/Local/hermes/node"):
            if base.exists():
                for pattern in ("**/node.exe", "**/bin/node"):
                    yield from (str(p) for p in base.glob(pattern))
    seen = set()
    for candidate in candidates():
        if not candidate or candidate in seen:
            continue
        seen.add(candidate)
        try:
            version = subprocess.check_output([candidate, "--version"], text=True, timeout=10).strip()
            if int(version.lstrip("v").split(".")[0]) >= 24:
                return candidate
        except (OSError, ValueError, subprocess.SubprocessError):
            pass
    raise ValueError("GSD requires Node.js 24+. Install it explicitly, then rerun, or use --skip-gsd.")


def merge_gsd_workers(path, models):
    """Fill missing official GSD worker pins. Explicit conflicting pairs stay intact."""
    config = json.loads(path.read_text(encoding="utf-8-sig")) if path.exists() else {}
    if not isinstance(config, dict):
        raise ValueError("GSD defaults must be a JSON object")
    mapping = json.loads((ROOT / "config/gsd-overrides.json").read_text(encoding="utf-8"))
    overrides = config.setdefault("model_overrides", {})
    effort_config = config.setdefault("effort", {})
    if not isinstance(effort_config, dict):
        raise ValueError("GSD effort must be an object")
    effort = effort_config.setdefault("agent_overrides", {})
    if not isinstance(overrides, dict) or not isinstance(effort, dict):
        raise ValueError("GSD worker override sections must be objects")
    conflicts = []
    expected = {}
    for agent, role in mapping.items():
        model = models[role]["model"]
        level = models[role].get("effort", models[role].get("reasoning_effort"))
        if model.lower() in ("inherit", "auto", "default") or level not in ("low", "medium", "high"):
            raise ValueError("Explicit worker models and effort required")
        if ((agent in overrides and overrides[agent] != model)
                or (agent in effort and effort[agent] != level)):
            conflicts.append(agent)
            # Preserve the whole pair; never attach our effort to a different user model.
            continue
        overrides.setdefault(agent, model)
        effort.setdefault(agent, level)
        expected[agent] = (model, level)
    write_managed(path, (json.dumps(config, ensure_ascii=False, indent=2) + "\n").encode())
    return expected, conflicts


def verify_gsd_workers(codex, expected):
    if not (codex / "agents/gsd-executor.toml").is_file():
        raise ValueError("GSD standard executor agent is missing after installation")
    for agent, (model, effort) in expected.items():
        path = codex / "agents" / (agent + ".toml")
        if not path.exists():
            # Optional pack agents are mapped in advance but standard need not install them.
            continue
        with path.open("rb") as stream:
            profile = tomllib.load(stream)
        if profile.get("model") != model or profile.get("model_reasoning_effort") != effort:
            raise ValueError(f"GSD worker pin did not reach {agent}; refusing to claim explicit routing")


def actual_user_home():
    """Obtain the account profile independently of a temporary HOME override."""
    if os.name == "nt":
        import ctypes
        buffer = ctypes.create_unicode_buffer(32768)
        result = ctypes.windll.shell32.SHGetFolderPathW(None, 0x28, None, 0, buffer)
        if result != 0 or not buffer.value:
            raise ValueError("Cannot verify the actual Windows user profile; use --skip-gsd")
        return Path(buffer.value).resolve()
    import pwd
    return Path(pwd.getpwuid(os.getuid()).pw_dir).resolve()


def unpack_gsd(destination):
    lock = json.loads((ROOT / "vendor/gsd-lock.json").read_text(encoding="utf-8"))
    if lock["version"] != "1.19.0" or lock["archive"] != "opengsd-gsd-core-1.19.0.tgz":
        raise ValueError("Unexpected GSD lock version/archive")
    archive = ROOT / "vendor" / lock["archive"]
    digest = hashlib.sha512(archive.read_bytes()).digest()
    expected = lock["sha512"]
    actual = "sha512-" + base64.b64encode(digest).decode()
    if expected not in (actual, digest.hex()):
        raise ValueError("GSD archive SHA-512 mismatch")
    with tarfile.open(archive, "r:gz") as bundle:
        members = bundle.getmembers()
        for member in members:
            name = PurePosixPath(member.name)
            target = (destination / member.name).resolve()
            if (name.is_absolute() or ".." in name.parts or "\\" in member.name or ":" in member.name
                    or not target.is_relative_to(destination.resolve())
                    or not (member.isfile() or member.isdir())):
                raise ValueError(f"Unsafe GSD archive member: {member.name}")
        bundle.extractall(destination, members=members)
    return destination / "package/bin/install.js"


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--codex-home", type=Path, default=Path(os.environ.get("CODEX_HOME", Path.home() / ".codex")))
    parser.add_argument("--skills-home", type=Path, default=Path.home() / ".agents/skills")
    parser.add_argument("--data-dir", type=Path, default=Path.home() / ".sec-pro")
    parser.add_argument("--skip-gsd", action="store_true", help="Install SEC components only (required for isolated homes)")
    args = parser.parse_args(argv)
    if sys.version_info < (3, 11):
        parser.error("Python 3.11+ is required")
    codex, skills, data = (p.expanduser().resolve() for p in (args.codex_home, args.skills_home, args.data_dir))
    conflicts = []
    if not args.skip_gsd:
        real_home = actual_user_home()
        if Path.home().resolve() != real_home or codex != (real_home / ".codex").resolve() or skills != (real_home / ".agents/skills").resolve() or data != (real_home / ".sec-pro").resolve():
            raise ValueError("Custom homes/data require --skip-gsd: upstream GSD can write ~/.agents and ~/.gsd")
        node = node_runtime()
        with tempfile.TemporaryDirectory(prefix="secpro-gsd-") as temp:
            installer = unpack_gsd(Path(temp))
            model_path = data / "models.json"
            models = json.loads((model_path if model_path.exists() else ROOT / "config/models.json").read_text(encoding="utf-8"))
            models = models.get("workers", models)
            expected, conflicts = merge_gsd_workers(real_home / ".gsd/defaults.json", models)
            subprocess.run([node, str(installer), "--codex", "--global", "--config-dir", str(codex), "--no-legacy-cleanup", "--profile=standard"], check=True)
            verify_gsd_workers(codex, expected)
            if conflicts:
                print("Preserved existing explicit GSD worker overrides (SEC defaults not applied): " + ", ".join(conflicts), file=sys.stderr)
    for directory, target in ((ROOT / "skills", skills), (ROOT / "agents", codex / "agents")):
        for source in sorted(directory.rglob("*")):
            if source.is_file():
                write_managed(target / source.relative_to(directory), source.read_bytes())
    # Render only install-local locations into the short managed block.
    template = (ROOT / "config/agents-block.md").read_text(encoding="utf-8")
    block = template.replace("{{SKILLS_HOME}}", str(skills)).replace("{{PACKAGE_ROOT}}", str(ROOT)).replace("{{DATA_DIR}}", str(data)).rstrip()
    merge_agents(codex / "AGENTS.md", block)
    manifest = {"name": "SEC Pro Beta", "version": json.loads((ROOT / 'release-info.json').read_text())['version'], "package_root": str(ROOT), "codex_home": str(codex), "skills_home": str(skills), "data_dir": str(data), "gsd_installed": not args.skip_gsd, "gsd_override_conflicts": conflicts}
    write_managed(data / "installation.json", (json.dumps(manifest, ensure_ascii=False, indent=2) + "\n").encode())
    # Models live in explicit agent profiles; preserve personal runtime settings.
    if not (data / "models.json").exists():
        write_managed(data / "models.json", (ROOT / "config/models.json").read_bytes())
    if not (data / "workers.json").exists():
        registry = json.loads((ROOT / 'config/workers.json').read_text(encoding='utf-8'))
        legacy = json.loads((data / 'models.json').read_text(encoding='utf-8'))
        legacy = legacy.get('workers', legacy)
        for role in ('reader','writer','coder'):
            if role in legacy:
                profile = dict(registry['models']['gpt-reader' if role=='reader' else 'gpt-coder'])
                profile['model'] = legacy[role]['model']
                profile['effort'] = legacy[role].get('effort', legacy[role].get('reasoning_effort','medium'))
                profile['capabilities'] = [{'reader':'reading','writer':'writing','coder':'coding'}[role]]
                baseline = registry['models']['gpt-reader' if role=='reader' else 'gpt-coder']
                if profile['model'] != baseline['model'] or profile['effort'] != baseline['effort']:
                    registry['models']['legacy-'+role] = profile
        write_managed(data / 'workers.json', (json.dumps(registry,ensure_ascii=False,indent=2)+'\n').encode())
    print(json.dumps({"installed": True, **manifest}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (OSError, ValueError, KeyError, subprocess.SubprocessError, tarfile.TarError) as error:
        print(f"SEC Pro Beta installation failed: {error}", file=sys.stderr)
        sys.exit(2)
