"""Build a source-only transfer archive; never include local uploads or secrets."""
from pathlib import Path
import tarfile

ROOT = Path(__file__).resolve().parents[1]
FILES = [
    ".dockerignore", ".gitignore", "compose.yaml",
    "backend/main.py", "backend/requirements.txt",
    "frontend/package.json", "frontend/package-lock.json", "frontend/index.html",
    "frontend/vite.config.js", "frontend/tailwind.config.js", "frontend/postcss.config.js",
    "deploy/api.Dockerfile", "deploy/web.Dockerfile", "deploy/Caddyfile",
    "deploy/.env.example", "deploy/configure.py", "deploy/package.py", "deploy/start.sh",
    "docs/ORACLE_FREE_DEPLOYMENT.md",
]
DIRECTORIES = ["backend/app", "frontend/src", "frontend/public"]


def source_files():
    candidates = [ROOT / name for name in FILES]
    for directory in DIRECTORIES:
        base = ROOT / directory
        if base.exists():
            candidates.extend(path for path in base.rglob("*") if path.is_file())
    for path in sorted(set(candidates)):
        relative = path.relative_to(ROOT)
        if path.is_symlink() or any(parent.is_symlink() for parent in path.parents if parent != ROOT):
            raise ValueError(f"Refusing symlink in package: {relative}")
        if "__pycache__" in relative.parts or path.suffix in {".pyc", ".pyo"}:
            continue
        if path.name.startswith(".env") and relative.as_posix() != "deploy/.env.example":
            continue
        if path.suffix.lower() in {".pem", ".key"}:
            continue
        if not path.is_file():
            raise FileNotFoundError(relative)
        yield path, relative.as_posix()


def main():
    destination = ROOT / "output" / "deployment" / "finsight-deploy.tar.gz"
    destination.parent.mkdir(parents=True, exist_ok=True)
    files = list(source_files())
    with tarfile.open(destination, "w:gz", format=tarfile.PAX_FORMAT) as archive:
        for path, name in files:
            info = archive.gettarinfo(str(path), arcname=name)
            info.uid = info.gid = 0
            info.uname = info.gname = ""
            info.mode = 0o644
            with path.open("rb") as source:
                archive.addfile(info, source)
    print(f"Packaged {len(files)} source files: {destination}")


if __name__ == "__main__":
    main()
