import pytest

from pymsch import Block, Content, Schematic


def make_schematic(*blocks: Block, labels: list[str] = [], **tags: str):
    schem = Schematic()

    for block in blocks:
        assert schem.add_block(block), f"Block overlapped: {block}"

    for label in labels:
        schem.add_label(label)

    for tag, value in tags.items():
        schem.set_tag(tag, value)

    return schem


def assert_schematic_blocks_eq(want: Schematic, got: Schematic):
    for want_tile, got_tile in zip(want.tiles, got.tiles, strict=True):
        assert want_tile.block == got_tile.block
        assert want_tile.x == got_tile.x
        assert want_tile.y == got_tile.y
        assert want_tile.config == got_tile.config
        assert want_tile.rotation == got_tile.rotation


@pytest.mark.parametrize(
    ["schematic", "data"],
    [
        pytest.param(
            make_schematic(Block(Content.SWITCH, 0, 0, False, 0)),
            "bXNjaAF4nBXIUQqAIBAA0dkKgzpi9GEqtGBbpNH1y/l5MAjSM5g/EuNjzcgcUwm3XlVPA1z2W8qFblkFV16tYf+30JrgAzvqDyA=",
            id="switch_off",
        ),
        pytest.param(
            make_schematic(Block(Content.SWITCH, 0, 0, True, 0)),
            "bXNjaAF4nBXIUQqAIBAA0dkKgzpi9GEqtGBbpNH1y/l5MAjSM5g/EuNjzcgcUwm3XlVPA1z2W8qFblkFV16tYf+30JqEDzvsDyE=",
            id="switch_on",
        ),
        pytest.param(
            make_schematic(
                Block(Content.SORTER, 0, 0, None, 0),
                Block(Content.SORTER, 1, 0, Content.COPPER, 0),
                Block(Content.SORTER, 2, 0, Content.PYRATITE, 0),
            ),
            "bXNjaAF4nDWIOw6AIBTACigODh7QOKC8gQTBAN7fX+zSphiUoUtuF4YzPfaMXupWwtFCToCNbpVY0fOisDWXJuXehh8F/Vf6rYkLXaIPQw==",
            id="sorters",
        ),
    ],
)
class TestBase32:
    def test_read_str(self, schematic: Schematic, data: str):
        got = Schematic.read_str(data)
        assert_schematic_blocks_eq(schematic, got)

    def test_round_trip(self, schematic: Schematic, data: str):
        got = Schematic.read_str(schematic.write_str())
        assert_schematic_blocks_eq(schematic, got)
