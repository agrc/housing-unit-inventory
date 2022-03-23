import pandas as pd
import pytest
from pandas import testing as tm

import housing_unit_inventory
from housing_unit_inventory import dissolve


class TestSpatialDissolve:

    def test_recursive_geometric_union_of_series_recurses_correct_number_of_times(self, mocker):
        shape1 = mocker.Mock()
        shape2 = shape1
        shape3 = shape1
        shape4 = shape1

        series = pd.Series([shape1, shape2, shape3, shape4])

        dissolve._recursive_geometric_union_of_series(series)

        assert shape1.union.call_count == 3

    def test_dissolve_geometries_groups_proper_number_of_times(self, mocker):
        duplicates_df = pd.DataFrame({
            'PARCEL_ID': ['1', '1', '2'],
            'SHAPE': ['shape1', 'shape2', 'shape3'],
        })

        recursive_union_mock = mocker.Mock()

        mocker.patch('housing_unit_inventory.dissolve._recursive_geometric_union_of_series', new=recursive_union_mock)

        dissolved_geometries = dissolve._dissolve_geometries(duplicates_df, 'PARCEL_ID')

        assert recursive_union_mock.call_count == 2

    def test_dissolve_geometries_groups_formats_resulting_dataframe_properly(self, mocker):
        duplicates_df = pd.DataFrame({
            'PARCEL_ID': ['1', '1', '2'],
            'SHAPE': ['shape1', 'shape2', 'shape3'],
        })

        recursive_union_mock = mocker.Mock()
        recursive_union_mock.side_effect = [pd.Series(['shape10']), pd.Series(['shape20'])]

        mocker.patch('housing_unit_inventory.dissolve._recursive_geometric_union_of_series', new=recursive_union_mock)

        dissolved_geometries = dissolve._dissolve_geometries(duplicates_df, 'PARCEL_ID')

        test_df = pd.DataFrame({
            'PARCEL_ID': ['1', '2'],
            'SHAPE': ['shape10', 'shape20'],
        })

        tm.assert_frame_equal(dissolved_geometries, test_df)


class TestExtractAndCombine:

    def test_extract_duplicates_and_uniques_divides_properly(self):
        parcels_df = pd.DataFrame({
            'PARCEL_ID': ['1', '1', '2', '3'],
            'SHAPE': ['shape1a', 'shape1b', 'shape2', 'shape3'],
        })

        duplicates, uniques = dissolve._extract_duplicates_and_uniques(parcels_df, 'PARCEL_ID')

        test_duplicates_df = pd.DataFrame({
            'PARCEL_ID': ['1', '1'],
            'SHAPE': ['shape1a', 'shape1b'],
        })

        test_uniques_df = pd.DataFrame({
            'PARCEL_ID': ['2', '3'],
            'SHAPE': ['shape2', 'shape3'],
        })
        test_uniques_df.index = [2, 3]

        tm.assert_frame_equal(duplicates, test_duplicates_df)
        tm.assert_frame_equal(uniques, test_uniques_df)

    def test_combine_geometries_and_attributes_gets_all_columns(self):
        geometries_df = pd.DataFrame({
            'PARCEL_ID': ['1', '2', '3'],
            'SHAPE': ['shape1', 'shape2', 'shape3'],
        })

        attributes_df = pd.DataFrame({
            'PARCEL_ID': ['1', '2', '3'],
            'VALUE': [10, 20, 30],
        })

        combined_df = dissolve._combine_geometries_and_attributes(geometries_df, attributes_df, 'PARCEL_ID')

        test_df = pd.DataFrame({
            'PARCEL_ID': ['1', '2', '3'],
            'VALUE': [10, 20, 30],
            'SHAPE': ['shape1', 'shape2', 'shape3'],
        })

        tm.assert_frame_equal(combined_df, test_df)

    def test_combine_geometries_and_attributes_validates_1to1(self):
        geometries_df = pd.DataFrame({
            'PARCEL_ID': ['1', '2', '3', '3'],
            'SHAPE': ['shape1', 'shape2', 'shape3', 'shape3'],
        })

        attributes_df = pd.DataFrame({
            'PARCEL_ID': ['1', '2', '3'],
            'VALUE': [10, 20, 30],
        })

        with pytest.raises(ValueError) as error:
            combined_df = dissolve._combine_geometries_and_attributes(geometries_df, attributes_df, 'PARCEL_ID')

    def test_recombine_dissolved_with_all(self):
        dissolved_df = pd.DataFrame({
            'PARCEL_ID': ['1', '2'],
            'SHAPE': ['shape1', 'shape2'],
            'VALUE': [10, 20],
        })

        uniques_df = pd.DataFrame({
            'PARCEL_ID': ['3', '4'],
            'SHAPE': ['shape3', 'shape4'],
            'VALUE': [30, 40],
        })

        combined_df = dissolve._recombine_dissolved_with_all(dissolved_df, uniques_df)

        test_df = pd.DataFrame({
            'PARCEL_ID': ['1', '2', '3', '4'],
            'SHAPE': ['shape1', 'shape2', 'shape3', 'shape4'],
            'VALUE': [10, 20, 30, 40],
        })

        tm.assert_frame_equal(combined_df, test_df)
