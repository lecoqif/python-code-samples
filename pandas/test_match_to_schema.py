"""Practice examples and regression tests for schema matching."""

import numpy as np
import pytest
from pandas.testing import assert_frame_equal

import pandas as pd


def test_reorders_and_casts_without_losing_duplicate_index():
    index = pd.Index([20, 10, 20], name="trade")
    frame = pd.DataFrame({"price": [1.5, 2.5, 3.5], "quantity": [2, 3, 4]}, index=index)
    before = frame.copy(deep=True)
    result = frame.match_to_schema({"quantity": "Int64", "price": "Float64"}, cast=True)
    expected = pd.DataFrame(
        {
            "quantity": pd.array([2, 3, 4], dtype="Int64"),
            "price": pd.array([1.5, 2.5, 3.5], dtype="Float64"),
        },
        index=index,
    )
    assert_frame_equal(result, expected)
    assert_frame_equal(frame, before)


def test_inserts_typed_missing_columns_and_drops_extras():
    frame = pd.DataFrame({"quantity": [2, 3], "obsolete": [8, 9]}, index=[20, 10])
    result = frame.match_to_schema(
        {"symbol": "string", "quantity": "Int64"},
        missing_columns="insert",
        extra_columns="drop",
        cast=True,
    )
    expected = pd.DataFrame(
        {
            "symbol": pd.array([pd.NA, pd.NA], dtype="string"),
            "quantity": pd.array([2, 3], dtype="Int64"),
        },
        index=frame.index,
    )
    assert_frame_equal(result, expected)


def test_strict_dtype_and_name_validation():
    frame = pd.DataFrame({"quantity": [2, 3]})
    with pytest.raises(TypeError):
        frame.match_to_schema({"quantity": "Int64"})
    with pytest.raises(ValueError):
        frame.match_to_schema({"quantity": "int64", "price": "float64"})
    with pytest.raises(ValueError):
        frame.match_to_schema({})


def test_empty_schema_keeps_the_rows():
    index = pd.Index([20, 10, 20], name="trade")
    frame = pd.DataFrame({"quantity": [2, 3, 4]}, index=index)
    result = frame.match_to_schema({}, extra_columns="drop")
    assert_frame_equal(result, pd.DataFrame(index=index), check_column_type=False)
    assert result is not frame


def test_strict_dtype_extra_columns():
    frame = pd.DataFrame({"quantity": [2, 3], "price": [10, 20]})
    with pytest.raises(ValueError):
        frame.match_to_schema({"quantity": "int64"})

    with pytest.raises(TypeError):
        frame.match_to_schema(
            {"quantity": "int64", "stock": "int64"},
            missing_columns="insert",
            extra_columns="drop",
        )


def test_with_python_types():
    frame = pd.DataFrame({"quantity": [2, 3]}, dtype="int64")
    result = frame.match_to_schema({"quantity": int})
    assert_frame_equal(result, frame)


def test_object_dtype_uses_native_astype():
    frame = pd.DataFrame({"x": [1]})
    assert_frame_equal(
        frame.match_to_schema({"x": "object"}, cast=True), frame.astype("object")
    )


@pytest.mark.parametrize("copy_on_write", [False, True])
def test_scalar_mutations_are_isolated_in_both_directions(copy_on_write):
    with pd.option_context("mode.copy_on_write", copy_on_write):
        frame = pd.DataFrame({"x": [1, 2]})
        result = frame.match_to_schema({"x": "int64"})
        result.iloc[0, 0] = 10
        frame.iloc[1, 0] = 20
        assert result["x"].tolist() == [10, 2]
        assert frame["x"].tolist() == [1, 20]


def test_multiindex_metadata_and_missing_column_alignment():
    index = pd.MultiIndex.from_tuples(
        [("b", 2), ("a", 1), ("b", 2)], names=["key", "position"]
    )
    frame = pd.DataFrame({"x": [1, 2, 3]}, index=index)
    frame.columns.name = "fields"
    result = frame.match_to_schema(
        {"text": "string", "x": "int64"}, missing_columns="insert"
    )
    expected = frame.copy()
    expected.insert(0, "text", pd.array([pd.NA] * 3, dtype="string"))
    assert_frame_equal(result, expected)


