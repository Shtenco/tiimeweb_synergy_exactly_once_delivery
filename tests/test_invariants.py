import unittest
from experiments.exactly_once_lab import fingerprint, quantile

class TestExactlyOnceHelpers(unittest.TestCase):
    def test_fingerprint_is_deterministic(self):
        self.assertEqual(fingerprint('payload'),fingerprint('payload'))
        self.assertNotEqual(fingerprint('payload'),fingerprint('changed'))
    def test_quantile(self):
        self.assertEqual(quantile([1,3,5],50),3)

if __name__ == '__main__': unittest.main()
