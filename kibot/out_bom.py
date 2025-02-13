# -*- coding: utf-8 -*-
# Copyright (c) 2020-2021 Salvador E. Tropea
# Copyright (c) 2020-2021 Instituto Nacional de Tecnología Industrial
# License: MIT
# Project: KiBot (formerly KiPlot)
"""
Internal BoM (Bill of Materials) output for KiBot.
This is somehow compatible with KiBoM.
"""
import os
from .gs import GS
from .misc import W_BADFIELD
from .optionable import Optionable, BaseOptions
from .registrable import RegOutput
from .error import KiPlotConfigurationError
from .kiplot import get_board_comps_data, load_any_sch
from .bom.columnlist import ColumnList, BoMError
from .bom.bom import do_bom
from .var_kibom import KiBoM
from .kicad.v5_sch import Schematic
from .fil_base import BaseFilter, apply_exclude_filter, apply_fitted_filter, apply_fixed_filter, reset_filters
from .macros import macros, document, output_class  # noqa: F401
from . import log
# To debug the `with document` we can use:
# from .mcpyrate.debug import macros, step_expansion
# with step_expansion:

logger = log.get_logger(__name__)
VALID_STYLES = {'modern-blue', 'modern-green', 'modern-red', 'classic'}
DEFAULT_ALIASES = [['r', 'r_small', 'res', 'resistor'],
                   ['l', 'l_small', 'inductor'],
                   ['c', 'c_small', 'cap', 'capacitor'],
                   ['sw', 'switch'],
                   ['zener', 'zenersmall'],
                   ['d', 'diode', 'd_small'],
                   ]


class BoMColumns(Optionable):
    """ Information for the BoM columns """
    def __init__(self):
        super().__init__()
        self._unkown_is_error = True
        with document:
            self.field = ''
            """ Name of the field to use for this column """
            self.name = ''
            """ Name to display in the header. The field is used when empty """
            self.join = Optionable
            """ [list(string)|string=''] List of fields to join to this column """
        self._field_example = 'Row'
        self._name_example = 'Line'

    def config(self, parent):
        super().config(parent)
        if not self.field:
            raise KiPlotConfigurationError("Missing or empty `field` in columns list ({})".format(str(self._tree)))
        # Ensure this is None or a list
        # Also arrange it as field, cols...
        field = self.field.lower()
        if isinstance(self.join, type):
            self.join = None
        elif isinstance(self.join, str):
            if self.join:
                self.join = [field, self.join.lower()]
            else:
                self.join = None
        else:
            self.join = [field]+[c.lower() for c in self.join]


class BoMLinkable(Optionable):
    """ Base class for HTML and XLSX formats """
    def __init__(self):
        super().__init__()
        with document:
            self.col_colors = True
            """ Use colors to show the field type """
            self.datasheet_as_link = ''
            """ Column with links to the datasheet """
            self.digikey_link = Optionable
            """ [string|list(string)=''] Column/s containing Digi-Key part numbers, will be linked to web page """
            self.generate_dnf = True
            """ Generate a separated section for DNF (Do Not Fit) components """
            self.hide_pcb_info = False
            """ Hide project information """
            self.hide_stats_info = False
            """ Hide statistics information """
            self.highlight_empty = True
            """ Use a color for empty cells. Applies only when `col_colors` is `true` """
            self.logo = Optionable
            """ [string|boolean=''] PNG file to use as logo, use false to remove """
            self.title = 'KiBot Bill of Materials'
            """ BoM title """

    def config(self, parent):
        super().config(parent)
        # digikey_link
        if isinstance(self.digikey_link, type):
            self.digikey_link = []
        elif isinstance(self.digikey_link, list):
            self.digikey_link = [c.lower() for c in self.digikey_link]
        # Logo
        if isinstance(self.logo, type):
            self.logo = ''
        elif isinstance(self.logo, bool):
            self.logo = '' if self.logo else None
        elif self.logo:
            self.logo = os.path.abspath(self.logo)
            if not os.path.isfile(self.logo):
                raise KiPlotConfigurationError('Missing logo file `{}`'.format(self.logo))
        # Datasheet as link
        self.datasheet_as_link = self.datasheet_as_link.lower()


