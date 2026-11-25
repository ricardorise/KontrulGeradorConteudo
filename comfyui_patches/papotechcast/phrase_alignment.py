"""Alinhamento de frases do roteiro com a transcrição do WhisperX — versão TOLERANTE.

Substitui a comparação exata de palavras, que falha sempre que o ASR difere do roteiro:
  roteiro : "o Quest três S, o modelo de entrada ... trezentos e quarenta e nove dólares"
  WhisperX: "O Quest 3, seu modelo de entrada ... 349 dólares"

Como funciona
1. Normaliza os dois lados para a MESMA forma falada: minúsculas, sem acento/pontuação e números
   convertidos para palavras (349 -> "trezentos e quarenta e nove"; "3S" -> "três s").
2. Procura a janela da transcrição mais parecida com a frase (similaridade de sequência de palavras).
3. Usa a posição da frase no roteiro (a narração segue a ordem do roteiro) para desempatar trechos parecidos.
4. Só aceita com confiança mínima e sem ambiguidade; senão interrompe para revisão, informando o que foi ouvido.
O horário é o da primeira palavra reconhecida da frase (nunca é estimado).
Mantém a regra original: a frase precisa ser única no roteiro.
"""

import hashlib
import json
import math
import re
import unicodedata
from difflib import SequenceMatcher
from pathlib import Path

from .pipeline import command

MIN_SCORE = 0.70  # similaridade mínima para aceitar o trecho
AMBIGUITY_MARGIN = 0.04  # diferença mínima para o 2º melhor trecho (em outro lugar) não ser empate
POSITION_WEIGHT = 0.2  # peso do desvio de posição relativa (roteiro x transcrição) no ranking
POSITION_PENALTY_CAP = 0.08
MIN_WORD_SCORE = 0.5  # confiança mínima do WhisperX para a palavra que dá o horário


def tokens(text):
    plain = ''.join(c for c in unicodedata.normalize('NFD', text.lower()) if unicodedata.category(c) != 'Mn')
    return re.findall(r'\w+', plain)


def occurrences(haystack, needle):
    return [i for i in range(len(haystack) - len(needle) + 1) if haystack[i:i + len(needle)] == needle]


# ---- números por extenso (pt-BR) -------------------------------------------------------------
_UNITS = ['zero', 'um', 'dois', 'três', 'quatro', 'cinco', 'seis', 'sete', 'oito', 'nove', 'dez', 'onze', 'doze',
          'treze', 'quatorze', 'quinze', 'dezesseis', 'dezessete', 'dezoito', 'dezenove']
_TENS = ['', '', 'vinte', 'trinta', 'quarenta', 'cinquenta', 'sessenta', 'setenta', 'oitenta', 'noventa']
_HUNDREDS = ['', 'cento', 'duzentos', 'trezentos', 'quatrocentos', 'quinhentos', 'seiscentos', 'setecentos',
             'oitocentos', 'novecentos']


def _below_1000(n):
    if n == 100:
        return 'cem'
    parts = []
    hundreds, rest = divmod(n, 100)
    if hundreds:
        parts.append(_HUNDREDS[hundreds])
    if rest:
        if rest < 20:
            parts.append(_UNITS[rest])
        else:
            tens, unit = divmod(rest, 10)
            parts.append(_TENS[tens] + (' e ' + _UNITS[unit] if unit else ''))
    return ' e '.join(parts)


def number_words(n):
    if n < 0:
        return 'menos ' + number_words(-n)
    if n < 1000:
        return _UNITS[0] if n == 0 else _below_1000(n)
    if n < 10 ** 6:
        thousands, rest = divmod(n, 1000)
        head = 'mil' if thousands == 1 else _below_1000(thousands) + ' mil'
        joiner = ' e ' if rest < 100 or rest % 100 == 0 else ' '
        return head + (joiner + _below_1000(rest) if rest else '')
    if n < 10 ** 9:
        millions, rest = divmod(n, 10 ** 6)
        head = 'um milhão' if millions == 1 else _below_1000(millions) + ' milhões'
        return head + (' e ' + number_words(rest) if rest and rest < 1000 else (' ' + number_words(rest) if rest else ''))
    return ' '.join(_UNITS[int(d)] for d in str(n))  # números enormes: dígito a dígito


