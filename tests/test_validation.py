from controller.incidents import pick_reference


def test_fresh_prompt_borrows_the_previous_prompts_history():
    ref = pick_reference({"P2": (600, 36)}, {"P1": (6000, 36)}, "P1")
    assert ref["P2"] == (6000, 36)


def test_a_prompt_with_its_own_history_keeps_it():
    ref = pick_reference({"P1": (600, 5)}, {"P1": (6000, 40), "P3": (100, 1)}, "P3")
    assert ref["P1"] == (6000, 40)