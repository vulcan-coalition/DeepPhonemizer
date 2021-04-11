import torch
import re
from typing import Dict, Union, Tuple

from dp.model import TransformerModel


# yeah some hard core regex warranted in the future for special chars
class Phonemizer:

    def __init__(self,
                 checkpoint_path: str,
                 punctuation='().,:?!',
                 expand_acronyms=True,
                 lang_phoneme_dict: Dict[str, Dict[str, str]] = None) -> None:
        checkpoint = torch.load(checkpoint_path, map_location=torch.device('cpu'))
        self.model = TransformerModel.from_config(checkpoint['config'])
        self.model.load_state_dict(checkpoint['model'])
        self.preprocessor = checkpoint['preprocessor']
        self.lang_phoneme_dict = lang_phoneme_dict
        self.expand_acronyms = expand_acronyms
        punctuation += ' '
        self.punc_set = set(punctuation)
        self.punc_pattern=re.compile(f'([{punctuation}])')

    def __call__(self, text: str, lang: str) -> str:
        words = re.split(self.punc_pattern, text)
        if self.expand_acronyms:
            words = [self.expand_acronym(w) for w in words]

        # collect dictionary phonemes for words and hyphenated words
        word_phonemes = {word: self.get_dict_entry(word, lang) for word in words}

        # collect dictionary phonemes for subwords in hyphenated words
        word_splits = {w: w.split('-') for w in words if word_phonemes[w] is None}
        subwords = {w for values in word_splits.values() for w in values if len(w) > 0}
        for subword in subwords:
            if subword not in word_phonemes:
                word_phonemes[subword] = self.get_dict_entry(subword, lang)

        # predict all non-hyphenated words and all subwords of hyphenated words
        words_to_predict = []
        for word, phons in word_phonemes.items():
            if phons is None and '-' not in word:
                words_to_predict.append(word)

        # can be batched
        for word in words_to_predict:
            phons = self.predict_word(word, lang)
            word_phonemes[word] = phons

        # collect all phonemes
        output = []
        for word in words:
            phons = word_phonemes[word]
            if phons is None:
                subwords = word_splits[word]
                subphons = [word_phonemes[w] for w in subwords]
                phons = '-'.join(subphons)
            output.append(phons)
        return ''.join(output)

    def predict_word(self, word: str, lang: str) -> str:
        tokens = self.preprocessor.text_tokenizer(word)
        decoded = self.preprocessor.text_tokenizer.decode(tokens, remove_special_tokens=True)
        if len(decoded) == 0:
            return ''
        pred = self.model.generate(torch.tensor(tokens).unsqueeze(0))
        pred_decoded = self.preprocessor.phoneme_tokenizer.decode(pred, remove_special_tokens=True)
        phons = ''.join(pred_decoded)
        return phons

    def get_dict_entry(self, word: str, lang: str) -> Union[str, None]:
        if word in self.punc_set:
            return word
        if not self.lang_phoneme_dict or lang not in self.lang_phoneme_dict:
            return None
        phoneme_dict = self.lang_phoneme_dict[lang]
        left, word, right = self.strip_left_right(word)
        if word in phoneme_dict:
            return left + phoneme_dict[word] + right
        elif word.lower() in phoneme_dict:
            return left + phoneme_dict[word.lower()] + right
        elif word.title() in phoneme_dict:
            return left + phoneme_dict[word.title()] + right
        else:
            return None

    def strip_left_right(self, word: str) -> Tuple[str, str, str]:
        left, right = 0, len(word)
        for i in range(len(word)):
            if word[i].isalnum():
                left = i
                break
        for i in range(len(word), 1, -1):
            if word[i - 1].isalnum():
                right = i
                break
        return word[:left], word[left:right], word[right:]

    def expand_acronym(self, word: str) -> str:
        if word.isupper():
            return '-'.join(list(word))
        else:
            return word


if __name__ == '__main__':
    checkpoint_path = '../checkpoints/latest_model.pt'
    lang_phoneme_dict = {'de': {'E-Mail': 'ˈiːmeɪ̯l'}}
    phonemizer = Phonemizer(checkpoint_path=checkpoint_path, lang_phoneme_dict=lang_phoneme_dict)
    phons = phonemizer('Der E-Mail kleine SPD Prinzen-könig - Francesco Cardinale, pillert an seinem Pillermann.', lang='de')
    print(phons)
