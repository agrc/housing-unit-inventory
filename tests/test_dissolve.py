import pandas as pd
import pytest
from pandas import testing as tm

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


class TestAttributeDissolveHelpers:

    def test_group_common_field_ops_combines_ops(self):
        field_map = {
            'foo': 'sum',
            'bar': 'sum',
        }

        ops_and_fields = dissolve._group_common_field_ops(field_map)

        test_map = {
            'sum': ['foo', 'bar'],
        }

        assert ops_and_fields == test_map

    def test_group_common_field_ops_still_retuns_lists_for_single_field_ops(self):
        field_map = {
            'foo': 'sum',
            'bar': 'count',
        }

        ops_and_fields = dissolve._group_common_field_ops(field_map)

        test_map = {
            'sum': ['foo'],
            'count': ['bar'],
        }

        assert ops_and_fields == test_map

    def test_smart_groupby_sum_sums_rows_with_all_different_values(self):
        dup_parcels_df = pd.DataFrame({
            'PARCEL_ID': ['1', '1', '2'],
            'BLDG_SQFT': [100, 200, 200],
            'TOTAL_MKT_VALUE': [50, 10, 40],
            'LAND_MKT_VALUE': [10, 20, 15],
            'PARCEL_ACRES': [.5, .1, .1],
        })

        sum_fields = ['BLDG_SQFT', 'TOTAL_MKT_VALUE', 'LAND_MKT_VALUE']
        test_fields = sum_fields + ['PARCEL_ACRES']

        summed_df = dup_parcels_df.groupby('PARCEL_ID').agg(dissolve._smart_groupby_sum, sum_fields,
                                                            test_fields)[sum_fields]

        test_df = pd.DataFrame({
            'BLDG_SQFT': [300., 200.],
            'TOTAL_MKT_VALUE': [60., 40.],
            'LAND_MKT_VALUE': [30., 15.],
        })
        test_df.index = ['1', '2']
        test_df.index.name = 'PARCEL_ID'

        tm.assert_frame_equal(summed_df, test_df)

    def test_smart_groupby_sum_sums_rows_with_one_different_value(self):
        dup_parcels_df = pd.DataFrame({
            'PARCEL_ID': ['1', '1', '2'],
            'BLDG_SQFT': [200, 200, 200],
            'TOTAL_MKT_VALUE': [10, 10, 40],
            'LAND_MKT_VALUE': [21, 20, 15],
            'PARCEL_ACRES': [.5, .5, .1],
        })

        sum_fields = ['BLDG_SQFT', 'TOTAL_MKT_VALUE', 'LAND_MKT_VALUE']
        test_fields = sum_fields + ['PARCEL_ACRES']

        summed_df = dup_parcels_df.groupby('PARCEL_ID').agg(dissolve._smart_groupby_sum, sum_fields,
                                                            test_fields)[sum_fields]

        test_df = pd.DataFrame({
            'BLDG_SQFT': [400., 200.],
            'TOTAL_MKT_VALUE': [20., 40.],
            'LAND_MKT_VALUE': [41., 15.],
        })
        test_df.index = ['1', '2']
        test_df.index.name = 'PARCEL_ID'

        tm.assert_frame_equal(summed_df, test_df)

    def test_smart_groupby_sum_sums_rows_with_one_different_value_in_a_non_sum_field(self):
        dup_parcels_df = pd.DataFrame({
            'PARCEL_ID': ['1', '1', '2'],
            'BLDG_SQFT': [200, 200, 200],
            'TOTAL_MKT_VALUE': [10, 10, 40],
            'LAND_MKT_VALUE': [20, 20, 15],
            'PARCEL_ACRES': [.5, .6, .1],
        })

        sum_fields = ['BLDG_SQFT', 'TOTAL_MKT_VALUE', 'LAND_MKT_VALUE']
        test_fields = sum_fields + ['PARCEL_ACRES']

        summed_df = dup_parcels_df.groupby('PARCEL_ID').agg(dissolve._smart_groupby_sum, sum_fields,
                                                            test_fields)[sum_fields]

        test_df = pd.DataFrame({
            'BLDG_SQFT': [400., 200.],
            'TOTAL_MKT_VALUE': [20., 40.],
            'LAND_MKT_VALUE': [40., 15.],
        })
        test_df.index = ['1', '2']
        test_df.index.name = 'PARCEL_ID'

        tm.assert_frame_equal(summed_df, test_df)

    def test_smart_groupby_sum_doesnt_sum_rows_with_same_values(self):
        dup_parcels_df = pd.DataFrame({
            'PARCEL_ID': ['1', '1', '2'],
            'BLDG_SQFT': [100, 100, 200],
            'TOTAL_MKT_VALUE': [50, 50, 40],
            'LAND_MKT_VALUE': [10, 10, 15],
            'PARCEL_ACRES': [.5, .5, .1],
        })

        sum_fields = ['BLDG_SQFT', 'TOTAL_MKT_VALUE', 'LAND_MKT_VALUE']
        test_fields = sum_fields + ['PARCEL_ACRES']

        summed_df = dup_parcels_df.groupby('PARCEL_ID').agg(dissolve._smart_groupby_sum, sum_fields,
                                                            test_fields)[sum_fields]

        test_df = pd.DataFrame({
            'BLDG_SQFT': [100., 200.],
            'TOTAL_MKT_VALUE': [50., 40.],
            'LAND_MKT_VALUE': [10., 15.],
        })
        test_df.index = ['1', '2']
        test_df.index.name = 'PARCEL_ID'

        tm.assert_frame_equal(summed_df, test_df)

    def test_smart_groupby_sum_passes_with_no_duplicate_rows(self):
        dup_parcels_df = pd.DataFrame({
            'PARCEL_ID': ['1', '2'],
            'BLDG_SQFT': [100, 200],
            'TOTAL_MKT_VALUE': [50, 40],
            'LAND_MKT_VALUE': [10, 15],
            'PARCEL_ACRES': [.5, .1],
        })

        sum_fields = ['BLDG_SQFT', 'TOTAL_MKT_VALUE', 'LAND_MKT_VALUE']
        test_fields = sum_fields + ['PARCEL_ACRES']

        summed_df = dup_parcels_df.groupby('PARCEL_ID').agg(dissolve._smart_groupby_sum, sum_fields,
                                                            test_fields)[sum_fields]

        test_df = pd.DataFrame({
            'BLDG_SQFT': [100., 200.],
            'TOTAL_MKT_VALUE': [50., 40.],
            'LAND_MKT_VALUE': [10., 15.],
        })
        test_df.index = ['1', '2']
        test_df.index.name = 'PARCEL_ID'

        tm.assert_frame_equal(summed_df, test_df)


