import numpy as np
import pandas as pd
import pytest
from arcgis.features import GeoAccessor, GeoSeriesAccessor
from mock_arcpy import arcpy
from pandas import testing as tm

from housing_unit_inventory import dissolve, helpers


class TestYearBuilt:

    def test_get_proper_built_yr_value_series_gets_most_common(self, mocker):
        test_parcels_df = pd.DataFrame({
            'PARCEL_ID': [1, 2, 3, 4],
            'BUILT_YR': [5, 5, 6, 7],
            'common_area_key': [1, 1, 1, 2],
        })

        built_yr_series = helpers.get_proper_built_yr_value_series(test_parcels_df, 'common_area_key', 'BUILT_YR')

        test_series = pd.Series(data=[5, 7], index=[1, 2], name='BUILT_YR')
        test_series.index.name = 'common_area_key'
        tm.assert_series_equal(built_yr_series, test_series)

    def test_get_proper_built_yr_value_series_zero_mode_gets_max(self, mocker):
        test_parcels_df = pd.DataFrame({
            'PARCEL_ID': [1, 2, 3, 4],
            'BUILT_YR': [0, 0, 6, 7],
            'common_area_key': [1, 1, 1, 2],
        })

        built_yr_series = helpers.get_proper_built_yr_value_series(test_parcels_df, 'common_area_key', 'BUILT_YR')

        test_series = pd.Series(data=[6, 7], index=[1, 2], name='BUILT_YR')
        test_series.index.name = 'common_area_key'
        tm.assert_series_equal(built_yr_series, test_series)

    def test_get_proper_built_yr_value_series_multiple_modes_gets_max_and_mode_of_other(self, mocker):
        test_parcels_df = pd.DataFrame({
            'PARCEL_ID': [1, 2, 3, 4, 5],
            'BUILT_YR': [4, 5, 6, 6, 7],
            'common_area_key': [1, 1, 2, 2, 2],
        })

        built_yr_series = helpers.get_proper_built_yr_value_series(test_parcels_df, 'common_area_key', 'BUILT_YR')

        test_series = pd.Series(data=[5, 6], index=[1, 2], name='BUILT_YR')
        test_series.index.name = 'common_area_key'
        tm.assert_series_equal(built_yr_series, test_series)

    def test_get_proper_built_yr_value_series_one_single_mode_then_one_multi_mode(self, mocker):
        test_parcels_df = pd.DataFrame({
            'PARCEL_ID': [1, 2, 3, 4],
            'BUILT_YR': [4, 4, 6, 7],
            'common_area_key': [1, 1, 2, 2],
        })

        built_yr_series = helpers.get_proper_built_yr_value_series(test_parcels_df, 'common_area_key', 'BUILT_YR')

        test_series = pd.Series(data=[4, 7], index=[1, 2], name='BUILT_YR')
        test_series.index.name = 'common_area_key'
        tm.assert_series_equal(built_yr_series, test_series)


class TestAddresses:

    def test_get_non_base_addr_points_with_non_base_addrs(self, mocker):
        test_df = pd.DataFrame({
            'id': [0, 1, 2, 3],
            'PtType': ['', '', 'BASE ADDRESS', ''],
        })
        from_featureclass_mock = mocker.Mock()
        from_featureclass_mock.return_value = test_df
        mocker.patch.object(pd.DataFrame.spatial, 'from_featureclass', new=from_featureclass_mock)

        mock_fc = mocker.Mock()

        output_df = helpers.get_non_base_addr_points(mock_fc)

        test_df = pd.DataFrame({
            'id': [0, 1, 3],
            'PtType': ['', '', ''],
        }, index=[0, 1, 3])

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

        test_series = pd.Series(data=[1, 2], index=[11, 12], name='UNIT_COUNT')
        test_series.index.name = 'parcel_oid'
        tm.assert_series_equal(spatial_join_results_series, test_series)


