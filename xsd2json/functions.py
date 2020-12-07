from .xsd_parser import XSDParser


def xsd_to_json_schema(xsd_src, code_mirror_format=False):
    """
    Helper function to initialise XSDParser and parsing a file or a content
    :param xsd_src: Path to XSD file OR XSD content as string
    :param code_mirror_format: Either using codemirror json format or not
    :return:
    """
    xsd_parser = XSDParser(xsd_src)
    result = xsd_parser.json_schema(code_mirror_format=code_mirror_format)
    return result
