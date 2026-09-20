from random import Random

import pytest

from tokenization.tokenizer import UNK_KEY, TrieTokenizer, detokenize, tokenize


@pytest.mark.parametrize(
    "text, expected",
    [
        ("", []),
        ("abcx", [3, 5]),
        ("abzbc", [2, -1, 4]),
        ("UNKabcq", [0, 3, -1]),
        ("zz", [-1, -1]),
        ("ababc", [2, 3]),
        ("<UNK>", [-1]),
    ],
)
def test_longest_match_and_unknown_characters(text, expected):
    vocab = {"a": 1, "ab": 2, "abc": 3, "bc": 4, "x": 5, "UNK": 0, UNK_KEY: -1}
    assert tokenize(text, vocab) == expected
    assert TrieTokenizer(vocab).tokenize(text) == expected


def test_partial_prefix_falls_back_to_last_complete_token():
    vocab = {"a": 0, "abcdef": 1, "bc": 2, UNK_KEY: -1}
    assert tokenize("abcdx", vocab) == [0, 2, -1, -1]
    assert TrieTokenizer(vocab).tokenize("abcdx") == [0, 2, -1, -1]


def test_unicode_uses_code_points_without_normalization():
    vocab = {"é": 1, "猫": 2, "猫🐈": 3, UNK_KEY: 0}
    text = "é猫🐈e\u0301"
    assert tokenize(text, vocab) == [1, 3, 0, 0]
    assert TrieTokenizer(vocab).tokenize(text) == [1, 3, 0, 0]


def test_custom_unknown_key_and_empty_entries():
    vocab = {"?": 9, "": 1, "a": 0}
    assert tokenize("az?", vocab, "?") == [0, 9, 9]
    assert TrieTokenizer(vocab, "?").tokenize("az?") == [0, 9, 9]
    assert detokenize([0, 9, 100], vocab, "?", "[unknown]") == "a[unknown][unknown]"


def test_trie_retains_compiled_vocabulary_after_caller_mutation():
    vocab = {"a": 1, UNK_KEY: 0}
    trie = TrieTokenizer(vocab)
    vocab.update({"a": 2, "b": 3, UNK_KEY: -1})
    assert trie.tokenize("ab") == [1, 0]


def test_detokenize_accepts_iterator_and_handles_unknown_ids():
    vocab = {"a": 0, "bc": 1, UNK_KEY: 2}
    assert detokenize(iter([0, 1, 2, 999]), vocab) == "abc??"
    assert detokenize(tokenize("abca", vocab), vocab) == "abca"


def test_missing_reserved_key_raises_key_error():
    with pytest.raises(KeyError):
        tokenize("a", {"a": 1})
    with pytest.raises(KeyError):
        TrieTokenizer({"a": 1})


def test_generated_inputs_match_independent_vocabulary_scan():
    random = Random(42)
    for _ in range(500):
        words = {
            "".join(random.choices("abc猫", k=random.randint(1, 6))) for _ in range(20)
        }
        vocab = {word: index for index, word in enumerate(sorted(words))}
        vocab[UNK_KEY] = -1
        text = "".join(random.choices("abc猫?", k=random.randint(0, 80)))
        expected = []
        position = 0
        while position < len(text):
            matches = [word for word in words if text.startswith(word, position)]
            if matches:
                word = max(matches, key=len)
                expected.append(vocab[word])
                position += len(word)
            else:
                expected.append(-1)
                position += 1
        assert tokenize(text, vocab) == expected
        assert TrieTokenizer(vocab).tokenize(text) == expected
