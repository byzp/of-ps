import re

input_file = "a.py"
output_file = "output.py"

hex_pattern = re.compile(r"0x[0-9a-fA-F]+")

with open(input_file, "r", encoding="utf-8") as f:
    content = f.read()


def hex_to_dec(match):
    return str(int(match.group(0), 16))


new_content = hex_pattern.sub(hex_to_dec, content)

with open(output_file, "w", encoding="utf-8") as f:
    f.write(new_content)
