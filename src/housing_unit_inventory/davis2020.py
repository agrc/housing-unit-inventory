import os

import arcpy
import pandas as pd
# import numpy as np
# from arcgis import GIS
from arcgis.features import GeoAccessor, GeoSeriesAccessor
from arcgis.geometry import Geometry

#: TODO:
#:      Do as much in data frames as possible
#:      Switch scratch to a scratch.gdb within the scratch workspace
#:          (https://pro.arcgis.com/en/pro-app/latest/tool-reference/environment-settings/scratch-gdb.htm)
#:          Delete/create scratch gdb at start of process to ensure clean slate
#:          Don't pass scratch around, use arcpy.env.scratchGDB instead
#:      Come up with a better way to pass analyzed parcels around
#:      Is 'building_type_id' used?
#:      Can Mobile homes fit the same process as the other common area ones?
#:      Look at new WFRC data for 'single_family_adu', 'mixed th/single_family', and 'mixed condo/th' subtypes


def _get_non_base_addr_points(address_pts, scratch):
    # get address points without base address point
    address_pts_lyr = arcpy.MakeFeatureLayer_management(address_pts, 'address_pts_lyr')
    query = (''' PtType <> 'BASE ADDRESS' ''')
    arcpy.SelectLayerByAttribute_management(address_pts_lyr, 'NEW_SELECTION', query)
    address_pts_no_base = arcpy.FeatureClassToFeatureClass_conversion(
        address_pts_lyr, scratch, '_00_address_pts_no_base'
    )

    return address_pts_no_base


def _get_parcels_in_modelling_area(parcels, area_boundary, scratch):
    parcels_layer = arcpy.MakeFeatureLayer_management(parcels, 'parcels')
    arcpy.SelectLayerByLocation_management(parcels_layer, 'HAVE_THEIR_CENTER_IN', area_boundary)
    parcels_for_modeling = arcpy.FeatureClassToFeatureClass_conversion(
        parcels_layer, scratch, '_01_parcels_for_modeling'
    )
    # recalc acreage
    arcpy.CalculateField_management(parcels_for_modeling, 'PARCEL_ACRES', '!SHAPE.area@ACRES!')

    # create the main layer
    parcels_for_modeling_layer = arcpy.MakeFeatureLayer_management(parcels_for_modeling, 'parcels_for_modeling_lyr')

    return parcels_for_modeling_layer


def _dissolve_duplicate_parcels(parcels_for_modeling_layer):
    #: TODO: rename '_clean_parcels' because that's what it does
    # dissolve on parcel id,summarizing attributes in various ways
    parcels_dissolved_fc = 'memory/dissolved'
    if arcpy.Exists(parcels_dissolved_fc):
        arcpy.management.Delete(parcels_dissolved_fc)
    parcels_dissolved = arcpy.management.Dissolve(
        parcels_for_modeling_layer, parcels_dissolved_fc, 'PARCEL_ID', [
            ['PARCEL_ID', 'COUNT'],
            ['TAXEXEMPT_TYPE', 'FIRST'],
            ['TOTAL_MKT_VALUE', 'SUM'],
            ['LAND_MKT_VALUE', 'SUM'],
            ['PARCEL_ACRES', 'SUM'],
            ['PROP_CLASS', 'FIRST'],
            ['PRIMARY_RES', 'FIRST'],
            ['HOUSE_CNT', 'MAX'],
            ['BLDG_SQFT', 'SUM'],
            ['FLOORS_CNT', 'MAX'],
            ['BUILT_YR', 'FIRST'],
            ['EFFBUILT_YR', 'FIRST'],
        ], 'MULTI_PART', 'DISSOLVE_LINES'
    )

    # rename columns
    #: moves OBJECTID, COUNT_PARCEL_ID
    parcels_dissolved_df = pd.DataFrame.spatial.from_featureclass(parcels_dissolved)
    parcels_dissolved_df.columns = [
        'OBJECTID',
        'PARCEL_ID',
        'COUNT_PARCEL_ID',
        'TAXEXEMPT_TYPE',
        'TOTAL_MKT_VALUE',
        'LAND_MKT_VALUE',
        'PARCEL_ACRES',
        'PROP_CLASS',
        'PRIMARY_RES',
        'HOUSE_CNT',
        'BLDG_SQFT',
        'FLOORS_CNT',
        'BUILT_YR',
        'EFFBUILT_YR',
        'SHAPE',
    ]

    #: Remove parcels without parcel ids or empty geometries
    parcels_dissolved_df.dropna(subset=['PARCEL_ID', 'SHAPE'], inplace=True)

    return parcels_dissolved_df


