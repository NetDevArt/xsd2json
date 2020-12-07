from pathlib import Path

from device.modules.xsd2json.xsd2json.xsd_parser import XSDParser

if __name__ == '__main__':
    xsd_file = Path(__file__).resolve().parent.joinpath('xsd', 'SET_PRM.xsd')
    # Test with codemirror
    xsd_parser = XSDParser(xsd_file)
    cm_result = xsd_parser.json_schema(code_mirror_format=True)
    print(cm_result)

    # Test without codemirror
    # xsd_parser2 = XSDParser(xsd_file)
    # result = xsd_parser2.json_schema(code_mirror_format=False)
    # print(result)
