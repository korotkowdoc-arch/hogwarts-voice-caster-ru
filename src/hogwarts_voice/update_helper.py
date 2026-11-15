"""Out-of-process atomic-ish source update with rollback.

Called only from the updater button, and only after user confirmation.
Waits for the GUI to EXIT before swapping any Python code.
"""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
import uuid

def parent_stopped(pid: int, *, timeout=45.0) -> bool:
    if pid<=0:
        return False
    if os.name=="nt":
        import ctypes
        SYNCHRONIZE=0x00100000
        kernel=ctypes.WinDLL("kernel32",use_last_error=True)
        kernel.OpenProcess.argtypes=[ctypes.c_ulong,ctypes.c_int,ctypes.c_ulong]
        kernel.OpenProcess.restype=ctypes.c_void_p
        kernel.WaitForSingleObject.argtypes=[ctypes.c_void_p,ctypes.c_ulong]
        kernel.WaitForSingleObject.restype=ctypes.c_ulong
        kernel.CloseHandle.argtypes=[ctypes.c_void_p]
        handle=kernel.OpenProcess(SYNCHRONIZE,False,pid)
        if not handle:
            return True  # old process is already gone
        try:
            return kernel.WaitForSingleObject(handle,int(timeout*1000))==0
        finally:
            kernel.CloseHandle(handle)
    deadline=time.monotonic()+timeout
    while time.monotonic()<deadline:
        try:
            os.kill(pid,0)
        except ProcessLookupError:
            return True
        time.sleep(.1)
    return False

def install_source(stage: Path, root: Path, *, verify=None) -> Path:
    """Only src/ is replaced; config, models, run.bat and user files survive."""
    stage=Path(stage).resolve()
    root=Path(root).resolve()
    new=stage/"src"
    original=root/"src"
    if not new.is_dir() or not (new/"hogwarts_voice"/"__init__.py").is_file():
        raise ValueError("Staged application missing")
    if not original.is_dir() or not (original/"hogwarts_voice"/"__init__.py").exists():
        raise ValueError("Current install missing")
    if stage.parent!=root or not stage.name.startswith(".hvc-stage-"):
        raise ValueError("Untrusted staging directory")
    backups=root/".hvc-backups"
    backups.mkdir(exist_ok=True)
    backup=backups/(time.strftime("%Y%m%d-%H%M%S")+
                    "-"+uuid.uuid4().hex[:10])
    backup.mkdir(exist_ok=False)
    saved=backup/"src"
    shutil.move(str(original),str(saved))
    try:
        shutil.move(str(new),str(original))
        if verify is not None:
            verify(original)
        else:
            cmd=[sys.executable,"-c",
                 "from hogwarts_voice.ru_asr_listener import run; "
                 "from hogwarts_voice.ui import App; print('OK')"]
            env=os.environ.copy()
            env["PYTHONPATH"]=str(original)+os.pathsep+env.get("PYTHONPATH","")
            subprocess.run(cmd,env=env,cwd=root,timeout=20,check=True,
                           stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        return backup
    except BaseException:
        # Restore BOTH the installed app and the staged candidate. A failed
        # smoke test must never leave the user unable to retry the update.
        if original.exists():
            new.parent.mkdir(parents=True,exist_ok=True)
            if new.exists():
                shutil.rmtree(new)
            shutil.move(str(original),str(new))
        shutil.move(str(saved),str(original))
        raise

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--stage",type=Path,required=True)
    parser.add_argument("--root",type=Path,required=True)
    parser.add_argument("--pid",type=int,required=True)
    args=parser.parse_args()
    root=args.root.resolve()
    logfile=root/"last-update.log"
    if not parent_stopped(args.pid):
        logfile.write_text("Update cancelled: application did not exit",
                           encoding="utf-8")
        return 2
    try:
        backup=install_source(args.stage,root)
        manifest=json.loads((args.stage/"manifest.json").read_text(encoding="utf-8"))
        logfile.write_text(
            f"Installed {manifest['version']} {manifest['sha']}\n"
            f"Backup: {backup}\n",encoding="utf-8")
        shutil.rmtree(args.stage,ignore_errors=True)
        # Do not reinstall packages or replace the user's settings.
        launcher=root/"run.bat"
        if os.name=="nt" and launcher.is_file():
            subprocess.Popen(["cmd","/c",str(launcher)],cwd=str(root),
                             creationflags=getattr(subprocess,"CREATE_NO_WINDOW",0),
                             stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL)
        return 0
    except BaseException as exc:
        logfile.write_text(f"Update failed, rollback attempted: {exc}",
                           encoding="utf-8")
        return 1

if __name__=="__main__":
    raise SystemExit(main())
