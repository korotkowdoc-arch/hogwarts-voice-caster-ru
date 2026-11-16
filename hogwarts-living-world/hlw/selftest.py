"""Offline smoke test packaged into the Windows executable.

Never touches game files, cloud networks, normal user database or API keys.
"""
from __future__ import annotations

import tempfile
from pathlib import Path

from .characters import compact_context
from .providers import DailyBudget, FreeRouter, NoFreeProvider
from .world import World

def run_smoke_test() -> bool:
    with tempfile.TemporaryDirectory(prefix="hlw-self-test-") as tmp:
        root=Path(tmp)
        world=World(root/"smoke.sqlite3")
        try:
            a=world.apply("selftest","sebastian","player_helped","smoke_1")
            b=world.apply("selftest","sebastian","player_helped","smoke_2")
            duplicate=world.apply("selftest","sebastian","player_helped","smoke_2")
            expected=(a["affinity"],b["affinity"],duplicate["duplicate"])==(12,24,True)
            context=world.context("selftest","sebastian")
            expected=expected and ("Себастьян" in context and "Игрок помог" in context)
            expected=expected and (sum(e["kind"]=="owl_letter_proposal"
                                      for e in world.pending("selftest",100))==1)
            backup=world.backup(root/"backup")
            expected=expected and backup.is_file() and world.integrity_check()=="ok"
        finally:
            world.db.close()
        router=FreeRouter(DailyBudget(root/"counts.json",{"gemini":1,"groq":1}),
                          transport=lambda *_args,**_kwargs:
                             (_ for _ in ()).throw(AssertionError("Network call forbidden")),
                          keys={})
        try:
            router.complete([{"role":"user","content":"Привет"}])
            expected=False
        except NoFreeProvider:
            pass
        return bool(expected)
