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


class TestClassifyFromArea:

    def test_classify_from_area_properly_classifies(self, mocker):
        test_parcels_df = pd.DataFrame({
            'PARCEL_ID': [11, 12],
            'SHAPE': ['parcel_shape_1', 'parcel_shape_2'],
        })

        test_common_areas_df = pd.DataFrame({
            'common_area_key': [1],
            'SHAPE': ['addr_shape_1'],
        })

        joined_df = pd.DataFrame({
            'PARCEL_ID': [11, 12],
            'SHAPE': ['parcel_shape_1', 'parcel_shape_2'],
            'common_area_key': [1, 1]
        })

        join_method_mock = mocker.MagicMock()
        join_method_mock.return_value = joined_df

        mocker.patch.object(pd.DataFrame.spatial, 'join', new=join_method_mock)
        mocker.patch('housing_unit_inventory.helpers.change_geometry')

        classify_info = ('common_area_key', 'parcel_type', 'owned_unit_grouping')
        oug_parcels = helpers.classify_from_area(test_parcels_df, test_common_areas_df, classify_info)

        test_df = pd.DataFrame({
            'PARCEL_ID': [11, 12],
            'SHAPE': ['parcel_shape_1', 'parcel_shape_2'],
            'common_area_key': [1, 1],
            'parcel_type': ['owned_unit_grouping', 'owned_unit_grouping']
        })

        tm.assert_frame_equal(oug_parcels, test_df)

    def test_classify_from_area_doesnt_classify_non_matching(self, mocker):
        test_parcels_df = pd.DataFrame({
            'PARCEL_ID': [11, 12],
            'SHAPE': ['parcel_shape_1', 'parcel_shape_2'],
        })

        test_common_areas_df = pd.DataFrame({
            'common_area_key': [1],
            'SHAPE': ['addr_shape_1'],
        })

        joined_df = pd.DataFrame({
            'PARCEL_ID': [11, 12],
            'SHAPE': ['parcel_shape_1', 'parcel_shape_2'],
            'common_area_key': [1, np.nan]
        })

        join_method_mock = mocker.MagicMock()
        join_method_mock.return_value = joined_df

        mocker.patch.object(pd.DataFrame.spatial, 'join', new=join_method_mock)
        mocker.patch('housing_unit_inventory.helpers.change_geometry')

        classify_info = ('common_area_key', 'parcel_type', 'owned_unit_grouping')
        oug_parcels = helpers.classify_from_area(test_parcels_df, test_common_areas_df, classify_info)

        test_df = pd.DataFrame({
            'PARCEL_ID': [11, 12],
            'SHAPE': ['parcel_shape_1', 'parcel_shape_2'],
            'common_area_key': [1, np.nan],
            'parcel_type': ['owned_unit_grouping', np.nan]
        })

        tm.assert_frame_equal(oug_parcels, test_df)

    def test_classify_from_area_raises_warning_on_more_rows_after_join(self, mocker):
        test_parcels_df = pd.DataFrame({
            'PARCEL_ID': [11, 12],
            'SHAPE': ['parcel_shape_1', 'parcel_shape_2'],
        })

        test_common_areas_df = pd.DataFrame({
            'common_area_key': [1],
            'SHAPE': ['addr_shape_1'],
        })

        joined_df = pd.DataFrame({
            'PARCEL_ID': [11, 12, np.nan],
            'SHAPE': ['parcel_shape_1', 'parcel_shape_2', np.nan],
            'common_area_key': [1, 1, 1]
        })

        join_method_mock = mocker.MagicMock()
        join_method_mock.return_value = joined_df

        mocker.patch.object(pd.DataFrame.spatial, 'join', new=join_method_mock)
        mocker.patch('housing_unit_inventory.helpers.change_geometry')

        with pytest.warns(UserWarning) as record:
            classify_info = ('common_area_key', 'parcel_type', 'owned_unit_grouping')
            oug_parcels = helpers.classify_from_area(test_parcels_df, test_common_areas_df, classify_info)
        assert record[0].message.args[
            0] == 'Different number of features in joined dataframe (3) than in original parcels (2)'

    def test_classify_from_area_raises_warning_on_fewer_rows_after_join(self, mocker):
        test_parcels_df = pd.DataFrame({
            'PARCEL_ID': [11, 12],
            'SHAPE': ['parcel_shape_1', 'parcel_shape_2'],
        })

        test_common_areas_df = pd.DataFrame({
            'common_area_key': [1],
            'SHAPE': ['addr_shape_1'],
        })

        joined_df = pd.DataFrame({
            'PARCEL_ID': [11],
            'SHAPE': ['parcel_shape_1'],
            'common_area_key': [1],
        })

        join_method_mock = mocker.MagicMock()
        join_method_mock.return_value = joined_df

        mocker.patch.object(pd.DataFrame.spatial, 'join', new=join_method_mock)
        mocker.patch('housing_unit_inventory.helpers.change_geometry')

        with pytest.warns(UserWarning) as record:
            classify_info = ('common_area_key', 'parcel_type', 'owned_unit_grouping')
            oug_parcels = helpers.classify_from_area(test_parcels_df, test_common_areas_df, classify_info)
        assert record[0].message.args[
            0] == 'Different number of features in joined dataframe (1) than in original parcels (2)'

    def test_classify_from_area_raises_warning_on_more_duplicate_parcel_ids_after_join(self, mocker):
        test_parcels_df = pd.DataFrame({
            'PARCEL_ID': [11, 12],
            'SHAPE': ['parcel_shape_1', 'parcel_shape_2'],
        })

        test_common_areas_df = pd.DataFrame({
            'common_area_key': [1],
            'SHAPE': ['addr_shape_1'],
        })

        joined_df = pd.DataFrame({
            'PARCEL_ID': [11, 11],
            'SHAPE': ['parcel_shape_1', 'parcel_shape_1'],
            'common_area_key': [1, 1]
        })

        join_method_mock = mocker.MagicMock()
        join_method_mock.return_value = joined_df

        mocker.patch.object(pd.DataFrame.spatial, 'join', new=join_method_mock)
        mocker.patch('housing_unit_inventory.helpers.change_geometry')

        with pytest.warns(UserWarning) as record:
            classify_info = ('common_area_key', 'parcel_type', 'owned_unit_grouping')
            oug_parcels = helpers.classify_from_area(test_parcels_df, test_common_areas_df, classify_info)
        assert record[0].message.args[0] == '2 duplicate parcels found in join; check areas features for overlaps'

    def test_classify_from_area_raises_error_on_missing_classify_info(self, mocker):
        test_parcels_df = pd.DataFrame({
            'PARCEL_ID': [11, 12],
            'SHAPE': ['parcel_shape_1', 'parcel_shape_2'],
        })

        test_common_areas_df = pd.DataFrame({
            'common_area_key': [1],
            'SHAPE': ['addr_shape_1'],
        })

        joined_df = pd.DataFrame({
            'PARCEL_ID': [11, 12],
            'SHAPE': ['parcel_shape_1', 'parcel_shape_2'],
            'common_area_key': [1, 1]
        })

        join_method_mock = mocker.MagicMock()
        join_method_mock.return_value = joined_df

        mocker.patch.object(pd.DataFrame.spatial, 'join', new=join_method_mock)
        mocker.patch('housing_unit_inventory.helpers.change_geometry')

        with pytest.raises(ValueError) as error:
            classify_info = ('common_area_key', 'parcel_type')
            oug_parcels = helpers.classify_from_area(test_parcels_df, test_common_areas_df, classify_info)
        assert 'classify_info should be (areas_unique_key_column, classify_column, classify_value)' in str(error.value)

    def test_classify_from_area_ignores_empty_classify_info(self, mocker):
        test_parcels_df = pd.DataFrame({
            'PARCEL_ID': [11, 12],
            'SHAPE': ['parcel_shape_1', 'parcel_shape_2'],
        })

        test_common_areas_df = pd.DataFrame({
            'common_area_key': [1],
            'SHAPE': ['addr_shape_1'],
        })

        joined_df = pd.DataFrame({
            'PARCEL_ID': [11, 12],
            'SHAPE': ['parcel_shape_1', 'parcel_shape_2'],
            'common_area_key': [1, 1]
        })

        join_method_mock = mocker.MagicMock()
        join_method_mock.return_value = joined_df

        mocker.patch.object(pd.DataFrame.spatial, 'join', new=join_method_mock)
        mocker.patch('housing_unit_inventory.helpers.change_geometry')

        oug_parcels = helpers.classify_from_area(test_parcels_df, test_common_areas_df)
        test_df = pd.DataFrame({
            'PARCEL_ID': [11, 12],
            'SHAPE': ['parcel_shape_1', 'parcel_shape_2'],
            'common_area_key': [1, 1],
        })

        tm.assert_frame_equal(oug_parcels, test_df)

    def test_classify_from_area_adds_area_info_from_join(self, mocker):
        test_parcels_df = pd.DataFrame({
            'PARCEL_ID': [11, 12],
            'SHAPE': ['parcel_shape_1', 'parcel_shape_2'],
        })

        test_common_areas_df = pd.DataFrame({
            'common_area_key': [1],
            'SHAPE': ['addr_shape_1'],
            'NAME': ['city1'],
        })

        joined_df = pd.DataFrame({
            'PARCEL_ID': [11, 12],
            'SHAPE': ['parcel_shape_1', 'parcel_shape_2'],
            'common_area_key': [1, 1],
            'NAME': ['city1', 'city1'],
        })

        join_method_mock = mocker.MagicMock()
        join_method_mock.return_value = joined_df

        mocker.patch.object(pd.DataFrame.spatial, 'join', new=join_method_mock)
        mocker.patch('housing_unit_inventory.helpers.change_geometry')

        oug_parcels = helpers.classify_from_area(test_parcels_df, test_common_areas_df)
        test_df = pd.DataFrame({
            'PARCEL_ID': [11, 12],
            'SHAPE': ['parcel_shape_1', 'parcel_shape_2'],
            'common_area_key': [1, 1],
            'NAME': ['city1', 'city1'],
        })

        tm.assert_frame_equal(oug_parcels, test_df)