def _join_extended_parcel_info(info_csv, parcels_dissolved_sdf, scratch):
    ext_desc = pd.read_csv(info_csv, dtype={'ACCOUNTNO': str})

    # format account numbers so that they are all 9 characters long
    ext_desc['ACCOUNTNO'] = ext_desc['ACCOUNTNO'].zfill(9)
    ext_desc = ext_desc[['ACCOUNTNO', 'des_all', 'class']].copy()

    updated_parcels = os.path.join(scratch, '_01_parcels_extended')

    parcels_sdf = parcels_dissolved_sdf.merge(ext_desc, left_on='PARCEL_ID', right_on='ACCOUNTNO', how='left')
    parcels_sdf.spatial.to_featureclass(location=updated_parcels, sanitize_columns=False)

    parcels_for_modeling_layer = arcpy.MakeFeatureLayer_management(updated_parcels, 'parcels_for_modeling_lyr')

    return parcels_for_modeling_layer


def _add_fields(layer, fields):

    for field, field_type in fields.items():
        arcpy.management.AddField(layer, field, field_type)

    return layer


#: done with pandas instead
def _remove_empty_geomtries(layer):

    #: According to Esri, a geometry is empty if area and/or length are emtpy/0.
    shape_fields = ['OID@', 'SHAPE@AREA', 'SHAPE@LENGTH']
    with arcpy.da.UpdateCursor(layer, shape_fields) as empties_cursor:
        for row in empties_cursor:
            oid, area, length = row
            if not area and not length:
                empties_cursor.deleteRow()
                continue

            if not area or not length:
                print(f'Feature OID {oid} has missing area or length but not both')

    return layer


def _remove_empty_geometries_dataframe(dfs, shape_field='SHAPE'):
    """Drop any rows (in place) in a spatially enabled dataframe that have na values in shape_field

    Args:
        dfs (list<spatially enabled DataFrame>): List of dataframes to clean
        shape_field (str, optional): Field to check for empty geometries. Defaults to 'SHAPE'.
    """

    for df in dfs:
        df.dropna(subset=[shape_field], inplace=True)


def _build_field_mapping(target, join, fields):
    """Build a field mappings object from the input tables and a list of fields and their grouping stats

    Args:
        target (FeatureLayer): The target of the spatial join
        join (FeatureLayer): The layer that will be spatially joined to the target
        fields (dict): Mapping of field names to the statistic operation (supported by arcpy's spatial join) for them

    Returns:
        arcpy.FieldMappings: A field mapping that includes all the fields in both tables and the appropriate
        statistical operations for fields of features that will be combined
    """

    fieldmappings = arcpy.FieldMappings()
    fieldmappings.addTable(target)
    fieldmappings.addTable(join)

    for field_name, statistic in fields.items():
        fieldindex = fieldmappings.findFieldMapIndex(field_name)
        fieldmap = fieldmappings.getFieldMap(fieldindex)
        fieldmap.mergeRule = statistic
        fieldmappings.replaceFieldMap(fieldindex, fieldmap)

    return fieldmappings


def _create_centroids_within_common_area(parcels, common_areas, output):

    # parcels that are contained by condo common areas
    arcpy.SelectLayerByLocation_management(
        in_layer=parcels, overlap_type='INTERSECT', select_features=common_areas, selection_type='NEW_SELECTION'
    )

    # convert condo parcels that are contained by common areas into centroids
    centroids = arcpy.FeatureToPoint_management(parcels, output, 'INSIDE')

    return centroids


def _get_layer_with_address_point_count(target_features, join_features, output_features, count_field_name):

    fieldmappings = arcpy.FieldMappings()
    fieldmappings.addTable(target_features)
    fieldmappings.addTable(join_features)

    oug_sj2 = arcpy.SpatialJoin_analysis(
        target_features,
        join_features,
        output_features,
        'JOIN_ONE_TO_ONE',
        'KEEP_ALL',
        fieldmappings,
        match_option='INTERSECT'
    )

    arcpy.CalculateField_management(oug_sj2, field=count_field_name, expression='!Join_Count!')
    arcpy.DeleteField_management(oug_sj2, 'Join_Count')

    return oug_sj2


def _update_year_built(layer, year_fields):
    # update year built with max if mode is 0
    #: BUILT_YR is mode of join, BUILT_YR2 is max
    with arcpy.da.UpdateCursor(layer, year_fields) as cursor:
        for row in cursor:
            if row[0] is None or row[0] < 1 or row[0] == '':  #: if not row[0]:
                row[0] = row[1]

            cursor.updateRow(row)


def _remove_analyzed_features(layer, selecting_features):
    # delete features from working parcels
    arcpy.SelectLayerByLocation_management(
        in_layer=layer,
        overlap_type='HAVE_THEIR_CENTER_IN',
        select_features=selecting_features,
        selection_type='NEW_SELECTION'
    )
    arcpy.SelectLayerByLocation_management(
        in_layer=layer, overlap_type='WITHIN', select_features=selecting_features, selection_type='ADD_TO_SELECTION'
    )

    count_type = arcpy.GetCount_management(layer)
    parcels_for_modeling_layer = arcpy.DeleteFeatures_management(layer)

    # count of remaining parcels
    count_remaining = arcpy.GetCount_management(parcels_for_modeling_layer)

    return parcels_for_modeling_layer, count_type, count_remaining


