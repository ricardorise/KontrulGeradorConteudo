import importlib
import json
import sys
import tempfile
import types
import unittest
from pathlib import Path

HERE = Path(__file__).parent
package = types.ModuleType('papo_fuzzy_test'); package.__path__ = [str(HERE)]; sys.modules['papo_fuzzy_test'] = package
if 'papo_fuzzy_test.pipeline' not in sys.modules:
    try:
        importlib.import_module('papo_fuzzy_test.pipeline')
    except Exception:  # fora do servidor: stub mínimo
        stub = types.ModuleType('papo_fuzzy_test.pipeline')
        stub.command = lambda *a, **k: (_ for _ in ()).throw(AssertionError('o cache deve evitar a GPU'))
        sys.modules['papo_fuzzy_test.pipeline'] = stub
a = importlib.import_module('papo_fuzzy_test.phrase_alignment')

REAL = json.loads((HERE / 'fixtures' / 'whisperx_run.json').read_text())
REAL_SCRIPT = (HERE / 'fixtures' / 'roteiro.txt').read_text()
REAL_WORDS = REAL.get('word_segments') or [w for s in REAL['segments'] for w in s['words']]


def words(text, step=1.0, score=.9):
    return [dict(word=w, start=round(i * step, 3), end=round(i * step + .5, 3), score=score) for i, w in enumerate(text.split())]


def run_resolve(script, transcript_words, phrases):
    with tempfile.TemporaryDirectory() as folder:
        run = Path(folder); audio = run / 'narracao.wav'; audio.write_bytes(b'fixture')
        (run / 'roteiro.txt').write_text(script)
        (run / 'alinhamento-whisperx.json').write_text(json.dumps({'word_segments': transcript_words}))
        (run / 'alinhamento-whisperx.sha256').write_text(a.hashlib.sha256(audio.read_bytes()).hexdigest())
        assets = dict(brolls=[dict(source='b.mp4', phrase=p, at=None, duration=None) for p in phrases])
        out = a.resolve(assets, dict(run=folder, audio=str(audio)))
        report = json.loads((run / 'alinhamento-frases.json').read_text())
        return out['brolls'], report


class NumberTests(unittest.TestCase):
    def test_number_words(self):
        cases = {0: 'zero', 21: 'vinte e um', 100: 'cem', 101: 'cento e um', 349: 'trezentos e quarenta e nove',
                 599: 'quinhentos e noventa e nove', 1000: 'mil', 1200: 'mil e duzentos', 2026: 'dois mil e vinte e seis',
                 1234: 'mil duzentos e trinta e quatro', 1000000: 'um milhão'}
        for n, words_ in cases.items():
            self.assertEqual(a.number_words(n), words_, n)

    def test_spoken_tokens_unify_digits_and_words(self):
        self.assertEqual(a.spoken_tokens('Quest 3S'), a.spoken_tokens('Quest três S'))
        self.assertEqual(a.spoken_tokens('349 dólares'), a.spoken_tokens('trezentos e quarenta e nove dólares'))


class RealTranscriptTests(unittest.TestCase):
    """Dados reais de uma execução que falhava com a comparação exata."""

    def test_the_three_phrases_that_failed_are_now_located(self):
        phrases = ['o Quest três S, o modelo', 'Esse tá saindo por trezentos', 'Ou seja, quase o dobro do três']
        with tempfile.TemporaryDirectory() as folder:
            run = Path(folder); audio = run / 'narracao.wav'; audio.write_bytes(b'x')
            (run / 'roteiro.txt').write_text(REAL_SCRIPT)
            (run / 'alinhamento-whisperx.json').write_text(json.dumps(REAL))
            (run / 'alinhamento-whisperx.sha256').write_text(a.hashlib.sha256(audio.read_bytes()).hexdigest())
            assets = dict(brolls=[dict(source='b.mp4', phrase=p, at=None, duration=None) for p in phrases])
            resolved = a.resolve(assets, dict(run=folder, audio=str(audio)))['brolls']
            report = json.loads((run / 'alinhamento-frases.json').read_text())
        times = [b['at'] for b in resolved]
        self.assertEqual(times, sorted(times))  # na ordem em que aparecem na narração
        self.assertTrue(all(r['similarity'] >= a.MIN_SCORE for r in report))
        self.assertIn('trezentos', report[1]['heard'])
        # 1ª frase: começa na palavra "O" logo antes de "Quest 3," (horário real do WhisperX)
        index = next(i for i, w in enumerate(REAL_WORDS) if w['word'].lower().startswith('quest') and REAL_WORDS[i + 1]['word'].startswith('3'))
        self.assertEqual(times[0], REAL_WORDS[index - 1]['start'])

    def test_phrase_not_in_audio_is_rejected_with_what_was_heard(self):
        with self.assertRaisesRegex(ValueError, 'não encontrou a frase'):
            run_resolve('Olá mundo. Frase totalmente diferente aqui.', words('olá mundo'), ['Frase totalmente diferente aqui'])