class TestFinalMergingAndCleaning:

    def test_concat_evaluated_dataframes_merges_normally(self):
        df1 = pd.DataFrame({'PARCEL_ID': [1, 2, 3], 'DATA': ['a', 'b', 'c']})

        df2 = pd.DataFrame({'PARCEL_ID': [4, 5, 6], 'DATA': ['d', 'e', 'f']})

        concat_df = helpers.concat_evaluated_dataframes([df1, df2])

        test_df = pd.DataFrame(
            {'DATA': ['a', 'b', 'c', 'd', 'e', 'f']},
            index=[1, 2, 3, 4, 5, 6],
        )
        test_df.index.name = 'PARCEL_ID'

        tm.assert_frame_equal(concat_df, test_df)

    def test_concat_evaluated_dataframes_raises_error_on_duplicate_index_values(self):
        df1 = pd.DataFrame({'PARCEL_ID': [1, 2, 3], 'DATA': ['a', 'b', 'c']})

        df2 = pd.DataFrame({'PARCEL_ID': [4, 5, 3], 'DATA': ['d', 'e', 'f']})

        with pytest.raises(ValueError) as error:
            concat_df = helpers.concat_evaluated_dataframes([df1, df2])

        assert 'Index has duplicate keys:' in str(error.value)

    def test_update_unit_count_fixes_single_family(self):
        parcels_df = pd.DataFrame({
            'PARCEL_ID': [1, 2],
            'SUBTYPE': ['single_family', 'single_family'],
            'UNIT_COUNT': [1, 0],
            'NOTE': ['', ''],
            'HOUSE_CNT': [1, 1],
        })

        helpers.update_unit_count(parcels_df)

        test_df = pd.DataFrame({
            'PARCEL_ID': [1, 2],
            'SUBTYPE': ['single_family', 'single_family'],
            'UNIT_COUNT': [1, 1],
            'NOTE': ['', ''],
            'HOUSE_CNT': [1, 1],
        })

        tm.assert_frame_equal(parcels_df, test_df)

    def test_update_unit_count_fixes_duplex(self):
        parcels_df = pd.DataFrame({
            'PARCEL_ID': [1, 2],
            'SUBTYPE': ['duplex', 'duplex'],
            'UNIT_COUNT': [1, 2],
            'NOTE': ['', ''],
            'HOUSE_CNT': [1, 1],
        })

        helpers.update_unit_count(parcels_df)

        test_df = pd.DataFrame({
            'PARCEL_ID': [1, 2],
            'SUBTYPE': ['duplex', 'duplex'],
            'UNIT_COUNT': [2, 2],
            'NOTE': ['', ''],
            'HOUSE_CNT': [1, 1],
        })

        tm.assert_frame_equal(parcels_df, test_df)

    def test_update_unit_count_fixes_tri_quad(self):
        parcels_df = pd.DataFrame({
            'PARCEL_ID': [1, 2],
            'SUBTYPE': ['apartment', 'apartment'],
            'NOTE': ['triplex-quadplex', 'triplex-quadplex'],
            'UNIT_COUNT': [1, 4],
            'HOUSE_CNT': [3, 4],
        })

        helpers.update_unit_count(parcels_df)

        test_df = pd.DataFrame({
            'PARCEL_ID': [1, 2],
            'SUBTYPE': ['apartment', 'apartment'],
            'NOTE': ['triplex-quadplex', 'triplex-quadplex'],
            'UNIT_COUNT': [3, 4],
            'HOUSE_CNT': [3, 4],
        })

        tm.assert_frame_equal(parcels_df, test_df)

    def test_update_unit_count_fixes_everything(self):
        parcels_df = pd.DataFrame({
            'PARCEL_ID': [1, 2, 3],
            'SUBTYPE': ['single_family', 'duplex', 'apartment'],
            'NOTE': ['', '', 'triplex-quadplex'],
            'UNIT_COUNT': [0, 1, 1],
            'HOUSE_CNT': [42, 42, 4],
        })

        helpers.update_unit_count(parcels_df)

        test_df = pd.DataFrame({
            'PARCEL_ID': [1, 2, 3],
            'SUBTYPE': ['single_family', 'duplex', 'apartment'],
            'NOTE': ['', '', 'triplex-quadplex'],
            'UNIT_COUNT': [1, 2, 4],
            'HOUSE_CNT': [42, 42, 4],
        })

        tm.assert_frame_equal(parcels_df, test_df)

    def test_update_unit_count_fixes_nothing(self):
        parcels_df = pd.DataFrame({
            'PARCEL_ID': [1, 2, 3],
            'SUBTYPE': ['single_family', 'duplex', 'apartment'],
            'NOTE': ['', '', 'triplex-quadplex'],
            'UNIT_COUNT': [1, 2, 4],
            'HOUSE_CNT': [42, 42, 4],
        })

        helpers.update_unit_count(parcels_df)

        test_df = pd.DataFrame({
            'PARCEL_ID': [1, 2, 3],
            'SUBTYPE': ['single_family', 'duplex', 'apartment'],
            'NOTE': ['', '', 'triplex-quadplex'],
            'UNIT_COUNT': [1, 2, 4],
            'HOUSE_CNT': [42, 42, 4],
        })

        tm.assert_frame_equal(parcels_df, test_df)

    def test_remove_zero_unit_house_counts_all_combos(self):
        parcels_df = pd.DataFrame({
            'PARCEL_ID': [1, 2, 3, 4],
            'UNIT_COUNT': [0, 0, 1, 1],
            'HOUSE_CNT': [0, 1, 0, 1],
        })

        helpers.remove_zero_unit_house_counts(parcels_df)

        test_df = pd.DataFrame({
            'PARCEL_ID': [4],
            'UNIT_COUNT': [1],
            'HOUSE_CNT': [1],
        }, index=[3])

        tm.assert_frame_equal(parcels_df, test_df)
