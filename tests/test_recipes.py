import pytest

from llm_clip_polisher.recipes import RECIPE_NAMES, build_messages, get_recipe


def test_recipes_match_goal():
    assert RECIPE_NAMES == ("tighten", "simplify", "punctuate", "translate")


@pytest.mark.parametrize("name", RECIPE_NAMES)
def test_every_recipe_has_helpful_system_prompt(name):
    recipe = get_recipe(name)
    assert recipe.name == name
    assert "ONLY the" in recipe.system_prompt
    assert "no preamble" in recipe.system_prompt
    assert recipe.summary.strip()


def test_unknown_recipe_lists_valid_choices():
    with pytest.raises(ValueError) as err:
        get_recipe("mystify")
    assert "tighten" in str(err.value) and "translate" in str(err.value)


def test_translate_without_language_raises():
    with pytest.raises(ValueError) as err:
        build_messages(get_recipe("translate"), None, "Hola")
    assert "--to" in str(err.value)


def test_translate_includes_target_language():
    messages = build_messages(get_recipe("translate"), "french", "Bonjour")
    assert "french" in messages[0]["content"]
    assert messages[1] == {"role": "user", "content": "Bonjour"}
    assert len(messages) == 2


def test_other_recipes_do_not_need_language():
    messages = build_messages(get_recipe("tighten"), None, "Words here")
    assert [m["role"] for m in messages] == ["system", "user"]


def test_rules_keep_numbers_and_names():
    system = get_recipe("tighten").system_prompt
    assert "meaning" in system
    assert "numbers" in system
