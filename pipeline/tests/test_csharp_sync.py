"""The C# model enums and the pipeline's field lists must name the same fields."""

import re
from pathlib import Path

from nbagm import derive

IDS_CS = Path(__file__).resolve().parents[2] / "src" / "NbaGm.Core" / "Model" / "Ids.cs"


def enum_keys(name):
    body = re.search(r"public enum " + name + r"\s*\{(.*?)\}", IDS_CS.read_text(), re.S).group(1)
    body = re.sub(r"//[^\n]*", "", body)
    members = [m.strip() for m in body.split(",") if m.strip()]
    return [re.sub(r"(?<!^)([A-Z])", r"_\1", m).lower() for m in members]


def test_attributes_match():
    assert enum_keys("AttributeId") == [a.key for a in derive.ATTRIBUTES]


def test_tendencies_match():
    assert enum_keys("TendencyId") == [t.key for t in derive.TENDENCIES]


def test_traits_match():
    assert enum_keys("TraitId") == [t.key for t in derive.TRAITS]
