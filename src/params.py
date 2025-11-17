from dataclasses import dataclass
from typing import Callable, Any

import stops


@dataclass
class IndexParams:
    max_token_length: int # max characters per token, applied immediately after word splitting
    word_ngram_limit: int # max number of tokens (words) per n-gram (phrase) for mail body
    code_ngram_limit: int # max number of tokens (words) per n-gram (phrase) for code fragments
    subject_ngram_limit: int # max number of tokens (words) per n-gram (phrase) for mail subject
    max_terms: int # max terms per mail document
    max_code_terms: int # max terms from code fragment parsing
    stop_words: list[str] # tokens in this list are removed (except for code segmentation)
    stop_prefixes: list[str] # tokens that have a prefix in this list are removed immediately
    stop_terms: list[str] # terms in this list are removed during a terminal step in the pipeline
    stop_lines: list[str] #  lines that start with one of these regexes are ignored prior to tokenization
    stop_func: Callable[[Any], bool] # mail documents are not indexes that evaluate true


DEFAULT_PARAMS = IndexParams(
    max_token_length=100,
    word_ngram_limit=3,
    code_ngram_limit=10,
    subject_ngram_limit=5,
    max_terms=2500,
    max_code_terms=100,
    stop_words=stops.STOP_WORDS,
    stop_prefixes=stops.STOP_PREFIXES,
    stop_terms=stops.STOP_TERMS,
    stop_lines=stops.STOP_LINES,
    stop_func=stops.STOP_FUNC
)
