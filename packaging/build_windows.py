"""Build a self-contained release without changing a running dist."""
import argparse
import ast
import hashlib
import importlib.metadata as metadata
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
import zipfile

PROJECT = Path(__file__).resolve().parents[1]


def sha256(path):
    with path.open("rb") as file:
        return hashlib.file_digest(file, "sha256").hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--resume", type=Path, help="Resume packaging an unfinished release")
    args = parser.parse_args()
    source = ast.parse((PROJECT / "src/dictation_app.py").read_text(encoding="utf-8-sig"))
    version = next(node.value.value for node in source.body if isinstance(node, ast.Assign)
                   and any(isinstance(target, ast.Name) and target.id == "APP_VERSION" for target in node.targets))
    for line in (PROJECT / "requirements-windows.lock").read_text(encoding="utf-8").splitlines():
        if line.strip() and not line.startswith("#"):
            name, wanted = line.split("==", 1)
            if metadata.version(name) != wanted:
                raise RuntimeError(f"Build dependency mismatch: {name}; install requirements-windows.lock")
    compiler = PROJECT / "packaging/tools/nsis-3.13/makensis.exe"
    if not compiler.is_file():
        raise RuntimeError("NSIS 3.13 portable compiler is required under packaging/tools/nsis-3.13")
    release = args.resume.resolve() if args.resume else PROJECT / "releases" / f"{version}-{time.strftime('%Y%m%d-%H%M%S')}"
    if args.resume:
        executable = release / "TravelDeskWhisper/TravelDeskWhisper.exe"
        if release.parent != PROJECT / "releases" or not executable.is_file():
            raise RuntimeError("Resume target must be an existing build under releases")
        for path in ("src/dictation_app.py", "packaging/local-whisper-dictation-windows.spec", "packaging/windows-version.txt", "packaging/traveldesk-whisper.ico"):
            if (PROJECT / path).stat().st_mtime > executable.stat().st_mtime:
                raise RuntimeError("Source changed after compilation; create a new release")
    else:
        release.mkdir(parents=True, exist_ok=False)
    (PROJECT / "build_release").mkdir(exist_ok=True)
    build_path = PROJECT / "build_release" / release.name
    command = [sys.executable, "-m", "PyInstaller", str(PROJECT / "packaging/local-whisper-dictation-windows.spec"),
               "--distpath", str(release), "--workpath", str(build_path), "--noconfirm"]
    print(f"{'Resuming packaging' if args.resume else 'Building'} {release}", flush=True)
    if not args.resume:
        with (release / "build.log").open("w", encoding="utf-8") as log:
            subprocess.run(command, cwd=PROJECT, stdout=log, stderr=subprocess.STDOUT, check=True)
    app = release / "TravelDeskWhisper"
    for name in ("config.json", "README.md", ".env.example", "requirements-windows.lock"):
        shutil.copy2(PROJECT / name, app / name)
    config = json.loads((app / "config.json").read_text(encoding="utf-8"))
    if (config["transcription_provider"], config["model_size"], config["device"]) != ("local", "small", "cpu"):
        raise RuntimeError("The general Windows release must use local/small/CPU")
    from huggingface_hub import snapshot_download

    model_files = ("config.json", "model.bin", "tokenizer.json", "vocabulary.txt")
    model = Path(snapshot_download("Systran/faster-whisper-small", local_files_only=True, allow_patterns=list(model_files)))
    model_dest = app / "models/small"
    model_dest.mkdir(parents=True, exist_ok=True)
    for name in model_files:
        shutil.copy2(model / name, model_dest / name)
    shutil.copytree(PROJECT / "packaging/licenses", app / "licenses", dirs_exist_ok=True)
    python_license = Path(sys.base_prefix) / "LICENSE.txt"
    if python_license.is_file():
        shutil.copy2(python_license, app / "licenses/Python.txt")
    for distribution in metadata.distributions():
        for item in distribution.files or []:
            item_path = Path(item)
            if '.dist-info' in str(item) and item_path.name.lower().startswith(("license", "copying", "notice")):
                source_path = Path(distribution.locate_file(item))
                if source_path.is_file():
                    destination = app / "licenses" / distribution.metadata["Name"] / item_path.name
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(source_path, destination)
    release_info = {"version": version, "built_at": time.strftime('%Y-%m-%dT%H:%M:%S%z'),
                    "model": "Systran/faster-whisper-small", "model_revision": model.name,
                    "model_sha256": sha256(model_dest / "model.bin"),
                    "packages": {name: metadata.version(name) for name in ("faster-whisper", "ctranslate2", "sounddevice", "pyinstaller")}}
    (app / "release.json").write_text(json.dumps(release_info, indent=2) + "\n", encoding="utf-8")
    environment = {**os.environ, "HF_HUB_OFFLINE": "1", "HF_HOME": str(release / "empty-cache")}
    subprocess.run([str(app / "TravelDeskWhisper.exe"), "--self-test", str(release / "self-test.json"),
                    "--audio", str(PROJECT / "tmp/openai-dictation-test.wav")], env=environment, check=True, timeout=120)
    result = json.loads((release / "self-test.json").read_text(encoding="utf-8"))
    if not result["ok"] or not result["bundled_model"]:
        raise RuntimeError("Frozen offline self-test failed")
    print("Frozen offline transcription passed. Creating installer...", flush=True)
    files = sorted(path for path in app.rglob("*") if path.is_file())
    for path in files:
        if path.name == ".env" or path.suffix.lower() in (".wav", ".mp3", ".log", ".jsonl"):
            raise RuntimeError(f"Private/runtime file in distribution: {path.name}")
    uninstall = release / "uninstall-files.nsh"
    lines = ['Delete "$INSTDIR\\' + str(path.relative_to(app)).replace('$', '$$') + '"'
             for path in files if path != app / "config.json"]
    directories = sorted((path for path in app.rglob("*") if path.is_dir()), key=lambda path: len(path.parts), reverse=True)
    lines += ['RMDir "$INSTDIR\\' + str(path.relative_to(app)).replace('$', '$$') + '"' for path in directories]
    uninstall.write_text("\n".join(lines) + "\n", encoding="utf-8-sig")
    setup = release / f"TravelDeskWhisper-Setup-{version}-windows-x64.exe"
    with (release / "installer-build.log").open("w", encoding="utf-8") as log:
        subprocess.run([str(compiler), "/V3", "/WX", "/INPUTCHARSET", "UTF8", f"/DAPP_DIR={app}",
                        f"/DOUTPUT_FILE={setup}", f"/DUNINSTALL_MANIFEST={uninstall}",
                        str(PROJECT / "packaging/installer.nsi")], stdout=log, stderr=subprocess.STDOUT, check=True)
    print("Creating portable ZIP...", flush=True)
    archive = release / "TravelDeskWhisper-windows.zip"
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED, compresslevel=5) as zip_file:
        for path in files:
            zip_file.write(path, str(Path("TravelDeskWhisper") / path.relative_to(app)))
    with zipfile.ZipFile(archive) as zip_file:
        if zip_file.testzip():
            raise RuntimeError("ZIP integrity failed")
        for path in files:
            name = str(Path("TravelDeskWhisper") / path.relative_to(app)).replace("\\", "/")
            with zip_file.open(name) as archived:
                if hashlib.file_digest(archived, "sha256").hexdigest() != sha256(path):
                    raise RuntimeError(f"ZIP content differs from staged file: {path.name}")
    hashes = {path.name: {"sha256": sha256(path), "bytes": path.stat().st_size} for path in (setup, archive)}
    (release / "SHA256.json").write_text(json.dumps(hashes, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"release": str(release), "installer": str(setup), "hashes": hashes}), flush=True)


if __name__ == "__main__":
    main()