def _reclassify_tri_quad_to_appartment(layer, fields):
    with arcpy.da.UpdateCursor(layer, fields) as cursor:
        for row in cursor:
            if row[2] in ['duplex', 'apartment', 'townhome', 'multi_family']:
                row[0] = row[2]

            if row[2] == 'triplex-quadplex':
                row[0] = 'apartment'
                row[1] = row[2]

            cursor.updateRow(row)


def evaluate_pud(input_parcel_layer, common_areas_features, scratch, address_points, output_gdb):
    """Run the PUD process.

    Saves analyzed PUD parcels to output gdb/_02_pud feature class and passes the original parcel layer without the PUD
    parcels for further analysis

    Args:
        input_parcel_layer (FeatureLayer): The parcel layer we're working against
        common_areas_features (Feature Class): Boundaries of all the PUDs that encompas any PUD parcels
        scratch (GDB): Scratch GDB
        address_points (Feature Class): State address points with BASE_ADDRESS points removed
        output_gdb (GDB): GDB to store parcels with data (_02_pud)

    Returns:
        FeatureLayer: input_parcel_layer with the PUD parcels removed
    """

    ###############
    # PUD
    ###############

    #: Join centroids of intersecting parcels to PUD boundaries => oug_sj (_03a_pud_sj)
    #: Use spatial join to set various fields
    #: Save count of centroids to parcel_count
    #: Update fields in oug_sj
    #: Join address points to output of first join => oug_sj2 (_02_pud)
    #: Save count of address points to ap_count
    #: From main parcel layer, delete parcels that have their center in, or are completely within, oug_sj2
    #: Update fields in oug_sj2

    #: Summarize specific fields of parcels whose center is in the common area with specific stats for each field
    #: Count number of address points in the common area parcel
    #: BUILT_YR should be most common or latest (if most common is 0)

    tag = 'single_family'  #: TYPE_WFRC
    tag2 = 'pud'  #: SUBTYPE_WFRC

    pud_centroids = _create_centroids_within_common_area(
        input_parcel_layer, common_areas_features, os.path.join(scratch, '_03a_pud_centroids')
    )

    # recalc acreage
    arcpy.CalculateField_management(common_areas_features, 'PARCEL_ACRES', '!SHAPE.area@ACRES!')

    #==================================================
    # summarize units attributes within pud areas
    #==================================================

    # use spatial join to summarize market value & acreage from centroids
    target_features = common_areas_features
    join_features = pud_centroids
    output_features = os.path.join(scratch, '_03a_pud_sj')

    #: Use the proper statistics when combining attributes from the PUD parcel centroids into the common area parcel
    fields = {
        'TOTAL_MKT_VALUE': 'Sum',
        'LAND_MKT_VALUE': 'Sum',
        'BLDG_SQFT': 'Sum',
        'FLOORS_CNT': 'Mean',
        'BUILT_YR': 'Mode',
        'BUILT_YR2': 'Max',
    }

    fieldmappings = _build_field_mapping(common_areas_features, pud_centroids, fields)

    # run the spatial join, use 'Join_Count' for number of units
    oug_sj = arcpy.SpatialJoin_analysis(
        target_features,
        join_features,
        output_features,
        'JOIN_ONE_TO_ONE',
        'KEEP_ALL',
        fieldmappings,
        match_option='INTERSECT'
    )

    # calculate the type field
    arcpy.CalculateField_management(oug_sj, field='TYPE', expression=f"'{tag}'")

    arcpy.CalculateField_management(oug_sj, field='SUBTYPE', expression=f"'{tag2}'")

    # rename join_count
    arcpy.CalculateField_management(oug_sj, field='parcel_count', expression='!Join_Count!')

    arcpy.DeleteField_management(oug_sj, 'Join_Count')

    #################################
    # get count from address points
    #################################
    #: TODO: replace w/ summarize within?

    # summarize address points address_point_count 'ap_count'
    target_features = oug_sj
    join_features = address_points  #: Should have BASE_ADDRESSes removed
    output_features = os.path.join(output_gdb, '_02_pud')
    count_field_name = 'ap_count'

    oug_sj2 = _get_layer_with_address_point_count(target_features, join_features, output_features, count_field_name)

    #################################
    # WRAP-UP
    #################################

    parcels_without_pud_parcels, count_type, count_remaining = _remove_analyzed_features(input_parcel_layer, oug_sj2)

    _update_year_built(oug_sj2, ['BUILT_YR', 'BUILT_YR2'])

    # calculate basebldg field
    arcpy.CalculateField_management(oug_sj2, field='basebldg', expression='1')

    # calculate building_type_id field
    arcpy.CalculateField_management(oug_sj2, field='building_type_id', expression='1')

    # message
    print(f'{count_type} "{tag}" parcels were selected.\n{count_remaining} parcels remain...')

    return parcels_without_pud_parcels


