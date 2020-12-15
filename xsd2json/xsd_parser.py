import simplejson as json
from collections import OrderedDict
from distutils.util import strtobool

from lxml import etree
from pathlib import Path

RESTRICTION_TYPES = (
    'enumeration',
    'fractionDigits',
    'length',
    'maxExclusive',
    'maxInclusive',
    'maxLength',
    'minExclusive',
    'minInclusive',
    'minLength',
    'pattern',
    'totalDigits',
    'whiteSpace'
)


class XSDParser:
    def __init__(self, xsd_src):
        self.complex_types = {}
        self.simple_types = {}
        self.element_mappings = []

        # Support for pathlib path
        if isinstance(xsd_src, Path) and xsd_src.is_file():
            xsd_src = xsd_src.__str__()

        try:
            # Read the XML content from string (from an opened file)
            self.root = etree.XML(xsd_src)
        except etree.XMLSyntaxError:
            # Or parse the file from its path
            doc = etree.parse(xsd_src)
            self.root = doc.getroot()

        self.namespaces = self.root.nsmap
        self.build_type_extensions()

    def build_type_extensions(self):
        """
        Build lists of named type extensions :
            - Complex :
                Get its type
                Get elements as children
            - Simple:
                Get its type
                Get Union children (if it has some)
                Get its restrictions
        """
        for complex_type_element in self.root.findall("xs:complexType", namespaces=self.namespaces):
            name = complex_type_element.attrib['name']
            schema = {}
            self.parse_complex_type_elements(complex_type_element, schema)
            self.complex_types[name] = schema

        for simple_type_element in self.root.findall("xs:simpleType", namespaces=self.namespaces):
            name = simple_type_element.attrib['name']
            schema = {}
            # Simple types could be defined under an xs:union
            if simple_type_element.findall(".//xs:union", namespaces=self.namespaces):
                # TODO : Manage the case that union has 'memberTypes' defined elsewhere instead nested simpleType
                for children_simple_types in simple_type_element.findall(".//xs:simpleType", namespaces=self.namespaces):
                    schema.setdefault('children', []).append(self.get_simple_type_restrictions(children_simple_types))
            else:
                schema = self.get_simple_type_restrictions(simple_type_element)
            self.simple_types[name] = schema

        # Then check if an element in complexType depends on an other complexType
        self.build_complex_type_dependencies(self.complex_types)

    def parse_complex_type_elements(self, element, schema):
        # Parse each child element
        for child_element in element.findall(".//xs:element", namespaces=self.namespaces):
            element_name = child_element.attrib.get('name')
            element_type = child_element.attrib.get('type')
            simple_types = child_element.findall(".//xs:simpleType", namespaces=self.namespaces)

            if element_name:
                schema.setdefault('children', OrderedDict())
            self.is_required_element(child_element, schema)

            # If child element has a type, it is a complexType defined elsewhere
            # OR a simple type like : "xs:string or xs:decimal" without defined restrictions
            if element_type:
                if element_type.startswith('xs:'):
                    element_type = element_type.replace('xs:', '')
                schema['children'][element_name] = {
                    'type': element_type
                }
                self.is_required_element(child_element, schema['children'][element_name])
            elif len(simple_types):
                # Simple types could be defined under an xs:union
                for simple_type in simple_types:
                    restriction_schema = self.get_simple_type_restrictions(simple_type)
                    schema['children'][element_name] = restriction_schema

        # If element has attributes, insert it
        self.get_attributes_restrictions(schema, element)

    def build_complex_type_dependencies(self, complex_type):
        """
        Some complexType could depends on other complexType, build the tree
        """
        for item in [item for item in complex_type if item not in ["min_occurs", "max_occurs", "nillable", "attrs"]]:
            if 'children' in complex_type[item]:
                for child in complex_type[item]['children']:
                    # If item has a type, check if it is defined
                    if 'type' in complex_type[item]['children'][child]:
                        type = complex_type[item]['children'][child]['type']
                        if not type == self.xsd_to_json_schema_type(type):
                            # Before adding that type, recurse on its children
                            self.build_complex_type_dependencies(self.xsd_to_json_schema_type(type))
                            complex_type[item]['children'][child] = self.xsd_to_json_schema_type(type)
            elif item == 'children':
                for child in complex_type[item]:
                    if isinstance(child, str) and 'type' in complex_type[item][child]:
                        type = complex_type[item][child]['type']
                        if not type == self.xsd_to_json_schema_type(type):
                            self.build_complex_type_dependencies(self.xsd_to_json_schema_type(type))
                            complex_type[item][child] = self.xsd_to_json_schema_type(type)
                    else:
                        type = child['type']
                        if not type == self.xsd_to_json_schema_type(type):
                            self.build_complex_type_dependencies(self.xsd_to_json_schema_type(type))
                            index_to_replace = complex_type[item].index(child)
                            complex_type[item][index_to_replace] = self.xsd_to_json_schema_type(type)
            elif item == 'type':
                type = complex_type[item]
                if not type == self.xsd_to_json_schema_type(type):
                    complex_type[item] = self.xsd_to_json_schema_type(type)
                break

    def get_simple_type_restrictions(self, simple_type):
        """
        https://www.w3schools.com/xml/schema_facets.asp
        Restrictions can have 'base' attribute to define the type of the value, then children below :
            - enumeration	    (multiple, acts as OR clause) Defines a list of acceptable values
            - fractionDigits	Specifies the maximum number of decimal places allowed. Must be equal to or greater than zero
            - length	        Specifies the exact number of characters or list items allowed. Must be equal to or greater than zero
            - maxExclusive	    Specifies the upper bounds for numeric values (the value must be less than this value)
            - maxInclusive	    Specifies the upper bounds for numeric values (the value must be less than or equal to this value)
            - maxLength	        Specifies the maximum number of characters or list items allowed. Must be equal to or greater than zero
            - minExclusive	    Specifies the lower bounds for numeric values (the value must be greater than this value)
            - minInclusive	    Specifies the lower bounds for numeric values (the value must be greater than or equal to this value)
            - minLength	        Specifies the minimum number of characters or list items allowed. Must be equal to or greater than zero
            - pattern	        (multiple, acts as OR clause) Defines the exact sequence of characters that are acceptable
            - totalDigits	    Specifies the exact number of digits allowed. Must be greater than zero
            - whiteSpace	    Specifies how white space (line feeds, tabs, spaces, and carriage returns) is handled
        """
        schema = dict()
        for restriction_elem in simple_type.findall(".//xs:restriction", namespaces=self.namespaces):
            schema['type'] = restriction_elem.attrib.get('base').replace('xs:', '')
            self.is_required_element(simple_type, schema)
            for restriction_type in RESTRICTION_TYPES:
                for item in restriction_elem.findall(".//xs:{}".format(restriction_type), namespaces=self.namespaces):
                    value = item.attrib.get('value')
                    if restriction_type == "enumeration" or restriction_type == "pattern":
                        schema.setdefault(restriction_type, []).append(value)
                    else:
                        schema[restriction_type] = value

        return schema

    def get_attributes_restrictions(self, schema, element):
        attrib = element.find(".//xs:attribute", namespaces=self.namespaces)
        if attrib is not None:
            attr_name = attrib.attrib.get('name')
            schema.setdefault('attrs', {})
            schema['attrs'][attr_name] = self.get_simple_type_restrictions(attrib)
            print(schema)


    @staticmethod
    def is_required_element(element, schema):
        # When parsing elements recursively, check if this one is required or nillable
        # Then : add min and max occurs (default to one if not provided)
        min_occurs = int(element.attrib.get('minOccurs', 1))
        max_occurs = element.attrib.get('maxOccurs') or int(element.attrib.get('maxOccurs', 1))
        nillable = strtobool(element.attrib.get('nillable')) if element.attrib.get('nillable') else False
        schema['min_occurs'] = min_occurs
        schema['max_occurs'] = max_occurs
        schema['nillable'] = nillable

    def parse_element_recurse(self, element, schema):
        """
        Parse elements recursively.
        If element has a type, retrieve its complexType to push it in json as children.
        If element has simpleType, push them into json as "AcceptableValues"
        """
        element_name = element.attrib.get('name')
        element_type = element.attrib.get('type')

        if element_name:
            # Prepare the children dict if does not exist yet, and tell if that element is required
            schema.setdefault('children', OrderedDict())

            schema['children'][element_name] = OrderedDict()
            # If this element has a type, retrieve its children schema
            if element_type:
                # schema['children'][element_name] = self.xsd_to_json_schema_type(element_type)
                schema['children'][element_name] = self.xsd_to_json_schema_type(element_type)

            # If element has attributes, get it
            self.get_attributes_restrictions(schema['children'][element_name], element)

            # Update schema pointer to build the tree with its own children
            schema = schema['children'][element_name]
            self.is_required_element(element, schema)

            # Append the element to the element_mappings to avoid re-process it
            self.element_mappings.append(element_name)

        # Call this function recursively to append all children
        for child_element in element.findall(".//xs:element", namespaces=self.namespaces):
            if not self.element_mappings.__contains__(child_element.attrib.get('name')):
                self.parse_element_recurse(child_element, schema)

    def json_schema(self, code_mirror_format):
        """
        Main entry point
            - Parse all elements from an xsd file
            - For each element, include children and types (complex / simple)
            - Produce a json (with codemirror compatibility if selected)
        :return:
        """
        schema = OrderedDict()
        # Starting point: all elements in the root of the document
        # This allows us to exclude complexType used as named types (e.g. tests/person.xsd)
        for element in self.root.findall("xs:element", namespaces=self.namespaces):
            self.parse_element_recurse(element, schema)

        # Format the schema - so for each children,
        if code_mirror_format:
            new_schema = self.format_codemirror(schema, topLevel=True)
            for item in new_schema:
                # Simply get children names
                if isinstance(new_schema[item], set):
                    new_schema[item] = list(new_schema[item])
                if 'children' in new_schema[item] and isinstance(new_schema[item]['children'], set):
                    new_schema[item]['children'] = list(new_schema[item]['children'])
                # And get enumeration in attrs, else None
                if 'attrs' in new_schema[item]:
                    for attr in new_schema[item]['attrs']:
                        if 'enumeration' in new_schema[item]['attrs'][attr]:
                            new_schema[item]['attrs'][attr] = new_schema[item]['attrs'][attr]['enumeration']
                        else:
                            new_schema[item]['attrs'][attr] = None

            schema = new_schema
        else:
            if len(schema['children']) == 1:
                first_property = next(iter(schema['children']))
                # If the sole top level item has child properties, then flatten
                # If there's no child properties, do no flatten
                if 'children' in schema['children'][first_property]:
                    schema = schema['children'][first_property]

        # Set schema
        schema['schema'] = 'http://json-schema.org/schema#'
        schema['type'] = 'object'
        return json.dumps(schema, sort_keys=False, indent=4)

    def xsd_to_json_schema_type(self, element_type):
        """
        Check if the type exists in lists, then append the sub schema
        """
        if element_type in self.complex_types or element_type in self.simple_types:
            try:
                return self.complex_types[element_type]
            except KeyError:
                return self.simple_types[element_type]
        else:
            return element_type

    def format_codemirror(self, schema, tmp_schema=None, topLevel=False, parent=None):
        items = schema['children'] if 'children' in schema else []
        for item in items:
            if not(isinstance(item, dict)):
                if topLevel:
                    tmp_schema = OrderedDict() if not tmp_schema else tmp_schema
                    tmp_schema.setdefault('!top', set([])).add(item)
                if parent:
                    tmp_schema[parent]['children'].add(item)
                tmp_schema.setdefault(item, OrderedDict()).setdefault('children', set())
                copy = {x: schema['children'][item][x] for x in schema['children'][item] if x not in ['children']}
                tmp_schema[item].update(copy)
                self.format_codemirror(schema['children'][item], tmp_schema=tmp_schema, parent=item)
            else:
                # For items with (union) multiple restrictions (a string OR a pattern for example)
                tmp_schema[parent].setdefault('conditions', []).append(item)
        return tmp_schema