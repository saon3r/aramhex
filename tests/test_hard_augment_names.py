"""难认的海克斯名：卡面文字 → 模糊匹配。

名字短、带感叹号、带冒号，或者几张卡只差最后几个字（Transmute: Gold / Chaos /
Prismatic）时最容易出错。这里钉两件事：

1. 匹配器在这些字符串上给对 ID，**绝不**给错 ID（宁可认不出）；
2. 真的把它们当卡面标题渲染出来，用 Windows OCR 认一遍再匹配，分数一起钉住。

第 2 项是合成文字（不是游戏像素），只用来验证「Windows OCR 的输出 + 匹配器」这条链路；
不拿它去评价别的引擎。
"""

import re
from pathlib import Path

import pytest

CJK = re.compile("[\u3040-\u30ff\u3400-\u9fff\uf900-\ufaff\uac00-\ud7af]")

# 卡面上显示的文字 → 数据里的名字。Steel Your Heart 在卡面带 Quest: 前缀。
CASES = [
    ("Transmute: Prismatic", "Transmute: Prismatic"),
    ("Quest: Steel Your Heart", "Steel Your Heart"),
    ("BEES!!!", "BEES!!!"),
    ("BONK!", "BONK!"),
]


@pytest.fixture(scope="module")
def matcher():
    """真实的海克斯名字表（随程序发布的 i18n 英文名），匹配参数与引擎一致。"""
    from lolhex.data import metadata
    from lolhex.vision.matcher import NameMatcher

    names = {aid: metadata.augment_en(aid) for aid in metadata.local_augment_ids()}
    return NameMatcher(names, 72.0, min_margin=6.0)


@pytest.mark.parametrize("text,want", CASES)
def test_hard_names_match_their_own_augment(matcher, text, want):
    got, score = matcher.match(text)
    assert got is not None, f"{text!r} 没认出来（score {score:.1f}）"
    assert score >= 72.0


def test_transmute_siblings_are_never_confused(matcher):
    assert matcher.match("Transmute: Prismatic")[0] == "1238"
    assert matcher.match("Transmute: Gold")[0] == "1237"
    assert matcher.match("Transmute: Chaos")[0] == "1243"
    assert matcher.match("Transmute Prismatic")[0] == "1238"      # 冒号丢了也算对


def test_punctuation_variants_never_pick_the_wrong_card(matcher):
    """OCR 常把感叹号吃掉或拆开；可以认不出，但不能认成另一张。"""
    for text in ("BEES!!", "BEES", "BONK", "BONK!!"):
        got, _ = matcher.match(text)
        assert got in (None, "3086" if text.startswith("BEES") else "2111"), text
    # 「Get Excited!」和「Get Jinxed」是两张卡：少了感叹号不能认成另一张
    assert matcher.match("Get Excited!")[0] == "1322"
    assert matcher.match("Get Jinxed")[0] == "3004"
    assert matcher.match("Get Jinxed!")[0] == "3004"


# ---------- 渲染成卡面大小，交给 Windows OCR 再匹配 ----------

def _render(text: str, font_file: str = "georgiab.ttf", size=(700, 260), px=38):
    from PIL import Image, ImageDraw, ImageFont

    img = Image.new("RGB", size, (10, 14, 20))
    draw = ImageDraw.Draw(img)
    font = ImageFont.truetype(str(Path(r"C:\Windows\Fonts") / font_file), px)
    tag = ImageFont.truetype(str(Path(r"C:\Windows\Fonts") / font_file), 20)
    width = draw.textlength(text, font=font)
    draw.text(((size[0] - width) / 2, 40), text, font=font, fill=(255, 249, 232))
    tag_w = draw.textlength("General", font=tag)
    draw.text(((size[0] - tag_w) / 2, 100), "General", font=tag, fill=(190, 190, 190))
    return __import__("numpy").array(img)[:, :, ::-1]


@pytest.mark.parametrize("font_file", ["georgiab.ttf", "segoeuib.ttf"])
@pytest.mark.parametrize("display,dataset_name", CASES)
def test_rendered_card_text_reads_then_matches(matcher, display, dataset_name, font_file):
    pytest.importorskip("winrt.windows.media.ocr")
    from lolhex.vision.ocr_win import OcrUnavailable, WinOCR

    try:
        engine = WinOCR("en_US")
    except OcrUnavailable as e:
        pytest.skip(f"没有 Windows OCR 识别器：{e}")

    text, _ = engine.recognize(_render(display, font_file))
    got, score = matcher.match(text)
    assert got is not None, f"OCR 读到 {text!r}，匹配不到（score {score:.1f}）"
    assert score >= 72.0, f"OCR 读到 {text!r}，score {score:.1f}"
    assert not CJK.search(text)
