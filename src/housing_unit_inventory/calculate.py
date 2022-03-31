# import logging
import warnings
from datetime import datetime

# import numpy as np
# import pandas as pd


def update_unit_count(parcels_df):
    """Update unit counts in-place for single family, duplex, and tri/quad

    Args:
        parcels_df (pd.DataFrame): The evaluated parcel dataset with UNIT_COUNT, HOUSE_CNT, SUBTYPE, and NOTE columns
    """

    # fix single family (non-pud)
    parcels_df.loc[(parcels_df['UNIT_COUNT'] == 0) & (parcels_df['SUBTYPE'] == 'single_family'), 'UNIT_COUNT'] = 1

    # fix duplex
    parcels_df.loc[(parcels_df['SUBTYPE'] == 'duplex'), 'UNIT_COUNT'] = 2

    # fix triplex-quadplex
    parcels_df.loc[(parcels_df['UNIT_COUNT'] < parcels_df['HOUSE_CNT']) & (parcels_df['NOTE'] == 'triplex-quadplex'),
                   'UNIT_COUNT'] = parcels_df['HOUSE_CNT']


def remove_zero_unit_house_counts(parcels_df):
    """Remove any rows in-place that don't have either a UNIT_COUNT or a HOUSE_CNT

    Any NaNs in UNIT_COUNT and HOUSE_CNT will be converted to 0s, and rows where both UNIT_COUNT and HOUSE_CNT == 0
    will be dropped.

    Args:
        parcels_df (pd.DataFrame): Parcels dataset with populated UNIT_COUNT and HOUSE_CNT columns
    """
    parcels_df.fillna({'UNIT_COUNT': 0, 'HOUSE_CNT': 0}, inplace=True)
    rows_with_zeros = parcels_df[(parcels_df['UNIT_COUNT'] == 0) & (parcels_df['HOUSE_CNT'] == 0)]
    parcels_df.drop(rows_with_zeros.index, inplace=True)


def built_decade(parcels_df, built_yr_field='BUILT_YR'):
    """Calculate BUILT_DECADE from BUILT_YR in-place

    Raises a UserWarning with the number of rows whose BUILT_YR is before 1846 or after the current year + 2 (yes,
    there were structures prior to Fort Buenaventura, but I highly doubt any are still in use as housing).

    Args:
        parcels_df (pd.DataFrame): Parcels dataset with BUILT_YR column
    """

    this_year = datetime.now().year
    invalid_built_year_rows = parcels_df[(parcels_df[built_yr_field] < 1846) |
                                         (parcels_df[built_yr_field] > this_year + 2)]
    if invalid_built_year_rows.shape[0]:
        warnings.warn(
            f'{invalid_built_year_rows.shape[0]} parcels have an invald built year (before 1847 or after current '
            'year plus two)'
        )

    #: Decade is floor division by 10, then multiply by 10
    parcels_df['BLT_DECADE'] = parcels_df[built_yr_field] // 10 * 10


def acreages(parcels_df, acres_field):
    """Calculate the acreages of polygon geometries in the SHAPE field by dividing by 4046.8564

    Args:
        parcels_df (pd.DataFrame): Spatial data frame with polygon SHAPE column with units in meters
        acres_field (str): Column to store calculated acreage values
    """

    #: Manually dividing .area by conversion factor is an order of magnitude faster than .get_area() and avoids runaway
    #: memory situation, but doesn't do any spatial reference magic.

    if parcels_df.spatial.sr['wkid'] != 26912:
        warnings.warn(f'Input data not in UTM 12N (input sr: {parcels_df.spatial.sr}). Acreages may be inaccurate.')

    parcels_df[acres_field] = parcels_df['SHAPE'].apply(lambda shape: shape.area / 4046.8564)


def approximate_floors(parcels_df, floors_count_field):

    parcels_df['APX_HGHT'] = parcels_df[floors_count_field].round()
    parcels_df.drop(columns=[floors_count_field], inplace=True)


def dwelling_units_per_acre(parcels_df, unit_count_field, acres_field):

    parcels_df['DUA'] = parcels_df[unit_count_field] / parcels_df[acres_field]
