"""Answer selection from inert OAS question and answer pairs."""
from collections import Counter, defaultdict
from difflib import SequenceMatcher
import re


def normalize(text):
    return re.sub(r"[^\w\s]", "", text)


def _tokens(question):
    text = question.replace(" ", "")
    return [text[i:i + 2] for i in range(len(text) - 1)] if len(text) >= 2 else list(text)


def _ratio(left, right):
    return SequenceMatcher(None, left, right).ratio()


class AnswerBank:
    def __init__(self, rows):
        self.answers = defaultdict(set)
        self.questions = defaultdict(set)
        self.index = defaultdict(set)
        for question, answer in rows:
            question, answer = normalize(question), normalize(answer)
            self.answers[question].add(answer)
            self.questions[answer].add(question)
            for token in _tokens(question):
                self.index[token].add(question)

    def _similar_questions(self, question):
        counts = Counter(key for token in _tokens(question) for key in self.index.get(token, ()))
        candidates = sorted(counts, key=lambda key: (-counts[key], key))[:30]
        scores = [(key, _ratio(question, key)) for key in candidates]
        return sorted(((key, score) for key, score in scores if score >= .8), key=lambda item: -item[1])

    @staticmethod
    def _choose(candidates):
        """Return a unique best 1-based option, or zero for a tie or no evidence."""
        if not candidates:
            return 0
        highest = max(score for score, _ in candidates)
        options = {index for score, index in candidates if score == highest}
        return next(iter(options)) if len(options) == 1 else 0

    def choose(self, question, options):
        special = [(1, i) for i, option in enumerate(options, 1) if option == "其余选项皆对"]
        if special:
            return self._choose(special)
        exact_question = question in self.answers
        similar = [(question, 1)] if exact_question else self._similar_questions(question)
        exact = [(score, i) for key, score in similar for i, option in enumerate(options, 1)
                 if option in self.answers[key]]
        if exact:
            return self._choose(exact)
        fuzzy = [(_ratio(option, answer), i) for key, _ in similar
                 for answer in self.answers[key] for i, option in enumerate(options, 1)]
        fuzzy = [(score, i) for score, i in fuzzy if score >= .5]
        if fuzzy or exact_question:
            return self._choose(fuzzy)
        reverse = [(_ratio(question, key), i) for i, option in enumerate(options, 1)
                   for key in self.questions.get(option, ())]
        return self._choose([(score, i) for score, i in reverse if score >= .5])