def spoken_tokens(text):
    """Inteiros, milhares pt-BR, decimais e códigos como 3S, na forma falada.

    Decimal é normalizado como "virgula" + fração, não como valor monetário;
    reais/centavos continuam sendo palavras reconhecidas pelo ASR.
    """
    def expand(match):
        raw = match.group()
        if re.fullmatch(r'\d{1,3}(?:\.\d{3})+(?:,\d+)?', raw):
            raw = raw.replace('.', '')
        parts = re.split(r'[.,]', raw, maxsplit=1)
        def integer(value):
            if len(value) > 18 or (len(value) > 1 and value.startswith('0')):
                return ' '.join(_UNITS[int(d)] for d in value)
            return number_words(int(value))
        result = integer(parts[0])
        if len(parts) > 1:
            result += ' virgula ' + integer(parts[1])
        return ' ' + result + ' '
    expanded = re.sub(r'\d{1,3}(?:\.\d{3})+(?:,\d+)?(?!\d)|\d+(?:[.,]\d+)?', expand, text)
    return tokens(expanded)


# ---- busca tolerante -------------------------------------------------------------------------
def best_matches(sequence, phrase, expected_ratio=None):
    """Scan word windows with a safe multiset upper bound before sequence alignment.

    A second pass is only needed when nothing reaches MIN_SCORE, so even a bad
    match can report the actual best heard text without keeping every window.
    """
    n = len(phrase)
    if not n or not sequence:
        return []
    if n > 256:
        raise ValueError('Frase de referência longa demais; escolha um trecho de até 256 palavras.')
    lengths = sorted({min(len(sequence), max(1, round(n * f))) for f in (0.75, 0.9, 1.0, 1.1, 1.25, 1.5)})
    matcher = SequenceMatcher(None, [], phrase, autojunk=False)
    for cutoff in (MIN_SCORE, 0.0):
        found, best = [], None
        for size in lengths:
            for start in range(len(sequence) - size + 1):
                window = sequence[start:start + size]
                penalty = 0.0 if expected_ratio is None else min(
                    POSITION_PENALTY_CAP, POSITION_WEIGHT * abs(start / len(sequence) - expected_ratio))
                matcher.set_seq1(window)
                upper = matcher.quick_ratio()
                if upper < cutoff or (cutoff == 0 and best is not None and upper - penalty < best[0]):
                    continue
                score = matcher.ratio()
                candidate = (score - penalty, score, start, size)
                if cutoff:
                    if score >= cutoff:
                        found.append(candidate)
                elif best is None or candidate > best:
                    best = candidate
        if found:
            # Script position only resolves close lexical matches, never a much weaker one.
            strongest = max(c[1] for c in found)
            found = [c for c in found if c[1] >= strongest - AMBIGUITY_MARGIN]
            return sorted(found, reverse=True)
        if cutoff == 0:
            return [best] if best is not None else []
    return []


def locate(sequence, phrase, expected_ratio=None):
    """Melhor trecho da transcrição para a frase: (início, tamanho, similaridade) ou levanta ValueError."""
    candidates = best_matches(sequence, phrase, expected_ratio)
    if not candidates:
        raise LookupError(None)
    adjusted, score, start, size = candidates[0]
    if score < MIN_SCORE:
        raise LookupError((start, size, score))
    for other_adjusted, _, other_start, other_size in candidates[1:]:
        apart = other_start >= start + size or other_start + other_size <= start
        if apart:
            if other_adjusted >= adjusted - AMBIGUITY_MARGIN:
                raise LookupError((start, size, score, 'ambígua'))
            break
    return start, size, score


