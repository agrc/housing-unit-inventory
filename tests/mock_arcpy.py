import sys
from unittest.mock import Mock

#: Creates a mock arcpy object and inserts it as a module so that any subsequent 'import arcpy' calls load the mock.
#: Put in it's own module so that it can be imported before arcpy or other modules that import arcpy in turn
module_name = 'arcpy'
arcpy = Mock(name=module_name)
sys.modules[module_name] = arcpy
