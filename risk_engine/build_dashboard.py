"""Build the dashboard: a small HTML page plus a separate data file.

The data used to be inlined as a ~530 KB <script type="application/json"> blob.
That renders fine in a real DOM but did not start in the artifact viewer, which
left every placeholder showing and no table or charts. Splitting the data into a
sibling script keeps the page itself around 35 KB and uses the ordinary
multi-file pattern.
"""

import os

HERE = os.path.dirname(os.path.abspath(__file__))

tpl = open(os.path.join(HERE, "dashboard_template.html")).read()
data = open(os.path.join(HERE, "dashboard_data.json")).read()

page = os.path.join(HERE, "dashboard.html")
open(page, "w").write(tpl)

datajs = os.path.join(HERE, "data.js")
open(datajs, "w").write("window.__RISK_DATA = " + data + ";\n")

print(f"wrote {page} ({os.path.getsize(page)/1024:.0f} KB)")
print(f"wrote {datajs} ({os.path.getsize(datajs)/1024:.0f} KB)")
