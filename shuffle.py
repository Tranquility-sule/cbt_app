"""
Deterministic shuffling for exam questions and options.

The same attempt_id + exam_id always produces the same order for a given
student, so refreshing the page never scrambles their view. Different
students get different (pseudo-random) orders, which discourages
copying from a neighbor's screen.
"""
import random


def _seeded_random(seed_parts):
    seed_str = "-".join(str(p) for p in seed_parts)
    return random.Random(seed_str)


def ordered_questions(questions, attempt_seed, shuffle_enabled):
    if not shuffle_enabled:
        return list(questions)
    rng = _seeded_random(("questions", attempt_seed))
    shuffled = list(questions)
    rng.shuffle(shuffled)
    return shuffled


def ordered_options(options, attempt_seed, question_id, shuffle_enabled):
    if not shuffle_enabled:
        return list(options)
    rng = _seeded_random(("options", attempt_seed, question_id))
    shuffled = list(options)
    rng.shuffle(shuffled)
    return shuffled