class MatchingTests(unittest.TestCase):
    def test_asr_numeric_and_word_differences_still_match(self):
        script = 'O preço caiu de trezentos e quarenta e nove dólares para duzentos e noventa e seis dólares hoje.'
        heard = words('O preço caiu de 349 dólares para 296 dólares hoje.')
        out, report = run_resolve(script, heard, ['caiu de trezentos e quarenta e nove dólares'])
        self.assertEqual(out[0]['at'], 2.0)  # "caiu"
        self.assertGreaterEqual(report[0]['similarity'], .95)

    def test_position_hint_picks_the_right_one_among_similar_sentences(self):
        script = 'Primeiro a gente vê o preço caiu bastante. ' + 'blá ' * 30 + 'No final o preço caiu bastante mesmo.'
        script = script.replace('Primeiro a gente vê o preço caiu bastante.', 'Primeiro a gente vê isso e o preço caiu bastante.')
        heard = words(script, step=1.0)
        out, _ = run_resolve(script, heard, ['final o preço caiu bastante mesmo'])
        late = next(w['start'] for w in heard if w['word'] == 'final')
        self.assertEqual(out[0]['at'], late)

    def test_identical_candidates_without_position_hint_are_rejected_as_ambiguous(self):
        sequence = a.spoken_tokens('um dois três quatro cinco seis sete oito') * 2
        with self.assertRaises(LookupError) as raised:
            a.locate(sequence, a.spoken_tokens('três quatro cinco'), None)
        self.assertIn('ambígua', raised.exception.args[0])

    def test_phrase_longer_than_transcript_does_not_crash(self):
        with self.assertRaises(ValueError):
            run_resolve('um dois três quatro cinco seis', words('um dois'), ['um dois três quatro cinco seis'])

    def test_low_word_confidence_is_rejected(self):
        with self.assertRaisesRegex(ValueError, 'sem confiança'):
            run_resolve('Olá mundo bonito.', words('olá mundo bonito', score=.2), ['olá mundo bonito'])

    def test_script_must_still_have_unique_phrase(self):
        with self.assertRaisesRegex(ValueError, 'repetida'):
            run_resolve('Olá mundo. Olá mundo.', words('olá mundo olá mundo'), ['olá mundo'])


class RegressionTests(unittest.TestCase):
    def test_low_similarity_error_includes_heard_and_score(self):
        with self.assertRaisesRegex(ValueError, 'correspondência ouvida.*0%'):
            run_resolve('Frase ausente completamente.', words('olá mundo'), ['Frase ausente completamente'])

    def test_inserted_word_must_not_supply_the_start_time(self):
        heard = words('alpha inserida beta gamma delta epsilon')
        heard[0]['score'] = .1
        heard[2]['score'] = .1
        out, _ = run_resolve('alpha beta gamma delta epsilon', heard, ['alpha beta gamma delta epsilon'])
        self.assertEqual(out[0]['at'], 3)

    def test_stronger_lexical_match_wins_over_position(self):
        phrase = a.spoken_tokens('alpha beta gamma delta epsilon')
        sequence = a.spoken_tokens('alpha beta gamma delta outro ' + 'nada ' * 100 + 'alpha beta gamma delta epsilon')
        start, size, score = a.locate(sequence, phrase, 0)
        self.assertEqual(score, 1)
        self.assertEqual(sequence[start:start+size], phrase)

    def test_script_uniqueness_uses_the_same_spoken_number_form(self):
        with self.assertRaisesRegex(ValueError, 'repetida'):
            run_resolve('Custou 349 dólares. Custou trezentos e quarenta e nove dólares.', words('custou 349 dólares'), ['custou 349 dólares'])

    def test_thousands_decimal_and_model_codes(self):
        self.assertEqual(a.spoken_tokens('1.299 reais'), a.spoken_tokens('mil duzentos e noventa e nove reais'))
        self.assertEqual(a.spoken_tokens('349,90'), a.spoken_tokens('trezentos e quarenta e nove vírgula noventa'))
        self.assertEqual(a.spoken_tokens('Quest 3S'), a.spoken_tokens('Quest três s'))

    def test_nonfinite_timestamps_never_produce_an_estimated_time(self):
        heard = words('alpha beta gamma')
        for w in heard: w['start'] = float('nan')
        with self.assertRaisesRegex(ValueError, 'sem confiança'):
            run_resolve('alpha beta gamma', heard, ['alpha beta gamma'])


if __name__ == '__main__':
    unittest.main()
