"""Check Windows .bat launchers have CRLF before publishing ZIP."""
from pathlib import Path
root = Path(__file__).resolve().parents[1]
for name in ("install.bat", "run.bat", "install-voice-id.bat"):
    content = (root / name).read_bytes()
    assert content.startswith(b"@echo off\r\n"), f"{name}: missing CRLF"
    assert b"\n" not in content.replace(b"\r\n", b""), f"{name}: mixed line endings"
    assert b"\x00" not in content, f"{name}: invalid NUL"
    print("[OK] Windows CRLF:", name)