class TestAttributeDissolve:

    def test_dissolve_attributes_count(self):

        #: duplicates_df, dissolve_field, fields_map, sum_duplicate_test_fields

        dups = pd.DataFrame({
            'PARCEL_ID': ['1', '1'],
            'OWNER': ['foo', 'foo'],
        })

        fields_map = {'OWNER': 'count'}

        dissolved_df = dissolve._dissolve_attributes(dups, 'PARCEL_ID', fields_map, [])

        test_df = pd.DataFrame({'OWNER': [2]})
        test_df.index = ['1']
        test_df.index.name = 'PARCEL_ID'

        tm.assert_frame_equal(dissolved_df, test_df)

    def test_dissolve_attributes_first_int(self):

        dups = pd.DataFrame({
            'PARCEL_ID': ['1', '1'],
            'OWNER': [1, 2],
        })

        fields_map = {'OWNER': 'first'}

        dissolved_df = dissolve._dissolve_attributes(dups, 'PARCEL_ID', fields_map, [])

        test_df = pd.DataFrame({'OWNER': [1]})
        test_df.index = ['1']
        test_df.index.name = 'PARCEL_ID'

        tm.assert_frame_equal(dissolved_df, test_df)

    def test_dissolve_attributes_first_str(self):

        dups = pd.DataFrame({
            'PARCEL_ID': ['1', '1'],
            'OWNER': ['foo', 'bar'],
        })

        fields_map = {'OWNER': 'first'}

        dissolved_df = dissolve._dissolve_attributes(dups, 'PARCEL_ID', fields_map, [])

        test_df = pd.DataFrame({'OWNER': ['foo']})
        test_df.index = ['1']
        test_df.index.name = 'PARCEL_ID'

        tm.assert_frame_equal(dissolved_df, test_df)

    def test_dissolve_attributes_max(self):

        dups = pd.DataFrame({
            'PARCEL_ID': ['1', '1'],
            'OWNER': [1, 15],
        })

        fields_map = {'OWNER': 'max'}

        dissolved_df = dissolve._dissolve_attributes(dups, 'PARCEL_ID', fields_map, [])

        test_df = pd.DataFrame({'OWNER': [15]})
        test_df.index = ['1']
        test_df.index.name = 'PARCEL_ID'

        tm.assert_frame_equal(dissolved_df, test_df)

    def test_dissolve_attributes_sum_all_fields_duplicated_returns_first(self):

        dups = pd.DataFrame({
            'PARCEL_ID': ['1', '1'],
            'TEST': [100, 100],
            'PARCEL_ACRES': [1, 1],
        })

        fields_map = {'TEST': 'sum'}

        dissolved_df = dissolve._dissolve_attributes(dups, 'PARCEL_ID', fields_map, ['TEST', 'PARCEL_ACRES'])

        test_df = pd.DataFrame({'TEST': [100]})
        test_df.index = ['1']
        test_df.index.name = 'PARCEL_ID'

        tm.assert_frame_equal(dissolved_df, test_df)

    def test_dissolve_attributes_sum_mixed_duplicate_unique_fields_returns_sum(self):

        dups = pd.DataFrame({
            'PARCEL_ID': ['1', '1'],
            'TEST': [100, 100],
            'PARCEL_ACRES': [1, 110],
        })

        fields_map = {'TEST': 'sum'}

        dissolved_df = dissolve._dissolve_attributes(dups, 'PARCEL_ID', fields_map, ['TEST', 'PARCEL_ACRES'])

        test_df = pd.DataFrame({'TEST': [200.]})
        test_df.index = ['1']
        test_df.index.name = 'PARCEL_ID'

        tm.assert_frame_equal(dissolved_df, test_df)

    def test_dissolve_attributes_sum_all_unique_fields_returns_sum(self):

        dups = pd.DataFrame({
            'PARCEL_ID': ['1', '1'],
            'TEST': [100, 200],
            'PARCEL_ACRES': [1, 110],
        })

        fields_map = {'TEST': 'sum'}

        dissolved_df = dissolve._dissolve_attributes(dups, 'PARCEL_ID', fields_map, ['TEST', 'PARCEL_ACRES'])

        test_df = pd.DataFrame({'TEST': [300.]})
        test_df.index = ['1']
        test_df.index.name = 'PARCEL_ID'

        tm.assert_frame_equal(dissolved_df, test_df)

    def test_dissolve_attributes_max(self):

        dups = pd.DataFrame({
            'PARCEL_ID': ['1', '1'],
            'TEST': [100, 200],
        })

        fields_map = {'TEST': 'max'}

        dissolved_df = dissolve._dissolve_attributes(dups, 'PARCEL_ID', fields_map, [])

        test_df = pd.DataFrame({'TEST': [200]})
        test_df.index = ['1']
        test_df.index.name = 'PARCEL_ID'

        tm.assert_frame_equal(dissolved_df, test_df)

    def test_dissolve_attributes_two_fields_same_op(self):

        dups = pd.DataFrame({
            'PARCEL_ID': ['1', '1'],
            'TEST': [100, 200],
            'TEST2': [300, 400],
        })

        fields_map = {'TEST': 'max', 'TEST2': 'max'}

        dissolved_df = dissolve._dissolve_attributes(dups, 'PARCEL_ID', fields_map, [])

        test_df = pd.DataFrame({
            'TEST': [200],
            'TEST2': [400],
        })
        test_df.index = ['1']
        test_df.index.name = 'PARCEL_ID'

        tm.assert_frame_equal(dissolved_df, test_df)

    def test_dissolve_attributes_two_fields_different_op(self):

        dups = pd.DataFrame({
            'PARCEL_ID': ['1', '1'],
            'TEST': [100, 200],
            'TEST2': [300, 400],
        })

        fields_map = {'TEST': 'max', 'TEST2': 'first'}

        dissolved_df = dissolve._dissolve_attributes(dups, 'PARCEL_ID', fields_map, [])

        test_df = pd.DataFrame({
            'TEST': [200],
            'TEST2': [300],
        })
        test_df.index = ['1']
        test_df.index.name = 'PARCEL_ID'

        tm.assert_frame_equal(dissolved_df, test_df)

    def test_dissolve_attributes_two_groups_two_fields_same_op(self):

        dups = pd.DataFrame({
            'PARCEL_ID': ['1', '1', '2', '2'],
            'TEST': [100, 200, 300, 400],
            'TEST2': [500, 600, 700, 800],
        })

        fields_map = {'TEST': 'max', 'TEST2': 'max'}

        dissolved_df = dissolve._dissolve_attributes(dups, 'PARCEL_ID', fields_map, [])

        test_df = pd.DataFrame({
            'TEST': [200, 400],
            'TEST2': [600, 800],
        })
        test_df.index = ['1', '2']
        test_df.index.name = 'PARCEL_ID'

        tm.assert_frame_equal(dissolved_df, test_df)

    def test_dissolve_attributes_two_groups_two_fields_two_ops(self):

        dups = pd.DataFrame({
            'PARCEL_ID': ['1', '1', '2', '2'],
            'TEST': [100, 200, 300, 400],
            'TEST2': [500, 600, 700, 800],
        })

        fields_map = {'TEST': 'max', 'TEST2': 'first'}

        dissolved_df = dissolve._dissolve_attributes(dups, 'PARCEL_ID', fields_map, [])

        test_df = pd.DataFrame({
            'TEST': [200, 400],
            'TEST2': [500, 700],
        })
        test_df.index = ['1', '2']
        test_df.index.name = 'PARCEL_ID'

        tm.assert_frame_equal(dissolved_df, test_df)

    def test_dissolve_attributes_warns_unknown_op(self):

        dups = pd.DataFrame({
            'PARCEL_ID': ['1', '1'],
            'TEST': [100, 200],
        })

        fields_map = {'TEST': 'foo'}

        with pytest.warns(UserWarning) as warning:
            dissolved_df = dissolve._dissolve_attributes(dups, 'PARCEL_ID', fields_map, [])

        assert warning[0].message.args[0] == 'Attribute operation "foo" not supported, skipping...'

    def test_dissolve_attributes_warns_unknown_op_does_next_op(self):

        dups = pd.DataFrame({
            'PARCEL_ID': ['1', '1'],
            'TEST': [100, 200],
            'TEST2': [300, 400],
        })

        fields_map = {'TEST': 'foo', 'TEST2': 'first'}

        with pytest.warns(UserWarning) as warning:
            dissolved_df = dissolve._dissolve_attributes(dups, 'PARCEL_ID', fields_map, [])

        test_df = pd.DataFrame({
            'TEST2': [300],
        })
        test_df.index = ['1']
        test_df.index.name = 'PARCEL_ID'

        tm.assert_frame_equal(dissolved_df, test_df)
        assert warning[0].message.args[0] == 'Attribute operation "foo" not supported, skipping...'

    def test_dissolve_attributes_handles_dissolve_field_count(self):

        dups = pd.DataFrame({
            'PARCEL_ID': ['1', '1'],
            'TEST': [100, 200],
        })

        fields_map = {'PARCEL_ID': 'count', 'TEST': 'max'}

        dissolved_df = dissolve._dissolve_attributes(dups, 'PARCEL_ID', fields_map, [])

        test_df = pd.DataFrame({
            'PARCEL_ID_count': [2],
            'TEST': [200],
        })
        test_df.index = ['1']
        test_df.index.name = 'PARCEL_ID'

        tm.assert_frame_equal(dissolved_df, test_df)

    def test_dissolve_attributes_warns_dissolve_field_not_count_op(self):

        dups = pd.DataFrame({
            'PARCEL_ID': ['1', '1'],
            'TEST': [100, 200],
        })

        fields_map = {'PARCEL_ID': 'max', 'TEST': 'max'}

        with pytest.warns(UserWarning) as warning:
            dissolved_df = dissolve._dissolve_attributes(dups, 'PARCEL_ID', fields_map, [])

        test_df = pd.DataFrame({
            'PARCEL_ID_max': ['1'],
            'TEST': [200],
        })
        test_df.index = ['1']
        test_df.index.name = 'PARCEL_ID'

        tm.assert_frame_equal(dissolved_df, test_df)
        assert warning[0].message.args[
            0] == 'Dissolve field "PARCEL_ID" should only use "count" operation; result likely nonsensical'