def evaluate_multi_family_with_common_area(
    input_parcel_layer, common_areas_features, scratch, address_points, output_gdb
):

    #: Join centroids of intersecting parcels to PUD boundaries => oug_sj (_03b_mf_sj)
    #: Save count of centroids to parcel_count
    #: Join address points to output of first join => oug_sj2 (_02_multi_family)
    #: Save count of address points to ap_count
    #: From main parcel layer, delete parcels that have their center in, or are completely within, oug_sj2
    #: Update fields in oug_sj2

    tag = 'multi_family'

    mf_centroids = _create_centroids_within_common_area(
        input_parcel_layer, common_areas_features, os.path.join(scratch, '_03a_mf_centroids')
    )

    # recalc acreage
    arcpy.CalculateField_management(common_areas_features, 'PARCEL_ACRES', '!SHAPE.area@ACRES!')

    #==================================================
    # summarize units attributes within pud areas
    #==================================================

    # use spatial join to summarize market value & acreage
    target_features = common_areas_features
    join_features = mf_centroids
    output_features = os.path.join(scratch, '_03b_mf_sj')

    #: Use the proper statistics when combining attributes from the PUD parcel centroids into the common area parcel
    fields = {
        'TOTAL_MKT_VALUE': 'Sum',
        'LAND_MKT_VALUE': 'Sum',
        'BLDG_SQFT': 'Sum',
        'FLOORS_CNT': 'Mean',
        'BUILT_YR': 'Mode',
        'BUILT_YR2': 'Max',
    }

    fieldmappings = _build_field_mapping(common_areas_features, mf_centroids, fields)

    # run the spatial join, use 'Join_Count' for number of units
    oug_sj = arcpy.SpatialJoin_analysis(
        target_features, join_features, output_features, 'JOIN_ONE_TO_ONE', 'KEEP_ALL', fieldmappings, 'INTERSECT'
    )

    # calculate the type field
    arcpy.CalculateField_management(oug_sj, field='TYPE', expression=f"'{tag}'")

    # rename join_count
    arcpy.CalculateField_management(oug_sj, field='parcel_count', expression='!Join_Count!')

    arcpy.DeleteField_management(oug_sj, 'Join_Count')

    #################################
    # get count from address points
    #################################

    # summarize address points address_point_count 'ap_count'
    target_features = oug_sj
    join_features = address_points
    output_features = os.path.join(output_gdb, '_02_multi_family')
    count_field_name = 'ap_count'

    oug_sj2 = _get_layer_with_address_point_count(target_features, join_features, output_features, count_field_name)

    #################################
    # WRAP-UP
    #################################

    parcels_without_multifamily_parcels, count_type, count_remaining = _remove_analyzed_features(
        input_parcel_layer, oug_sj2
    )

    # update year built with max if mode is 0
    _update_year_built(oug_sj2, ['BUILT_YR', 'BUILT_YR2'])

    # calculate basebldg field
    arcpy.CalculateField_management(oug_sj2, field='basebldg', expression='1')

    # calculate building_type_id field
    arcpy.CalculateField_management(oug_sj2, field='building_type_id', expression='2')

    # message
    print(f'{count_type} "{tag}" parcels were selected.\n{count_remaining} parcels remain...')

    return parcels_without_multifamily_parcels


def evaluate_single_family(input_parcel_layer, output_gdb):
    #: Query out 'single_family' parcels from main parcel feature class
    #: Update type, subtype
    #: save to _02_single_family
    #: Delete queried parcels from main parcel layer

    query = (" class IN ('single_family') ")
    tag = 'single_family'

    # select the features
    arcpy.SelectLayerByAttribute_management(input_parcel_layer, 'NEW_SELECTION', query)

    # count the selected features
    count_type = arcpy.GetCount_management(input_parcel_layer)

    # calculate the type field
    arcpy.CalculateField_management(input_parcel_layer, field='TYPE', expression=f"'{tag}'")

    arcpy.CalculateField_management(input_parcel_layer, field='SUBTYPE', expression=f"'{tag}'")

    # create the feature class for the parcel type
    arcpy.FeatureClassToFeatureClass_conversion(input_parcel_layer, output_gdb, f'_02_{tag}')

    # calculate basebldg field
    arcpy.CalculateField_management(os.path.join(output_gdb, f'_02_{tag}'), field='basebldg', expression='1')

    # calculate building_type_id field
    arcpy.CalculateField_management(os.path.join(output_gdb, f'_02_{tag}'), field='building_type_id', expression='1')

    # delete features from working parcels
    parcels_without_single_family_parcels = arcpy.DeleteFeatures_management(input_parcel_layer)

    # count remaining features
    arcpy.SelectLayerByAttribute_management(parcels_without_single_family_parcels, 'CLEAR_SELECTION')
    count_remaining = arcpy.GetCount_management(parcels_without_single_family_parcels)

    # message
    print(f'{count_type} "{tag}" parcels were selected.\n{count_remaining} parcels remain...')

    return parcels_without_single_family_parcels


