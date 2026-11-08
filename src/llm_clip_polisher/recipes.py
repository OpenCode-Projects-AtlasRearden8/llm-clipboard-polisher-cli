"""Recipe definitions: one rewrite per invocation, prompt built locally."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Recipe:
    name: str
    summary: str
    system_prompt: str


RECIPES: dict[str, Recipe] = {
    "tighten": Recipe(
        name="tighten",
        summary="Trim fluff so the text says the same thing in fewer words.",
        system_prompt=(
            "You are an editing assistant that tightens text for busy readers.\n"
            "Rewrite the user's text so it says exactly the same thing in fewer words.\n"
            "Cut filler, redundant phrases, and padding. Keep the voice, tone, and "
            "meaning intact. Keep names, numbers, and technical terms unchanged.\n"
            "Reply with ONLY the rewritten text: no preamble, no explanation, "
            "no surrounding quotes, and nothing else."
        ),
    ),
    "simplify": Recipe(
        name="simplify",
        summary="Rewrite in plain English, like you'd explain it to a friend.",
        system_prompt=(
            "You are an editing assistant that simplifies text the way a friendly "
            "teacher would, never condescending.\n"
            "Rewrite the user's text in plain English: shorter sentences, common "
            "words instead of jargon, and a clear structure.\n"
            "Keep the meaning, key facts, and any numbers accurate. Simplify the "
            "wording, not the message.\n"
            "Reply with ONLY the rewritten text: no preamble, no explanation, "
            "no surrounding quotes, and nothing else."
        ),
    ),
    "punctuate": Recipe(
        name="punctuate",
        summary="Fix punctuation, capitalization, and light grammar only.",
        system_prompt=(
            "You are an editing assistant that fixes punctuation and capitalization.\n"
            "Correct punctuation, capitalization, and light grammar mistakes in the "
            "user's text. Do not reword sentences, do not add or remove meaning, and "
            "do not change the style.\n"
            "Reply with ONLY the corrected text: no preamble, no explanation, "
            "no surrounding quotes, and nothing else."
        ),
    ),
    "translate": Recipe(
        name="translate",
        summary="Translate the text into a language given with --to.",
        system_prompt=(
            "You are a translation assistant.\n"
            "Translate the user's text into the requested language.\n"
            "Use natural, everyday phrasing in the target language and keep the "
            "meaning, tone, and any names or numbers unchanged.\n"
            "Reply with ONLY the translated text: no preamble, no explanation, "
            "no surrounding quotes, and nothing else."
        ),
    ),
}

RECIPE_NAMES = tuple(RECIPES)


def get_recipe(name: str) -> Recipe:
    try:
        return RECIPES[name]
    except KeyError:
        valid = ", ".join(RECIPE_NAMES)
        raise ValueError(f"unknown recipe {name!r}; choose one of: {valid}") from None


def build_messages(
    recipe: Recipe, target_language: str | None, text: str
) -> list[dict]:
    messages: list[dict] = []
    system = recipe.system_prompt
    if recipe.name == "translate":
        if not target_language:
            raise ValueError("the translate recipe needs a language, e.g. --to es")
        system += f"\nThe requested target language is: {target_language}."
    messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": text})
    return messages
