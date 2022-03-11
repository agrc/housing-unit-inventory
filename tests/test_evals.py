import numpy as np
import pandas as pd
import pytest
from arcgis.features import GeoAccessor, GeoSeriesAccessor
from arcgis.geometry import Geometry
from pandas import testing as tm

from housing_unit_inventory import evaluations, helpers


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

        common_area_df = pd.DataFrame({
            common_area_key_column: ['foo', 'bar'],
            'source': ['one', 'two'],
            'SHAPE': ['common_shape1', 'common_shape2'],
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

        mocker.patch('housing_unit_inventory.helpers.get_address_point_count_series', new=addr_count_method_mock)

        # common_area_types_method_mock = lambda x: x
        mocker.patch('housing_unit_inventory.helpers.set_common_area_types', new=lambda x: x)

        oug_parcels_df = evaluations.owned_unit_groupings(parcels_df, common_area_key_column, 'foo', common_area_df)

        test_df = pd.DataFrame(
            {
                'SHAPE': ['common_shape1', 'common_shape2'],
                'TOTAL_MKT_VALUE': [25, 15],
                'LAND_MKT_VALUE': [12, 10],
                'BLDG_SQFT': [800, 1000],
                'FLOORS_CNT': [1., 2.],
                'BUILT_YR': [1901, 1902],
                'PARCEL_COUNT': [2, 1],
                'UNIT_COUNT': [2, 1],
                'PARCEL_ID': ['oug_foo', 'oug_bar'],
            },
            index=['foo', 'bar'],
        )
        test_df.index.name = common_area_key_column

        tm.assert_frame_equal(oug_parcels_df, test_df)


@pytest.fixture
def parcels_df():
    parcels_df = pd.DataFrame({
        'PARCEL_ID': ['1', '2', '3', '4', '5', '6', '7'],
        'parcel_type': [
            'single_family', 'multi_family', 'duplex', 'apartment', 'townhome', 'triplex-quadplex', 'mobile_home_park'
        ],
    })

    return parcels_df


class TestByParcelTypes:

    def test_by_parcel_types_single_family_subsets_and_assigns_properly(self, parcels_df):
        parcel_types = ['single_family']
        attribute_dict = {
            'TYPE': 'single_family',
            'SUBTYPE': 'single_family',
            'basebldg': '1',
            'building_type_id': '1',
        }

        results_df = evaluations.by_parcel_types(parcels_df, parcel_types, attribute_dict)

        test_df = pd.DataFrame({
            'PARCEL_ID': ['1'],
            'parcel_type': ['single_family'],
            'TYPE': 'single_family',
            'SUBTYPE': 'single_family',
            'basebldg': '1',
            'building_type_id': '1',
        })

        tm.assert_frame_equal(results_df, test_df)

    def test_by_parcel_types_multi_family_group_subsets_and_assigns_properly(self, parcels_df, mocker):
        parcel_types = ['multi_family', 'duplex', 'apartment', 'townhome', 'triplex-quadplex']
        attribute_dict = {
            'TYPE': 'multi_family',
            'basebldg': '1',
            'building_type_id': '2',
        }

        addr_pt_count_series = pd.Series(data=[2, 2, 2, 2, 2], index=['2', '3', '4', '5', '6'], name='UNIT_COUNT')
        addr_pt_count_series.index.name = 'PARCEL_ID'

        addr_pt_function_mock = mocker.MagicMock()
        addr_pt_function_mock.return_value = addr_pt_count_series

        mocker.patch('housing_unit_inventory.helpers.get_address_point_count_series', new=addr_pt_function_mock)

        results_df = evaluations.by_parcel_types(
            parcels_df, parcel_types, attribute_dict, True, helpers.set_multi_family_single_parcel_subtypes
        )

        test_df = pd.DataFrame({
            'PARCEL_ID': ['2', '3', '4', '5', '6'],
            'parcel_type': ['multi_family', 'duplex', 'apartment', 'townhome', 'triplex-quadplex'],
            'TYPE': ['multi_family', 'multi_family', 'multi_family', 'multi_family', 'multi_family'],
            'basebldg': ['1', '1', '1', '1', '1'],
            'building_type_id': ['2', '2', '2', '2', '2'],
            'SUBTYPE': ['multi_family', 'duplex', 'apartment', 'townhome', 'apartment'],
            'NOTE': ['', '', '', '', 'triplex-quadplex'],
            'UNIT_COUNT': [2, 2, 2, 2, 2],
        })

        tm.assert_frame_equal(results_df, test_df)

    def test_by_parcel_types_mobile_home_communities_subsets_and_assigns_properly(self, parcels_df, mocker):
        parcel_types = ['mobile_home_park']
        attribute_dict = {
            'TYPE': 'multi_family',
            'SUBTYPE': 'mobile_home_park',
            'basebldg': '1',
        }

        addr_pt_count_series = pd.Series(data=[10], index=['7'], name='UNIT_COUNT')
        addr_pt_count_series.index.name = 'PARCEL_ID'

        addr_pt_function_mock = mocker.MagicMock()
        addr_pt_function_mock.return_value = addr_pt_count_series

        mocker.patch('housing_unit_inventory.helpers.get_address_point_count_series', new=addr_pt_function_mock)

        results_df = evaluations.by_parcel_types(parcels_df, parcel_types, attribute_dict, True)

        test_df = pd.DataFrame({
            'PARCEL_ID': ['7'],
            'parcel_type': ['mobile_home_park'],
            'TYPE': ['multi_family'],
            'SUBTYPE': ['mobile_home_park'],
            'basebldg': ['1'],
            'UNIT_COUNT': [10],
        })