def evaluate_multi_family_single_parcles(input_parcel_layer, scratch, address_points, output_gdb):

    #: Query out various multi-family parcels from main parcel feature class
    #: Update type, subtype
    #: Spatially join address points to queried parcels, calculate count
    #: save to _02_multi_family2

    query = (" class IN ('multi_family', 'duplex','apartment', 'townhome', 'triplex-quadplex') ")
    tag = 'multi_family'

    # select the features
    arcpy.SelectLayerByAttribute_management(input_parcel_layer, 'NEW_SELECTION', query)

    # count the selected features
    count_type = arcpy.GetCount_management(input_parcel_layer)

    # calculate the type field
    arcpy.CalculateField_management(input_parcel_layer, field='TYPE', expression=f"'{tag}'")

    # calculate the type field
    # arcpy.CalculateField_management(parcels_for_modeling_layer, field='SUBTYPE', expression="!class!",
    #                                 expression_type="PYTHON3")

    #: reclassify triplex-quadplex to apartment

    fields = ['SUBTYPE', 'NOTE', 'class']
    _reclassify_tri_quad_to_appartment(input_parcel_layer, fields)

    # create the feature class for the parcel type
    mf2_commons = arcpy.FeatureClassToFeatureClass_conversion(input_parcel_layer, scratch, '_02_mf2_commons')

    #################################
    # get count from address points
    #################################

    # summarize address points address_point_count 'ap_count'
    target_features = mf2_commons
    join_features = address_points
    output_features = os.path.join(output_gdb, '_02_multi_family2')

    oug_sj2 = _get_layer_with_address_point_count(target_features, join_features, output_features, 'ap_count')

    #################################
    # WRAP-UP
    #################################

    # calculate basebldg field
    arcpy.CalculateField_management(oug_sj2, field='basebldg', expression='1')

    # calculate building_type_id field
    arcpy.CalculateField_management(oug_sj2, field='building_type_id', expression='2')

    # delete features from working parcels
    parcels_without_multifamily_singles = arcpy.DeleteFeatures_management(input_parcel_layer)

    # count remaining features
    arcpy.SelectLayerByAttribute_management(parcels_without_multifamily_singles, 'CLEAR_SELECTION')
    count_remaining = arcpy.GetCount_management(parcels_without_multifamily_singles)

    # message
    print(f'{count_type} "{tag}" parcels were selected.\n{count_remaining} parcels remain...')

    return parcels_without_multifamily_singles


def evaluate_mobile_home_communities(input_parcel_layer, common_areas_features, scratch, address_points, output_gdb):

    #: Select parcels that have their center in mobile home boundaries or are classified as mobile_home_park
    #: Set type, subtype
    #: Copy to scratch fc
    #: Join adddress points to scratch fc, get count
    #: Save to _02_mobile_home_park

    tag = 'multi_family'
    tag2 = 'mobile_home_park'

    # use overlay to select mobile home parks parcels
    arcpy.SelectLayerByLocation_management(
        in_layer=input_parcel_layer,
        overlap_type='HAVE_THEIR_CENTER_IN',
        select_features=common_areas_features,
        selection_type='NEW_SELECTION'
    )
    query = (" class IN ('mobile_home_park') ")
    arcpy.SelectLayerByAttribute_management(input_parcel_layer, 'ADD_TO_SELECTION', query)

    # count the selected features
    count_type = arcpy.GetCount_management(input_parcel_layer)

    # calculate the type field
    arcpy.CalculateField_management(input_parcel_layer, field='TYPE', expression=f"'{tag}'")

    # calculate the type field
    arcpy.CalculateField_management(input_parcel_layer, field='SUBTYPE', expression=f"'{tag2}'")

    # create the feature class for the parcel type
    mobile_home_community_parcels = arcpy.FeatureClassToFeatureClass_conversion(
        input_parcel_layer, scratch, f'_07a_{tag}'
    )

    # delete features from working parcels
    parcels_without_mobile_home_communities = arcpy.DeleteFeatures_management(input_parcel_layer)

    # count remaining features
    arcpy.SelectLayerByAttribute_management(parcels_without_mobile_home_communities, 'CLEAR_SELECTION')
    count_remaining = arcpy.GetCount_management(parcels_without_mobile_home_communities)

    # recalc acreage
    # arcpy.CalculateGeometryAttributes_management(mhp, [['PARCEL_ACRES', 'AREA']], area_unit='ACRES')
    arcpy.CalculateField_management(mobile_home_community_parcels, 'PARCEL_ACRES', '!SHAPE.area@ACRES!')

    #################################
    # get count from address points
    #################################

    # summarize address points address_point_count 'ap_count'
    target_features = mobile_home_community_parcels
    join_features = address_points
    output_features = os.path.join(output_gdb, '_02_mobile_home_park')
    count_field_name = 'ap_count'

    oug_sj2 = _get_layer_with_address_point_count(target_features, join_features, output_features, count_field_name)

    # calculate basebldg field
    arcpy.CalculateField_management(oug_sj2, field='basebldg', expression='1')

    # message
    print(f'{count_type} "{tag}" parcels were selected.\n{count_remaining} parcels remain...')

    return parcels_without_mobile_home_communities


