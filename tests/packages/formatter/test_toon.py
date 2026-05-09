"""TOON wrapper — confirm we hit the real 0.9.x encoder, not the 0.1.0 stub."""

from __future__ import annotations

import toon_format

from a2kit.packages.formatter.toon import encode_toon


class TestToonVersion:
    def test_real_encoder_pinned(self):
        # Round 8 Gotcha 2: 0.1.0 ships a NotImplementedError stub. The real
        # encoder is 0.9.x. Bail loudly if a future bump regresses.
        assert toon_format.__version__.startswith("0.9"), (
            f"toon_format must be pinned to 0.9.x; got {toon_format.__version__}. "
            "0.1.0 is the stub release with NotImplementedError encoders."
        )

    def test_encoder_actually_works(self):
        # If we ever land on the stub, this raises NotImplementedError instead
        # of returning a string.
        result = encode_toon({"a": 1})
        assert isinstance(result, str)
        assert result  # non-empty


class TestEncodeToonMatchesLibrary:
    """encode_toon must be byte-identical to toon_format.encode."""

    def test_flat_dict(self):
        v = {"a": 1, "b": "two"}
        assert encode_toon(v) == toon_format.encode(v)

    def test_list_of_dicts(self):
        v = [{"id": 1, "name": "alice"}, {"id": 2, "name": "bob"}]
        assert encode_toon(v) == toon_format.encode(v)

    def test_nested(self):
        v = {"outer": {"inner": [1, 2, 3]}, "tags": ["x", "y"]}
        assert encode_toon(v) == toon_format.encode(v)

    def test_scalar(self):
        assert encode_toon("hello") == toon_format.encode("hello")
        assert encode_toon(42) == toon_format.encode(42)

    def test_empty_collections(self):
        assert encode_toon({}) == toon_format.encode({})
        assert encode_toon([]) == toon_format.encode([])
