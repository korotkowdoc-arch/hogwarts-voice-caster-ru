"""Safe speculative preprocessing for hold-to-cast on a single offline ASR.

Never dispatch before button release. If a stable trailing quiet period is
heard while held, submit a preview on the existing ASR worker. Reuse it only
when NO more speech was detected before release; otherwise decode the whole
phrase after release. Silent audio and untrained noise cannot send commands.
"""
from __future__ import annotations
import audioop

class EarlyDecode:
    def __init__(self, *, minimum_ms=380, quiet_ms=210, speech_rms=360):
        self.minimum_ms=minimum_ms
        self.quiet_ms=quiet_ms
        self.speech_rms=speech_rms
        self.reset()

    def reset(self):
        self.duration_ms=0.
        self.quiet_duration_ms=0.
        self.speech_samples=0
        self.future=None
        self.invalidated=False
        self.preview_bytes=0

    def feed(self, pcm: bytes, *, snapshot, submit):
        """snapshot returns all PCM recorded so far; submit returns Future.

        Feed AFTER the PCM was appended to PushToTalkCapture.
        """
        if not pcm or len(pcm)%2:
            return
        block_ms=len(pcm)/32.0   # 16000 mono samples/s * 2 bytes
        self.duration_ms+=block_ms
        active=audioop.rms(pcm,2)>=self.speech_rms
        if active:
            self.speech_samples+=len(pcm)//2
            self.quiet_duration_ms=0
            if self.future is not None:
                self.invalidated=True
        else:
            self.quiet_duration_ms+=block_ms
        if (self.future is None and self.speech_samples>=3200
                and self.duration_ms>=self.minimum_ms
                and self.quiet_duration_ms>=self.quiet_ms):
            data=snapshot()
            if data:
                self.preview_bytes=len(data)
                self.future=submit(data)

    def release_future(self, pcm: bytes):
        """Return reusable inference Future or None (trigger full decode)."""
        result=self.future if not self.invalidated else None
        if result is not None and len(pcm)<self.preview_bytes:
            result=None
        self.reset()
        return result
