import logging
from pathlib import Path

import arcpy
import pandas as pd
from arcgis.features import GeoAccessor, GeoSeriesAccessor

from . import calculate, dissolve, evaluations, helpers


def davis_county():
    arcpy.env.overwriteOutput = True

    #: Inputs
    input_dir_path = Path(r"c:\gis\git\housing-unit-inventory\Parcels\2020-Davis\Inputs")
    opensgid_path = Path(r"c:\gis\projects\housinginventory\opensgid.agrc.utah.gov.sde")
    parcels_fc = input_dir_path / r"Davis_County_LIR_Parcels.gdb/Parcels_Davis_LIR_UTM12"
    # parcels_fc = Path(r'c:\gis\projects\housinginventory\housinginventory.gdb\davis_test_parcels')
    address_pts = input_dir_path / r"AddressPoints_Davis.gdb/address_points_davis"
    common_areas_fc = input_dir_path / r"Common_Areas.gdb/Common_Areas_Reviewed"
    extended_info_csv = input_dir_path / r"davis_extended_simplified.csv"
    mobile_home_communities = input_dir_path / r"Mobile_Home_Parks.shp"
    subcounties = input_dir_path / r"SubCountyArea_2019.shp"
    cities = opensgid_path / "opensgid.boundaries.municipal_boundaries"
    metro_townships = opensgid_path / "opensgid.boundaries.metro_townships"
    census_blocks = opensgid_path / "opensgid.demographic.census_blocks_2020"
    census_tracts = opensgid_path / "opensgid.demographic.census_tracts_2020"

    #: Output
    output_dir_path = Path(r"c:\gis\projects\housinginventory")
    output_fc = output_dir_path / r"housinginventory.gdb\davis2020_9"
    output_csv = output_dir_path / r"davis2020_9.csv"
    census_output_fc = output_dir_path / r"housinginventory.gdb\davis2020_9_by_tract"

    #: Address points (used later)
    address_pts_no_base_df = helpers.get_non_base_addr_points(address_pts)

    #: STEP 1: Prep parcels, load in extra data as needed
    #: Dissolve duplicate parcel ids
    logging.info("Loading and dissolving parcels...")
    parcels_cleaned_df = helpers.load_and_clean_parcels(parcels_fc)

    #: Load Extended Descriptions - be sure to format ACCOUNTNO column as text in excel first
    logging.info("Merging csv data...")
    csv_fields = ["ACCOUNTNO", "des_all", "class"]
    parcels_merged_df = helpers.add_extra_info_from_csv(extended_info_csv, 9, csv_fields, parcels_cleaned_df)

    logging.debug("Creating initial parcel centroids...")
    parcel_centroids_df = helpers.get_centroids_copy_of_polygon_df(parcels_merged_df, "PARCEL_ID")

    davis_field_mapping = {
        "class": "parcel_type",
    }
    standardized_parcels_df = helpers.standardize_fields(parcels_merged_df, davis_field_mapping)

    #: Get a count of all parcels
    count_all = standardized_parcels_df.shape[0]
    logging.info("Initial parcels in modeling area:\t %s", count_all)

    #: STEP 2: Classify owned unit grouping (puds, condos, etc) and mobile home community parcels
    #: TODO: Split OUGs along census blocks to allow more accurate aggregation at the block level?
    #: Classify parcels within common areas
    logging.info("Classifying OUGs and MHCs...")
    common_area_key = "common_area_key"  #: OBJECTID gets copied to this as a new field
    oug_field_mappings = {
        "TYPE_WFRC": "TYPE",
        "SUBTYPE_WFRC": "SUBTYPE",
    }
    owned_unit_groupings_df = helpers.load_and_clean_owned_unit_groupings(
        common_areas_fc, common_area_key, field_mapping=oug_field_mappings
    )

    common_area_classify_info = (common_area_key, "parcel_type", "owned_unit_grouping")
    parcels_with_oug_df = helpers.classify_from_area(
        standardized_parcels_df, parcel_centroids_df, "PARCEL_ID", owned_unit_groupings_df, common_area_classify_info
    )

    #: Classify parcels within mobile home communities
    mobile_home_key = "mobile_home_key"
    mobile_home_communities_df = pd.DataFrame.spatial.from_featureclass(mobile_home_communities)
    mobile_home_communities_df[mobile_home_key] = mobile_home_communities_df["OBJECTID"]

    mobile_home_classify_info = (mobile_home_key, "parcel_type", "mobile_home_park")
    classified_parcels_df = helpers.classify_from_area(
        parcels_with_oug_df, parcel_centroids_df, "PARCEL_ID", mobile_home_communities_df, mobile_home_classify_info
    )

    #: NOTE: by this point, there should be no county-specific stuff left, it should all have been translated to a
    #: common interface

    #: STEP 3: Run evaluations for each type of parcel
    logging.info("Evaluating owned unit groupings...")
    oug_features_df = evaluations.owned_unit_groupings(
        classified_parcels_df, common_area_key, owned_unit_groupings_df, address_pts_no_base_df
    )

    logging.info("Evaluating single family parcels...")
    single_family_attributes = {
        "TYPE": "single_family",
        "SUBTYPE": "single_family",
    }
    single_family_features_df = evaluations.by_parcel_types(
        classified_parcels_df, ["single_family"], single_family_attributes
    )

    logging.info("Evaluating multi-family, single-parcel parcels...")
    multi_family_types = ["multi_family", "duplex", "apartment", "townhome", "triplex-quadplex"]
    multi_family_attributes = {
        "TYPE": "multi_family",
    }
    multi_family_single_parcel_features_df = evaluations.by_parcel_types(
        classified_parcels_df,
        multi_family_types,
        multi_family_attributes,
        address_pts_no_base_df,
        helpers.set_multi_family_single_parcel_subtypes,
    )

    logging.info("Evaluating mobile home communities...")
    mobile_home_attributes = {
        "TYPE": "multi_family",
        "SUBTYPE": "mobile_home_park",
    }
    mobile_home_communities_features_df = evaluations.by_parcel_types(
        classified_parcels_df, ["mobile_home_park"], mobile_home_attributes, address_pts_no_base_df
    )

    #: STEP 4: Merge the evaluated parcels together and clean
    #: Merge the evaluated parcels into one dataframe
    logging.info("Merging dataframes...")
    evaluated_parcels_df = helpers.concat_evaluated_dataframes(
        [
            oug_features_df,
            single_family_features_df,
            multi_family_single_parcel_features_df,
            mobile_home_communities_features_df,
        ]
    )

    #: Clean unneeded dataframes
    logging.debug("Deleting references to old dataframes...")
    del oug_features_df
    del single_family_features_df
    del multi_family_single_parcel_features_df
    del mobile_home_communities_features_df
    del parcels_cleaned_df
    del parcels_merged_df
    del parcel_centroids_df
    del standardized_parcels_df
    del parcels_with_oug_df
    del classified_parcels_df

    #: Add city and sub-county info
    logging.info("Adding city, subcounty, and census block info...")
    logging.debug("Getting evaluated parcel centroids...")
    evaluated_centroids_df = helpers.get_centroids_copy_of_polygon_df(evaluated_parcels_df, "PARCEL_ID")

    logging.debug("Merging cities and metro townships...")
    cities_df = pd.DataFrame.spatial.from_featureclass(cities)
    metro_townships_df = pd.DataFrame.spatial.from_featureclass(metro_townships)
    cities_townships_df = helpers.concat_cities_metro_townships(cities_df, metro_townships_df)

    parcels_with_cities_df = helpers.classify_from_area(
        evaluated_parcels_df, evaluated_centroids_df, "PARCEL_ID", cities_townships_df
    )

    subcounties_df = pd.DataFrame.spatial.from_featureclass(subcounties)
    parcels_with_subcounties_df = helpers.classify_from_area(
        parcels_with_cities_df, evaluated_centroids_df, "PARCEL_ID", subcounties_df
    )

    #: Add census block info (block group is first digit of block id)
    census_blocks_df = pd.DataFrame.spatial.from_featureclass(census_blocks)
    census_blocks_fields = ["geoid20"]
    final_parcels_df = helpers.classify_from_area(
        parcels_with_subcounties_df,
        evaluated_centroids_df,
        "PARCEL_ID",
        census_blocks_df,
        columns_to_keep=census_blocks_fields,
    )

    final_parcels_df = helpers.extract_tract_geoid(final_parcels_df, block_geoid="geoid20")

    final_parcels_df["COUNTY"] = "DAVIS"

    #: Rename fields
    #: CITY exists from some previous operation; drop it first
    final_parcels_df.drop(columns=["CITY"], inplace=True)
    final_parcels_df.rename(
        columns={
            "name": "CITY",  #: from cities
            "NewSA": "SUBCOUNTY",  #: From subcounties/regions
            "BUILT_YR": "APX_BLT_YR",
            "BLDG_SQFT": "TOT_BD_FT2",
            "TOTAL_MKT_VALUE": "TOT_VALUE",
            "PARCEL_ACRES": "ACRES",
            "geoid20": "BLOCK_FIPS",
        },
        inplace=True,
    )

    #: Clean up some nulls
    logging.info("Cleaning up final data")
    final_parcels_df["IS_OUG"].fillna("No", inplace=True)

    #: Recalculate acreages
    logging.info("Recalculating acreages...")
    calculate.acreages(final_parcels_df, "ACRES")

    calculate.update_unit_count(final_parcels_df)

    calculate.built_decade(final_parcels_df, "APX_BLT_YR")

    calculate.dwelling_units_per_acre(final_parcels_df, "UNIT_COUNT", "ACRES")

    #: Remove data points with zero units
    calculate.remove_zero_unit_house_counts(final_parcels_df)

    final_fields = [
        "SHAPE",
        "UNIT_ID",
        "TYPE",
        "SUBTYPE",
        "IS_OUG",
        "UNIT_COUNT",
        "DUA",
        "ACRES",
        "TOT_BD_FT2",
        "TOT_VALUE",
        "APX_BLT_YR",
        "BLT_DECADE",
        "CITY",
        "COUNTY",
        "SUBCOUNTY",
        "PARCEL_ID",
        "BLOCK_FIPS",
        "TRACT_FIPS",
    ]

    logging.info("Writing final data out to disk...")
    output_df = final_parcels_df.reindex(columns=final_fields)
    output_df.spatial.to_featureclass(output_fc, sanitize_columns=False)
    output_df.drop(columns=["SHAPE"]).to_csv(output_csv)

    logging.info("Evaluating against Census data...")
    census_tracts_df = pd.DataFrame.spatial.from_featureclass(census_tracts)
    evaluations.compare_to_census_tracts(output_df, census_tracts_df, census_output_fc)


