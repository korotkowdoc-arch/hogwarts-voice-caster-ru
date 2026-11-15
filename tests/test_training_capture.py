"""Training and live PTT must share the one-press-one-phrase contract."""
import unittest
from unittest.mock import patch
from hogwarts_voice.training_capture import capture_one_hold, TrainingTimeout
from hogwarts_voice.ptt import PushToTalkCapture

class FakeClock:
    def __init__(self):
        self.t = 0.0
        self.callback = None
        self.pressed = False
    def now(self):
        return self.t
    def sleep(self, dt):
        self.t += .02
        self.pressed = .10 <= self.t < .72
        if self.callback:
            self.callback(b"\x11\x11" * 320, 320, None, None)
    def key(self, key):
        return self.pressed
    def stream(self, **kwargs):
        self.callback = kwargs["callback"]
        return self
    def __enter__(self):
        return self
    def __exit__(self, *args):
        self.callback = None

class HoldTrainingTests(unittest.TestCase):
    def test_training_uses_same_16k_int16_hold_protocol(self):
        fake = FakeClock()
        changes = []
        pcm = capture_one_hold(
            device=None, key="F9", key_is_down=fake.key,
            stream_factory=fake.stream, clock=fake.now, sleep=fake.sleep,
            state_callback=changes.append,
        )
        self.assertGreater(len(pcm), 14000)
        self.assertLess(len(pcm), 22000)
        self.assertTrue(any("ЗАПИСЬ" in x for x in changes))
        self.assertTrue(any("Образец" in x for x in changes))

    def test_timeout_without_press(self):
        fake = FakeClock()
        fake.key = lambda vk: False
        with self.assertRaises(TrainingTimeout):
            capture_one_hold(
                key_is_down=fake.key, stream_factory=fake.stream,
                clock=fake.now, sleep=fake.sleep, wait_seconds=.25,
            )

if __name__ == "__main__":
    unittest.main()