class BoMHTML(BoMLinkable):
    """ HTML options """
    def __init__(self):
        super().__init__()
        with document:
            self.style = 'modern-blue'
            """ Page style. Internal styles: modern-blue, modern-green, modern-red and classic.
                Or you can provide a CSS file name. Please use .css as file extension. """

    def config(self, parent):
        super().config(parent)
        # Style
        if not self.style:
            self.style = 'modern-blue'
        if self.style not in VALID_STYLES:
            self.style = os.path.abspath(self.style)
            if not os.path.isfile(self.style):
                raise KiPlotConfigurationError('Missing style file `{}`'.format(self.style))


class BoMCSV(Optionable):
    """ CSV options """
    def __init__(self):
        super().__init__()
        with document:
            self.separator = ','
            """ CSV Separator. TXT and TSV always use tab as delimiter """
            self.hide_pcb_info = False
            """ Hide project information """
            self.hide_stats_info = False
            """ Hide statistics information """
            self.quote_all = False
            """ Enclose all values using double quotes """


class BoMXLSX(BoMLinkable):
    """ XLSX options """
    def __init__(self):
        super().__init__()
        with document:
            self.max_col_width = 60
            """ [20,999] Maximum column width (characters) """
            self.style = 'modern-blue'
            """ Head style: modern-blue, modern-green, modern-red and classic. """

    def config(self, parent):
        super().config(parent)
        # Style
        if not self.style:
            self.style = 'modern-blue'
        if self.style not in VALID_STYLES:
            raise KiPlotConfigurationError('Unknown style `{}`'.format(self.style))


class ComponentAliases(Optionable):
    _default = DEFAULT_ALIASES

    def __init__(self):
        super().__init__()


class GroupFields(Optionable):
    _default = ColumnList.DEFAULT_GROUPING

    def __init__(self):
        super().__init__()


class NoConflict(Optionable):
    _default = "['Config', 'Part']"

    def __init__(self):
        super().__init__()


class Aggregate(Optionable):
    def __init__(self):
        super().__init__()
        with document:
            self.file = ''
            """ Name of the schematic to aggregate """
            self.name = ''
            """ Name to identify this source. If empty we use the name of the schematic """
            self.ref_id = ''
            """ A prefix to add to all the references from this project """
            self.number = 1
            """ Number of boards to build (components multiplier). Use negative to substract """

    def config(self, parent):
        super().config(parent)
        if not self.file:
            raise KiPlotConfigurationError("Missing or empty `file` in aggregate list ({})".format(str(self._tree)))
        if not self.name:
            self.name = os.path.splitext(os.path.basename(self.file))[0]