def washington_county():
    #: NOTE:
    #: The large number of PUDs that encompass unbuildable areas makes it difficult to consistently evaluate PUD density
    #: PUD density also complicated by lack of roads parcels and fast-paced development

    #: Getting OUG from subdivisions:
    #:  Select by location against Condo, Multiple Unit, and Townhouse propertytypes, where subdivision contains parcels
    #:  Manually review
    #:  Select by location against Mobile Home propertytype parcels, where subdivision contains parcels
    #: Manual edits to type for roads/oug roads

    #: OUG Criteria:
    #: Individual parcels are drawn around houses/buildings, leaving a common area with a null parcel
    #: Parcels cover more than the buildings but don't extend to street/subdivision lines like a "normal" SFH parcel would
    #: A common amenity (pool, open space area, clubhouse) is on either its own parcel or a common null parcel
    #: Small parking areas around townhomes are considered part of the density area (a SFH's driveway is part of its parcel and thus its density)
    #: Long roads in OUGs should be extracted if at all possible (if they have their own parcel)
    #: Road should be included in mobile home communities' OUG polygon
    #: Large separate open space parcels (cliff faces, etc) should be extracted

    #: OUG Roads:
    #: Select null parcels that intersect roads, classify propertytype as Road
    #: Select Road propertytype parcels that intersect ougs, classify propertype as OUG Road
    #: OUG roads will be extracted from OUGS/not included in density
    #: Roads in mobile home OUGs should be set to null to be included with density

    #: Mobile Home Community Criteria:
    #: single parcel covering multiple units
    #: roads considered part of community for density calc
    #: MHCs that have individual parcels but include common areas, private roads should be considered OUGs
    #:  Does it feel like a SFH neighborhood? If so, probably not an OUG

    #: Inputs
    input_gdb = Path(r"C:\gis\Projects\HousingInventory\WashingtonCo.gdb")
    opensgid_path = Path(r"c:\gis\projects\housinginventory\opensgid.agrc.utah.gov.sde")
    parcels_fc = input_gdb / r"washco_20231214"  # _test_subset"
    cama_csv = input_gdb.parent / r"Data/Washington/WashCo_cama.csv"
    address_pts = input_gdb / r"address_points_20231208"
    common_areas_fc = input_gdb / r"washington_ougs_noroads"
    mobile_home_communities = input_gdb / r"washington_mhcs"
    cities = opensgid_path / "opensgid.boundaries.municipal_boundaries"
    metro_townships = opensgid_path / "opensgid.boundaries.metro_townships"
    census_blocks = opensgid_path / "opensgid.demographic.census_blocks_2020"
    census_tracts = opensgid_path / "opensgid.demographic.census_tracts_2020"

    #: Output
    output_dir_path = Path(r"c:\gis\projects\housinginventory")
    output_fc = output_dir_path / r"washingtonco.gdb\washington_2023"
    output_csv = output_dir_path / r"washington_2023.csv"
    census_output_fc = output_dir_path / r"washingtonco.gdb\washington_2023_by_tract"

    #: Address points (used later)
    address_pts_no_base_df = helpers.get_non_base_addr_points(address_pts, "pttype")

    #: STEP 1: Prep parcels, load in extra data as needed
    #: Dissolve duplicate parcel ids
    logging.info("Loading and dissolving parcels...")
    washco_parcels_df = pd.DataFrame.spatial.from_featureclass(parcels_fc)
    null_ids = (
        washco_parcels_df[washco_parcels_df["PARCEL_ID"].isnull()]
        .reindex(columns=["OBJECTID", "SHAPE", "PARCEL_ID"])
        .copy()
    )
    #: Add parcel id to null parcels so that future centroid-to-parcel joins work
    null_ids["PARCEL_ID"] = pd.Series([f"null_{i}" for i in range(0, len(null_ids))], index=null_ids.index)

    non_null_ids = (
        washco_parcels_df[~washco_parcels_df["PARCEL_ID"].isnull()]
        .reindex(columns=["OBJECTID", "SHAPE", "PARCEL_ID"])
        .copy()
    )
    dupes, non_dupes = dissolve._extract_duplicates_and_uniques(non_null_ids, "PARCEL_ID")
    good_parcel_geometries = pd.concat([dissolve._dissolve_geometries(dupes, "PARCEL_ID"), non_dupes, null_ids])

    #: Load, dedupe, and merge residential cama data
    logging.debug("Loading, deduping, and merging CAMA data...")
    wascho_cama_df = pd.read_csv(cama_csv, thousands=",", low_memory=False)
    #: if parcel no and imp no are the same, it's a duplicate record
    wascho_cama_df.drop_duplicates(subset=["PARCELNO", "IMPNO"], keep="first", inplace=True)

    #: Convert propertytype: Commercial and description: apartments, group home, elderly, etc to multiple unit
    wascho_cama_df.loc[
        (wascho_cama_df["PROPERTYTYPE"] == "Commercial")
        & (wascho_cama_df["BLTASDESCRIPTION"].isin(["Apartments (Hi-Rise)", "Apartment > 3 Stories"])),
        "PROPERTYTYPE",
    ] = "Multiple Unit"

    #: Smartly merge CAMA records for multiple improvements for a single parcel number
    #: Only look at residential property types. Any residential properties hiding in commercial property types should
    #: be converted beforehand (check the bltasdescription field)
    grouped = wascho_cama_df[
        wascho_cama_df["PROPERTYTYPE"].isin(
            [
                "Residential",
                "Townhouse",
                "Mobile Home",
                "Condo",
                "Duplex",
                "Triplex",
                "Multiple Unit",
            ]
        )
    ].groupby("PARCELNO")
    combined_cama_df = grouped.apply(helpers.combine_washington_cama_parcels)
    parcels_merged_df = good_parcel_geometries.merge(
        combined_cama_df.reset_index(drop=True), left_on="PARCEL_ID", right_on="PARCELNO", how="left"
    ).convert_dtypes()

    #: Add parcel id to null parcels so that future centroid-to-parcel joins work
    # parcels_merged_df.loc[parcels_merged_df["PARCEL_ID"].isnull(), "PARCEL_ID"] = pd.Series(
    #     [f"null_{i}" for i in range(0, len(parcels_merged_df.loc[parcels_merged_df["PARCEL_ID"].isnull()]))]
    # )

    #: Set breakpoint here to export parcels_merged_df to fc to check for parcels that won't convert to point
    #: (usually slivers involving just two vertices and curves between them)

    logging.debug("Creating initial parcel centroids...")
    parcel_centroids_df = helpers.get_centroids_copy_of_polygon_df(parcels_merged_df, "PARCEL_ID")

    washington_field_mapping = {
        "PROPERTYTYPE": "parcel_type",
        "TOTALVALUE": "TOTAL_MKT_VALUE",
        "TOTALUNITCOUNT": "HOUSE_CNT",
        "IMPSF": "BLDG_SQFT",
        "BLTASYEARBUILT": "BUILT_YR",
    }
    standardized_parcels_df = helpers.standardize_fields(parcels_merged_df, washington_field_mapping)
    standardized_parcels_df["original_parcel_type"] = standardized_parcels_df["parcel_type"]

    #: Get a count of all parcels
    count_all = standardized_parcels_df.shape[0]
    logging.info("Initial parcels in modeling area:\t %s", count_all)

    #: STEP 2: Classify owned unit grouping (puds, condos, etc) and mobile home community parcels
    #: TODO: Split OUGs along census blocks to allow more accurate aggregation at the block level?
    #: Classify parcels within common areas
    logging.info("Classifying OUGs and MHCs...")
    common_area_key = "common_area_key"  #: OBJECTID gets copied to this as a new field
    # oug_field_mappings = {
    #     "TYPE_WFRC": "TYPE",
    #     "SUBTYPE_WFRC": "SUBTYPE",
    # }
    owned_unit_groupings_df = helpers.load_and_clean_owned_unit_groupings(common_areas_fc, common_area_key)
    # owned_unit_groupings_df.drop(columns=["TYPE", "SUBTYPE"], inplace=True)

    #: NOTE: This adds TYPE and SUBTYPE to the parcels from the oug features
    #: Need to figure out a better way to pass PROPERTYTYPE through so we can get the subtype in the oug analysis
    common_area_classify_info = (common_area_key, "parcel_type", "owned_unit_grouping")
    parcels_with_oug_df = helpers.classify_from_area(
        standardized_parcels_df, parcel_centroids_df, "PARCEL_ID", owned_unit_groupings_df, common_area_classify_info
    )

    #: Classify parcels within mobile home communities
    mobile_home_key = "mobile_home_key"
    mobile_home_communities_df = pd.DataFrame.spatial.from_featureclass(mobile_home_communities)
    mobile_home_communities_df[mobile_home_key] = mobile_home_communities_df["OBJECTID"]

    mobile_home_classify_info = (mobile_home_key, "parcel_type", "mobile_home_park")
    classified_parcels_df = helpers.classify_from_area(
        parcels_with_oug_df, parcel_centroids_df, "PARCEL_ID", mobile_home_communities_df, mobile_home_classify_info
    )

    #: NOTE: by this point, there should be no county-specific stuff left, it should all have been translated to a
    #: common interface

    #: STEP 3: Run evaluations for each type of parcel
    logging.info("Evaluating owned unit groupings...")
    oug_features_df = evaluations.owned_unit_groupings(
        classified_parcels_df, common_area_key, owned_unit_groupings_df, address_pts_no_base_df
    )

    logging.info("Evaluating single family parcels...")
    single_family_types = ["Residential", "Townhouse", "Mobile Home"]
    single_family_attributes = {
        "TYPE": "single_family",
        # "SUBTYPE": "single_family",
    }
    single_family_features_df = evaluations.by_parcel_types(
        classified_parcels_df, single_family_types, single_family_attributes
    )

    logging.info("Evaluating multi-family, single-parcel parcels...")
    multi_family_types = ["Multiple Unit", "Duplex", "Condo", "Triplex"]
    multi_family_attributes = {
        "TYPE": "multi_family",
    }
    multi_family_single_parcel_features_df = evaluations.by_parcel_types(
        classified_parcels_df,
        multi_family_types,
        multi_family_attributes,
        # helpers.set_multi_family_single_parcel_subtypes,  #: This may not be necessary
    )

    logging.info("Evaluating mobile home communities...")
    mobile_home_attributes = {
        "TYPE": "multi_family",
        "SUBTYPE": "mobile_home_park",
    }
    mobile_home_communities_features_df = evaluations.by_parcel_types(
        classified_parcels_df, ["mobile_home_park"], mobile_home_attributes, address_pts_no_base_df
    )

    #: STEP 4: Merge the evaluated parcels together and clean
    #: Merge the evaluated parcels into one dataframe
    logging.info("Merging dataframes...")
    evaluated_parcels_df = helpers.concat_evaluated_dataframes(
        [
            oug_features_df,
            single_family_features_df,
            multi_family_single_parcel_features_df,
            mobile_home_communities_features_df,
        ]
    )

    #: Clean unneeded dataframes
    logging.debug("Deleting references to old dataframes...")
    del oug_features_df
    del single_family_features_df
    del multi_family_single_parcel_features_df
    del mobile_home_communities_features_df
    del parcels_merged_df
    del parcel_centroids_df
    del standardized_parcels_df
    del parcels_with_oug_df
    del classified_parcels_df

    #: Add city and sub-county info
    logging.info("Adding city, subcounty, and census block info...")
    logging.debug("Getting evaluated parcel centroids...")
    evaluated_centroids_df = helpers.get_centroids_copy_of_polygon_df(evaluated_parcels_df, "PARCEL_ID")

    logging.debug("Merging cities and metro townships...")
    cities_df = pd.DataFrame.spatial.from_featureclass(cities)
    metro_townships_df = pd.DataFrame.spatial.from_featureclass(metro_townships)
    cities_townships_df = helpers.concat_cities_metro_townships(cities_df, metro_townships_df)

    parcels_with_cities_df = helpers.classify_from_area(
        evaluated_parcels_df, evaluated_centroids_df, "PARCEL_ID", cities_townships_df
    )

    #: Add census block info (block group is first digit of block id)
    census_blocks_df = pd.DataFrame.spatial.from_featureclass(census_blocks)
    census_blocks_fields = ["geoid20"]
    final_parcels_df = helpers.classify_from_area(
        parcels_with_cities_df,
        evaluated_centroids_df,
        "PARCEL_ID",
        census_blocks_df,
        columns_to_keep=census_blocks_fields,
    )

    final_parcels_df = helpers.extract_tract_geoid(final_parcels_df, block_geoid="geoid20")

    final_parcels_df["COUNTY"] = "Washington"

    #: Rename fields
    final_parcels_df.rename(
        columns={
            "name": "CITY",  #: from cities
            # "NewSA": "SUBCOUNTY",  #: From subcounties/regions
            "BUILT_YR": "APX_BLT_YR",
            "BLDG_SQFT": "TOT_BD_FT2",
            "TOTAL_MKT_VALUE": "TOT_VALUE",
            "PARCEL_ACRES": "ACRES",
            "geoid20": "BLOCK_FIPS",
        },
        inplace=True,
    )

    #: Clean up some nulls
    logging.info("Cleaning up final data")
    final_parcels_df["IS_OUG"].fillna("No", inplace=True)

    #: Recalculate acreages
    logging.info("Recalculating acreages...")
    calculate.acreages(final_parcels_df, "ACRES")

    final_parcels_df.loc[final_parcels_df["UNIT_COUNT"].isna(), "UNIT_COUNT"] = final_parcels_df["HOUSE_CNT"]
    final_parcels_df.loc[final_parcels_df["SUBTYPE"].isna(), "SUBTYPE"] = final_parcels_df.loc[
        final_parcels_df["SUBTYPE"].isna(), "parcel_type"
    ]

    #: Translate WashCo unit types to standard types
    unit_type_mapping = {
        "Residential": "single_family",
        "Townhouse": "townhome",
        "Mobile Home": "mobile_home_park",
        "mobile_home_park": "mobile_home_park",  #: .map() will replace an entry with NA if it's not present in the dict
        "Condo": "condo",
        "Duplex": "duplex",
        "Triplex": "apartment",
        "Multiple Unit": "apartment",
    }
    final_parcels_df["SUBTYPE"] = final_parcels_df["SUBTYPE"].map(unit_type_mapping)
    final_parcels_df["UNIT_ID"] = range(len(final_parcels_df))

    calculate.built_decade(final_parcels_df, "APX_BLT_YR")

    #: Fix missing unit counts if square footage or built year is present
    final_parcels_df.loc[
        ((final_parcels_df["UNIT_COUNT"].isna()) | (final_parcels_df["UNIT_COUNT"] == 0))
        & ((final_parcels_df["TOT_BD_FT2"] > 0) | (final_parcels_df["APX_BLT_YR"] > 0)),
        "UNIT_COUNT",
    ] = 1

    calculate.dwelling_units_per_acre(final_parcels_df, "UNIT_COUNT", "ACRES")

    #: Remove data points with zero units
    calculate.remove_zero_unit_house_counts(final_parcels_df)

    final_fields = [
        "SHAPE",
        "UNIT_ID",
        "TYPE",
        "SUBTYPE",
        "IS_OUG",
        "UNIT_COUNT",
        "DUA",
        "ACRES",
        "TOT_BD_FT2",
        "TOT_VALUE",
        "APX_BLT_YR",
        "BLT_DECADE",
        "CITY",
        "COUNTY",
        "SUBCOUNTY",
        "PARCEL_ID",
        "BLOCK_FIPS",
        "TRACT_FIPS",
    ]

    logging.info("Writing final data out to disk...")
    output_df = final_parcels_df.reindex(columns=final_fields)
    output_df.spatial.to_featureclass(output_fc, sanitize_columns=False)
    output_df.drop(columns=["SHAPE"]).to_csv(output_csv)

    logging.info("Evaluating against Census data...")
    census_tracts_df = pd.DataFrame.spatial.from_featureclass(census_tracts)
    evaluations.compare_to_census_tracts(output_df, census_tracts_df, census_output_fc)

    pass