class TestCommonAreas:

    def test_load_and_clean_owned_unit_groupings_subsets_properly(self, mocker):
        common_areas_df = pd.DataFrame({
            'OBJECTID': [1, 2, 3],
            'TYPE': ['single_family', 'bar', 'multi_family'],
            'SUBTYPE': ['bar', 'pud', 'foo'],
            'SHAPE': ['shape1', 'shape2', 'shape3']
        })
        from_featureclass_method_mock = mocker.MagicMock()
        from_featureclass_method_mock.return_value = common_areas_df
        mocker.patch.object(pd.DataFrame.spatial, 'from_featureclass', new=from_featureclass_method_mock)

        common_area_key = 'common_area_key'

        common_areas_subset_df = helpers.load_and_clean_owned_unit_groupings('fake_fc_path', common_area_key)

        test_df = pd.DataFrame(
            {
                'OBJECTID': [2, 3],
                'TYPE': ['bar', 'multi_family'],
                'SUBTYPE': ['pud', 'foo'],
                'SHAPE': ['shape2', 'shape3'],
                'common_area_key': [2, 3],
                'IS_OUG': ['Yes', 'Yes'],
            },
            index=[1, 2],
        )

        tm.assert_frame_equal(common_areas_subset_df, test_df)

    def test_load_and_clean_owned_unit_groupings_renames_fields(self, mocker):
        common_areas_df = pd.DataFrame({
            'OBJECTID': [2, 3],
            'TYPE_WFRC': ['bar', 'multi_family'],
            'SUBTYPE_WFRC': ['pud', 'foo'],
            'SHAPE': ['shape2', 'shape3']
        })
        from_featureclass_method_mock = mocker.MagicMock()
        from_featureclass_method_mock.return_value = common_areas_df
        mocker.patch.object(pd.DataFrame.spatial, 'from_featureclass', new=from_featureclass_method_mock)

        common_area_key = 'common_area_key'
        field_mapping = {
            'TYPE_WFRC': 'TYPE',
            'SUBTYPE_WFRC': 'SUBTYPE',
        }

        common_areas_subset_df = helpers.load_and_clean_owned_unit_groupings(
            'fake_fc_path', common_area_key, field_mapping=field_mapping
        )

        test_df = pd.DataFrame(
            {
                'OBJECTID': [2, 3],
                'TYPE': ['bar', 'multi_family'],
                'SUBTYPE': ['pud', 'foo'],
                'SHAPE': ['shape2', 'shape3'],
                'common_area_key': [2, 3],
                'IS_OUG': ['Yes', 'Yes'],
            },
            index=[0, 1],
        )

        tm.assert_frame_equal(common_areas_subset_df, test_df)

    def test_load_and_clean_owned_unit_groupings_raises_unique_key_error(self, mocker):
        common_areas_df = pd.DataFrame({
            'OBJECTID': [1, 2, 2],
            'TYPE': ['single_family', 'bar', 'multi_family'],
            'SUBTYPE': ['bar', 'pud', 'foo'],
        })
        from_featureclass_method_mock = mocker.MagicMock()
        from_featureclass_method_mock.return_value = common_areas_df
        mocker.patch.object(pd.DataFrame.spatial, 'from_featureclass', new=from_featureclass_method_mock)

        common_area_key = 'common_area_key'

        with pytest.raises(ValueError) as error:
            common_areas_subset_df = helpers.load_and_clean_owned_unit_groupings('fake_fc_path', common_area_key)
        assert 'Unique key column OBJECTID does not contain unique values.' in str(error.value)

    def test_load_and_clean_owned_unit_groupings_raises_warning_and_removes_empty_geometries(self, mocker):
        common_areas_df = pd.DataFrame({
            'OBJECTID': [1, 2, 3],
            'TYPE': ['multi_family', 'bar', 'multi_family'],
            'SUBTYPE': ['bar', 'pud', 'foo'],
            'SHAPE': [np.nan, 'shape2', 'shape3'],
        })
        from_featureclass_method_mock = mocker.MagicMock()
        from_featureclass_method_mock.return_value = common_areas_df
        mocker.patch.object(pd.DataFrame.spatial, 'from_featureclass', new=from_featureclass_method_mock)

        common_area_key = 'common_area_key'

        with pytest.warns(UserWarning) as record:
            common_areas_subset_df = helpers.load_and_clean_owned_unit_groupings('fake_fc_path', common_area_key)

        assert record[0].message.args[0] == '1 common area row[s] had empty geometries'

        test_df = pd.DataFrame(
            {
                'OBJECTID': [2, 3],
                'TYPE': ['bar', 'multi_family'],
                'SUBTYPE': ['pud', 'foo'],
                'SHAPE': ['shape2', 'shape3'],
                'common_area_key': [2, 3],
                'IS_OUG': ['Yes', 'Yes'],
            },
            index=[1, 2],
        )

        tm.assert_frame_equal(common_areas_subset_df, test_df)

    def test_set_multi_family_single_parcel_subtypes_sets_normal(self):
        test_data_df = pd.DataFrame({
            'id': [1, 2, 3, 4],
            'parcel_type': ['multi_family', 'duplex', 'apartment', 'townhome'],
        })

        with_types_df = helpers.set_multi_family_single_parcel_subtypes(test_data_df)

        test_results_df = pd.DataFrame({
            'id': [1, 2, 3, 4],
            'parcel_type': ['multi_family', 'duplex', 'apartment', 'townhome'],
            'SUBTYPE': ['multi_family', 'duplex', 'apartment', 'townhome'],
            'NOTE': ['', '', '', '']
        })

        tm.assert_frame_equal(with_types_df, test_results_df)

    def test_set_multi_family_single_parcel_subtypes_sets_tri_quad(self):
        test_data_df = pd.DataFrame({
            'id': [1],
            'parcel_type': ['triplex-quadplex'],
        })

        with_types_df = helpers.set_multi_family_single_parcel_subtypes(test_data_df)

        test_results_df = pd.DataFrame({
            'id': [1],
            'parcel_type': ['triplex-quadplex'],
            'SUBTYPE': ['apartment'],
            'NOTE': ['triplex-quadplex'],
        })

        tm.assert_frame_equal(with_types_df, test_results_df)

    def test_get_common_areas_intersecting_parcels_by_key_removes_nonmatching(self):
        parcels_df = pd.DataFrame({
            'common_area_key': [1, 2],
            'PARCEL_ID': ['a', 'b'],
        })

        common_areas_df = pd.DataFrame({
            'common_area_key': [1, 2, 3],
            'area_name': ['foo', 'bar', 'baz'],
        })

        subset_df = helpers.get_common_areas_intersecting_parcels_by_key(common_areas_df, parcels_df, 'common_area_key')

        test_df = pd.DataFrame({
            'common_area_key': [1, 2],
            'area_name': ['foo', 'bar'],
        })

        tm.assert_frame_equal(subset_df, test_df)


