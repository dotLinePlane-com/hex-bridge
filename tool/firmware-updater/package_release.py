"""Package the successful ESP-IDF build. Developer entry point: release.cmd."""
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile

HERE = Path(__file__).resolve().parent
BUILD = HERE.parents[1] / "build"


def package():
    project = json.loads((BUILD / "project_description.json").read_text("utf-8"))
    flash = json.loads((BUILD / "flasher_args.json").read_text("utf-8"))
    version = project["project_version"]
    if (project["project_name"] != "hex-bridge" or project["target"] != "esp32"
            or flash["extra_esptool_args"]["chip"] != "esp32"
            or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._+-]*", version)):
        raise ValueError("Unexpected project, chip or version")
    # Review any layout change before shipping an updater that writes user data.
    roles = [flash[k] for k in ("bootloader", "partition-table", "app")]
    if (flash["flash_files"] != {r["offset"]: r["file"] for r in roles}
            or any(str(r["encrypted"]).lower() != "false" for r in roles)):
        raise ValueError("Unsupported flash layout or encryption")

    work = HERE / ".pack"
    work.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(dir=work) as temp:
        stage = Path(temp)
        payload = stage / "firmware"
        payload.mkdir()
        images = []
        for r in roles:
            source = (BUILD / r["file"]).resolve()
            source.relative_to(BUILD)
            data = source.read_bytes()
            if not data:
                raise ValueError(f"Empty image: {source}")
            (payload / source.name).write_bytes(data)
            images.append(dict(file=source.name, offset=r["offset"],
                               sha256=hashlib.sha256(data).hexdigest()))
        manifest = dict(version=version, args=flash["write_flash_args"], images=images)
        (payload / "manifest.json").write_text(json.dumps(manifest, indent=2), "utf-8")
        name = f"HEX-Bridge-Updater-{version}"
        subprocess.run([sys.executable, "-m", "PyInstaller", "--onefile", "--windowed",
                        "--name", name, "--collect-all", "esptool",
                        "--add-data", f"{payload};firmware", "--specpath", str(stage),
                        "--distpath", str(stage), "--workpath", str(work / "cache"),
                        str(HERE / "updater.py")], check=True)
        exe = stage / (name + ".exe")
        subprocess.run([exe, "--self-test"], cwd=stage, check=True, timeout=120)
        release = HERE / "release"
        release.mkdir(exist_ok=True)
        exe.replace(release / exe.name)
        print(release / exe.name)


if __name__ == "__main__":
    package()
