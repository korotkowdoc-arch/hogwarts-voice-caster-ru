"""Conservative opt-in update checker and staged source downloader.

Only the owner's hardcoded GitHub repository is trusted. User preferences,
installed models, downloaded assets and game mods are never overwritten.
Downloads do NOT execute during staging. Installation occurs in a separate
process after the app has exited, with rollback on failed import.
"""
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
import io
import json
import os
import re
import subprocess
import sys
import tempfile
import urllib.request
import zipfile

REPO="korotkowdoc-arch/hogwarts-voice-caster-ru"
MAX_ZIP_BYTES=15_000_000
MAX_EXTRACT_BYTES=25_000_000
_AGENT="HogwartsVoiceCasterRU-Update/1.0"
_SEMVER=re.compile(r'__version__\s*=\s*["\\'](\d+\.\d+\.\d+)["\\']')
_SHA=re.compile(r"^[0-9a-f]{40}$")

@dataclass(frozen=True)
class Update:
    version: str
    sha: str

def version_tuple(v: str) -> tuple[int,int,int]:
    parts=v.split(".")
    if len(parts)!=3 or not all(x.isdigit() and len(x)<=5 for x in parts):
        raise ValueError("Invalid release version")
    return tuple(int(x) for x in parts)

def parse_version(source: str) -> str:
    match=_SEMVER.search(source)
    if not match:
        raise ValueError("No valid version in remote __init__.py")
    version_tuple(match.group(1))
    return match.group(1)

def _get(url, *, max_size=500_000) -> bytes:
    request=urllib.request.Request(url,headers={"User-Agent":_AGENT})
    with urllib.request.urlopen(request,timeout=30) as response:
        result=response.read(max_size+1)
    if len(result)>max_size:
        raise ValueError("Update source exceeds size limit")
    return result

def check_update(installed_version: str) -> Update | None:
    version_tuple(installed_version)
    record=json.loads(_get(
        f"https://api.github.com/repos/{REPO}/commits/main"))
    sha=record.get("sha","")
    if not isinstance(sha,str) or not _SHA.fullmatch(sha):
        raise ValueError("Unexpected GitHub commit ID")
    remote=_get(
        f"https://raw.githubusercontent.com/{REPO}/{sha}/"
        "src/hogwarts_voice/__init__.py",max_size=25000)
    newest=parse_version(remote.decode("utf-8"))
    if version_tuple(newest)<=version_tuple(installed_version):
        return None
    return Update(newest,sha)

def unpack_source_archive(archive: bytes, staged_root: Path) -> Path:
    """Extract ONLY safe source paths from the pinned commit zip."""
    folder=staged_root/"src"
    total=0
    count=0
    with zipfile.ZipFile(io.BytesIO(archive)) as stream:
        for info in stream.infolist():
            if info.is_dir():
                continue
            path=PurePosixPath(info.filename)
            parts=path.parts
            if (path.is_absolute() or
                    any(part in (".","..") for part in parts) or
                    len(parts)<4 or parts[1]!="src" or
                    info.flag_bits & 0x1):
                continue
            # GitHub archive format: {project}-{sha}/src/{package}/...
            # Never extract symlinks from a ZIP, even if GitHub is trusted.
            filetype=(info.external_attr >> 16) & 0o170000
            if filetype == 0o120000:
                raise ValueError("Symlink in source archive")
            total+=info.file_size
            count+=1
            if info.file_size>MAX_EXTRACT_BYTES or total>MAX_EXTRACT_BYTES or count>500:
                raise ValueError("Update archive too large")
            relative=Path(*parts[2:])
            if not relative.parts or relative.parts[0]!="hogwarts_voice":
                continue
            destination=folder.joinpath(relative)
            destination.parent.mkdir(parents=True,exist_ok=True)
            with stream.open(info) as src, destination.open("wb") as out:
                # Limit decompressed bytes on read as well as metadata.
                remaining=info.file_size
                while remaining:
                    chunk=src.read(min(remaining,1024*1024))
                    if not chunk:
                        raise ValueError("Truncated ZIP entry")
                    out.write(chunk)
                    remaining-=len(chunk)
    if not (folder/"hogwarts_voice"/"__init__.py").is_file():
        raise ValueError("Archive contains no Python application")
    if not (folder/"hogwarts_voice"/"ru_asr_listener.py").is_file():
        raise ValueError("Archive incomplete")
    return folder

def stage_update(update: Update, project_root: Path) -> Path:
    if not _SHA.fullmatch(update.sha):
        raise ValueError("Invalid update commit ID")
    project_root=Path(project_root).resolve()
    archive=_get(f"https://codeload.github.com/{REPO}/zip/{update.sha}",
                 max_size=MAX_ZIP_BYTES)
    stage=Path(tempfile.mkdtemp(prefix=".hvc-stage-",dir=project_root))
    try:
        folder=unpack_source_archive(archive,stage)
        actual=parse_version((folder/"hogwarts_voice"/"__init__.py").read_text(
            encoding="utf-8"))
        if actual!=update.version:
            raise ValueError("Update version changed during download")
        (stage/"manifest.json").write_text(json.dumps({
            "sha":update.sha,"version":update.version}),encoding="utf-8")
    except BaseException:
        import shutil
        shutil.rmtree(stage,ignore_errors=True)
        raise
    return stage

def launch_installer(stage: Path, root: Path) -> None:
    env=os.environ.copy()
    env["PYTHONPATH"]=str(root/"src")+os.pathsep+env.get("PYTHONPATH","")
    flags=getattr(subprocess,"CREATE_NO_WINDOW",0)
    subprocess.Popen([
        sys.executable,"-m","hogwarts_voice.update_helper",
        "--stage",str(stage),"--root",str(root),"--pid",str(os.getpid()),
    ],cwd=str(root),env=env,creationflags=flags,
       stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,
       stderr=subprocess.DEVNULL,close_fds=True)
