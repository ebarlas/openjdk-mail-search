import re

from params import IndexParams


def normalize(t):
    return re.sub(r'[^\w+#]+', '', t.lower())


class Indexer:
    def __init__(self, params: IndexParams):
        self.params = params

    def tokenize(self, text):
        tokens = [t.lower() for t in text.split() if len(t) <= self.params.max_token_length]
        return [t for t in tokens if not any(t.startswith(sp) for sp in self.params.stop_prefixes)]

    def normalize(self, t):
        return re.sub(r'[^\w+#]+', '', t)

    def normalize_and_filter(self, tokens):
        tokens = [self.normalize(t) for t in tokens]
        return [t for t in tokens if t and t not in self.params.stop_words]

    @staticmethod
    def ngrams(arr, start, limit):
        result = []
        for i in range(start, min(len(arr), start + limit)):
            result.append(arr[start:i + 1])
        return result

    def code_ngrams(self, arr):
        result = []
        for i in range(len(arr)):
            result.extend(Indexer.ngrams(arr, i, self.params.code_ngram_limit))
        return result

    def add_code_ngrams(self, terms, arr):
        for sub in self.code_ngrams(arr):
            # joining here ensures simple query-time matching based on normalized input
            # e.g. query for java.util.concurrent normalizes to javautilconcurrent
            n = self.normalize(''.join(sub))
            if n:
                term = [n]
                if len(terms) < self.params.max_code_terms and term not in terms:
                    terms.append(term)
        return terms

    def add_all_code_ngrams(self, terms, tokens):
        code_terms = []
        delimiters = ['/', '.', '=', '::']
        for t in tokens:
            for d in delimiters:
                if d in t:
                    self.add_code_ngrams(code_terms, t.split(d))
        for term in code_terms:
            if len(terms) < self.params.max_terms and term not in terms:
                terms.append(term)
        return terms

    def add_word_ngrams(self, terms, tokens, limit):
        for i in range(len(tokens)):
            sub = Indexer.ngrams(tokens, i, limit)
            for s in sub:
                if len(terms) < self.params.max_terms and s not in terms:
                    terms.append(s)
        return terms

    def index_field(self, terms, text, parse_code, all_ngrams, ngram_limit):
        tokens = self.tokenize(text)
        norm_tokens = self.normalize_and_filter(tokens)
        self.add_word_ngrams(terms, norm_tokens, ngram_limit)
        if all_ngrams:
            if norm_tokens:  # empty field
                if len(terms) < self.params.max_terms and norm_tokens not in terms:
                    terms.append(norm_tokens)
        if parse_code:  # lowest priority, in case max-terms reached
            self.add_all_code_ngrams(terms, tokens)

    def index(self, author, email, subject, body):
        targets = (
            (author, False, True, self.params.subject_ngram_limit),
            (email, False, True, self.params.subject_ngram_limit),
            (subject, False, True, self.params.subject_ngram_limit),
            (body, True, False, self.params.word_ngram_limit)
        )
        terms = []
        for text, parse_code, all_ngrams, ngram_limit in targets:
            self.index_field(terms, text, parse_code, all_ngrams, ngram_limit)
        return terms
