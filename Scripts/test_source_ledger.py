"""Source provenance is stable across checkout platforms, not content changes."""
import hashlib
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_source_ledger as ledger


class SourceLedgerTests(unittest.TestCase):
    def test_text_lf_and_crlf_have_identical_size_and_hash(self):
        for suffix in (".csv", ".txt"):
            with self.subTest(suffix=suffix), tempfile.TemporaryDirectory(dir=ledger.ROOT) as temporary:
                root = Path(temporary)
                path = root / ("source" + suffix)
                with patch.object(ledger, "ROOT", root):
                    path.write_bytes(b"block,district\n123,8\n")
                    linux = ledger.entry(path, "fixture")
                    path.write_bytes(b"block,district\r\n123,8\r\n")
                    self.assertEqual(ledger.entry(path, "fixture"), linux)
                    self.assertEqual(ledger.sha256(path), linux["sha256"])
                    path.write_bytes(b"block,district\r\n123,9\r\n")
                    self.assertNotEqual(ledger.entry(path, "fixture")["sha256"], linux["sha256"])

    def test_binary_bytes_are_not_normalized(self):
        with tempfile.TemporaryDirectory(dir=ledger.ROOT) as temporary:
            root = Path(temporary)
            path = root / "source.csv.gz"
            content = b"\x00\xff\r\n\rarchive"
            path.write_bytes(content)
            with patch.object(ledger, "ROOT", root):
                entry = ledger.entry(path, "fixture")
            self.assertEqual(entry["bytes"], len(content))
            self.assertEqual(entry["sha256"], hashlib.sha256(content).hexdigest())

    def test_json_review_hash_ignores_checkout_formatting_not_semantics(self):
        with tempfile.TemporaryDirectory(dir=ledger.ROOT) as temporary:
            path = Path(temporary) / 'review.json'
            path.write_bytes(b'{"a":1,"b":2}\n')
            first = ledger.ledger_bytes(path)
            path.write_bytes(b'{\r\n  "b": 2, "a": 1\r\n}\r\n')
            self.assertEqual(ledger.ledger_bytes(path), first)
            path.write_bytes(b'{"a":1,"b":3}')
            self.assertNotEqual(ledger.ledger_bytes(path), first)

    def test_text_preserves_lone_cr_and_whitespace(self):
        with tempfile.TemporaryDirectory(dir=ledger.ROOT) as temporary:
            path = Path(temporary) / "source.csv"
            path.write_bytes(b"a, b\rc,d\r\n")
            self.assertEqual(ledger.ledger_bytes(path), b"a, b\rc,d\n")


if __name__ == "__main__":
    unittest.main()
