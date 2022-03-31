import numpy as np
import pandas as pd
import pytest
from arcgis.features import GeoAccessor, GeoSeriesAccessor
# from arcgis.geometry import Geometry
from pandas import testing as tm

from housing_unit_inventory import calculate


class TestCalculations:

    def test_update_unit_count_fixes_single_family(self):
        parcels_df = pd.DataFrame({
            'PARCEL_ID': [1, 2],
            'SUBTYPE': ['single_family', 'single_family'],
            'UNIT_COUNT': [1, 0],
            'NOTE': ['', ''],
            'HOUSE_CNT': [1, 1],
        })

        calculate.update_unit_count(parcels_df)

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

        calculate.update_unit_count(parcels_df)

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

        calculate.update_unit_count(parcels_df)

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

        calculate.update_unit_count(parcels_df)

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

        calculate.update_unit_count(parcels_df)

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

        calculate.remove_zero_unit_house_counts(parcels_df)

        test_df = pd.DataFrame(
            {
                'PARCEL_ID': [2, 3, 4],
                'UNIT_COUNT': [0, 1, 1],
                'HOUSE_CNT': [1, 0, 1],
            },
            index=[1, 2, 3],
        )

        tm.assert_frame_equal(parcels_df, test_df, check_dtype=False)

    def test_remove_zero_unit_house_counts_properly_handles_nans(self):
        parcels_df = pd.DataFrame({
            'PARCEL_ID': [1, 2, 3, 4],
            'UNIT_COUNT': [np.nan, np.nan, 1, 1],
            'HOUSE_CNT': [np.nan, 1, np.nan, 1],
        })

        calculate.remove_zero_unit_house_counts(parcels_df)

        test_df = pd.DataFrame(
            {
                'PARCEL_ID': [2, 3, 4],
                'UNIT_COUNT': [0, 1, 1],
                'HOUSE_CNT': [1, 0, 1],
            },
            index=[1, 2, 3],
        )

        tm.assert_frame_equal(parcels_df, test_df, check_dtype=False)

    def test_remove_zero_unit_house_counts_mixed_zeroes_nans(self):
        parcels_df = pd.DataFrame({
            'PARCEL_ID': [1, 2, 3, 4],
            'UNIT_COUNT': [np.nan, 0, 1, 1],
            'HOUSE_CNT': [0, 1, np.nan, 1],
        })

        calculate.remove_zero_unit_house_counts(parcels_df)

        test_df = pd.DataFrame(
            {
                'PARCEL_ID': [2, 3, 4],
                'UNIT_COUNT': [0, 1, 1],
                'HOUSE_CNT': [1, 0, 1],
            },
            index=[1, 2, 3],
        )

        tm.assert_frame_equal(parcels_df, test_df, check_dtype=False)

    def test_built_decade_variety_of_years(self):
        parcels_df = pd.DataFrame({
            'PARCEL_ID': [1, 2, 3, 4],
            'BUILT_YR': [1851, 1900, 1902, 2022],
        })

        calculate.built_decade(parcels_df)

        test_df = pd.DataFrame({
            'PARCEL_ID': [1, 2, 3, 4],
            'BUILT_YR': [1851, 1900, 1902, 2022],
            'BUILT_DECADE': [1850, 1900, 1900, 2020]
        })

        tm.assert_frame_equal(parcels_df, test_df)

    def test_built_decade_raises_warning_for_invalid_year(self):
        parcels_df = pd.DataFrame({
            'PARCEL_ID': [1, 2, 3, 4],
            'BUILT_YR': [1851, 1900, 198, 2022],
        })
        with pytest.warns(UserWarning) as warning:
            calculate.built_decade(parcels_df)

        test_df = pd.DataFrame({
            'PARCEL_ID': [1, 2, 3, 4],
            'BUILT_YR': [1851, 1900, 198, 2022],
            'BUILT_DECADE': [1850, 1900, 190, 2020]
        })

        tm.assert_frame_equal(parcels_df, test_df)

        assert warning[0].message.args[
            0] == '1 parcels have an invald built year (before 1847 or after current year plus two)'

    def test_acreages_calculates_one_and_half_acres(self, mocker):
        geometry_mock_1 = mocker.Mock()
        geometry_mock_1.area = 4046.8564

        geometry_mock_2 = mocker.Mock()
        geometry_mock_2.area = 2023.4282

        parcels_df = pd.DataFrame({
            'PARCEL_ID': [1, 2],
            'SHAPE': [geometry_mock_1, geometry_mock_2],
        })

        mocker.patch.object(pd.DataFrame.spatial, 'sr', new={'wkid': 26912})

        calculate.acreages(parcels_df, 'acres')

        test_df = pd.DataFrame({
            'PARCEL_ID': [1, 2],
            'SHAPE': [geometry_mock_1, geometry_mock_2],
            'acres': [1., 0.5],
        })

        tm.assert_frame_equal(parcels_df, test_df)

    def test_acreages_warns_if_not_UTM12N(self, mocker):
        geometry_mock_1 = mocker.Mock()
        geometry_mock_1.area = 4046.8564

        parcels_df = pd.DataFrame({
            'PARCEL_ID': [1],
            'SHAPE': [geometry_mock_1],
        })

        mocker.patch.object(pd.DataFrame.spatial, 'sr', new={'wkid': 42})

        with pytest.warns(UserWarning) as record:
            calculate.acreages(parcels_df, 'acres')

        assert record[0].message.args[
            0] == "Input data not in UTM 12N (input sr: {'wkid': 42}). Acreages may be inaccurate."

    def test_approximate_floors_rounds_and_drops_orig_field(self):
        parcels_df = pd.DataFrame({
            'PARCEL_ID': [1, 2],
            'FLOORS_CNT': [1.2, 2.6],
        })

        calculate.approximate_floors(parcels_df, 'FLOORS_CNT')

        test_df = pd.DataFrame({
            'PARCEL_ID': [1, 2],
            'APX_HGHT': [1., 3.],
        })

        tm.assert_frame_equal(parcels_df, test_df)

    def test_dwelling_units_per_acre_calculates_correctly(self):
        parcels_df = pd.DataFrame({
            'acres': [1., .5],
            'units': [1, 10],
        })

        calculate.dwelling_units_per_acre(parcels_df, 'units', 'acres')

        test_df = pd.DataFrame({
            'acres': [1., .5],
            'units': [1, 10],
            'DUA': [1., 20.],
        })

        tm.assert_frame_equal(parcels_df, test_df)
