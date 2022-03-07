import numpy as np
import pandas as pd
from arcgis.features import GeoAccessor, GeoSeriesAccessor
from arcgis.geometry import Geometry
from pandas import testing as tm

from housing_unit_inventory import inventory


class TestSingleFamily:

    def test_evaluate_single_family_df_sets_proper_columns(self):
        test_data_df = pd.DataFrame({
            'id': [1, 2, 3],
            'parcel_type': ['single_family', 'single_family', 'single_family'],
        })

        with_types_df = inventory.evaluate_single_family_df(test_data_df)

        test_results_df = pd.DataFrame({
            'id': [1, 2, 3],
            'parcel_type': ['single_family', 'single_family', 'single_family'],
            'TYPE': ['single_family', 'single_family', 'single_family'],
            'SUBTYPE': ['single_family', 'single_family', 'single_family'],
            'basebldg': ['1', '1', '1'],
            'building_type_id': ['1', '1', '1'],
        })

        tm.assert_frame_equal(with_types_df, test_results_df)

    def test_evaluate_single_family_df_only_gets_single_family(self):
        test_data_df = pd.DataFrame({
            'id': [1, 2, 3],
            'parcel_type': ['single_family', 'industrial', 'multi_family'],
        })

        with_types_df = inventory.evaluate_single_family_df(test_data_df)

        test_results_df = pd.DataFrame({
            'id': [1],
            'parcel_type': ['single_family'],
            'TYPE': ['single_family'],
            'SUBTYPE': ['single_family'],
            'basebldg': ['1'],
            'building_type_id': ['1'],
        })

        tm.assert_frame_equal(with_types_df, test_results_df)


class TestMultiFamilySingleParcel:

    def test_evaluate_multi_family_single_parcel_df_merges_addr_data(self, mocker):
        test_parcels_df = pd.DataFrame({
            'PARCEL_ID': [10, 11],
            'parcel_type': ['apartment', 'apartment'],
            'SHAPE': ['parcel_shape_10', 'parcel_shape_11'],
        })

        # test_addr_pts_df = pd.DataFrame({
        #     'addr_id': [1, 2, 3, 4],
        #     'SHAPE': ['addr_1', 'addr_2', 'addr_3', 'addr_4'],
        # })

        addr_pt_count_series = pd.Series(data=[2, 2], index=[10, 11], name='ap_count')
        addr_pt_count_series.index.name = 'PARCEL_ID'

        addr_pt_function_mock = mocker.MagicMock()
        addr_pt_function_mock.return_value = addr_pt_count_series

        mocker.patch('housing_unit_inventory.helpers.get_address_point_count_series', new=addr_pt_function_mock)

        evaluated_df = inventory.evaluate_multi_family_single_parcel_df(test_parcels_df, mocker.Mock())

        test_results_df = pd.DataFrame({
            'PARCEL_ID': [10, 11],
            'parcel_type': ['apartment', 'apartment'],
            'SHAPE': ['parcel_shape_10', 'parcel_shape_11'],
            'TYPE': ['multi_family', 'multi_family'],
            'basebldg': ['1', '1'],
            'building_type_id': ['2', '2'],
            'SUBTYPE': ['apartment', 'apartment'],
            'NOTE': ['', ''],
            'ap_count': [2, 2],
        })

        tm.assert_frame_equal(evaluated_df, test_results_df)

    def test_evaluate_multi_family_single_parcel_df_ignores_single_family(self, mocker):
        test_parcels_df = pd.DataFrame({
            'PARCEL_ID': [10, 11, 12],
            'parcel_type': ['apartment', 'single_family', 'apartment'],
            'SHAPE': ['parcel_shape_10', 'parcel_shape_11', 'parcel_shape_12'],
        })

        addr_pt_count_series = pd.Series(name='ap_count')
        addr_pt_count_series.index.name = 'PARCEL_ID'

        addr_pt_function_mock = mocker.MagicMock()
        addr_pt_function_mock.return_value = addr_pt_count_series

        mocker.patch('housing_unit_inventory.helpers.get_address_point_count_series', new=addr_pt_function_mock)

        evaluated_df = inventory.evaluate_multi_family_single_parcel_df(test_parcels_df, mocker.Mock())

        test_results_df = pd.DataFrame({
            'PARCEL_ID': [10, 12],
            'parcel_type': ['apartment', 'apartment'],
            'SHAPE': ['parcel_shape_10', 'parcel_shape_12'],
            'TYPE': ['multi_family', 'multi_family'],
            'basebldg': ['1', '1'],
            'building_type_id': ['2', '2'],
            'SUBTYPE': ['apartment', 'apartment'],
            'NOTE': ['', ''],
            'ap_count': [np.nan, np.nan],
        })

        tm.assert_frame_equal(evaluated_df, test_results_df)