class TestDataSetupAndCleaning:

    def test_load_and_clean_parcels_drops_empties(self, mocker):
        parcel_df = pd.DataFrame({
            'OBJECTID': [0, 1, 2],
            'PARCEL_ID': ['15', '35', np.nan],
            'COUNT_PARCEL_ID': [1, 2, 1],
            'TAXEXEMPT_TYPE': ['', '', ''],
            'TOTAL_MKT_VALUE': [1, 3, 5],
            'LAND_MKT_VALUE': [4, 6, 8],
            'PARCEL_ACRES': [.25, 1.25, 4.3],
            'PROP_CLASS': ['foo', 'bar', 'fez'],
            'PRIMARY_RES': ['baz', 'bee', 'boo'],
            'HOUSE_CNT': [1, 2, 1],
            'BLDG_SQFT': [10, 20, 30],
            'FLOORS_CNT': [13, 42, 64],
            'BUILT_YR': [1984, 2001, 2011],
            'EFFBUILT_YR': [1910, 2016, 2000],
            'SHAPE': ['s1', np.nan, 's3'],
        })

        dissolve_dupes_mock = mocker.Mock()
        dissolve_dupes_mock.return_value = parcel_df
        mocker.patch.object(pd.DataFrame.spatial, 'from_featureclass')
        mocker.patch.object(dissolve, 'dissolve_duplicates_by_dataframe', new=dissolve_dupes_mock)

        cleaned_parcels = helpers.load_and_clean_parcels('foo')

        test_df = pd.DataFrame({
            'OBJECTID': [0],
            'PARCEL_ID': ['15'],
            'COUNT_PARCEL_ID': [1],
            'TAXEXEMPT_TYPE': [''],
            'TOTAL_MKT_VALUE': [1],
            'LAND_MKT_VALUE': [4],
            'PARCEL_ACRES': [.25],
            'PROP_CLASS': ['foo'],
            'PRIMARY_RES': ['baz'],
            'HOUSE_CNT': [1.],
            'BLDG_SQFT': [10],
            'FLOORS_CNT': [13],
            'BUILT_YR': [1984],
            'EFFBUILT_YR': [1910],
            'SHAPE': ['s1'],
        })

        tm.assert_frame_equal(cleaned_parcels, test_df)

    @pytest.mark.skip(reason='Don\'t need to rename fields when using custom, non arcpy dissolve')
    def test_load_and_clean_parcels_renames_fields_and_ignores_other_fields(self, mocker):
        parcel_df = pd.DataFrame({
            'OBJECTID': [0],
            'PARCEL_ID': ['15'],
            'COUNT_PARCEL_ID': [1],
            'FIRST_TAXEXEMPT_TYPE': [''],
            'MAX_TOTAL_MKT_VALUE': [1],
            'SUM_LAND_MKT_VALUE': [5],
            'SHAPE': ['shape1'],
            'HOUSE_CNT': [1],
        })

        dissolve_dupes_mock = mocker.Mock()
        dissolve_dupes_mock.return_value = parcel_df
        mocker.patch.object(pd.DataFrame.spatial, 'from_featureclass')
        mocker.patch.object(dissolve, 'dissolve_duplicates_by_dataframe', new=dissolve_dupes_mock)

        cleaned_parcels = helpers.load_and_clean_parcels('foo')

        test_df = pd.DataFrame({
            'OBJECTID': [0],
            'PARCEL_ID': ['15'],
            'COUNT_PARCEL_ID': [1],
            'TAXEXEMPT_TYPE': [''],
            'TOTAL_MKT_VALUE': [1],
            'LAND_MKT_VALUE': [5],
            'SHAPE': ['shape1'],
            'HOUSE_CNT': [1.],
        })

        tm.assert_frame_equal(cleaned_parcels, test_df)

    def test_load_and_clean_parcels_converts_house_count_to_float(self, mocker):
        parcel_df = pd.DataFrame({
            'OBJECTID': [0],
            'PARCEL_ID': ['15'],
            'SHAPE': ['shape1'],
            'HOUSE_CNT': ['1'],
        })

        dissolve_dupes_mock = mocker.Mock()
        dissolve_dupes_mock.return_value = parcel_df
        mocker.patch.object(pd.DataFrame.spatial, 'from_featureclass')
        mocker.patch.object(dissolve, 'dissolve_duplicates_by_dataframe', new=dissolve_dupes_mock)

        cleaned_parcels = helpers.load_and_clean_parcels('foo')

        test_df = pd.DataFrame({
            'OBJECTID': [0],
            'PARCEL_ID': ['15'],
            'SHAPE': ['shape1'],
            'HOUSE_CNT': [1.],
        })

        tm.assert_frame_equal(cleaned_parcels, test_df)

    def test_load_and_clean_parcels_converts_house_count_to_float_with_None(self, mocker):
        parcel_df = pd.DataFrame({
            'OBJECTID': [0],
            'PARCEL_ID': ['15'],
            'SHAPE': ['shape1'],
            'HOUSE_CNT': [None],
        })

        dissolve_dupes_mock = mocker.Mock()
        dissolve_dupes_mock.return_value = parcel_df
        mocker.patch.object(pd.DataFrame.spatial, 'from_featureclass')
        mocker.patch.object(dissolve, 'dissolve_duplicates_by_dataframe', new=dissolve_dupes_mock)

        cleaned_parcels = helpers.load_and_clean_parcels('foo')

        test_df = pd.DataFrame({
            'OBJECTID': [0],
            'PARCEL_ID': ['15'],
            'SHAPE': ['shape1'],
            'HOUSE_CNT': [np.nan],
        })

        tm.assert_frame_equal(cleaned_parcels, test_df)

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

    def test_add_extra_info_from_csv_merges_properly(self, mocker):
        csv_join_fields = ['ACCOUNTNO', 'class', 'des_all']
        csv_df = pd.DataFrame({
            csv_join_fields[0]: ['01', '02', '03'],
            csv_join_fields[1]: ['foo', 'bar', 'baz'],
            csv_join_fields[2]: ['fee', 'fi', 'fo']
        })

        parcels_df = pd.DataFrame({
            'PARCEL_ID': ['01', '02', '03'],
        })

        from_csv_method_mock = mocker.MagicMock()
        from_csv_method_mock.return_value = csv_df
        mocker.patch.object(pd, 'read_csv', new=from_csv_method_mock)

        joined_df = helpers.add_extra_info_from_csv('fake_csv_path', 2, csv_join_fields, parcels_df)

        test_df = pd.DataFrame({
            'PARCEL_ID': ['01', '02', '03'],
            'ACCOUNTNO': ['01', '02', '03'],
            'class': ['foo', 'bar', 'baz'],
            'des_all': ['fee', 'fi', 'fo']
        })

        tm.assert_frame_equal(joined_df, test_df)

    def test_add_extra_info_from_csv_pads_properly(self, mocker):
        csv_join_fields = ['ACCOUNTNO', 'class', 'des_all']
        csv_df = pd.DataFrame({
            csv_join_fields[0]: ['1', '2', '3'],
            csv_join_fields[1]: ['foo', 'bar', 'baz'],
            csv_join_fields[2]: ['fee', 'fi', 'fo']
        })

        parcels_df = pd.DataFrame({
            'PARCEL_ID': ['01', '02', '03'],
        })

        from_csv_method_mock = mocker.MagicMock()
        from_csv_method_mock.return_value = csv_df
        mocker.patch.object(pd, 'read_csv', new=from_csv_method_mock)

        joined_df = helpers.add_extra_info_from_csv('fake_csv_path', 2, csv_join_fields, parcels_df)

        test_df = pd.DataFrame({
            'PARCEL_ID': ['01', '02', '03'],
            'ACCOUNTNO': ['01', '02', '03'],
            'class': ['foo', 'bar', 'baz'],
            'des_all': ['fee', 'fi', 'fo']
        })

        tm.assert_frame_equal(joined_df, test_df)

    def test_add_extra_info_from_csv_removes_na_accountnos(self, mocker):
        csv_join_fields = ['ACCOUNTNO', 'class', 'des_all']
        csv_df = pd.DataFrame({
            csv_join_fields[0]: ['01', '02', np.nan],
            csv_join_fields[1]: ['foo', 'bar', 'baz'],
            csv_join_fields[2]: ['fee', 'fi', 'fo']
        })

        parcels_df = pd.DataFrame({
            'PARCEL_ID': ['01', '02', '03'],
        })

        from_csv_method_mock = mocker.MagicMock()
        from_csv_method_mock.return_value = csv_df
        mocker.patch.object(pd, 'read_csv', new=from_csv_method_mock)

        joined_df = helpers.add_extra_info_from_csv('fake_csv_path', 2, csv_join_fields, parcels_df)

        test_df = pd.DataFrame({
            'PARCEL_ID': ['01', '02', '03'],
            'ACCOUNTNO': ['01', '02', np.nan],
            'class': ['foo', 'bar', np.nan],
            'des_all': ['fee', 'fi', np.nan],
        })

        tm.assert_frame_equal(joined_df, test_df)

    def test_add_extra_info_from_csv_raises_error_on_non_unique_join_values(self, mocker):
        csv_join_fields = ['ACCOUNTNO', 'class', 'des_all']
        csv_df = pd.DataFrame({
            csv_join_fields[0]: ['1', '2', '2'],
            csv_join_fields[1]: ['foo', 'bar', 'baz'],
            csv_join_fields[2]: ['fee', 'fi', 'fo']
        })

        parcels_df = pd.DataFrame({
            'PARCEL_ID': ['01', '02', '03'],
        })

        from_csv_method_mock = mocker.MagicMock()
        from_csv_method_mock.return_value = csv_df
        mocker.patch.object(pd, 'read_csv', new=from_csv_method_mock)

        with pytest.raises(ValueError) as error:
            joined_df = helpers.add_extra_info_from_csv('fake_csv_path', 2, csv_join_fields, parcels_df)
        assert 'Values in csv join field ACCOUNTNO are not unique.' in str(error.value)

    def test_add_extra_info_from_csv_includes_rows_not_in_csv(self, mocker):
        csv_join_fields = ['ACCOUNTNO', 'class', 'des_all']
        csv_df = pd.DataFrame({
            csv_join_fields[0]: ['01', '02'],
            csv_join_fields[1]: ['foo', 'bar'],
            csv_join_fields[2]: ['fee', 'fi'],
        })

        parcels_df = pd.DataFrame({
            'PARCEL_ID': ['01', '02', '03'],
        })

        from_csv_method_mock = mocker.MagicMock()
        from_csv_method_mock.return_value = csv_df
        mocker.patch.object(pd, 'read_csv', new=from_csv_method_mock)

        joined_df = helpers.add_extra_info_from_csv('fake_csv_path', 2, csv_join_fields, parcels_df)

        test_df = pd.DataFrame({
            'PARCEL_ID': ['01', '02', '03'],
            'ACCOUNTNO': ['01', '02', np.nan],
            'class': ['foo', 'bar', np.nan],
            'des_all': ['fee', 'fi', np.nan],
        })

        tm.assert_frame_equal(joined_df, test_df)

    def test_get_centroids_copy_of_polygon_df_joins_properly(self, mocker):

        mocker.patch('arcpy.management.FeatureToPoint')
        mocker.patch.object(pd.DataFrame.spatial, 'to_featureclass')

        parcels_df = pd.DataFrame({
            'PARCEL_ID': ['01', '02'],
            'VALUE': [20, 4.2],
        })

        centroids_df = pd.DataFrame({
            'parcel_id': ['01', '02'],
            'SHAPE': ['shape1', 'shape2'],
        })

        from_featureclass_mock = mocker.Mock()
        from_featureclass_mock.return_value = centroids_df
        mocker.patch.object(pd.DataFrame.spatial, 'from_featureclass', new=from_featureclass_mock)
        mocker.patch.object(pd.DataFrame.spatial, 'set_geometry')

        output_df = helpers.get_centroids_copy_of_polygon_df(parcels_df, 'PARCEL_ID')

        test_df = pd.DataFrame({
            'PARCEL_ID': ['01', '02'],
            # 'VALUE': [20, 4.2],
            'SHAPE': ['shape1', 'shape2'],
        })

        tm.assert_frame_equal(output_df, test_df)

    def test_get_centroids_copy_of_polygon_df_handles_different_join_field_types(self, mocker):

        mocker.patch('arcpy.management.FeatureToPoint')
        mocker.patch.object(pd.DataFrame.spatial, 'to_featureclass')

        parcels_df = pd.DataFrame({
            'PARCEL_ID': [1, 2],
            'VALUE': [20, 4.2],
        })

        centroids_df = pd.DataFrame({
            'parcel_id': ['1', '2'],
            'SHAPE': ['shape1', 'shape2'],
        })

        from_featureclass_mock = mocker.Mock()
        from_featureclass_mock.return_value = centroids_df
        mocker.patch.object(pd.DataFrame.spatial, 'from_featureclass', new=from_featureclass_mock)
        mocker.patch.object(pd.DataFrame.spatial, 'set_geometry')

        output_df = helpers.get_centroids_copy_of_polygon_df(parcels_df, 'PARCEL_ID')

        test_df = pd.DataFrame({
            'PARCEL_ID': [1, 2],
            # 'VALUE': [20, 4.2],
            'SHAPE': ['shape1', 'shape2'],
        })

        tm.assert_frame_equal(output_df, test_df)

    def test_clean_dissolved_field_names_removes_prefixes(self):
        field_names = ['FIRST_THING', 'MAX_FOO', 'SUM_BAR']
        prefixes = ['FIRST', 'MAX', 'SUM']

        cleaned_names = helpers.clean_dissolve_field_names(field_names, prefixes)

        test_names = {
            'FIRST_THING': 'THING',
            'MAX_FOO': 'FOO',
            'SUM_BAR': 'BAR',
        }

        assert cleaned_names == test_names

    def test_clean_dissolved_field_names_doesnt_mangle_other_underscores(self):
        field_names = ['FIRST_THING', 'MAX_FOO', 'BAR_BAZ']
        prefixes = ['FIRST', 'MAX', 'SUM']

        cleaned_names = helpers.clean_dissolve_field_names(field_names, prefixes)

        test_names = {
            'FIRST_THING': 'THING',
            'MAX_FOO': 'FOO',
        }

        assert cleaned_names == test_names

    def test_clean_dissolved_field_names_ignores_single_word_names(self):
        field_names = ['FIRST_THING', 'MAX_FOO', 'BAR']
        prefixes = ['FIRST', 'MAX', 'SUM']

        cleaned_names = helpers.clean_dissolve_field_names(field_names, prefixes)

        test_names = {
            'FIRST_THING': 'THING',
            'MAX_FOO': 'FOO',
        }

        assert cleaned_names == test_names


