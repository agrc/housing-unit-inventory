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

- 'COUNT_PARCEL_ID'

Adds the following fields for analysis:

- 'TYPE'
- 'SUBTYPE'
- 'NOTE'
- 'BUILT_YR2'

## Extended Parcel Info

From Assesor. For davis, joins between AccountNo and Parcel ID.

- class: The detailed description of the parcel (sf, apartment, mobile home, etc)
- notes: Carried over but not used?

## Address Points

UT address points. Used to get unit count- need to have one point for every unit (apt, mobile home, condo, duplex, etc).

filters out any BASE ADRRESS PtType points.

## Common Areas

Created. Used to identify areas that contribute to the value/acreage of multiple units (PUDs, condos, mobile homes, etc).