def test_failed_conversion_leaves_original_and_schema_unchanged():
    frame = pd.DataFrame({"x": [1, 2], "y": ["3", "bad"]})
    before = frame.copy(deep=True)
    schema = {"x": "float64", "y": "int64"}
    with pytest.raises(ValueError):
        frame.match_to_schema(schema, cast=True)
    assert_frame_equal(frame, before)
    assert schema == {"x": "float64", "y": "int64"}


def test_wide_frame_does_not_fragment():
    import warnings

    frame = pd.DataFrame({f"x{i}": [i] for i in range(110)})
    with warnings.catch_warnings():
        warnings.simplefilter("error", pd.errors.PerformanceWarning)
        result = frame.match_to_schema({name: "int64" for name in frame.columns})
    assert_frame_equal(result, frame)


@pytest.mark.parametrize(
    "dtype",
    [None, "object", "float16", "complex128", "datetime64[ns]", "category", ">i4"],
)
def test_dtypes_follow_native_astype(dtype):
    frame = pd.DataFrame({"x": [1, 2]})
    assert_frame_equal(
        frame.match_to_schema({"x": dtype}, cast=True), frame.astype(dtype)
    )


@pytest.mark.parametrize("dtype", ["object", "float16", "datetime64[ns]", "category"])
def test_missing_columns_use_native_dtype_defaults(dtype):
    index = pd.Index([20, 10, 20], name="row")
    frame = pd.DataFrame(index=index)
    result = frame.match_to_schema({"x": dtype}, missing_columns="insert")
    expected = pd.DataFrame({"x": pd.Series(index=index, dtype=dtype)}, index=index)
    assert_frame_equal(result, expected)
    assert result["x"].isna().all()


def test_invalid_dtype_uses_native_error():
    with pytest.raises(TypeError):
        pd.DataFrame({"x": [1]}).match_to_schema({"x": "not-a-dtype"}, cast=True)


@pytest.mark.parametrize("dtype", ["int64", "bool"])
def test_impossible_missing_dtype_rejected_even_with_no_rows(dtype):
    with pytest.raises(TypeError):
        pd.DataFrame().match_to_schema({"x": dtype}, missing_columns="insert")


def test_zero_row_nullable_columns_preserve_dtypes():
    frame = pd.DataFrame(index=pd.Index([], name="row"))
    result = frame.match_to_schema(
        {"x": "Int64", "y": "Float64"}, missing_columns="insert"
    )
    expected = pd.DataFrame(
        {"x": pd.Series([], dtype="Int64"), "y": pd.Series([], dtype="Float64")},
        index=frame.index,
    )
    assert_frame_equal(result, expected)


def test_numpy_boolean_cast_and_dtype_objects():
    frame = pd.DataFrame({"x": [1]})
    result = frame.match_to_schema({"x": pd.Float64Dtype()}, cast=np.bool_(True))
    assert str(result["x"].dtype) == "Float64"


def test_duplicate_columns_cannot_be_hidden_by_dropping():
    frame = pd.DataFrame([[1, 2]], columns=["x", "x"])
    with pytest.raises(ValueError):
        frame.match_to_schema({}, extra_columns="drop")


@pytest.mark.parametrize("label", [1, ("value", "x"), float("nan")])
def test_flat_labels_and_column_metadata_use_native_index_semantics(label):
    columns = pd.Index([label, "other"], tupleize_cols=False, name="fields")
    frame = pd.DataFrame([[1, 2]], columns=columns)
    requested = float("nan") if isinstance(label, float) else label
    result = frame.match_to_schema({requested: "int64"}, extra_columns="drop")
    assert_frame_equal(result, frame.reindex(columns=[requested]))


def test_multiindex_columns_remain_outside_supported_scope():
    frame = pd.DataFrame([[1]], columns=pd.MultiIndex.from_tuples([("x", "value")]))
    with pytest.raises(TypeError, match="MultiIndex"):
        frame.match_to_schema({("x", "value"): "int64"})


@pytest.mark.parametrize(
    "kwargs", [{"missing_columns": "invalid"}, {"extra_columns": "invalid"}]
)
def test_invalid_policies_are_rejected(kwargs):
    with pytest.raises(ValueError):
        pd.DataFrame({"x": [1]}).match_to_schema({"x": "int64"}, **kwargs)