class TestClassifyFromArea:

    def test_classify_from_area_properly_classifies(self, mocker):
        test_parcels_df = pd.DataFrame({
            'PARCEL_ID': [11, 12],
            'UNIT_COUNT': [1, 2],
            'SHAPE': ['parcel_shape_1', 'parcel_shape_2'],
        })

        test_centroids_df = pd.DataFrame({
            'PARCEL_ID': [11, 12],
            'SHAPE': ['centroid_shape_1', 'centroid_shape_2'],
        })
        test_centroids_df.spatial = mocker.Mock()
        test_centroids_df.spatial.sr = {'wkid': 'foo'}

        test_common_areas_df = pd.DataFrame({
            'common_area_key': [1],
            'SHAPE': ['addr_shape_1'],
        })
        test_common_areas_df.spatial = mocker.Mock()
        test_common_areas_df.spatial.sr = {'wkid': 'foo'}

        joined_df = pd.DataFrame({
            'PARCEL_ID': [11, 12],
            'SHAPE': ['centroid_shape_1', 'centroid_shape_2'],
            'common_area_key': [1, 1],
            'index_right': [0, 1],
        })

        join_method_mock = mocker.MagicMock()
        join_method_mock.return_value = joined_df
        test_centroids_df.spatial.join = join_method_mock

        classify_info = ('common_area_key', 'parcel_type', 'owned_unit_grouping')
        oug_parcels = helpers.classify_from_area(
            test_parcels_df, test_centroids_df, 'PARCEL_ID', test_common_areas_df, classify_info
        )

        test_df = pd.DataFrame({
            'PARCEL_ID': [11, 12],
            'UNIT_COUNT': [1, 2],
            'SHAPE': ['parcel_shape_1', 'parcel_shape_2'],
            'common_area_key': [1, 1],
            'parcel_type': ['owned_unit_grouping', 'owned_unit_grouping']
        })

        tm.assert_frame_equal(oug_parcels, test_df)

    def test_classify_from_area_doesnt_classify_non_matching(self, mocker):
        test_parcels_df = pd.DataFrame({
            'PARCEL_ID': [11, 12],
            'UNIT_COUNT': [1, 2],
            'SHAPE': ['parcel_shape_1', 'parcel_shape_2'],
        })

        test_centroids_df = pd.DataFrame({
            'PARCEL_ID': [11, 12],
            'SHAPE': ['centroid_shape_1', 'centroid_shape_2'],
        })
        test_centroids_df.spatial = mocker.Mock()
        test_centroids_df.spatial.sr = {'wkid': 'foo'}

        test_common_areas_df = pd.DataFrame({
            'common_area_key': [1],
            'SHAPE': ['addr_shape_1'],
        })
        test_common_areas_df.spatial = mocker.Mock()
        test_common_areas_df.spatial.sr = {'wkid': 'foo'}

        joined_df = pd.DataFrame({
            'PARCEL_ID': [11, 12],
            'SHAPE': ['centroid_shape_1', 'centroid_shape_2'],
            'common_area_key': [1, np.nan],
            'index_right': [0, 1],
        })

        join_method_mock = mocker.MagicMock()
        join_method_mock.return_value = joined_df
        test_centroids_df.spatial.join = join_method_mock

        classify_info = ('common_area_key', 'parcel_type', 'owned_unit_grouping')
        oug_parcels = helpers.classify_from_area(
            test_parcels_df, test_centroids_df, 'PARCEL_ID', test_common_areas_df, classify_info
        )

        test_df = pd.DataFrame({
            'PARCEL_ID': [11, 12],
            'UNIT_COUNT': [1, 2],
            'SHAPE': ['parcel_shape_1', 'parcel_shape_2'],
            'common_area_key': [1, np.nan],
            'parcel_type': ['owned_unit_grouping', np.nan]
        })

        tm.assert_frame_equal(oug_parcels, test_df)

    # def test_classify_from_area_raises_warning_on_more_rows_after_join(self, mocker):
    #     test_parcels_df = pd.DataFrame({
    #         'PARCEL_ID': [11, 12],
    #         'SHAPE': ['parcel_shape_1', 'parcel_shape_2'],
    #     })

    #     test_common_areas_df = pd.DataFrame({
    #         'common_area_key': [1],
    #         'SHAPE': ['addr_shape_1'],
    #     })

    #     joined_df = pd.DataFrame({
    #         'PARCEL_ID': [11, 12, np.nan],
    #         'SHAPE': ['parcel_shape_1', 'parcel_shape_2', np.nan],
    #         'common_area_key': [1, 1, 1],
    #         'index_right': [0, 1, 2],
    #     })

    #     join_method_mock = mocker.MagicMock()
    #     join_method_mock.return_value = joined_df

    #     mocker.patch.object(pd.DataFrame.spatial, 'join', new=join_method_mock)
    #     mocker.patch('housing_unit_inventory.helpers.change_geometry')

    #     with pytest.warns(UserWarning) as record:
    #         classify_info = ('common_area_key', 'parcel_type', 'owned_unit_grouping')
    #         oug_parcels = helpers.classify_from_area(test_parcels_df, test_common_areas_df, classify_info)
    #     assert record[0].message.args[
    #         0] == 'Different number of features in joined dataframe (3) than in original parcels (2)'

    # def test_classify_from_area_raises_warning_on_fewer_rows_after_join(self, mocker):
    #     test_parcels_df = pd.DataFrame({
    #         'PARCEL_ID': [11, 12],
    #         'SHAPE': ['parcel_shape_1', 'parcel_shape_2'],
    #     })

    #     test_common_areas_df = pd.DataFrame({
    #         'common_area_key': [1],
    #         'SHAPE': ['addr_shape_1'],
    #     })

    #     joined_df = pd.DataFrame({
    #         'PARCEL_ID': [11],
    #         'SHAPE': ['parcel_shape_1'],
    #         'common_area_key': [1],
    #         'index_right': [0],
    #     })

    #     join_method_mock = mocker.MagicMock()
    #     join_method_mock.return_value = joined_df

    #     mocker.patch.object(pd.DataFrame.spatial, 'join', new=join_method_mock)
    #     mocker.patch('housing_unit_inventory.helpers.change_geometry')

    #     with pytest.warns(UserWarning) as record:
    #         classify_info = ('common_area_key', 'parcel_type', 'owned_unit_grouping')
    #         oug_parcels = helpers.classify_from_area(test_parcels_df, test_common_areas_df, classify_info)
    #     assert record[0].message.args[
    #         0] == 'Different number of features in joined dataframe (1) than in original parcels (2)'

    def test_classify_from_area_raises_warning_on_more_duplicate_parcel_ids_after_join(self, mocker):
        test_parcels_df = pd.DataFrame({
            'PARCEL_ID': [11, 12],
            'UNIT_COUNT': [1, 2],
            'SHAPE': ['parcel_shape_1', 'parcel_shape_2'],
        })

        test_centroids_df = pd.DataFrame({
            'PARCEL_ID': [11, 12],
            'SHAPE': ['centroid_shape_1', 'centroid_shape_2'],
        })
        test_centroids_df.spatial = mocker.Mock()
        test_centroids_df.spatial.sr = {'wkid': 'foo'}

        test_common_areas_df = pd.DataFrame({
            'common_area_key': [1],
            'SHAPE': ['addr_shape_1'],
        })
        test_common_areas_df.spatial = mocker.Mock()
        test_common_areas_df.spatial.sr = {'wkid': 'foo'}

        joined_df = pd.DataFrame({
            'PARCEL_ID': [11, 11],
            'SHAPE': ['centroid_shape_1', 'centroid_shape_2'],
            'common_area_key': [1, 1],
            'index_right': [0, 0],
        })

        join_method_mock = mocker.MagicMock()
        join_method_mock.return_value = joined_df
        test_centroids_df.spatial.join = join_method_mock

        with pytest.warns(UserWarning) as record:
            classify_info = ('common_area_key', 'parcel_type', 'owned_unit_grouping')
            oug_parcels = helpers.classify_from_area(
                test_parcels_df, test_centroids_df, 'PARCEL_ID', test_common_areas_df, classify_info
            )
        assert record[0].message.args[0] == '2 duplicate keys found in spatial join; check areas features for overlaps'

    def test_classify_from_area_raises_error_on_missing_classify_info(self, mocker):
        test_parcels_df = pd.DataFrame({
            'PARCEL_ID': [11, 12],
            'UNIT_COUNT': [1, 2],
            'SHAPE': ['parcel_shape_1', 'parcel_shape_2'],
        })

        test_centroids_df = pd.DataFrame({
            'PARCEL_ID': [11, 12],
            'SHAPE': ['centroid_shape_1', 'centroid_shape_2'],
        })
        test_centroids_df.spatial = mocker.Mock()
        test_centroids_df.spatial.sr = {'wkid': 'foo'}

        test_common_areas_df = pd.DataFrame({
            'common_area_key': [1],
            'SHAPE': ['addr_shape_1'],
        })
        test_common_areas_df.spatial = mocker.Mock()
        test_common_areas_df.spatial.sr = {'wkid': 'foo'}

        joined_df = pd.DataFrame({
            'PARCEL_ID': [11, 12],
            'SHAPE': ['centroid_shape_1', 'centroid_shape_2'],
            'common_area_key': [1, 1],
            'index_right': [0, 0],
        })

        join_method_mock = mocker.MagicMock()
        join_method_mock.return_value = joined_df
        test_centroids_df.spatial.join = join_method_mock

        with pytest.raises(ValueError) as error:
            classify_info = ('common_area_key', 'parcel_type')
            oug_parcels = helpers.classify_from_area(
                test_parcels_df, test_centroids_df, 'PARCEL_ID', test_common_areas_df, classify_info
            )
        assert 'classify_info should be (areas_unique_key_column, classify_column, classify_value)' in str(error.value)

    def test_classify_from_area_ignores_empty_classify_info(self, mocker):
        test_parcels_df = pd.DataFrame({
            'PARCEL_ID': [11, 12],
            'UNIT_COUNT': [1, 2],
            'SHAPE': ['parcel_shape_1', 'parcel_shape_2'],
        })

        test_centroids_df = pd.DataFrame({
            'PARCEL_ID': [11, 12],
            'SHAPE': ['centroid_shape_1', 'centroid_shape_2'],
        })
        test_centroids_df.spatial = mocker.Mock()
        test_centroids_df.spatial.sr = {'wkid': 'foo'}

        test_common_areas_df = pd.DataFrame({
            'common_area_key': [1],
            'SHAPE': ['addr_shape_1'],
        })
        test_common_areas_df.spatial = mocker.Mock()
        test_common_areas_df.spatial.sr = {'wkid': 'foo'}

        joined_df = pd.DataFrame({
            'PARCEL_ID': [11, 12],
            'SHAPE': ['centroid_shape_1', 'centroid_shape_2'],
            'common_area_key': [1, 1],
            'index_right': [0, 1],
        })

        join_method_mock = mocker.MagicMock()
        join_method_mock.return_value = joined_df
        test_centroids_df.spatial.join = join_method_mock

        oug_parcels = helpers.classify_from_area(test_parcels_df, test_centroids_df, 'PARCEL_ID', test_common_areas_df)
        test_df = pd.DataFrame({
            'PARCEL_ID': [11, 12],
            'UNIT_COUNT': [1, 2],
            'SHAPE': ['parcel_shape_1', 'parcel_shape_2'],
            'common_area_key': [1, 1],
        })

        tm.assert_frame_equal(oug_parcels, test_df)

    def test_classify_from_area_adds_area_info_from_join(self, mocker):
        test_parcels_df = pd.DataFrame({
            'PARCEL_ID': [11, 12],
            'UNIT_COUNT': [1, 2],
            'SHAPE': ['parcel_shape_1', 'parcel_shape_2'],
        })

        test_centroids_df = pd.DataFrame({
            'PARCEL_ID': [11, 12],
            'SHAPE': ['centroid_shape_1', 'centroid_shape_2'],
        })
        test_centroids_df.spatial = mocker.Mock()
        test_centroids_df.spatial.sr = {'wkid': 'foo'}

        test_common_areas_df = pd.DataFrame({
            'common_area_key': [1],
            'SHAPE': ['addr_shape_1'],
            'NAME': ['city1'],
        })
        test_common_areas_df.spatial = mocker.Mock()
        test_common_areas_df.spatial.sr = {'wkid': 'foo'}

        joined_df = pd.DataFrame({
            'PARCEL_ID': [11, 12],
            'SHAPE': ['centroid_shape_1', 'centroid_shape_2'],
            'common_area_key': [1, 1],
            'NAME': ['city1', 'city1'],
            'index_right': [0, 1],
        })

        join_method_mock = mocker.MagicMock()
        join_method_mock.return_value = joined_df
        test_centroids_df.spatial.join = join_method_mock

        oug_parcels = helpers.classify_from_area(test_parcels_df, test_centroids_df, 'PARCEL_ID', test_common_areas_df)
        test_df = pd.DataFrame({
            'PARCEL_ID': [11, 12],
            'UNIT_COUNT': [1, 2],
            'SHAPE': ['parcel_shape_1', 'parcel_shape_2'],
            'common_area_key': [1, 1],
            'NAME': ['city1', 'city1'],
        })

        tm.assert_frame_equal(oug_parcels, test_df)

    def test_classify_from_area_subsets_columns_in_area_data(self, mocker):
        mocker.patch.object(helpers.pd.DataFrame, 'spatial')

        test_parcels_df = pd.DataFrame({
            'PARCEL_ID': [11, 12],
            'UNIT_COUNT': [1, 2],
            'SHAPE': ['parcel_shape_1', 'parcel_shape_2'],
        })

        test_centroids_df = pd.DataFrame({
            'PARCEL_ID': [11, 12],
            'SHAPE': ['centroid_shape_1', 'centroid_shape_2'],
        })
        test_centroids_df.spatial.sr = {'wkid': 'foo'}

        test_areas_df = pd.DataFrame({
            'common_area_key': [1],
            'SHAPE': ['addr_shape_1'],
            'NAME': ['city1'],
            'field1': ['bar'],
            'field2': ['boo'],
        })
        test_areas_df.spatial.sr = {'wkid': 'foo'}

        joined_df = pd.DataFrame({
            'PARCEL_ID': [11, 12],
            'SHAPE': ['centroid_shape_1', 'centroid_shape_2'],
            'NAME': ['city1', 'city1'],
            'field2': ['boo', 'boo'],
            'index_right': [0, 1],
        })
        test_centroids_df.spatial.join.return_value = joined_df

        columns = ['Name', 'field2']

        area_joined_parcels = helpers.classify_from_area(
            test_parcels_df, test_centroids_df, 'PARCEL_ID', test_areas_df, columns_to_keep=columns
        )

        test_df = pd.DataFrame({
            'PARCEL_ID': [11, 12],
            'UNIT_COUNT': [1, 2],
            'SHAPE': ['parcel_shape_1', 'parcel_shape_2'],
            'NAME': ['city1', 'city1'],
            'field2': ['boo', 'boo'],
        })

        tm.assert_frame_equal(area_joined_parcels, test_df)

    def test_classify_from_area_reprojects(self, mocker):
        test_parcels_df = pd.DataFrame({
            'PARCEL_ID': [11, 12],
            'UNIT_COUNT': [1, 2],
            'SHAPE': ['parcel_shape_1', 'parcel_shape_2'],
        })

        test_centroids_df = pd.DataFrame({
            'PARCEL_ID': [11, 12],
            'SHAPE': ['centroid_shape_1', 'centroid_shape_2'],
        })
        test_centroids_df.spatial = mocker.Mock()
        test_centroids_df.spatial.sr = {'wkid': 'foo'}

        test_common_areas_df = pd.DataFrame({
            'common_area_key': [1],
            'SHAPE': ['addr_shape_1'],
        })
        test_common_areas_df.spatial = mocker.Mock()
        test_common_areas_df.spatial.sr = {'wkid': 'bar'}

        joined_df = pd.DataFrame({
            'PARCEL_ID': [11, 12],
            'SHAPE': ['centroid_shape_1', 'centroid_shape_2'],
            'common_area_key': [1, 1],
            'index_right': [0, 1],
        })

        test_common_areas_df.spatial.project.return_value = True

        join_method_mock = mocker.MagicMock()
        join_method_mock.return_value = joined_df
        test_centroids_df.spatial.join = join_method_mock

        classify_info = ('common_area_key', 'parcel_type', 'owned_unit_grouping')
        oug_parcels = helpers.classify_from_area(
            test_parcels_df, test_centroids_df, 'PARCEL_ID', test_common_areas_df, classify_info
        )

        test_df = pd.DataFrame({
            'PARCEL_ID': [11, 12],
            'UNIT_COUNT': [1, 2],
            'SHAPE': ['parcel_shape_1', 'parcel_shape_2'],
            'common_area_key': [1, 1],
            'parcel_type': ['owned_unit_grouping', 'owned_unit_grouping']
        })

        test_common_areas_df.spatial.project.assert_called_once()
        tm.assert_frame_equal(oug_parcels, test_df)

    def test_classify_from_area_raises_error_on_failed_reproject(self, mocker):
        test_parcels_df = pd.DataFrame({
            'PARCEL_ID': [11, 12],
            'UNIT_COUNT': [1, 2],
            'SHAPE': ['parcel_shape_1', 'parcel_shape_2'],
        })

        test_centroids_df = pd.DataFrame({
            'PARCEL_ID': [11, 12],
            'SHAPE': ['centroid_shape_1', 'centroid_shape_2'],
        })
        test_centroids_df.spatial = mocker.Mock()
        test_centroids_df.spatial.sr = {'wkid': 'foo'}

        test_common_areas_df = pd.DataFrame({
            'common_area_key': [1],
            'SHAPE': ['addr_shape_1'],
        })
        test_common_areas_df.spatial = mocker.Mock()
        test_common_areas_df.spatial.sr = {'wkid': 'bar'}

        test_common_areas_df.spatial.project.return_value = False

        classify_info = ('common_area_key', 'parcel_type', 'owned_unit_grouping')
        with pytest.raises(RuntimeError) as error:
            oug_parcels = helpers.classify_from_area(
                test_parcels_df, test_centroids_df, 'PARCEL_ID', test_common_areas_df, classify_info
            )
        assert 'Reprojecting area_df to foo did not succeed.' in str(error.value)


