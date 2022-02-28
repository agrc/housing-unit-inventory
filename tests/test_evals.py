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
            'class': ['single_family', 'single_family', 'single_family'],
        })

        with_types_df = inventory.evaluate_single_family_df(test_data_df)

        test_results_df = pd.DataFrame({
            'id': [1, 2, 3],
            'class': ['single_family', 'single_family', 'single_family'],
            'TYPE': ['single_family', 'single_family', 'single_family'],
            'SUBTYPE': ['single_family', 'single_family', 'single_family'],
            'basebldg': ['1', '1', '1'],
            'building_type_id': ['1', '1', '1'],
        })

        tm.assert_frame_equal(with_types_df, test_results_df)

    def test_evaluate_single_family_df_only_gets_single_family(self):
        test_data_df = pd.DataFrame({
            'id': [1, 2, 3],
            'class': ['single_family', 'industrial', 'multi_family'],
        })

        with_types_df = inventory.evaluate_single_family_df(test_data_df)

        test_results_df = pd.DataFrame({
            'id': [1],
            'class': ['single_family'],
            'TYPE': ['single_family'],
            'SUBTYPE': ['single_family'],
            'basebldg': ['1'],
            'building_type_id': ['1'],
        })

        tm.assert_frame_equal(with_types_df, test_results_df)