def _add_area_attribute(target_features, area_features, output_features):

    join_features = area_features
    rf_merged = arcpy.SpatialJoin_analysis(
        target_features,
        join_features,
        output_features,
        'JOIN_ONE_TO_ONE',
        'KEEP_ALL',
        match_option='HAVE_THEIR_CENTER_IN'
    )

    return rf_merged


# def _get_common_areas_as_df(common_areas_fc, type_field, common_area_name):


def davis():
    arcpy.env.overwriteOutput = True

    # show all columns
    pd.options.display.max_columns = None

    #: Inputs
    taz_shp = '.\\Inputs\\TAZ.shp'
    parcels = '.\\Inputs\\Davis_County_LIR_Parcels.gdb\\Parcels_Davis_LIR_UTM12'
    address_pts = '.\\Inputs\\AddressPoints_Davis.gdb\\address_points_davis'
    common_areas = r'.\Inputs\Common_Areas.gdb\Common_Areas_Reviewed'
    davis_extended = r'.\Inputs\davis_extended_simplified.csv'
    mobile_home_communities = '.\\Inputs\\Mobile_Home_Parks.shp'

    # create output gdb
    outputs = '.\\Outputs'
    gdb = os.path.join(outputs, 'classes_HUI.gdb')
    if not arcpy.Exists(gdb):
        arcpy.CreateFileGDB_management(outputs, 'classes_HUI.gdb')

    scratch = os.path.join(outputs, 'scratch_HUI.gdb')
    if not arcpy.Exists(scratch):
        arcpy.CreateFileGDB_management(outputs, 'scratch_HUI.gdb')

    #: Address points (used later)
    address_pts_no_base = _get_non_base_addr_points(address_pts, scratch)

    #: Prep Main Parcel Layer
    # select parcels within modeling area
    parcels_in_study_area = _get_parcels_in_modelling_area(parcels, taz_shp, scratch)

    #: Dissolve duplicate parcel ids
    parcels_dissolved_sdf = _dissolve_duplicate_parcels(parcels_in_study_area)

    # Load Extended Descriptions - be sure to format ACCOUNTNO column as text in excel first
    #: NOTE: this parcels_for_modeling_layer is completely independent of the earlier one.
    #: FeatureLayer
    parcels_for_modeling_layer = _join_extended_parcel_info(davis_extended, parcels_dissolved_sdf, scratch)

    #: More parcel prep
    fields = {
        'TYPE': 'TEXT',
        'SUBTYPE': 'TEXT',
        'NOTE': 'TEXT',
        'BUILT_YR2': 'SHORT',
    }
    parcels_for_modeling_layer = _add_fields(parcels_for_modeling_layer, fields)
    parcels_for_modeling_layer = _remove_empty_geomtries(parcels_for_modeling_layer)

    # add second built year field
    arcpy.CalculateField_management(parcels_for_modeling_layer, 'BUILT_YR2', '!BUILT_YR!')

    # get a count of all parcels
    count_all = arcpy.GetCount_management(parcels_for_modeling_layer)
    print(f'# initial parcels in modeling area:\n {count_all}')

    ###############
    # Common Areas
    ###############

    common_areas_lyr = arcpy.MakeFeatureLayer_management(common_areas, 'common_areas_lyr')

    # Planned Unit Developments
    query = ''' SUBTYPE_WFRC IN ('pud') '''
    arcpy.SelectLayerByAttribute_management(common_areas_lyr, 'NEW_SELECTION', query)
    ca_pud = arcpy.FeatureClassToFeatureClass_conversion(common_areas_lyr, scratch, '_02g_ca_pud')

    # multi_family
    query = ''' TYPE_WFRC IN ('multi_family') '''
    arcpy.SelectLayerByAttribute_management(common_areas_lyr, 'NEW_SELECTION', query)
    ca_multi_family = arcpy.FeatureClassToFeatureClass_conversion(common_areas_lyr, scratch, '_02e_ca_multi_family')

    #: Run the evaluations
    #: PUDs
    parcels_without_puds = evaluate_pud(parcels_for_modeling_layer, ca_pud, scratch, address_pts_no_base, gdb)

    #: Condos and other multi-parcel, multi-family dwellings
    parcels_without_condos = evaluate_multi_family_with_common_area(
        parcels_without_puds, ca_multi_family, scratch, address_pts_no_base, gdb
    )

    #: Single family dwellings
    parcels_without_single_family = evaluate_single_family(parcels_without_condos, gdb)

    #: Apartments, duplexes, other single-parcel, mutli-family dwellings
    parcels_without_apartments = evaluate_multi_family_single_parcles(
        parcels_without_single_family, scratch, address_pts_no_base, gdb
    )

    #: Mobile home communities
    parcels_without_mobile_homes = evaluate_mobile_home_communities(
        parcels_without_apartments, mobile_home_communities, scratch, address_pts_no_base, gdb
    )
    #
    #
    #
    #: Merge all the different counted residential layers back togethere and format w/Pandas
    # create paths
    res_files = ['_02_pud', '_02_single_family', '_02_mobile_home_park', '_02_multi_family', '_02_multi_family2']
    res_files = [os.path.join(gdb, res_file) for res_file in res_files]

    # merge features
    rf_merged = arcpy.Merge_management(
        res_files, os.path.join(scratch, '_10_Housing_Unit_Inventory'), add_source='ADD_SOURCE_INFO'
    )

    #-----------------------------
    # add cities as an attribute
    #-----------------------------
    cities = r'.\Inputs\Cities.shp'
    output_features = os.path.join(scratch, '_10b_Housing_Unit_Inventory_City')
    rf_merged = _add_area_attribute(rf_merged, cities, output_features)

    #---------------------------------
    # add subcounties as an attribute
    #---------------------------------
    subcounties = r'.\Inputs\SubCountyArea_2019.shp'
    output_features = os.path.join(scratch, '_10c_Housing_Unit_Inventory_SubCounty')
    rf_merged = _add_area_attribute(rf_merged, subcounties, output_features)

    #: convert to dataframe, format/rename, export
    rf_merged_df = pd.DataFrame.spatial.from_featureclass(rf_merged)
    # rf_merged_df = rf_merged_df[['OBJECTID','TYPE', 'SUBTYPE', 'PARCEL_ID','COUNT_PARCEL_ID', 'TOTAL_MKT_VALUE',
    #                              'LAND_MKT_VALUE', 'PARCEL_ACRES', 'HOUSE_CNT', 'parcel_count', 'ap_count', 'BLDG_SQFT',
    #                              'FLOORS_CNT','BUILT_YR', 'des_all','NAME','NewSA', 'SHAPE']].copy()

    #: Rename columns
    rf_merged_df = rf_merged_df.rename(columns={
        'NAME': 'CITY',
        'NewSA': 'SUBREGION',
        'parcel_count': 'PARCEL_COUNT',
    })

    # calc note column using property class
    #: TODO: Convert to fillna?
    #: 'NOTE' is not null if we already reclassified tri/quadplex to apartment
    # rf_merged_df.loc[(rf_merged_df['NOTE'].isnull()), 'NOTE'] = rf_merged_df['des_all']
    rf_merged_df['NOTE'].fillna(rf_merged_df['des_all'], in_place=True)

    # convert unit count columns to int
    rf_merged_df.loc[(rf_merged_df['HOUSE_CNT'].isnull()), 'HOUSE_CNT'] = 0
    rf_merged_df['HOUSE_CNT'] = rf_merged_df['HOUSE_CNT'].astype(int)
    rf_merged_df.loc[(rf_merged_df['ap_count'].isnull()), 'ap_count'] = 0
    rf_merged_df['ap_count'] = rf_merged_df['ap_count'].astype(int)

    # create new count field and calculate
    rf_merged_df['UNIT_COUNT'] = rf_merged_df['ap_count']

    # fix single family (non-pud)
    rf_merged_df.loc[(rf_merged_df['UNIT_COUNT'] == 0) & (rf_merged_df['SUBTYPE'] == 'single_family'), 'UNIT_COUNT'] = 1

    # fix duplex
    rf_merged_df.loc[(rf_merged_df['SUBTYPE'] == 'duplex'), 'UNIT_COUNT'] = 2

    # fix triplex-quadplex
    rf_merged_df.loc[(rf_merged_df['UNIT_COUNT'] < rf_merged_df['HOUSE_CNT']) &
                     (rf_merged_df['SUBTYPE'] == 'triplex-quadplex'), 'UNIT_COUNT'] = rf_merged_df['HOUSE_CNT']

    # calculate the decade
    rf_merged_df['BUILT_DECADE'] = 'NA'
    rf_merged_df.loc[(rf_merged_df['BUILT_YR'] >= 1840) & (rf_merged_df['BUILT_YR'] < 1850), 'BUILT_DECADE'] = "1840's"
    rf_merged_df.loc[(rf_merged_df['BUILT_YR'] >= 1850) & (rf_merged_df['BUILT_YR'] < 1860), 'BUILT_DECADE'] = "1850's"
    rf_merged_df.loc[(rf_merged_df['BUILT_YR'] >= 1860) & (rf_merged_df['BUILT_YR'] < 1870), 'BUILT_DECADE'] = "1860's"
    rf_merged_df.loc[(rf_merged_df['BUILT_YR'] >= 1870) & (rf_merged_df['BUILT_YR'] < 1880), 'BUILT_DECADE'] = "1870's"
    rf_merged_df.loc[(rf_merged_df['BUILT_YR'] >= 1880) & (rf_merged_df['BUILT_YR'] < 1890), 'BUILT_DECADE'] = "1880's"
    rf_merged_df.loc[(rf_merged_df['BUILT_YR'] >= 1890) & (rf_merged_df['BUILT_YR'] < 1900), 'BUILT_DECADE'] = "1890's"
    rf_merged_df.loc[(rf_merged_df['BUILT_YR'] >= 1900) & (rf_merged_df['BUILT_YR'] < 1910), 'BUILT_DECADE'] = "1900's"
    rf_merged_df.loc[(rf_merged_df['BUILT_YR'] >= 1910) & (rf_merged_df['BUILT_YR'] < 1920), 'BUILT_DECADE'] = "1910's"
    rf_merged_df.loc[(rf_merged_df['BUILT_YR'] >= 1920) & (rf_merged_df['BUILT_YR'] < 1930), 'BUILT_DECADE'] = "1920's"
    rf_merged_df.loc[(rf_merged_df['BUILT_YR'] >= 1930) & (rf_merged_df['BUILT_YR'] < 1940), 'BUILT_DECADE'] = "1930's"
    rf_merged_df.loc[(rf_merged_df['BUILT_YR'] >= 1940) & (rf_merged_df['BUILT_YR'] < 1950), 'BUILT_DECADE'] = "1940's"
    rf_merged_df.loc[(rf_merged_df['BUILT_YR'] >= 1950) & (rf_merged_df['BUILT_YR'] < 1960), 'BUILT_DECADE'] = "1950's"
    rf_merged_df.loc[(rf_merged_df['BUILT_YR'] >= 1960) & (rf_merged_df['BUILT_YR'] < 1970), 'BUILT_DECADE'] = "1960's"
    rf_merged_df.loc[(rf_merged_df['BUILT_YR'] >= 1970) & (rf_merged_df['BUILT_YR'] < 1980), 'BUILT_DECADE'] = "1970's"
    rf_merged_df.loc[(rf_merged_df['BUILT_YR'] >= 1980) & (rf_merged_df['BUILT_YR'] < 1990), 'BUILT_DECADE'] = "1980's"
    rf_merged_df.loc[(rf_merged_df['BUILT_YR'] >= 1990) & (rf_merged_df['BUILT_YR'] < 2000), 'BUILT_DECADE'] = "1990's"
    rf_merged_df.loc[(rf_merged_df['BUILT_YR'] >= 2000) & (rf_merged_df['BUILT_YR'] < 2010), 'BUILT_DECADE'] = "2000's"
    rf_merged_df.loc[(rf_merged_df['BUILT_YR'] >= 2010) & (rf_merged_df['BUILT_YR'] < 2020), 'BUILT_DECADE'] = "2010's"
    rf_merged_df.loc[(rf_merged_df['BUILT_YR'] >= 2020) & (rf_merged_df['BUILT_YR'] < 2030), 'BUILT_DECADE'] = "2020's"

    # add county
    rf_merged_df['COUNTY'] = 'DAVIS'

    # remove data points with zero units
    rf_merged_df = rf_merged_df[~(rf_merged_df['UNIT_COUNT'] == 0) & ~(rf_merged_df['HOUSE_CNT'] == 0)].copy()

    # Final ordering and subsetting of fields
    rf_merged_df = rf_merged_df[[
        'OBJECTID', 'PARCEL_ID', 'TYPE', 'SUBTYPE', 'NOTE', 'CITY', 'SUBREGION', 'COUNTY', 'UNIT_COUNT', 'PARCEL_COUNT',
        'FLOORS_CNT', 'PARCEL_ACRES', 'BLDG_SQFT', 'TOTAL_MKT_VALUE', 'BUILT_YR', 'BUILT_DECADE', 'SHAPE'
    ]].copy()

    # export to feature class
    rf_merged_df.spatial.to_featureclass(
        location=os.path.join(gdb, '_04_davis_housing_unit_inventory'), sanitize_columns=False
    )

    # export the final table
    del rf_merged_df['SHAPE']
    rf_merged_df.to_csv(os.path.join(outputs, 'davis_housing_unit_inventory.csv'), index=False)
