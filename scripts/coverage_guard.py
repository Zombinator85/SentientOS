import sys
import xml.etree.ElementTree as ET


def main() -> None:
    path = 'coverage.xml'
    try:
        tree = ET.parse(path)
    except Exception as exc:
        print(f'Failed to parse {path}: {exc}')
        sys.exit(1)

    root = tree.getroot()
    fail = False
    for file in root.findall('.//class'):
        filename = file.get('filename', 'unknown')
        rate_str = file.get('line-rate', '0')
        try:
            rate = float(rate_str)
        except ValueError:
            rate = 0.0
        if rate < 0.75:
            print(f'{filename} coverage {rate*100:.1f}% < 75%')
            fail = True
    if fail:
        sys.exit(1)


if __name__ == '__main__':
    main()