class TestFinalMergingAndCleaning:

    def test_concat_evaluated_dataframes_merges_normally(self):
        df1 = pd.DataFrame({'PARCEL_ID': [1, 2, 3], 'DATA': ['a', 'b', 'c']})

        df2 = pd.DataFrame({'PARCEL_ID': [4, 5, 6], 'DATA': ['d', 'e', 'f']})

        concat_df = helpers.concat_evaluated_dataframes([df1, df2])

        test_df = pd.DataFrame({
            'PARCEL_ID': [1, 2, 3, 4, 5, 6],
            'DATA': ['a', 'b', 'c', 'd', 'e', 'f'],
        })
        test_df.index = [0, 1, 2, 0, 1, 2]

        tm.assert_frame_equal(concat_df, test_df)

    def test_concat_cities_metro_townships_concats_normally(self):
        cities_df = pd.DataFrame({
            'name': ['foo', 'bar'],
            'ugrcode': ['fo', 'br'],
            'SHAPE': ['shape1', 'shape2'],
        })

        townships_df = pd.DataFrame({
            'name': ['baz'],
            'ugrcode': ['bz'],
            'SHAPE': ['shape3'],
        })

        concat_df = helpers.concat_cities_metro_townships(cities_df, townships_df)

        test_df = pd.DataFrame({
            'name': ['foo', 'bar', 'baz'],
            'ugrcode': ['fo', 'br', 'bz'],
            'SHAPE': ['shape1', 'shape2', 'shape3'],
        })

    def test_concat_cities_metro_townships_gets_inner_fields(self):
        cities_df = pd.DataFrame({
            'name': ['foo', 'bar'],
            'ugrcode': ['fo', 'br'],
            'SHAPE': ['shape1', 'shape2'],
            'thing': [1, 2],
        })

        townships_df = pd.DataFrame({
            'name': ['baz'],
            'ugrcode': ['bz'],
            'SHAPE': ['shape3'],
            'fake': [3],
        })

        concat_df = helpers.concat_cities_metro_townships(cities_df, townships_df)

        test_df = pd.DataFrame({
            'name': ['foo', 'bar', 'baz'],
            'ugrcode': ['fo', 'br', 'bz'],
            'SHAPE': ['shape1', 'shape2', 'shape3'],
        })

    def test_concat_cities_metro_townships_removes_columns(self):
        cities_df = pd.DataFrame({
            'name': ['foo', 'bar'],
            'ugrcode': ['fo', 'br'],
            'SHAPE': ['shape1', 'shape2'],
            'thing': [1, 2],
        })

        townships_df = pd.DataFrame({
            'name': ['baz'],
            'ugrcode': ['bz'],
            'SHAPE': ['shape3'],
            'thing': [3],
        })

        concat_df = helpers.concat_cities_metro_townships(cities_df, townships_df)

        test_df = pd.DataFrame({
            'name': ['foo', 'bar', 'baz'],
            'ugrcode': ['fo', 'br', 'bz'],
            'SHAPE': ['shape1', 'shape2', 'shape3'],
        })


class TestFIPSExtraction:

    def test_extract_tract_geoid_normal(self):
        dataframe = pd.DataFrame({
            'id': [1, 2],
            'block': [223336666664444, 223339999994444],
        })

        extracted_df = helpers.extract_tract_geoid(dataframe, 'block', 'tract')

        test_df = pd.DataFrame({
            'id': [1, 2],
            'block': [223336666664444, 223339999994444],
            'tract': ['22333666666', '22333999999'],
        })

        tm.assert_frame_equal(extracted_df, test_df)
