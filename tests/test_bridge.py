import unittest
import struct
from hogwarts_voice.bridge import SpellBridge, SIZE, WRITE, READ, CONSUMER_HB, DROPPED, TOTAL

class DummyMap:
    def __init__(self, size):
        self.buf = bytearray(size)
    def __getitem__(self, k):
        return self.buf[k]
    def __setitem__(self, k, v):
        self.buf[k] = v
    def close(self):
        pass

class BridgeTests(unittest.TestCase):
    def setUp(self):
        self.mem = DummyMap(SIZE)
        self.bridge = SpellBridge(self.mem).connect()

    def test_heartbeat_requires_live_consumer(self):
        self.assertFalse(self.bridge.alive())
        struct.pack_into("<I", self.mem.buf, CONSUMER_HB, 1)
        self.assertTrue(self.bridge.poll(now=100.0))
        self.assertTrue(self.bridge.alive(now=101.0))
        self.assertFalse(self.bridge.alive(now=102.1))

    def test_ring_command_layout(self):
        struct.pack_into("<I", self.mem.buf, CONSUMER_HB, 1)
        self.bridge.poll(now=100.0)
        self.assertEqual(self.bridge.send("Lumos", now=100.1), (True, "sent"))
        self.assertEqual(struct.unpack_from("<I", self.mem.buf, WRITE)[0], 1)
        self.assertEqual(struct.unpack_from("<I", self.mem.buf, TOTAL)[0], 1)
        self.assertEqual(self.mem.buf[64:69], b"Lumos")
        self.assertEqual(struct.unpack_from("<I", self.mem.buf, 64+28)[0], 0)

    def test_queue_full(self):
        struct.pack_into("<I", self.mem.buf, CONSUMER_HB, 1)
        self.bridge.poll(now=100)
        struct.pack_into("<I", self.mem.buf, WRITE, 255)
        self.assertEqual(self.bridge.send("Lumos", now=100), (False, "command queue full"))
        self.assertEqual(struct.unpack_from("<I", self.mem.buf, DROPPED)[0], 1)

    def test_invalid_name(self):
        struct.pack_into("<I", self.mem.buf, CONSUMER_HB, 1)
        self.bridge.poll(now=100)
        self.assertFalse(self.bridge.send("люмос", now=100)[0])

if __name__ == "__main__":
    unittest.main()
