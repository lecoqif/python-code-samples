"""Reproducible microbenchmark: python -m tokenization.benchmark."""

import argparse
import platform
from random import Random
from statistics import median
from timeit import repeat

from tokenization.tokenizer import UNK_KEY, TrieTokenizer, tokenize


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--length", type=int, default=10000)
    parser.add_argument("--repeats", type=int, default=5)
    args = parser.parse_args()
    if args.length < 1 or args.repeats < 1:
        parser.error("length and repeats must be positive")

    random = Random(42)
    words = sorted(
        {"".join(random.choices("abcdef", k=random.randint(1, 12))) for _ in range(500)}
    )
    vocab = {word: index for index, word in enumerate(words)}
    vocab[UNK_KEY] = -1
    trie = TrieTokenizer(vocab)
    cases = {
        "mixed text": "".join(random.choices("abcdef?", k=args.length)),
        "unknown text": "?" * args.length,
    }
    print(
        f"{platform.python_implementation()} {platform.python_version()}, {len(vocab)} entries"
    )
    build = median(repeat(lambda: TrieTokenizer(vocab), number=1, repeat=args.repeats))
    print(f"Trie construction: {build * 1000:.3f} ms (median of {args.repeats})")
    for name, text in cases.items():
        assert tokenize(text, vocab) == trie.tokenize(text)
        reference = median(
            repeat(lambda: tokenize(text, vocab), number=1, repeat=args.repeats)
        )
        compiled = median(
            repeat(lambda: trie.tokenize(text), number=1, repeat=args.repeats)
        )
        print(
            f"{name}, {len(text)} characters: reference={reference * 1000:.3f} ms, trie={compiled * 1000:.3f} ms"
        )


if __name__ == "__main__":
    main()
