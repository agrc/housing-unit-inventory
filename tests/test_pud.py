import pandas as pd
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


class TestNoBaseAddress:

    def test_get_non_base_addr_points_with_non_base_addrs(self, mocker):
        test_df = pd.DataFrame({'id': [0, 1, 2, 3], 'PtType': ['', '', 'BASE ADDRESS', '']})
        from_featureclass_mock = mocker.Mock()
        from_featureclass_mock.return_value = test_df
        mocker.patch.object(pd.DataFrame.spatial, 'from_featureclass', new=from_featureclass_mock)

        mock_fc = mocker.Mock()

        output_df = helpers.get_non_base_addr_points(mock_fc)

        test_df = pd.DataFrame({'id': [0, 1, 3], 'PtType': ['', '', '']}, index=[0, 1, 3])

        tm.assert_frame_equal(output_df, test_df)