class TestMobileHomeCommunities:

    def test_evaluate_mobile_home_communities_df_merges_addr_data(self, mocker):
        test_parcels_df = pd.DataFrame({
            'PARCEL_ID': [10, 11],
            'parcel_type': ['mobile_home_park', 'mobile_home_park'],
            'SHAPE': ['parcel_shape_10', 'parcel_shape_11'],
        })

        addr_pt_count_series = pd.Series(data=[2, 2], index=[10, 11], name='ap_count')
        addr_pt_count_series.index.name = 'PARCEL_ID'

        addr_pt_function_mock = mocker.MagicMock()
        addr_pt_function_mock.return_value = addr_pt_count_series

        mocker.patch('housing_unit_inventory.helpers.get_address_point_count_series', new=addr_pt_function_mock)

        evaluated_df = inventory.evaluate_mobile_home_communities_df(test_parcels_df, mocker.Mock())

        test_results_df = pd.DataFrame({
            'PARCEL_ID': [10, 11],
            'parcel_type': ['mobile_home_park', 'mobile_home_park'],
            'SHAPE': ['parcel_shape_10', 'parcel_shape_11'],
            'TYPE': ['multi_family', 'multi_family'],
            'SUBTYPE': ['mobile_home_park', 'mobile_home_park'],
            'basebldg': ['1', '1'],
            'ap_count': [2, 2],
        })

        tm.assert_frame_equal(evaluated_df, test_results_df)


class TestOwnedUnitGroupings:

    def test_eval_owned_unit_groupings_aggregates_correctly(self, mocker):

        common_area_key_column = 'common_area_key'
        parcels_df = pd.DataFrame({
            'PARCEL_ID': [1, 2, 3],
            'parcel_type': ['owned_unit_grouping', 'owned_unit_grouping', 'owned_unit_grouping'],
            common_area_key_column: ['foo', 'foo', 'bar'],
            'TOTAL_MKT_VALUE': [10, 15, 15],
            'LAND_MKT_VALUE': [5, 7, 10],
            'BLDG_SQFT': [300, 500, 1000],
            'FLOORS_CNT': [1, 1, 2],
            'SHAPE': ['shape1', 'shape2', 'shape3'],
            'CENTROIDS': ['centroid1', 'centroid2', 'centroid3'],
            'POLYS': ['poly1', 'poly2', 'poly3'],
        })

        year_built_series = pd.Series(data=[1901, 1902], index=['foo', 'bar'], name='BUILT_YR')
        year_built_series.index.name = common_area_key_column
        year_built_method_mock = mocker.Mock()
        year_built_method_mock.return_value = year_built_series

        mocker.patch('housing_unit_inventory.helpers.get_proper_built_yr_value_series', new=year_built_method_mock)

        addr_pt_series = pd.Series(data=[2, 1], index=['foo', 'bar'], name='UNIT_COUNT')
        addr_pt_series.index.name = common_area_key_column
        addr_count_method_mock = mocker.Mock()
        addr_count_method_mock.return_value = addr_pt_series

        mocker.patch('housing_unit_inventory.helpers.get_address_point_count_series', new=year_built_method_mock)

        # common_area_types_method_mock = lambda x: x
        mocker.patch('housing_unit_inventory.helpers.set_common_area_types', new=lambda x: x)

        oug_parcels_df = inventory.evalute_owned_unit_groupings_df(parcels_df, common_area_key_column, 'foo')

        test_df = pd.DataFrame({
            'PARCEL_ID': [2, 3],
            'parcel_type': ['owned_unit_grouping', 'owned_unit_grouping'],
            common_area_key_column: ['foo', 'bar'],
            'TOTAL_MKT_VALUE': [25, 15],
            'LAND_MKT_VALUE': [12, 10],
            'BLDG_SQFT': [800, 1000],
            'FLOORS_CNT': [1, 2],
            'PARCEL_COUNT': [2, 1],
        })
