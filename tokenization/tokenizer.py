"""Reference and trie implementations of greedy longest-match tokenization."""

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field

UNK_KEY = "<UNK>"


def tokenize(text: str, vocab: Mapping[str, int], unk_key: str = UNK_KEY) -> list[int]:
    """Choose the longest vocabulary entry at each position.

    Unknown characters each emit the reserved unknown ID. Empty entries are
    ignored; token IDs should be unique for unambiguous detokenization.
    """
    unknown_id = vocab[unk_key]
    max_length = max(map(len, vocab))
    result: list[int] = []
    start = 0
    while start < len(text):
        for end in range(min(len(text), start + max_length), start, -1):
            token_id = vocab.get(text[start:end])
            if token_id is not None:
                result.append(token_id)
                start = end
                break
        else:
            result.append(unknown_id)
            start += 1
    return result


def detokenize(
    tokens: Iterable[int],
    vocab: Mapping[str, int],
    unk_key: str = UNK_KEY,
    unknown_text: str = "?",
) -> str:
    """Join vocabulary text; replace reserved and unrecognized IDs."""
    reverse = {token_id: text for text, token_id in vocab.items()}
    reverse[vocab[unk_key]] = unknown_text
    return "".join(reverse.get(token_id, unknown_text) for token_id in tokens)


@dataclass(slots=True)
class _TrieNode:
    children: dict[str, "_TrieNode"] = field(default_factory=dict)
    token_id: int | None = None


class TrieTokenizer:
    """Compile a vocabulary once, with no dependency on later mapping edits."""

    def __init__(self, vocab: Mapping[str, int], unk_key: str = UNK_KEY) -> None:
        self._unknown_id = vocab[unk_key]
        self._root = _TrieNode()
        for text, token_id in vocab.items():
            node = self._root
            for char in text:
                if char not in node.children:
                    node.children[char] = _TrieNode()
                node = node.children[char]
            node.token_id = token_id

    def tokenize(self, text: str) -> list[int]:
        """Walk shared prefixes, retaining the last complete token match."""
        result: list[int] = []
        start = 0
        while start < len(text):
            node = self._root
            token_id = self._unknown_id
            next_start = start + 1
            for end in range(start, len(text)):
                child = node.children.get(text[end])
                if child is None:
                    break
                node = child
                if node.token_id is not None:
                    token_id = node.token_id
                    next_start = end + 1
            result.append(token_id)
            start = next_start
        return result
