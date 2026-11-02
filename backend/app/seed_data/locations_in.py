"""Editable, name-only India location reference data for the demo."""

STATES = [
    ("Andhra Pradesh", "AP", "state"), ("Arunachal Pradesh", "AR", "state"),
    ("Assam", "AS", "state"), ("Bihar", "BR", "state"),
    ("Chhattisgarh", "CG", "state"), ("Goa", "GA", "state"),
    ("Gujarat", "GJ", "state"), ("Haryana", "HR", "state"),
    ("Himachal Pradesh", "HP", "state"), ("Jharkhand", "JH", "state"),
    ("Karnataka", "KA", "state"), ("Kerala", "KL", "state"),
    ("Madhya Pradesh", "MP", "state"), ("Maharashtra", "MH", "state"),
    ("Manipur", "MN", "state"), ("Meghalaya", "ML", "state"),
    ("Mizoram", "MZ", "state"), ("Nagaland", "NL", "state"),
    ("Odisha", "OD", "state"), ("Punjab", "PB", "state"),
    ("Rajasthan", "RJ", "state"), ("Sikkim", "SK", "state"),
    ("Tamil Nadu", "TN", "state"), ("Telangana", "TG", "state"),
    ("Tripura", "TR", "state"), ("Uttar Pradesh", "UP", "state"),
    ("Uttarakhand", "UK", "state"), ("West Bengal", "WB", "state"),
    ("Andaman and Nicobar Islands", "AN", "union_territory"),
    ("Chandigarh", "CH", "union_territory"),
    ("Dadra and Nagar Haveli and Daman and Diu", "DN", "union_territory"),
    ("Delhi", "DL", "union_territory"),
    ("Jammu and Kashmir", "JK", "union_territory"),
    ("Ladakh", "LA", "union_territory"),
    ("Lakshadweep", "LD", "union_territory"),
    ("Puducherry", "PY", "union_territory"),
]

# Names only, not a claim about official administrative boundaries or rankings.
OTHER_CITIES = {
    "AP": ("Vijayawada", "Visakhapatnam"), "AR": ("Itanagar", "Naharlagun"),
    "AS": ("Guwahati", "Dibrugarh"), "BR": ("Patna", "Gaya"),
    "CG": ("Raipur", "Bilaspur"), "GA": ("Panaji", "Margao"),
    "GJ": ("Ahmedabad", "Surat"), "HR": ("Gurugram", "Faridabad"),
    "HP": ("Shimla", "Dharamshala"), "JH": ("Ranchi", "Jamshedpur"),
    "KA": ("Bengaluru", "Mysuru"), "KL": ("Kochi", "Thiruvananthapuram"),
    "MH": ("Mumbai", "Pune"), "MN": ("Imphal", "Thoubal"),
    "ML": ("Shillong", "Tura"), "MZ": ("Aizawl", "Lunglei"),
    "NL": ("Kohima", "Dimapur"), "OD": ("Bhubaneswar", "Cuttack"),
    "PB": ("Ludhiana", "Amritsar"), "RJ": ("Jaipur", "Jodhpur"),
    "SK": ("Gangtok", "Namchi"), "TN": ("Chennai", "Coimbatore"),
    "TG": ("Hyderabad", "Warangal"), "TR": ("Agartala", "Udaipur"),
    "UP": ("Lucknow", "Kanpur"), "UK": ("Dehradun", "Haridwar"),
    "WB": ("Kolkata", "Siliguri"), "AN": ("Port Blair", "Diglipur"),
    "CH": ("Chandigarh",), "DN": ("Silvassa", "Daman"),
    "DL": ("New Delhi", "Delhi"), "JK": ("Srinagar", "Jammu"),
    "LA": ("Leh", "Kargil"), "LD": ("Kavaratti", "Agatti"),
    "PY": ("Puducherry", "Karaikal"),
}

GWALIOR_AREAS = (
    "City Centre", "Thatipur", "Morar", "Lashkar", "Gole Ka Mandir",
    "Maharaj Bada", "Hazira", "Phool Bagh", "Jayendraganj", "Sirol",
    "Padav", "Kampoo", "Bahodapur", "Govindpuri", "DD Nagar",
    "Madhav Nagar", "Shinde Ki Chhawni", "Gandhi Road", "Jhansi Road",
)

VENUE_TYPES = (
    ("mall", "Mall"), ("building", "Apartment Tower"),
    ("market", "Market Complex"), ("hospital", "Hospital"),
    ("office", "Office Complex"), ("station", "Transit Station"),
)