def resolve(assets, narration):
    anchored = [e for e in assets['brolls'] if e.get('phrase')]
    if not anchored:
        return assets
    run = Path(narration['run']).resolve()
    script = spoken_tokens((run / 'roteiro.txt').read_text(encoding='utf-8'))
    positions = {}
    for entry in anchored:
        phrase = spoken_tokens(entry['phrase'])
        if len(phrase) > 256:
            raise ValueError('Frase de referência longa demais; escolha um trecho de até 256 palavras.')
        matches = occurrences(script, phrase) if phrase else []
        if not phrase or len(matches) != 1:
            raise ValueError(f"Frase do B-roll ausente ou repetida no roteiro: {entry['phrase']}. Use uma frase única.")
        positions[entry['phrase']] = matches[0]
    audio = Path(narration['audio']).resolve()
    if audio.parent != run or audio.name != 'narracao.wav':
        raise ValueError('O alinhamento exige a narração gerada neste fluxo.')
    fingerprint = hashlib.sha256(audio.read_bytes()).hexdigest()
    cache = run / 'alinhamento-whisperx.json'
    stamp = run / 'alinhamento-whisperx.sha256'
    if not cache.is_file() or not stamp.is_file() or stamp.read_text() != fingerprint:
        worker = Path(__file__).with_name('alignment_worker.py').resolve()
        command(['docker', 'run', '--rm', '--gpus', 'device=1', '--network', 'none',
                 '-e', 'HF_HOME=/cache/hf', '-e', 'HF_HUB_OFFLINE=1',
                 '-v', f'{run}:/job', '-v', f'{worker}:/worker.py:ro',
                 '-v', 'kontrul-editor_hfcache:/cache', 'kontrul/asr:latest', 'python', '/worker.py'])
        stamp.write_text(fingerprint)
    result = json.loads(cache.read_text())
    words = result.get('word_segments') or [w for s in result['segments'] for w in s.get('words', [])]
    sequence, mapped = [], []
    for word in words:
        for token in spoken_tokens(word.get('word', '')):
            sequence.append(token)
            mapped.append(word)
    spoken_script = script

    resolved, report = [], []
    for entry in assets['brolls']:
        entry = dict(entry)
        if entry.get('phrase'):
            phrase = spoken_tokens(entry['phrase'])
            expected = positions[entry['phrase']] / len(spoken_script)
            try:
                start, size, score = locate(sequence, phrase, expected)
            except LookupError as error:
                info = error.args[0]
                heard = ' Transcrição vazia; similaridade 0%.'
                if info:
                    heard = f" Melhor correspondência ouvida: “{' '.join(sequence[info[0]:info[0] + info[1]])}” ({info[2]:.0%}"
                    heard += ', ambígua)' if len(info) > 3 else ').'
                raise ValueError(f"WhisperX não encontrou a frase com confiança: {entry['phrase']}.{heard} "
                                 'Revise a frase e o áudio; nenhum horário foi estimado.') from None
            matcher = SequenceMatcher(None, sequence[start:start + size], phrase, autojunk=False)
            word = None
            # Only lexical matches may anchor the phrase. Inserted ASR words cannot.
            for offset, _, count in matcher.get_matching_blocks():
                for index in range(start + offset, start + offset + count):
                    candidate = mapped[index]
                    try:
                        at = float(candidate['start'])
                        confidence = float(candidate.get('score', 0))
                    except (KeyError, ValueError, TypeError):
                        continue
                    if math.isfinite(at) and at >= 0 and math.isfinite(confidence) and confidence >= MIN_WORD_SCORE:
                        word = candidate
                        break
                if word is not None:
                    break
            heard = ' '.join(sequence[start:start + size])
            if word is None:
                raise ValueError(f"Alinhamento sem confiança suficiente: {entry['phrase']}. "
                                 f"Ouvido: “{heard}” ({score:.0%}); nenhuma palavra correspondente com score >= {MIN_WORD_SCORE} e horário válido. Nenhum horário foi estimado.")
            entry['at'] = float(word['start'])
            original, previous = [], None
            for item in mapped[start:start + size]:
                if item is not previous:
                    original.append(item.get('word', ''))
                    previous = item
            report.append({'phrase': entry['phrase'], 'heard': heard, 'heard_original': ' '.join(original),
                           'similarity': round(score, 4), 'at': entry['at']})
        resolved.append(entry)
    (run / 'brolls-alinhados.json').write_text(json.dumps(resolved, ensure_ascii=False, indent=2))
    (run / 'alinhamento-frases.json').write_text(json.dumps(report, ensure_ascii=False, indent=2))  # para conferência
    return dict(assets, brolls=resolved)
