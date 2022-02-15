import pandas as pd
from pandas import testing as tm

from housing_unit_inventory import davis2020


class TestHelperMethods:

    def test_get_proper_built_yr_value_series_gets_most_common(self, mocker):
        test_parcels_df = pd.DataFrame({'PARCEL_ID': [1, 1, 1, 2], 'BUILT_YR': [5, 5, 6, 7]})

        built_yr_series = davis2020._get_proper_built_yr_value_series(test_parcels_df, 'PARCEL_ID', 'BUILT_YR')

        test_series = pd.Series(data=[5, 7], index=[1, 2], name='BUILT_YR')
        test_series.index.name = 'PARCEL_ID'
        tm.assert_series_equal(built_yr_series, test_series)
