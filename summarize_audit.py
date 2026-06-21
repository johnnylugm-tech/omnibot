import json

with open("fr_audit_data.json") as f:
    data = json.load(f)

for fr, info in data.items():
    print(f"=== {fr} ===")
    print("MODULE:", info['module'])
    spec = info['spec']
    # Print the specific lines from spec that mention the FR
    for line in spec.splitlines():
        if fr in line:
            print("SPEC:", line.strip())
            
    test_spec = info['test_spec']
    for line in test_spec.splitlines():
        if fr in line:
            print("TEST_SPEC:", line.strip())
            
    code = info['code']
    print(f"CODE SIZE: {len(code)} bytes")
    # Show how many times the FR is tested
    print(f"TEST MATCHES: {code.count(fr.lower().replace('-', ''))} (approx)")
    
    # Check completeness
    if 'def ' in code or 'class ' in code:
        print("STATUS: Has code implementation.")
    else:
        print("STATUS: No implementation found.")
    print("")

