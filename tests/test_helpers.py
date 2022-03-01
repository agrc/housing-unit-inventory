import numpy as np
import pandas as pd
import pytest
from arcgis.features import GeoAccessor, GeoSeriesAccessor
from arcgis.geometry import Geometry
from pandas import testing as tm

from housing_unit_inventory import helpers


class TestYearBuilt:

    def test_get_proper_built_yr_value_series_gets_most_common(self, mocker):
        test_parcels_df = pd.DataFrame({'PARCEL_ID': [1, 1, 1, 2], 'BUILT_YR': [5, 5, 6, 7]})

        built_yr_series = helpers.get_proper_built_yr_value_series(test_parcels_df, 'PARCEL_ID', 'BUILT_YR')

        test_series = pd.Series(data=[5, 7], index=[1, 2], name='BUILT_YR')
        test_series.index.name = 'PARCEL_ID'
        tm.assert_series_equal(built_yr_series, test_series)

    def test_get_proper_built_yr_value_series_zeroes_gets_max(self, mocker):
        test_parcels_df = pd.DataFrame({'PARCEL_ID': [1, 1, 1, 2], 'BUILT_YR': [0, 0, 6, 7]})

        built_yr_series = helpers.get_proper_built_yr_value_series(test_parcels_df, 'PARCEL_ID', 'BUILT_YR')

        test_series = pd.Series(data=[6, 7], index=[1, 2], name='BUILT_YR')
        test_series.index.name = 'PARCEL_ID'
        tm.assert_series_equal(built_yr_series, test_series)

    def test_get_proper_built_yr_value_series_multiple_modes_gets_max(self, mocker):
        test_parcels_df = pd.DataFrame({'PARCEL_ID': [1, 1, 1, 2], 'BUILT_YR': [4, 5, 6, 7]})

        built_yr_series = helpers.get_proper_built_yr_value_series(test_parcels_df, 'PARCEL_ID', 'BUILT_YR')

        test_series = pd.Series(data=[6, 7], index=[1, 2], name='BUILT_YR')
        test_series.index.name = 'PARCEL_ID'
        tm.assert_series_equal(built_yr_series, test_series)


class TestAddresses:

    def test_get_non_base_addr_points_with_non_base_addrs(self, mocker):
        test_df = pd.DataFrame({'id': [0, 1, 2, 3], 'PtType': ['', '', 'BASE ADDRESS', '']})
        from_featureclass_mock = mocker.Mock()
        from_featureclass_mock.return_value = test_df
        mocker.patch.object(pd.DataFrame.spatial, 'from_featureclass', new=from_featureclass_mock)

        mock_fc = mocker.Mock()

        output_df = helpers.get_non_base_addr_points(mock_fc)

        test_df = pd.DataFrame({'id': [0, 1, 3], 'PtType': ['', '', '']}, index=[0, 1, 3])

        tm.assert_frame_equal(output_df, test_df)

    def test_get_address_point_count_series_counts_properly(self, mocker):
        test_parcels_df = pd.DataFrame({
            'parcel_oid': [11, 12],
            'SHAPE': ['parcel_shape_1', 'parcel_shape_2'],
        })

        test_address_pts_df = pd.DataFrame({
            'addr_id': [1, 2, 3],
            'SHAPE': ['addr_shape_1', 'addr_shape_2', 'addr_shape_3'],
        })

        joined_df = pd.DataFrame({
            'parcel_oid': [11, 12, 12],
            'SHAPE': ['parcel_shape_1', 'parcel_shape_2', 'parcel_shape_2'],
            'addr_id': [1, 2, 3]
        })

        join_method_mock = mocker.MagicMock()
        join_method_mock.return_value = joined_df

        mocker.patch.object(pd.DataFrame.spatial, 'join', new=join_method_mock)

        spatial_join_results_series = helpers.get_address_point_count_series(
            test_parcels_df, test_address_pts_df, 'parcel_oid'
        )

        test_series = pd.Series(data=[1, 2], index=[11, 12], name='ap_count')
        test_series.index.name = 'parcel_oid'
        tm.assert_series_equal(spatial_join_results_series, test_series)


