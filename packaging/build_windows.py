"""Build a portable Windows x64 ZIP with Python 3.12, app sources and guide."""
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "final_project-Windows-x64.zip"


def build():
    with tempfile.TemporaryDirectory() as temp:
        staging = Path(temp) / "final_project"
        app = staging / "app"
        runtime = staging / "runtime"
        runtime.mkdir(parents=True)
        app.mkdir()
        for source in ROOT.glob("*.py"):
            shutil.copy2(source, app)
        for name in ("database", "tests", "packaging"):
            shutil.copytree(ROOT / name, app / name, ignore=shutil.ignore_patterns("__pycache__"))
        for name in ("studio_theme.qss", "requirements.txt", "README.md"):
            shutil.copy2(ROOT / name, app)
        for name in ("FINAL_PROJECT_TH.md", "Start-PDFNoteStudio.cmd"):
            shutil.copy2(ROOT / name, staging)
            shutil.copy2(ROOT / name, app)

        embedded = Path(temp) / "python.zip"
        urllib.request.urlretrieve("https://www.python.org/ftp/python/3.12.10/python-3.12.10-embed-amd64.zip", embedded)
        with zipfile.ZipFile(embedded) as archive:
            archive.extractall(runtime)
        (runtime / "python312._pth").write_text("python312.zip\n.\nLib/site-packages\n../app\nimport site\n")
        subprocess.run([sys.executable, "-m", "pip", "install", "--target", str(runtime / "Lib/site-packages"),
                        "--platform", "win_amd64", "--python-version", "3.12", "--only-binary=:all:",
                        "--no-compile", "-r", str(ROOT / "requirements.txt"), "psycopg-binary", "tzdata",
                        "colorama", "socksio"], check=True)
        with zipfile.ZipFile(OUTPUT, "w", zipfile.ZIP_DEFLATED) as archive:
            for path in staging.rglob("*"):
                if path.is_file():
                    archive.write(path, path.relative_to(staging.parent))
    print(OUTPUT)


if __name__ == "__main__":
    build()
