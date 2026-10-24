from lolhex.messages import set_language, tr


def test_message_key_can_also_be_a_named_placeholder():
    set_language("en_GB")
    assert tr("augment.display.skill_name", name="Demo", key="Q") == "Demo (empowers Q)"
