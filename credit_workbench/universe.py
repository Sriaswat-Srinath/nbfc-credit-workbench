"""The issuer universe for the prototype.

Deliberately small (16) and deliberately mixed. Four institutions that failed,
four that came under severe stress and survived, eight that did not. The
failures are included so the tool can be demonstrated against known outcomes
WITHOUT the tool being fitted to them: nothing in the detection logic refers
to the outcome field, which exists only to label the demo.

`lender_type` matters because housing finance companies file under NHB/RBI-HFC
rules and other NBFCs under RBI's NBFC rules; indicators are compared within
type, never across.
"""

ISSUERS = [
    # symbol, name, type, group, outcome, outcome_date, outcome_class
    ("DHFL", "Dewan Housing Finance Corporation", "HFC", "Wadhawan",
     "Defaulted on NCD interest; later resolved under IBC",
     "2019-06-04", "default"),
    ("RHFL", "Reliance Home Finance", "HFC", "Reliance Capital",
     "Payment default; rated D", "2019-09-01", "default"),
    ("SREINFRA", "SREI Infrastructure Finance", "NBFC", "SREI",
     "RBI superseded the board", "2021-10-04", "intervention"),
    ("RELCAPITAL", "Reliance Capital", "CIC", "Reliance Capital",
     "RBI superseded the board", "2021-11-29", "intervention"),

    ("SAMMAANCAP", "Sammaan Capital (formerly Indiabulls Housing)", "HFC", None,
     "Funding run after the merger with Lakshmi Vilas Bank lapsed; survived",
     "2019-10-01", "stress"),
    ("PNBHOUSING", "PNB Housing Finance", "HFC", "Punjab National Bank",
     "Severe funding stress and a contested capital raise; survived",
     "2021-05-31", "stress"),
    ("IIFL", "IIFL Finance", "NBFC", "IIFL",
     "RBI barred fresh gold loans; restriction later lifted",
     "2024-03-04", "intervention"),
    ("EDELWEISS", "Edelweiss Financial Services", "NBFC", "Edelweiss",
     "RBI restricted two group entities", "2024-05-29", "intervention"),

    ("BAJFINANCE", "Bajaj Finance", "NBFC", "Bajaj", None, None, "none"),
    ("LICHSGFIN", "LIC Housing Finance", "HFC", "LIC", None, None, "none"),
    ("CHOLAFIN", "Cholamandalam Investment & Finance", "NBFC", "Murugappa",
     None, None, "none"),
    ("MUTHOOTFIN", "Muthoot Finance", "NBFC", "Muthoot", None, None, "none"),
    ("SHRIRAMFIN", "Shriram Finance", "NBFC", "Shriram", None, None, "none"),
    ("CANFINHOME", "Can Fin Homes", "HFC", "Canara Bank", None, None, "none"),
    ("REPCOHOME", "Repco Home Finance", "HFC", "Repco Bank", None, None, "none"),
    ("MANAPPURAM", "Manappuram Finance", "NBFC", "Manappuram",
     None, None, "none"),
]

BY_SYMBOL = {i[0]: dict(zip(
    ("symbol", "name", "lender_type", "group", "outcome", "outcome_date",
     "outcome_class"), i)) for i in ISSUERS}

# Related listed entities, for the group-contradiction check. These pairs are
# the cases where the listed parent's own accounts do not describe the
# operating lender.
RELATED = [
    ("RELCAPITAL", "RHFL", "Reliance Home Finance was a subsidiary of "
                           "Reliance Capital"),
    ("SREINFRA", None, "The lending book sat in SREI Equipment Finance, "
                       "which was never separately listed"),
]

if __name__ == "__main__":
    print(f"{len(ISSUERS)} issuers")
    for c in ("default", "intervention", "stress", "none"):
        n = [i[0] for i in ISSUERS if i[6] == c]
        print(f"  {c:13s} {len(n):2d}  {', '.join(n)}")
