# Input Data

## Parcels

LIR parcels. Uses these fields:

- 'OBJECTID'
- 'PARCEL_ID'
- 'TAXEXEMPT_TYPE'
- 'TOTAL_MKT_VALUE'
- 'LAND_MKT_VALUE'
- 'PARCEL_ACRES'
- 'PROP_CLASS'
- 'PRIMARY_RES'
- 'HOUSE_CNT'
- 'BLDG_SQFT'
- 'FLOORS_CNT'
- 'BUILT_YR'
- 'EFFBUILT_YR'
- 'SHAPE'

Duplicate OIDs are dissolved on parcel ID, adding the following field:

- 'COUNT_PARCEL_ID' (not used)

Adds the following fields for analysis:

- 'TYPE'
- 'SUBTYPE'
- 'NOTE'            Stores triplex-quadplex designation for unit count use, everything else gets description from assesor
- 'UNIT_COUNT'      Oug parcels get # of addr pts, sf parcels get 1, duplex get 2, tri/quad get HOUSE_CNT
- 'BUILT_DECADE'    Mathematically created
- 'COUNTY'          hardcoded

## Extended Parcel Info

From Assesor. For davis, joins between AccountNo and Parcel ID.

- class             The detailed description of the parcel (sf, apartment, mobile home, etc)
- des_all           Copied to NOTE field for non tri/quad parcels

## Other info

From UGRC/MPOs

- CITY              From spatially-joined city boundaries.
- SUBREGION         From spatially-joined subcounty boundaries (MPO/county), used to identify similar areas.

## Address Points

UT address points. Used to get unit count- need to have one point for every unit (apt, mobile home, condo, duplex, etc).

filters out any BASE ADRRESS PtType points.

## Common Areas

Created. Used to identify areas that contribute to the value/acreage of multiple units (PUDs, condos, mobile homes, etc).
