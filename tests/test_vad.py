import unittest
import numpy as np
from hogwarts_voice.vad import AdaptiveSpeechSegmenter

SR=16000
def block(amp, duration=0.02):
    return (np.full(round(SR*duration), amp, dtype=np.int16)).tobytes()

class AdaptiveVADTests(unittest.TestCase):
    def test_quiet_gap_inside_word_does_not_split_word(self):
        vad=AdaptiveSpeechSegmenter(silence_ms=170)
        sequence=(
            [block(90)]*10 +
            [block(700)]*8 +
            [block(225)]*6 +   # 120ms quiet phoneme, still one word
            [block(1300)]*14 +
            [block(90)]*15
        )
        found=[r for pcm in sequence if (r:=vad.feed(pcm)) is not None]
        self.assertEqual(len(found),1)
        self.assertGreater(len(found[0]),15000)
    def test_very_short_click_is_rejected(self):
        vad=AdaptiveSpeechSegmenter()
        data=[block(100)]*10+[block(2300)]*2+[block(100)]*14
        self.assertEqual([r for pcm in data if (r:=vad.feed(pcm)) is not None],[])
    def test_quiet_normal_speech_is_accepted(self):
        vad=AdaptiveSpeechSegmenter()
        data=[block(75)]*12+[block(450)]*18+[block(75)]*12
        found=[r for pcm in data if (r:=vad.feed(pcm)) is not None]
        self.assertEqual(len(found),1)
    def test_noise_only_is_not_speech(self):
        vad=AdaptiveSpeechSegmenter()
        self.assertEqual([r for x in range(100) if (r:=vad.feed(block(150))) is not None],[])
    def test_second_word_after_pause(self):
        vad=AdaptiveSpeechSegmenter()
        sequence=([block(80)]*10+[block(1200)]*25+[block(80)]*12)*2
        found=[r for pcm in sequence if (r:=vad.feed(pcm)) is not None]
        self.assertEqual(len(found),2)

if __name__=="__main__":
    unittest.main()
