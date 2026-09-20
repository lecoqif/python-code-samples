# Longest-match vocabulary tokenizer

[Implementation](tokenizer.py) · [Tests](test_tokenizer.py) · [Benchmark](benchmark.py)

Two implementations of the same greedy policy: a small reference that checks
candidate substrings, and a trie that reuses vocabulary prefixes. At each input
position, choose the longest complete vocabulary entry. If none matches, emit
one unknown ID and advance by one Unicode code point.

```python
from tokenization.tokenizer import TrieTokenizer, detokenize

vocab = {"a": 1, "ab": 2, "bc": 3, "<UNK>": 0}
tokenizer = TrieTokenizer(vocab)
assert tokenizer.tokenize("abzbc") == [2, 0, 3]
assert detokenize([2, 0, 3], vocab) == "ab?bc"
```

The reserved unknown key must exist. A literal `UNK` entry is an ordinary token;
the default reserved key is `<UNK>`. Empty entries are ignored, token ID zero
works normally, and unknown IDs detokenize to a configurable replacement.
Vocabulary IDs should be unique for unambiguous decoding. Unknown characters
are lossy, and Unicode normalization is left to the caller. This is a fixed
vocabulary tokenizer; it has no vocabulary-training or merge-learning stage.

The compiled trie owns its nodes and unknown ID, so later edits to the caller's
mapping cannot change its behavior. The reference limits substring candidates
to the maximum vocabulary-entry length. For input length N and maximum token
length L, the reference takes O(N L²) worst-case character work, including
substring construction and hashing, plus O(V) to find L across V entries. Trie
tokenization takes O(N L) worst-case work; it can revisit a prefix after a failed
longer match. Building and storing the trie takes O(S), where S is the total
number of vocabulary characters. Both return a list of IDs.

## Verification and comparison

```sh
.venv/bin/python run_samples.py tokenizer
.venv/bin/python -m tokenization.benchmark
```

Fourteen tests cover overlapping prefixes, failed longer matches, Unicode,
unknowns, empty input, caller mutation, and decoding. One test checks 500 seeded
generated cases against an independent vocabulary-scan oracle as well as both
implementations.

The benchmark uses seed 42, 453 vocabulary entries, 10,000 input characters per
case, and five repetitions. It checks identical output before timing and reports
median durations. One local CPython 3.13.7 run measured:

- Trie construction: 0.423 ms.
- Mixed text: reference 6.341 ms; compiled trie 1.948 ms.
- Unknown-only text: reference 9.625 ms; compiled trie 1.592 ms.

These are workload-specific observations, not speed guarantees. Construction is
reported separately; the trie tokenization timings reuse the compiled vocabulary.
Short inputs or different vocabularies can change the tradeoff. No benchmark
threshold is part of the tests.
