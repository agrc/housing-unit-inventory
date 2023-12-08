import logging
import warnings

import pandas as pd
from arcgis.features import GeoAccessor, GeoSeriesAccessor
from arcgis.geometry import Geometry

from . import helpers

#: TYPE (and SUBTYPE)
#:  single-family
#:      single-family
#:      pud
#:  multi-family
#:      duplex
#:      townhome
#:      apartment
#:      multi-family
#:      mobile_home_park


#: Unused now
def _series_single_mode(series):
    """Find the mode of series using pd.Series.mode. If there are multiple, only return the first (per sorting)

    Args:
        series (pd.Series): The series you want to find a single mode of

    Returns:
        pd.Series: A single-element series containing the first mode (based on pd.Series.mode's sorting)
    """

    modes = series.mode()
    if modes.size > 1:
        return modes.iloc[0:1]
    return modes


def owned_unit_groupings(parcels_df, common_area_key_col, address_points_df, common_area_df) -> pd.DataFrame.spatial:
    """Aggregate info from parcels in each OUG into the OUG geometry along with a new "parcel id" for each OUG

    Groups parcels by OUG id in common_area_key_col and performs the relevant aggregation stats for each attribute.
    Combines the attributes back to the OUG geometries for the final report.

    The "parcel id" is just '99' + the OUG ID if the ID can be converted to an int or '99' + a range from 0000-9999,
    so it will always be 99xxxx, where xxxx is either the OUG ID (may not be 4 digits) or the range value.

    Args:
        parcels_df (pd.DataFrame): All classified parcels as a DataFrame
        common_area_key_col (str): Column name for the key that identifies which OUG a parcel belongs to
        address_points_df (pd.DataFrame.spatial): Address points, used to calculate address point count
        common_area_df (pd.DataFrame.spatial): DataFrame of all the OUGs

    Returns:
        pd.DataFrame.spatial: common_area_df subsetted to relevant OUGs (and specific fields) with aggregated info added
    """

    #: arcgis.geometry.get_area, .contains, .centroid

    oug_parcels_df = parcels_df[parcels_df["parcel_type"] == "owned_unit_grouping"].copy()

    logging.debug("%s parcels being evaluated as owned unit groupings...", oug_parcels_df.shape[0])

    #: Basically a right join of common areas and parcels based on the common area key so that we don't get common area
    #: geometries that don't include any parcels
    intersecting_common_areas_df = helpers.get_common_areas_intersecting_parcels_by_key(
        common_area_df, parcels_df, common_area_key_col
    )

    #: use groupby to summarize the parcel attributes per common area
    #: each series should be indexed by and refer back to the common_area_key_col, not the parcels
    parcels_grouped_by_oug_id = oug_parcels_df.groupby(common_area_key_col)
    total_mkt_value_sum_series = parcels_grouped_by_oug_id["TOTAL_MKT_VALUE"].sum()
    land_mkt_value_sum_series = parcels_grouped_by_oug_id["LAND_MKT_VALUE"].sum()
    bldg_sqft_sum_series = parcels_grouped_by_oug_id["BLDG_SQFT"].sum()
    floors_cnt_mean_series = parcels_grouped_by_oug_id["FLOORS_CNT"].mean()
    built_yr_series = helpers.get_proper_built_yr_value_series(oug_parcels_df, common_area_key_col, "BUILT_YR")
    parcel_count_series = parcels_grouped_by_oug_id["SHAPE"].count().rename("PARCEL_COUNT")
    address_count_series = helpers.get_address_point_count_series(
        intersecting_common_areas_df, address_points_df, common_area_key_col
    )

    #: Merge all our new info to the common area polygons, using the common_area_key_col as the df index
    carry_over_fields = ["SHAPE", common_area_key_col, "SUBTYPE", "TYPE", "IS_OUG"]
    evaluated_oug_parcels_df = pd.concat(
        axis=1,
        objs=[
            intersecting_common_areas_df[carry_over_fields].copy().set_index(common_area_key_col),
            total_mkt_value_sum_series,
            land_mkt_value_sum_series,
            bldg_sqft_sum_series,
            floors_cnt_mean_series,
            built_yr_series,
            parcel_count_series,
            address_count_series,
        ],
    )

    #: Make sure pud's are set to single_family
    # evaluated_oug_parcels_with_types_df = helpers.set_common_area_types(evaluated_oug_parcels_df)
    evaluated_oug_parcels_df.loc[evaluated_oug_parcels_df["SUBTYPE"] == "pud", "TYPE"] = "single_family"

    #: Add a generated PARCEL_ID based on the common_area_key for future aligning with other parcels
    # evaluated_oug_parcels_with_types_df['PARCEL_ID'] = 'oug_' + evaluated_oug_parcels_with_types_df.index.astype(str)
    try:
        evaluated_oug_parcels_df["PARCEL_ID"] = 990000 + evaluated_oug_parcels_df.index.astype(int)
    except TypeError:
        warnings.warn(
            f"Common area key {common_area_key_col} cannot be converted to int for PARCEL_ID creation, using simple range instead"
        )
        evaluated_oug_parcels_df.insert(0, "PARCEL_ID", range(990000, 990000 + len(evaluated_oug_parcels_df)))

    #: Convert PARCEL_ID to str to match type with other PARCEL_IDs
    evaluated_oug_parcels_df = evaluated_oug_parcels_df.astype({"PARCEL_ID": str})

    #: TODO: implement some sort of count tracking. Maybe a separate data frame consisting of just the parcel ids, removing matching ones on each pass?

    return evaluated_oug_parcels_df


