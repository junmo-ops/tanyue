import pathlib
import tempfile
import unittest

from forum_backend.db import init_db
from forum_backend.services.words import query_title_words


class RandomWordsTests(unittest.TestCase):
    def test_random_batch_filters_noise_and_returns_only_words(self):
        with tempfile.TemporaryDirectory() as directory:
            path = str(pathlib.Path(directory) / 'forum.db')
            conn = init_db(path)
            try:
                for index in range(45):
                    word = '主题' + chr(0x4e00 + index)
                    for repeat in range(3):
                        conn.execute('INSERT INTO threads (tid, title) VALUES (?, ?)',
                                     (f'{index}-{repeat}', f'{word} 合集 12345 ABC'))
                conn.execute("INSERT INTO threads (tid, title) VALUES ('rare', '孤立词语')")
                conn.commit()
            finally:
                conn.close()
            first = query_title_words(path, {'mode': 'random'})
            second = query_title_words(path, {'mode': 'random'})
            self.assertEqual(first['mode'], 'random')
            self.assertEqual(len(first['items']), 30)
            words = [item['word'] for item in first['items']]
            self.assertEqual(len(set(words)), 30)
            self.assertTrue(all(word.startswith('主题') for word in words))
            self.assertTrue(all(set(item) == {'word'} for item in first['items']))
            self.assertNotEqual(first['items'], second['items'])

    def test_empty_database(self):
        with tempfile.TemporaryDirectory() as directory:
            path = str(pathlib.Path(directory) / 'forum.db')
            init_db(path).close()
            self.assertEqual(query_title_words(path, {'mode': 'random'})['items'], [])
