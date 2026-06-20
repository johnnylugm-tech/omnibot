"""Test isort-style sorting of __all__."""
items = [
    "GRAFANA_DASHBOARD",
    "GrafanaPanel",
    "PanelKind",
    "SUPPORTED_TIME_RANGES",
    "get_panel",
]

# Case-sensitive (default Python sorted)
cs = sorted(items)
print("Case-sensitive (Python default):")
for s in cs:
    print(f"  {s}")

# Case-insensitive (typical isort)
ci = sorted(items, key=str.casefold)
print("\nCase-insensitive (isort-style):")
for s in ci:
    print(f"  {s}")
