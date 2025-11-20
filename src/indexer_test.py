import unittest

from indexer import Indexer
from params import IndexParams


class TestIndexer(unittest.TestCase):
    def test_indexer(self):
        params = IndexParams(
            max_token_length=50,
            word_ngram_limit=2,
            code_ngram_limit=3,
            subject_ngram_limit=2,
            max_terms=100,
            max_code_terms=6,
            stop_words=['the', 'is', 'of'],
            stop_prefixes=[],
            stop_terms=[],
            stop_lines=[],
            stop_func=lambda m: False
        )

        idx = Indexer(params)

        self.assertEqual(idx.tokenize('a b c'), ['a', 'b', 'c'])
        self.assertEqual(idx.tokenize('a b ' + 'c' * 51), ['a', 'b'])

        self.assertEqual(idx.normalize('ABC'), 'ABC')
        self.assertEqual(idx.normalize('a % b'), 'ab')
        self.assertEqual(idx.normalize('a + b'), 'a+b')
        self.assertEqual(idx.normalize('a # b'), 'a#b')

        self.assertEqual(idx.code_ngrams(['a']), [['a']])
        self.assertEqual(idx.code_ngrams(['a', 'b']), [['a'], ['a', 'b'], ['b']])
        self.assertEqual(
            idx.code_ngrams(['a', 'b', 'c', 'd']),
            [['a'], ['a', 'b'], ['a', 'b', 'c'], ['b'], ['b', 'c'], ['b', 'c', 'd'], ['c'], ['c', 'd'], ['d']])

        self.assertEqual(idx.add_code_ngrams([['a']], ['a']), [['a']])
        self.assertEqual(idx.add_code_ngrams([['a']] * 100, ['x']), [['a']] * 100)
        self.assertEqual(idx.add_code_ngrams([], ['abc', 'x % y']), [['abc'], ['abcxy'], ['xy']])
        self.assertEqual(
            idx.add_code_ngrams([], ['java', 'util', 'concurrent']),
            [['java'], ['javautil'], ['javautilconcurrent'], ['util'], ['utilconcurrent'], ['concurrent']])
        self.assertEqual(
            idx.add_code_ngrams([], ['java', 'util', 'concurrent', 'map']),
            [['java'], ['javautil'], ['javautilconcurrent'], ['util'], ['utilconcurrent'], ['utilconcurrentmap']])

        self.assertEqual(
            idx.add_all_code_ngrams([], ['java.util.concurrent']),
            [['java'], ['javautil'], ['javautilconcurrent'], ['util'], ['utilconcurrent'], ['concurrent']])

        self.assertEqual(idx.add_word_ngrams([], ['a', 'a', 'a'], 2), [['a'], ['a', 'a']])
        self.assertEqual(idx.add_word_ngrams([], ['a', 'b', 'c'], 2), [['a'], ['a', 'b'], ['b'], ['b', 'c'], ['c']])

        author = 'James Gosling'
        email = 'james.gosling@sun.com'
        subject = 'Introducing the Java Programming Language'
        body = '''Greetings!
        
        Behold the following example of Java:
        
        public static void main(String[] args) {
          System.out.println("Hello, world!");
        }'''
        self.assertEqual(
            idx.index(author=author, email=email, subject=subject, body=body),
            [
                ['james'], ['james', 'gosling'], ['gosling'],
                ['jamesgoslingsuncom'],
                ['introducing'], ['introducing', 'java'], ['java'], ['java', 'programming'], ['programming'],
                    ['programming', 'language'], ['language'], ['introducing', 'java', 'programming', 'language'],
                ['greetings'], ['greetings', 'behold'], ['behold'], ['behold', 'following'], ['following'],
                    ['following', 'example'], ['example'], ['example', 'java'], ['java', 'public'], ['public'],
                    ['public', 'static'], ['static'], ['static', 'void'], ['void'], ['void', 'mainstring'],
                    ['mainstring'], ['mainstring', 'args'], ['args'], ['args', 'systemoutprintlnhello'],
                    ['systemoutprintlnhello'], ['systemoutprintlnhello', 'world'], ['world'], ['system'],
                    ['systemout'], ['out'], ['outprintlnhello'], ['printlnhello']
            ])

if __name__ == '__main__':
    unittest.main()
