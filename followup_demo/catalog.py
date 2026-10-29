"""
Demo product catalog and the performance markers techs check on each call.

Markers are defined per product category so a new SKU automatically inherits
the right checklist. In production these would be maintained in the
performance_markers table by the client.
"""

# (sku, name, category, base_price, description)
PRODUCTS = [
    ("HVAC-HP-3T", "3-Ton Heat Pump System (16 SEER2)", "HVAC", 7800.00,
     "Central heat pump with matched air handler; installed with new line set."),
    ("HVAC-FURN-96", "96% AFUE Gas Furnace", "HVAC", 4200.00,
     "High-efficiency two-stage gas furnace."),
    ("WH-TANKLESS-199", "Tankless Water Heater (199k BTU)", "Water Heater", 3100.00,
     "Whole-home on-demand gas water heater."),
    ("WH-HYBRID-50", "50-Gallon Hybrid Heat Pump Water Heater", "Water Heater", 2600.00,
     "Electric heat pump water heater with smart modes."),
    ("GEN-STANDBY-22", "22kW Standby Generator", "Generator", 11500.00,
     "Natural gas standby generator with automatic transfer switch."),
    ("WT-SOFT-48K", "48,000-Grain Water Softener", "Water Treatment", 1900.00,
     "Metered whole-home softener with brine tank."),
    ("WT-RO-5", "5-Stage Reverse Osmosis System", "Water Treatment", 650.00,
     "Under-sink drinking water filtration."),
    ("SH-TSTAT-WIFI", "Wi-Fi Smart Thermostat", "Smart Home", 320.00,
     "Learning thermostat with app control."),
    ("IAQ-UV-PURIFIER", "Whole-Home UV Air Purifier", "Indoor Air Quality", 1450.00,
     "In-duct UV + PCO air purification."),
]

PERFORMANCE_MARKERS = {
    "HVAC": [
        "Reaches the set temperature in a reasonable time",
        "Even temperature and airflow across rooms",
        "Noise level indoors and at the outdoor unit is acceptable",
        "Change in energy bill compared to the old system",
        "Customer knows the filter schedule and maintenance plan",
    ],
    "Water Heater": [
        "Hot water arrives quickly at the farthest tap",
        "Temperature stays consistent during showers and multiple fixtures",
        "No leaks, error codes, or unusual noises",
        "Change in utility bill since install",
    ],
    "Generator": [
        "Weekly self-test running on schedule",
        "Has it run during an outage? Did transfer happen automatically?",
        "No warning lights or alerts in the app/controller",
        "Customer knows the annual maintenance requirement",
    ],
    "Water Treatment": [
        "Noticeable change in water quality (taste, scale, spotting)",
        "Salt / filter level understood and being maintained",
        "No leaks or drop in water pressure",
        "Regeneration / flush cycle not disruptive",
    ],
    "Smart Home": [
        "Device stays connected to Wi-Fi and the app",
        "Schedules and set points working as configured",
        "Customer is comfortable using the app",
    ],
    "Indoor Air Quality": [
        "Noticeable change in air quality, odors, or allergy symptoms",
        "No unusual odors or noise from the unit",
        "Customer knows the bulb/cell replacement schedule",
    ],
}
