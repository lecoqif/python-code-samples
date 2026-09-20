import polars.selectors as cs
import pytest
from polars.exceptions import ColumnNotFoundError
from polars.testing import assert_frame_equal

import polars as pl


def test_null_and_nan_are_both_missing():
    df = pl.DataFrame({"x": [1.0, None, float("nan"), 4.0], "y": [1, 2, 3, None]})
    assert_frame_equal(df.dropna(), df.head(1))


def test_threshold_and_subset_preserve_other_columns():
    df = pl.DataFrame({"x": [1, None, None], "y": [None, 2, None], "z": [None] * 3})
    assert_frame_equal(df.dropna(thresh=1, subset=["x", "y"]), df.head(2))


def test_lazy_all_composes_with_projection():
    df = pl.DataFrame({"x": [1.0, None, float("nan")], "y": [None, 2, None]})
    result = df.lazy().dropna(how="all").select("y", "x").collect()
    assert_frame_equal(result, df.head(2).select("y", "x"))


def test_empty_subset_has_defined_semantics():
    df = pl.DataFrame({"x": [None, 1]})
    assert_frame_equal(df.dropna(subset=[]), df)
    assert_frame_equal(df.dropna(how="all", subset=[]), df.head(0))


@pytest.mark.parametrize("engine", ["auto", "streaming"])
def test_scan_composition_and_infinity(tmp_path, engine):
    frame = pl.DataFrame(
        {"x": [None, float("nan"), float("inf"), 3.0], "y": [1, 2, 3, 4]}
    )
    path = tmp_path / "input.parquet"
    frame.write_parquet(path)
    result = pl.scan_parquet(path).dropna(subset="x").select("y").collect(engine=engine)
    assert_frame_equal(result, frame.tail(2).select("y"))


def test_nested_nulls_are_not_top_level_missing_values():
    frame = pl.DataFrame({"items": [[None], None], "record": [{"x": None}, None]})
    assert_frame_equal(frame.dropna(), frame.head(1))


@pytest.mark.parametrize(
    "kwargs, error",
    [
        ({"subset": [1]}, TypeError),
        ({"subset": ["absent"], "thresh": 0}, ColumnNotFoundError),
        ({"thresh": 1, "how": "any"}, TypeError),
        ({"how": "invalid"}, ValueError),
    ],
)
def test_argument_validation_even_for_empty_frames(kwargs, error):
    with pytest.raises(error):
        pl.LazyFrame(schema={"x": pl.Float64}).dropna(**kwargs)


@pytest.mark.parametrize("subset", [["x", "x"], ("x", "x"), {"x"}, cs.float()])
def test_subset_uses_native_selector_semantics(subset):
    frame = pl.DataFrame({"x": [1.0, None, float("nan")], "y": [None, 2, 3]})
    for candidate in (frame, frame.lazy()):
        result = candidate.dropna(subset=subset)
        threshold = candidate.dropna(subset=subset, thresh=2)
        if isinstance(candidate, pl.LazyFrame):
            result, threshold = result.collect(), threshold.collect()
        assert_frame_equal(result, frame.head(1))
        # Duplicate names select one column, so they cannot satisfy thresh=2.
        assert_frame_equal(threshold, frame.head(0))


def test_empty_selector_matches_empty_subset():
    frame = pl.DataFrame({"x": [None, 1]})
    assert_frame_equal(frame.dropna(subset=cs.string()), frame)
    assert_frame_equal(frame.dropna(subset=cs.string(), how="all"), frame.head(0))


def test_typed_empty_input_and_multiple_chunks():
    empty = pl.DataFrame(schema={"x": pl.Float64, "y": pl.String})
    assert_frame_equal(empty.dropna(), empty)
    frame = pl.concat(
        [pl.DataFrame({"x": [1.0, None]}), pl.DataFrame({"x": [float("nan"), 2.0]})],
        rechunk=False,
    )
    assert frame.n_chunks() > 1
    assert_frame_equal(frame.dropna(), pl.DataFrame({"x": [1.0, 2.0]}))


def test_lazy_plan_does_not_execute_rows():
    def fail_if_executed(frame):
        pytest.fail("dropna executed rows while constructing the plan")

    lazy = pl.LazyFrame({"x": [1.0]}).map_batches(
        fail_if_executed, schema={"x": pl.Float64}
    )
    assert lazy.dropna().collect_schema() == lazy.collect_schema()
