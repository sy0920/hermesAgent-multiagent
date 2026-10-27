import sys
sys.path.insert(0, r"D:\codes\hermesAgent-multiagent\backend")
import re
from app.experts import _parse_soul, _SOUL_SECTION_RE

print("regex:", _SOUL_SECTION_RE.pattern)
t1 = "# Persona\n资深研究员\n\n# Expertise\n技术调研\n\n# Prompt\n输出要点列表\n"
t2 = "# Persona：资深研究员\n\n# Expertise：技术调研\n\n# Prompt：输出要点列表\n"
print("t1:", _parse_soul(t1))
print("t2:", _parse_soul(t2))
m = re.match(r"^#+\s*(Persona|Expertise|Prompt)\s*([\uff1a:]\s*[^\n]*)?$", "# Persona")
print("manual match:", m)