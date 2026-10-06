"""Manually supplied outside box measurements, independent of FGS and BGG."""

import math
from dataclasses import asdict, dataclass


@dataclass(frozen=True, slots=True)
class BoxDimensions:
    length: float
    width: float
    depth: float
    unit: str

    def __post_init__(self):
        if not isinstance(self.unit, str) or self.unit not in {"in", "cm"}:
            raise ValueError("Box dimensions require an explicit unit: in or cm.")
        for value in (self.length, self.width, self.depth):
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not 0 < value <= 1.7976931348623157e308
                or not math.isfinite(value)
            ):
                raise ValueError(
                    "Length, width and depth must be positive finite numbers."
                )

    @classmethod
    def from_dict(cls, value):
        if value is None:
            return None
        if not isinstance(value, dict) or set(value) != {
            "length",
            "width",
            "depth",
            "unit",
        }:
            raise ValueError("Supply length, width, depth and unit together.")
        return cls(**value)

    def to_dict(self):
        return asdict(self)

    @property
    def display(self):
        def number(value):
            text = str(value)
            return text[:-2] if text.endswith(".0") else text

        return (
            " × ".join(number(v) for v in (self.length, self.width, self.depth))
            + " "
            + self.unit
        )


def write_box_dimensions(connection, game_id, dimensions):
    """Write an already validated optional value in the caller's transaction."""
    if dimensions is None:
        connection.execute(
            "DELETE FROM game_box_dimensions WHERE game_id=?", (game_id,)
        )
    else:
        connection.execute(
            """INSERT INTO game_box_dimensions(game_id,length,width,depth,unit)
               VALUES (?,?,?,?,?) ON CONFLICT(game_id) DO UPDATE SET
               length=excluded.length,width=excluded.width,depth=excluded.depth,
               unit=excluded.unit,source_version_id=NULL""",
            (
                game_id,
                dimensions.length,
                dimensions.width,
                dimensions.depth,
                dimensions.unit,
            ),
        )