class TestCommonAreaTypes:

    def test_set_common_area_types(self):
        test_data_df = pd.DataFrame({
            'id': [1, 2, 3],
            'TYPE_WFRC': ['single_family', 'multi_family', 'multi_family'],
            'SUBTYPE_WFRC': ['pud', '', ''],
        })

        with_types_df = helpers.set_common_area_types(test_data_df)

        test_results_df = pd.DataFrame({
            'id': [1, 2, 3],
            'TYPE_WFRC': ['single_family', 'multi_family', 'multi_family'],
            'SUBTYPE_WFRC': ['pud', '', ''],
            'TYPE': ['single_family', 'multi_family', 'multi_family'],
            'SUBTYPE': ['pud', '', ''],
            'basebldg': ['1', '1', '1'],
            'building_type_id': ['1', '2', '2'],
        })

        tm.assert_frame_equal(with_types_df, test_results_df)

    def test_set_multi_family_single_parcel_subtypes_sets_normal(self):
        test_data_df = pd.DataFrame({
            'id': [1, 2, 3, 4],
            'class': ['multi_family', 'duplex', 'apartment', 'townhome'],
        })

        with_types_df = helpers.set_multi_family_single_parcel_subtypes(test_data_df)

        test_results_df = pd.DataFrame({
            'id': [1, 2, 3, 4],
            'class': ['multi_family', 'duplex', 'apartment', 'townhome'],
            'SUBTYPE': ['multi_family', 'duplex', 'apartment', 'townhome'],
            'NOTES': ['', '', '', '']
        })

        tm.assert_frame_equal(with_types_df, test_results_df)

    def test_set_multi_family_single_parcel_subtypes_sets_tri_quad(self):
        test_data_df = pd.DataFrame({
            'id': [1],
            'class': ['triplex-quadplex'],
        })

        with_types_df = helpers.set_multi_family_single_parcel_subtypes(test_data_df)

        test_results_df = pd.DataFrame({
            'id': [1],
            'class': ['triplex-quadplex'],
            'SUBTYPE': ['apartment'],
            'NOTES': ['triplex-quadplex'],
        })

        tm.assert_frame_equal(with_types_df, test_results_df)


class TestDataCleaning:

    def test_standardize_fields_renames_all_fields(self):
        parcels_df = pd.DataFrame({
            'account_no': [1, 2, 3],
            'type': ['sf', 'mf', 'condo'],
        })

        field_mapping = {
            'account_no': 'PARCEL_ID',
            'type': 'class',
        }

        renamed_df = helpers.standardize_fields(parcels_df, field_mapping)

        assert list(renamed_df.columns) == ['PARCEL_ID', 'class']

    def test_standardize_fields_renames_some_fields(self):
        parcels_df = pd.DataFrame({
            'account_no': [1, 2, 3],
            'class': ['sf', 'mf', 'condo'],
        })

        field_mapping = {
            'account_no': 'PARCEL_ID',
        }

        renamed_df = helpers.standardize_fields(parcels_df, field_mapping)

        assert list(renamed_df.columns) == ['PARCEL_ID', 'class']

    def test_standardize_fields_raises_exception_for_missing_field(self):
        parcels_df = pd.DataFrame({
            'account_no': [1, 2, 3],
            'type': ['sf', 'mf', 'condo'],
        })

        field_mapping = {
            'account_no': 'PARCEL_ID',
            'TYPE': 'class',
        }

        with pytest.raises(ValueError) as exception_info:
            renamed_df = helpers.standardize_fields(parcels_df, field_mapping)

            assert 'Field TYPE not found in parcels dataset.' in str(exception_info)
