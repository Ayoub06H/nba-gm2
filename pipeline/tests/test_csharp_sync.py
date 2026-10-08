"""The C# model enums and the pipeline's field lists must name the same fields."""

import re
from pathlib import Path

from nbagm.attributes import ATTRIBUTES
from nbagm.tendencies import TENDENCIES
from nbagm.traits import TRAITS

IDS_CS = Path(__file__).resolve().parents[2] / "src" / "NbaGm.Core" / "Model" / "Ids.cs"


def enum_keys(name):
    body = re.search(r"public enum " + name + r"\s*\{(.*?)\}", IDS_CS.read_text(), re.S).group(1)
    body = re.sub(r"//[^\n]*", "", body)
    members = [m.strip() for m in body.split(",") if m.strip()]
    return [re.sub(r"(?<!^)([A-Z])", r"_\1", m).lower() for m in members]


def test_attributes_match():
    assert enum_keys("AttributeId") == list(ATTRIBUTES)


def test_tendencies_match():
    assert enum_keys("TendencyId") == [t.key for t in TENDENCIES]


def test_traits_match():
    assert enum_keys("TraitId") == list(TRAITS)


def test_position_labels_match():
    from nbagm.league import POSITION_INDEX
    cs = (IDS_CS.parent / "Position.cs").read_text()
    for label, index in POSITION_INDEX.items():
        assert f'["{label}"] = {index}' in cs
