import re

STOP_WORDS = {"a", "an", "and", "are", "as", "at", "be", "but", "by", "for", "if", "in", "into", "is", "it", "no",
              "not", "of", "on", "or", "such", "that", "the", "their", "then", "there", "these", "they", "this", "to",
              "was", "will", "with"}


def tokenize(text):
    return text.split()


def normalize(t):
    return re.sub(r'[^\w+#]+', '', t.lower())


def normalize_and_filter(tokens):
    tokens = [normalize(t) for t in tokens]
    return [t for t in tokens if t and t not in STOP_WORDS]


def sub_ranges(arr):
    result = []
    for i in range(len(arr)):
        for j in range(i + 1, len(arr) + 1):
            result.append(arr[i:j])
    return result


def ngrams_from(arr, start, limit):
    result = []
    for i in range(start, min(len(arr), start + limit)):
        result.append(arr[start:i + 1])
    return result


def add_segment_ngrams(terms, arr, max_terms):
    for sub in sub_ranges(arr):
        n = normalize(''.join(sub))
        if n:
            term = [n]
            if len(terms) < max_terms and term not in terms:
                terms.append(term)


def add_delimited_tokens(terms, tokens, max_terms):
    delimiters = ['/', '.', '=', '::']
    for t in tokens:
        for d in delimiters:
            if d in t:
                add_segment_ngrams(terms, t.split(d), max_terms)


def add_sub_ranges_ahead(terms, tokens, limit, max_terms):
    for i in range(len(tokens)):
        sub = ngrams_from(tokens, i, limit)
        for s in sub:
            if len(terms) < max_terms and s not in terms:
                terms.append(s)


def index_field(terms, text, parse_code, all_ngrams, ngram_length, max_terms):
    tokens = tokenize(text)
    norm_tokens = normalize_and_filter(tokens)
    if all_ngrams:
        if len(terms) < max_terms and norm_tokens not in terms:
            terms.append(norm_tokens)
    add_sub_ranges_ahead(terms, norm_tokens, ngram_length, max_terms)
    if parse_code: # lowest priority, in case max-terms reached
        add_delimited_tokens(terms, tokens, max_terms)


def index(author, email, subject, body, ngram_length, max_terms):
    targets = (
        (author, False, True),
        (email, False, True),
        (subject, False, True),
        (body, True, False)
    )
    terms = []
    for text, parse_code, all_ngrams in targets:
        index_field(terms, text, parse_code, all_ngrams, ngram_length, max_terms)
    return terms