def by_parcel_types(parcels_df, parcel_types, attribute_dict, address_points_df=None, subtypes_method=None):
    """Run the evaluations subsetting by various parcel_types.

    Add TYPE and SUBTYPE based on values set in attribute_dict. Add UNIT_COUNT based on address points if passed in
    via address_points_df. Set SUBTYPE and add NOTE if helpers.set_multi_family_single_parcel_subtypes is passed via
    subtypes_method.

    Args:
        parcels_df (pd.DataFrame): Parcels dataset with a unique PARCEL_ID column
        parcel_types (List<str>): parcel_types to include in this particular evaluation
        attribute_dict (dict): Attribute names and values to set in the subsetted parcels
        address_points_df (pd.DataFrame.spatial, optional): If provided, calculates the number of address points in
        each parcel. Defaults to None.
        subtypes_method (method, optional): If provided, call this method with the parcels subset as a parameter to set
        the subtype (used to reassign tri-quad to apartment). Defaults to None.

    Returns:
        pd.DataFrame: The subset of parcels with the appropriate fields added.
    """

    working_parcels_df = parcels_df[parcels_df["parcel_type"].isin(parcel_types)].copy()
    for attribute, value in attribute_dict.items():
        working_parcels_df[attribute] = value

    if subtypes_method:
        working_parcels_df = subtypes_method(working_parcels_df)

    if isinstance(address_points_df, pd.DataFrame):
        address_points_series = helpers.get_address_point_count_series(
            working_parcels_df, address_points_df, "PARCEL_ID"
        )
        parcels_with_addr_pts_df = working_parcels_df.merge(address_points_series, how="left", on="PARCEL_ID")
        return parcels_with_addr_pts_df

    return working_parcels_df


def compare_to_census_tracts(evaluated_df, census_tracts_df, outpath):
    """Aggregate and compare the evaluated data to 2020 census tract data

    Aggregates data by the tract geoid/FIPS code and then averages, sums, etc. The aggregated data are then joined to the census geometries, populations, and unit counts using the FIPS code. Finally, it compares pre 2019 evaluated unit counts and the 2020 census housing unit totals. A positive number indicates the evaluation has more units than the census, a negative number indicates it had fewer units than the census.

    Args:
        evaluated_df (pd.DataFrame): The completely evaluated parcel/OUG data
        census_tracts_df (pd.DataFrame.spatial): The census tract data, including SHAPEs, population (pop100), and housing units (hu100)
        outpath (Path): Compared tract output location
    """

    #: Average density in dwelling units per acre
    avg_sf_dua = (
        evaluated_df[evaluated_df["TYPE"] == "single_family"][["DUA", "TRACT_FIPS"]]
        .groupby("TRACT_FIPS")
        .mean()
        .rename(columns={"DUA": "avg_sf_dua"})
    )
    avg_mf_dua = (
        evaluated_df[evaluated_df["TYPE"] == "multi_family"][["DUA", "TRACT_FIPS"]]
        .groupby("TRACT_FIPS")
        .mean()
        .rename(columns={"DUA": "avg_mf_dua"})
    )
    avg_all_dua = (
        evaluated_df[["DUA", "TRACT_FIPS"]].groupby("TRACT_FIPS").mean().rename(columns={"DUA": "avg_all_dua"})
    )

    #: Average single family sq ft and value
    sf_avgs = (
        evaluated_df[evaluated_df["TYPE"] == "single_family"][["TOT_BD_FT2", "TOT_VALUE", "TRACT_FIPS"]]
        .groupby("TRACT_FIPS")
        .mean()
        .rename(columns={"TOT_BD_FT2": "avg_sf_sqft", "TOT_VALUE": "avg_sf_value"})
    )

    #: Get count of units built before 2019 to provide a better check against 2020 census counts
    pre_2020_unit_count = (
        evaluated_df[evaluated_df["APX_BLT_YR"] < 2019][["TRACT_FIPS", "UNIT_COUNT"]]
        .groupby("TRACT_FIPS")
        .sum()
        .rename(columns={"UNIT_COUNT": "pre_2020_unit_count"})
    )

    #: Get total unit counts, sq ft, and value for each tract
    sums = evaluated_df[["UNIT_COUNT", "TOT_BD_FT2", "TOT_VALUE", "TRACT_FIPS"]].groupby("TRACT_FIPS").sum()

    #: Join sums to census tract geometries, population, and unit counts
    census_tracts_df.set_index("geoid20", inplace=True)
    joined_df = pd.concat(
        [
            census_tracts_df[["SHAPE", "pop100", "hu100"]],
            sums,
            pre_2020_unit_count,
            avg_sf_dua,
            avg_mf_dua,
            avg_all_dua,
            sf_avgs,
        ],
        axis=1,
    ).dropna(subset=["UNIT_COUNT"])

    #: Create a metric of evaluated counts minus 2020 census counts
    joined_df["eval_minus_census"] = joined_df["pre_2020_unit_count"] - joined_df["hu100"]

    joined_df.spatial.to_featureclass(outpath)