class BoMOptions(BaseOptions):
    def __init__(self):
        with document:
            self.number = 1
            """ Number of boards to build (components multiplier) """
            self.variant = ''
            """ Board variant, used to determine which components
                are output to the BoM. """
            self.output = GS.def_global_output
            """ filename for the output (%i=bom)"""
            self.format = ''
            """ [HTML,CSV,TXT,TSV,XML,XLSX] format for the BoM.
                Defaults to CSV or a guess according to the options. """
            # Equivalent to KiBoM INI:
            self.ignore_dnf = True
            """ Exclude DNF (Do Not Fit) components """
            self.fit_field = 'Config'
            """ Field name used for internal filters """
            self.use_alt = False
            """ Print grouped references in the alternate compressed style eg: R1-R7,R18 """
            self.columns = BoMColumns
            """ [list(dict)|list(string)] List of columns to display.
                Can be just the name of the field """
            self.normalize_values = False
            """ Try to normalize the R, L and C values, producing uniform units and prefixes """
            self.normalize_locale = False
            """ When normalizing values use the locale decimal point """
            self.ref_separator = ' '
            """ Separator used for the list of references """
            self.html = BoMHTML
            """ [dict] Options for the HTML format """
            self.xlsx = BoMXLSX
            """ [dict] Options for the XLSX format """
            self.csv = BoMCSV
            """ [dict] Options for the CSV, TXT and TSV formats """
            # * Filters
            self.exclude_filter = Optionable
            """ [string|list(string)='_mechanical'] Name of the filter to exclude components from BoM processing.
                The default filter excludes test points, fiducial marks, mounting holes, etc """
            self.dnf_filter = Optionable
            """ [string|list(string)='_kibom_dnf'] Name of the filter to mark components as 'Do Not Fit'.
                The default filter marks components with a DNF value or DNF in the Config field """
            self.dnc_filter = Optionable
            """ [string|list(string)='_kibom_dnc'] Name of the filter to mark components as 'Do Not Change'.
                The default filter marks components with a DNC value or DNC in the Config field """
            # * Grouping criteria
            self.group_connectors = True
            """ Connectors with the same footprints will be grouped together, independent of the name of the connector """
            self.merge_blank_fields = True
            """ Component groups with blank fields will be merged into the most compatible group, where possible """
            self.group_fields = GroupFields
            """ [list(string)] List of fields used for sorting individual components into groups.
                Components which match (comparing *all* fields) will be grouped together.
                Field names are case-insensitive.
                If empty: ['Part', 'Part Lib', 'Value', 'Footprint', 'Footprint Lib'] is used """
            self.group_fields_fallbacks = Optionable
            """ [list(string)] List of fields to be used when the fields in `group_fields` are empty.
                The first field in this list is the fallback for the first in `group_fields`, and so on """
            self.component_aliases = ComponentAliases
            """ [list(list(string))] A series of values which are considered to be equivalent for the part name.
                Each entry is a list of equivalen names. Example: ['c', 'c_small', 'cap' ]
                will ensure the equivalent capacitor symbols can be grouped together.
                If empty the following aliases are used:
                - ['r', 'r_small', 'res', 'resistor']
                - ['l', 'l_small', 'inductor']
                - ['c', 'c_small', 'cap', 'capacitor']
                - ['sw', 'switch']
                - ['zener', 'zenersmall']
                - ['d', 'diode', 'd_small'] """
            self.no_conflict = NoConflict
            """ [list(string)] List of fields where we tolerate conflicts.
                Use it to avoid undesired warnings.
                By default the field indicated in `fit_field` and the field `part` are excluded """
            self.aggregate = Aggregate
            """ [list(dict)] Add components from other projects """
            self.ref_id = ''
            """ A prefix to add to all the references from this project. Used for multiple projects """
            self.source_by_id = False
            """ Generate the `Source BoM` column using the reference ID instead of the project name """
            self.int_qtys = True
            """ Component quantities are always expressed as integers. Using the ceil() function """
        self._format_example = 'CSV'
        super().__init__()

    @staticmethod
    def _get_columns():
        """ Create a list of valid columns """
        if GS.sch:
            return GS.sch.get_field_names(ColumnList.COLUMNS_DEFAULT)
        return ColumnList.COLUMNS_DEFAULT

    def _guess_format(self):
        """ Figure out the format """
        if not self.format:
            # If we have HTML options generate an HTML
            if not isinstance(self.html, type):
                return 'html'
            # Same for XLSX
            if not isinstance(self.xlsx, type):
                return 'xlsx'
            # Default to a simple and common format: CSV
            return 'csv'
        # Explicit selection
        return self.format.lower()

    def _normalize_variant(self):
        """ Replaces the name of the variant by an object handling it. """
        if self.variant:
            if not RegOutput.is_variant(self.variant):
                raise KiPlotConfigurationError("Unknown variant name `{}`".format(self.variant))
            self.variant = RegOutput.get_variant(self.variant)
        else:
            # If no variant is specified use the KiBoM variant class with basic functionality
            self.variant = KiBoM()
            self.variant.config_field = self.fit_field
            self.variant.variant = []
            self.variant.name = 'default'
            # Delegate any filter to the variant
            self.variant.set_def_filters(self.exclude_filter, self.dnf_filter, self.dnc_filter)
            self.exclude_filter = self.dnf_filter = self.dnc_filter = None
            self.variant.config(self)  # Fill or adjust any detail

    def config(self, parent):
        super().config(parent)
        self.format = self._guess_format()
        self._expand_id = 'bom'
        self._expand_ext = self.format.lower()
        # HTML options
        if self.format == 'html' and isinstance(self.html, type):
            # If no options get the defaults
            self.html = BoMHTML()
            self.html.config(self)
        # CSV options
        if self.format in ['csv', 'tsv', 'txt'] and isinstance(self.csv, type):
            # If no options get the defaults
            self.csv = BoMCSV()
            self.csv.config(self)
        # XLSX options
        if self.format == 'xlsx' and isinstance(self.xlsx, type):
            # If no options get the defaults
            self.xlsx = BoMXLSX()
            self.xlsx.config(self)
        # group_fields
        if isinstance(self.group_fields, type):
            self.group_fields = ColumnList.DEFAULT_GROUPING
        else:
            # Make the grouping fields lowercase
            self.group_fields = [f.lower() for f in self.group_fields]
        # group_fields_fallbacks
        if isinstance(self.group_fields_fallbacks, type):
            self.group_fields_fallbacks = []
        else:
            # Make the grouping fields lowercase
            self.group_fields_fallbacks = [f.lower() for f in self.group_fields_fallbacks]
        # Fill with None if needed
        if len(self.group_fields_fallbacks) < len(self.group_fields):
            self.group_fields_fallbacks.extend([None]*(len(self.group_fields)-len(self.group_fields_fallbacks)))
        # component_aliases
        if isinstance(self.component_aliases, type):
            self.component_aliases = DEFAULT_ALIASES
        # Filters
        self.exclude_filter = BaseFilter.solve_filter(self.exclude_filter, 'exclude_filter')
        self.dnf_filter = BaseFilter.solve_filter(self.dnf_filter, 'dnf_filter')
        self.dnc_filter = BaseFilter.solve_filter(self.dnc_filter, 'dnc_filter')
        # Variants, make it an object
        self._normalize_variant()
        # Field names are handled in lowercase
        self.fit_field = self.fit_field.lower()
        # Fields excluded from conflict warnings
        no_conflict = set()
        if isinstance(self.no_conflict, type):
            no_conflict.add(self.fit_field)
            no_conflict.add('part')
        else:
            for field in self.no_conflict:
                no_conflict.add(field.lower())
        self.no_conflict = no_conflict
        # Make sure aggregate is a list
        if isinstance(self.aggregate, type):
            self.aggregate = []
        # Columns
        self.column_rename = {}
        self.join = []
        valid_columns = self._get_columns()
        if isinstance(self.columns, type):
            # If none specified make a list with all the possible columns.
            # Here are some exceptions:
            # Ignore the part and footprint library, also sheetpath and the Reference in singular
            ignore = [ColumnList.COL_PART_LIB_L, ColumnList.COL_FP_LIB_L, ColumnList.COL_SHEETPATH_L,
                      ColumnList.COL_REFERENCE_L[:-1]]
            if len(self.aggregate) == 0:
                ignore.append(ColumnList.COL_SOURCE_BOM_L)
                if self.number == 1:
                    # For one board avoid COL_GRP_BUILD_QUANTITY
                    ignore.append(ColumnList.COL_GRP_BUILD_QUANTITY_L)
            # Exclude the particular columns
            self.columns = [h for h in valid_columns if not h.lower() in ignore]
        else:
            # Ensure the column names are valid.
            # Also create the rename and join lists.
            # Lower case available columns (to check if valid)
            valid_columns_l = {c.lower(): c for c in valid_columns}
            logger.debug("Valid columns: {} ({})".format(valid_columns, len(valid_columns)))
            # Create the different lists
            columns = []
            for col in self.columns:
                if isinstance(col, str):
                    # Just a string, add to the list of used
                    new_col = col
                else:
                    # A complete entry
                    new_col = col.field
                    # A column rename
                    if col.name:
                        self.column_rename[col.field.lower()] = col.name
                    # Attach other columns
                    if col.join:
                        self.join.append(col.join)
                # Check this is a valid column
                if new_col.lower() not in valid_columns_l:
                    # The Field_Rename filter can change this situation:
                    # raise KiPlotConfigurationError('Invalid column name `{}`'.format(new_col))
                    logger.warning(W_BADFIELD+'Invalid column name `{}`'.format(new_col))
                columns.append(new_col)
            # This is the ordered list with the case style defined by the user
            self.columns = columns

    def aggregate_comps(self, comps):
        self.qtys = {GS.sch_basename: self.number}
        for prj in self.aggregate:
            if not os.path.isfile(prj.file):
                raise KiPlotConfigurationError("Missing `{}`".format(prj.file))
            logger.debug('Adding components from project {} ({}) using reference id `{}`'.
                         format(prj.name, prj.file, prj.ref_id))
            self.qtys[prj.name] = prj.number
            prj.sch = Schematic()
            load_any_sch(prj.sch, prj.file, prj.name)
            new_comps = prj.sch.get_components()
            for c in new_comps:
                c.ref = prj.ref_id+c.ref
                c.ref_id = prj.ref_id
            comps.extend(new_comps)
            prj.source = os.path.basename(prj.file)

    def run(self, output):
        format = self.format.lower()
        # Add some info needed for the output to the config object.
        # So all the configuration is contained in one object.
        self.source = GS.sch_basename
        self.date = GS.sch_date
        self.revision = GS.sch_rev
        self.debug_level = GS.debug_level
        self.kicad_version = GS.kicad_version
        # Get the components list from the schematic
        comps = GS.sch.get_components()
        get_board_comps_data(comps)
        # Apply the reference prefix
        for c in comps:
            c.ref = self.ref_id+c.ref
            c.ref_id = self.ref_id
        # Aggregate components from other projects
        self.aggregate_comps(comps)
        # Apply all the filters
        reset_filters(comps)
        apply_exclude_filter(comps, self.exclude_filter)
        apply_fitted_filter(comps, self.dnf_filter)
        apply_fixed_filter(comps, self.dnc_filter)
        # Apply the variant
        comps = self.variant.filter(comps)
        # We add the main project to the aggregate list so do_bom sees a complete list
        base_sch = Aggregate()
        base_sch.file = GS.sch_file
        base_sch.name = GS.sch_basename
        base_sch.ref_id = self.ref_id
        base_sch.number = self.number
        base_sch.sch = GS.sch
        self.aggregate.insert(0, base_sch)
        # To translate project to ID
        if self.source_by_id:
            self.source_to_id = {prj.name: prj.ref_id for prj in self.aggregate}
        try:
            do_bom(output, format, comps, self)
        except BoMError as e:
            raise KiPlotConfigurationError(str(e))
        # Undo the reference prefix
        if self.ref_id:
            l_id = len(self.ref_id)
            for c in filter(lambda c: c.project == GS.sch_basename, comps):
                c.ref = c.ref[l_id:]
                c.ref_id = ''

    def get_targets(self, out_dir):
        return [self._parent.expand_filename(out_dir, self.output)]


@output_class
class BoM(BaseOutput):  # noqa: F821
    """ BoM (Bill of Materials)
        Used to generate the BoM in CSV, HTML, TSV, TXT, XML or XLSX format using the internal BoM.
        Is compatible with KiBoM, but doesn't need to update the XML netlist because the components
        are loaded from the schematic.
        Important differences with KiBoM output:
        - All options are in the main `options` section, not in `conf` subsection.
        - The `Component` column is named `Row` and works just like any other column.
        This output is what you get from the 'Tools/Generate Bill of Materials' menu in eeschema. """
    def __init__(self):
        super().__init__()
        with document:
            self.options = BoMOptions
            """ [dict] Options for the `bom` output """
        self._sch_related = True
